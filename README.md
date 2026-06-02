# 专业版 MCP + LangChain Agent Demo

这是一个小型但工程化的 LLM Demo，采用前后端分离架构：

- 前端：React + TypeScript + Ant Design + Vite
- 后端：FastAPI
- 智能体：LangChain ReAct Agent
- 工具层：MCP Server
- RAG：Chroma 本地向量库
- 模型：通过 OpenAI 兼容接口调用你的 Qwen/vLLM
- 多模态：图片分析使用独立 `OMNI_*` 配置，不影响普通聊天模型
- 记忆：LangChain 风格持久化会话 + 长期记忆压缩

## 架构

```text
React Web UI
  -> FastAPI
  -> LangChain AgentExecutor(create_react_agent)
  -> LangChain Tool Adapters
  -> MCP Server
  -> Workspace RAG / Weather / Calculator / Time / Web Search / LangChain Docs MCP
```

## 环境准备

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

开发和测试依赖：

```bash
python -m pip install -r requirements-dev.txt
```

`.env.example` 只保留占位值。请把真实 API key 写入本地 `.env`，不要提交 `.env`。如果历史中曾提交过真实 key，请在服务商控制台轮换密钥。

普通聊天继续使用 `VLLM_*`。需要图片分析时，另行配置 `OMNI_BASE_URL`、`OMNI_API_KEY`、`OMNI_MODEL`；图片生成/编辑使用 `IMAGE_*`，保留 `VLLM_*` 作为旧配置兼容。

```bash
cd frontend
npm install
cd ..
```

## 启动顺序

1) 启动 MCP 工具服务（保持运行）

```bash
source .venv/bin/activate
MCP_TRANSPORT=streamable-http python -m app.mcp.server
```

2) 启动 FastAPI 后端（新终端）

```bash
source .venv/bin/activate
python api_server.py
```

3) 启动前端（新终端）

```bash
cd frontend
npm run dev
```

默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8001`
- MCP：`http://127.0.0.1:8765/mcp`

## 验证

```bash
source .venv/bin/activate
python -m compileall app api_server.py tests
python -m pytest
cd frontend
npm run lint
npm run test
npm run build
```

## MCP Inspector

如果想用图形界面查看 MCP server 的 tools、resources 和调用结果，可以启动官方 MCP Inspector：

```bash
./scripts/mcp-inspector.sh
```

终端会输出一个带 `MCP_PROXY_AUTH_TOKEN` 的本地地址，例如 `http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=...`。打开这个地址后，Inspector 会通过 `stdio` 自动启动 `app.mcp.server`，不需要单独启动 `8765` 端口的 MCP 服务。

## MCP 插件

内置 MCP 插件放在 `app/mcp/plugins/*.py`。每个插件导出 `register(mcp)`，并在里面用 `@mcp.tool()` 注册工具。重启 `app.mcp.server` 后会自动加载。也可以通过 `PLUGINS_DIR` 指向外部插件目录。当前示例：

- `app/mcp/plugins/weather_advisor.py`：天气预报、天气新闻搜索和出行建议工具集合。

## 记忆机制

会话保存在 `chat_memory/` 下。每个会话包含：

- `messages`：近期消息
- `summary`：长期压缩摘要

当消息数量超过 `MEMORY_COMPRESS_TRIGGER` 时，会触发压缩流程：

1. 把早期消息压缩成摘要写入 `summary`
2. 仅保留最近 `MEMORY_KEEP_RECENT` 条消息作为短期上下文
3. 后续对话时同时注入 `summary + recent messages`

## 支持工具

通过本地 MCP Server 暴露：

- `get_weather`
- `calculate`
- `get_current_time`
- `web_search`

额外接入官方文档 MCP：

- `https://docs.langchain.com/mcp`

对应工具为 `langchain_docs_search`，可直接问 LangChain / LangGraph / LangSmith 的文档问题。

## 关键文件

- `api_server.py`：FastAPI 启动入口，实际应用在 `app/main.py`
- `app/storage/memory_store.py`：持久化会话与长期记忆压缩
- `app/agent/langchain_agent.py`：Agent 与 Tool 组装
- `app/mcp/server.py`：天气、计算、时间、网页搜索等 MCP 工具服务
- `app/core/engine.py`：workspace RAG、Chroma、MCP client 等共享能力
- `frontend/src/App.tsx`：前端聊天界面

## AI 协作规则

- `AGENTS.md`：项目级详细工程规范，约束代码分层、复杂度控制、并发安全、文件原子性、知识库一致性等。
- `PERSONALIZATION.md`：可直接复制到产品 `custom instructions` 的短版提示词。
