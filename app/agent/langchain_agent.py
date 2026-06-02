from __future__ import annotations

import json
import os
import re
import sys
import threading
from typing import Any

import httpx
from dotenv import load_dotenv
from langchain_classic.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from openai import APIConnectionError

from app.core.config import ENV_PATH
from app.core.engine import MCPToolClient, normalize_mcp_server_url, strip_thinking
from app.services.payloads import workspace_rag_result_payload


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-turbo"
DEFAULT_LANGCHAIN_DOCS_MCP_URL = "https://docs.langchain.com/mcp"

_MCP_CLIENTS: dict[str, MCPToolClient] = {}
_MCP_CLIENTS_LOCK = threading.RLock()
_TOOL_CALL_STATE = threading.local()
_WORKSPACE_RAG_CONTEXT = threading.local()

_TRIVIAL_SEARCH_PATTERNS = (
    re.compile(r"^\s*[0-9+\-*/().,\s]+\s*$"),
    re.compile(r"^\s*(你好|您好|hi|hello|hey|谢谢|thanks|thank you)[！!。.\s]*$", re.I),
)


def should_skip_search(query: str) -> bool:
    """Return True when retrieval/search would add latency without adding evidence."""

    normalized = query.strip()
    if not normalized:
        return True
    if len(normalized) <= 4:
        return True
    return any(pattern.fullmatch(normalized) for pattern in _TRIVIAL_SEARCH_PATTERNS)


def skipped_search_message(tool_name: str, query: str) -> str:
    return (
        f"{tool_name} skipped: query `{query}` looks like a trivial prompt that should be "
        "answered directly or routed to calculator/current_time/weather instead of search."
    )


def reset_tool_call_state() -> None:
    _TOOL_CALL_STATE.seen = set()
    _TOOL_CALL_STATE.evidence = []


def collect_tool_evidence() -> list[dict]:
    evidence = getattr(_TOOL_CALL_STATE, "evidence", [])
    return list(evidence)


def bind_workspace_rag_context(current_runtime: Any, workspace_id: str) -> None:
    _WORKSPACE_RAG_CONTEXT.runtime = current_runtime
    _WORKSPACE_RAG_CONTEXT.workspace_id = workspace_id


def clear_workspace_rag_context() -> None:
    for attr in ("runtime", "workspace_id"):
        if hasattr(_WORKSPACE_RAG_CONTEXT, attr):
            delattr(_WORKSPACE_RAG_CONTEXT, attr)


def _tool_call_key(name: str, arguments: dict, server_url: str | None) -> str:
    normalized_url = normalize_mcp_server_url((server_url or os.getenv("MCP_SERVER_URL", "")).strip())
    encoded_arguments = json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)
    return f"{normalized_url}:{name}:{encoded_arguments}"


def _remember_tool_call(name: str, arguments: dict, server_url: str | None) -> bool:
    seen = getattr(_TOOL_CALL_STATE, "seen", None)
    if seen is None:
        seen = set()
        _TOOL_CALL_STATE.seen = seen
    key = _tool_call_key(name, arguments, server_url)
    if key in seen:
        return False
    seen.add(key)
    return True


def _current_workspace_rag_context() -> tuple[Any, str]:
    current_runtime = getattr(_WORKSPACE_RAG_CONTEXT, "runtime", None)
    workspace_id = getattr(_WORKSPACE_RAG_CONTEXT, "workspace_id", None)
    if current_runtime is None or not workspace_id:
        raise RuntimeError("workspace RAG context is not available for this tool call")
    return current_runtime, workspace_id


@tool
def workspace_rag_search(query: str) -> str:
    """Search the current workspace knowledge base and return cited evidence."""

    if should_skip_search(query):
        return skipped_search_message("workspace_rag_search", query)
    current_runtime, workspace_id = _current_workspace_rag_context()
    top_k = int(os.getenv("RAG_TOP_K", "6"))
    try:
        kb = current_runtime.workspace_kb(workspace_id)
        results = kb.search(query, top_k=top_k, debug=True)
    except RuntimeError:
        payload = {"query": query, "results": []}
        _remember_workspace_evidence(payload)
        return json.dumps(payload, ensure_ascii=False, indent=2)

    document_map = {item["filename"]: item for item in current_runtime.store.list_workspace_documents(workspace_id)}
    payload = {
        "query": query,
        "results": [workspace_rag_result_payload(workspace_id, document_map, result) for result in results],
    }
    _remember_workspace_evidence(payload)
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def get_weather(city: str) -> str:
    """Get current weather for a city using the Open-Meteo public API."""

    return call_mcp_tool("get_weather", {"city": city})


@tool
def weather_advisor(city: str) -> str:
    """Get weather forecast, related weather news, and practical advice for a city."""

    return call_mcp_tool("weather_advisor", {"city": city})


@tool
def calculator(expression: str) -> str:
    """Calculate a numeric expression. Supports +, -, *, /, **, and parentheses."""

    return call_mcp_tool("calculate", {"expression": expression})


@tool
def current_time(timezone: str = "Asia/Shanghai") -> str:
    """Get the current time for an IANA timezone, for example Asia/Shanghai or UTC."""

    return call_mcp_tool("get_current_time", {"timezone": timezone})


@tool
def web_search(query: str) -> str:
    """Search the web for external/current facts. Do not use for arithmetic, greetings, or generic chat."""

    if should_skip_search(query):
        return skipped_search_message("web_search", query)
    return call_mcp_tool("web_search", {"query": query, "max_results": 5})


@tool
def langchain_docs_search(query: str) -> str:
    """Search official LangChain docs. Do not use unless the question is about LangChain docs/API behavior."""

    if should_skip_search(query):
        return skipped_search_message("langchain_docs_search", query)
    return call_mcp_tool(
        "search_docs_by_lang_chain",
        {"query": query},
        server_url=os.getenv("LANGCHAIN_DOCS_MCP_URL", DEFAULT_LANGCHAIN_DOCS_MCP_URL),
    )


def get_mcp_client(server_url: str | None = None) -> MCPToolClient:
    normalized_url = normalize_mcp_server_url((server_url or os.getenv("MCP_SERVER_URL", "")).strip())
    with _MCP_CLIENTS_LOCK:
        if normalized_url not in _MCP_CLIENTS:
            _MCP_CLIENTS[normalized_url] = MCPToolClient(server_url=normalized_url)
        return _MCP_CLIENTS[normalized_url]


def close_mcp_clients() -> None:
    with _MCP_CLIENTS_LOCK:
        clients = list(_MCP_CLIENTS.values())
        _MCP_CLIENTS.clear()
    for client in clients:
        client.close()


def call_mcp_tool(name: str, arguments: dict, server_url: str | None = None) -> str:
    if not _remember_tool_call(name, arguments, server_url):
        return (
            f"MCP tool `{name}` skipped because the same arguments were already used in this turn. "
            "Do not retry the same failed tool call; answer with the available information and explain the limitation."
        )
    try:
        payload = get_mcp_client(server_url).call_tool(name, arguments)
    except Exception as exc:
        return (
            f"MCP tool `{name}` failed. Make sure the MCP server is running with: "
            "MCP_TRANSPORT=streamable-http python -m app.mcp.server\n"
            f"Error: {exc}\n"
            "Do not retry this same tool call. Use the available information to answer and clearly state the limitation."
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _remember_workspace_evidence(payload: object) -> None:
    if not isinstance(payload, dict):
        return
    results = payload.get("results")
    if not isinstance(results, list):
        return
    evidence = getattr(_TOOL_CALL_STATE, "evidence", None)
    if evidence is None:
        evidence = []
        _TOOL_CALL_STATE.evidence = evidence
    for item in results:
        if isinstance(item, dict):
            evidence.append({"kind": "rag", **item})


def build_llm(streaming: bool = False) -> ChatOpenAI:
    timeout = float(os.getenv("VLLM_TIMEOUT_SECONDS", "120"))
    trust_env = os.getenv("VLLM_TRUST_ENV", "0").lower() in {"1", "true", "yes", "on"}
    return ChatOpenAI(
        base_url=os.getenv("VLLM_BASE_URL", DEFAULT_BASE_URL),
        api_key=os.getenv("VLLM_API_KEY", "EMPTY"),
        model=os.getenv("VLLM_MODEL", DEFAULT_MODEL),
        temperature=0.7,
        timeout=timeout,
        http_client=httpx.Client(timeout=timeout, trust_env=trust_env),
        max_tokens=int(os.getenv("VLLM_MAX_TOKENS", "900")),
        streaming=streaming,
    )


def format_connection_error(exc: Exception) -> str:
    return (
        "连接模型服务失败。\n\n"
        "当前请求没有成功连到 LLM endpoint，常见原因是代理/TLS 被中断、网络无法访问 "
        "VLLM_BASE_URL，或模型服务地址不可用。\n\n"
        f"- VLLM_BASE_URL: {os.getenv('VLLM_BASE_URL', DEFAULT_BASE_URL)}\n"
        f"- VLLM_MODEL: {os.getenv('VLLM_MODEL', DEFAULT_MODEL)}\n"
        f"- VLLM_TRUST_ENV: {os.getenv('VLLM_TRUST_ENV', '0')}\n\n"
        "代码默认禁用 httpx 从环境变量读取代理。如果你必须通过代理访问模型服务，"
        "请设置 VLLM_TRUST_ENV=1，并确认 HTTPS_PROXY/HTTP_PROXY 指向可用代理；"
        "如果不需要代理，请保持 VLLM_TRUST_ENV=0。\n\n"
        f"原始错误: {exc}"
    )


def handle_agent_parsing_error(_: Exception) -> str:
    return (
        "格式错误。不要调用任何工具，也不要重试相同内容。"
        "下一步必须直接输出：Final Answer: 用中文给用户一个简短回答；"
        "如果缺少工具结果，就说明当前无法完成工具查询。"
    )


def build_agent(verbose: bool = True, streaming: bool = False):
    tools = [
        workspace_rag_search,
        get_weather,
        weather_advisor,
        calculator,
        current_time,
        web_search,
        langchain_docs_search,
    ]
    prompt = PromptTemplate.from_template(
        """你是一个基于 LangChain ReAct agent 构建的工具型智能体。
你可以使用这些工具：

{tools}

请严格使用下面格式。信息足够时可以不调用工具，直接输出 Final Answer：

Question: 用户问题
Thought: 简短说明下一步是否需要工具
Action: 如果需要工具，必须是 [{tool_names}] 之一
Action Input: 如果调用工具，传给工具的输入必须是一行纯文本
Observation: 工具返回结果
... 可以重复 Thought/Action/Action Input/Observation
Thought: 我已经有足够信息
Final Answer: 给用户的中文最终答案

规则：
- 不需要工具时，禁止输出 Action，直接输出 Final Answer。
- 先判断是否真的需要检索或搜索；简单问候、闲聊、解释、翻译、总结、数学题不要使用 web_search 或 langchain_docs_search。
- 只要问题涉及当前工作区中的知识库、文档、资料、文件、上传材料、PDF、Word、表格、论文材料、申请书等本地内容，优先使用 workspace_rag_search。
- 只有问题依赖最新/外部事实、用户明确要求联网搜索，或本地工具无法回答的开放网络信息时，才使用 web_search。
- 只有问题明确涉及 LangChain / LangGraph / LangSmith 文档、API、版本行为或官方用法时，才使用 langchain_docs_search。
- 只需要基础实时天气时使用 get_weather。
- 需要天气预报、天气新闻、预警、穿衣、出行、防晒、带伞等综合建议时，优先使用 weather_advisor。
- 需要计算时使用 calculator。
- 需要当前时间时使用 current_time。
- 需要开放网络信息时使用 web_search。
- 需要 LangChain / LangGraph / LangSmith 文档知识时，优先使用 langchain_docs_search。
- 如果用户问题包含多个任务，必须逐个调用对应工具。
- 在输出 Final Answer 前，必须确认每个任务都有对应 Observation。
- 如果工具返回 failed、skipped、error 或超时，不要用相同参数重复调用该工具；直接基于已有信息回答，并说明限制。
- 使用 workspace_rag_search 时，Final Answer 必须基于返回的 evidence；如果结果为空或证据不足，要说明“未检索到足够证据”，不要编造。
- 天气、时间和计算结果禁止凭常识猜测，必须来自工具 Observation。
- 不要输出 XML、JSON 工具调用或 <think> 思考块。
- Final Answer 必须是中文。

这是你和用户最近的对话历史，请用它保持上下文、偏好和用户已经给过的信息：
{chat_history}

Question: {input}
Thought:{agent_scratchpad}"""
    )
    agent = create_react_agent(build_llm(streaming=streaming), tools, prompt, stop_sequence=True)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=verbose,
        handle_parsing_errors=handle_agent_parsing_error,
        max_iterations=6,
        early_stopping_method="generate",
    )


def main() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=True)
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        question = "先查一下这个 demo 如何使用 MCP 做 RAG，再告诉我上海现在天气，并计算 24*7。"

    print(f"Using vLLM endpoint: {os.getenv('VLLM_BASE_URL', DEFAULT_BASE_URL)}")
    print(f"Using model: {os.getenv('VLLM_MODEL', DEFAULT_MODEL)}")
    print(f"Using MCP server URL: {os.getenv('MCP_SERVER_URL', 'stdio auto-start')}")
    print("LangChain agent: create_react_agent + AgentExecutor")
    print("LangChain tools: MCP adapters for RAG, weather, calculator, time, web search, and LangChain docs")
    print(f"\nUser: {question}\n")

    agent = build_agent()
    try:
        reset_tool_call_state()
        result = agent.invoke({"input": question, "chat_history": "暂无历史。"})
    except APIConnectionError as exc:
        print(format_connection_error(exc))
        raise SystemExit(1) from exc
    except httpx.HTTPError as exc:
        print(format_connection_error(exc))
        raise SystemExit(1) from exc
    finally:
        close_mcp_clients()

    print(strip_thinking(result["output"]))


if __name__ == "__main__":
    main()
