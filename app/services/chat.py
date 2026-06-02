from __future__ import annotations

import json
import queue
import re
import threading
import time
from typing import Any

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.callbacks import BaseCallbackHandler

from app.core.runtime import AppRuntime
from app.services.payloads import chat_payload, dedupe_sources, workspace_rag_result_payload
from app.core.engine import strip_thinking
from app.agent.langchain_agent import (
    bind_workspace_rag_context,
    clear_workspace_rag_context,
    collect_tool_evidence,
    reset_tool_call_state,
)


class FinalAnswerStreamHandler(BaseCallbackHandler):
    final_answer_markers = ("Final Answer:", "Final Answer：")

    def __init__(self) -> None:
        self.events: queue.Queue[dict | None] = queue.Queue()
        self._buffer = ""
        self._reasoning_line_buffer = ""
        self._streaming_final_answer = False
        self.has_emitted = False
        self._status_messages: set[str] = set()
        self._suppressed_tool_ends = 0
        self.llm_calls: list[dict] = []
        self.tool_calls: list[dict] = []
        self.first_final_token_at: float | None = None
        self._lock = threading.Lock()

    def on_llm_start(self, *args, **kwargs) -> None:
        self._buffer = ""
        self._reasoning_line_buffer = ""
        self._streaming_final_answer = False
        self._status_messages.clear()
        self._emit_status("分析问题，判断是否需要调用工具。")
        with self._lock:
            self.llm_calls.append({"start": time.perf_counter(), "duration_ms": None})

    def on_llm_end(self, *args, **kwargs) -> None:
        with self._lock:
            for item in reversed(self.llm_calls):
                if item["duration_ms"] is None:
                    item["duration_ms"] = round((time.perf_counter() - item["start"]) * 1000, 2)
                    break

    def on_llm_error(self, *args, **kwargs) -> None:
        self.on_llm_end(*args, **kwargs)

    def on_tool_start(self, serialized: dict, input_str: str, *args, **kwargs) -> None:
        if serialized.get("name") == "_Exception":
            self._suppressed_tool_ends += 1
            self._emit_status("模型输出格式有误，正在纠正。")
            return
        with self._lock:
            self.tool_calls.append(
                {
                    "name": serialized.get("name", "unknown"),
                    "input": str(input_str)[:200],
                    "start": time.perf_counter(),
                    "duration_ms": None,
                }
            )
            self.events.put(
                {
                    "type": "tool_start",
                    "name": self.tool_calls[-1]["name"],
                    "input": self.tool_calls[-1]["input"],
                }
            )

    def on_tool_end(self, *args, **kwargs) -> None:
        if self._suppressed_tool_ends:
            self._suppressed_tool_ends -= 1
            return
        with self._lock:
            for item in reversed(self.tool_calls):
                if item["duration_ms"] is None:
                    item["duration_ms"] = round((time.perf_counter() - item["start"]) * 1000, 2)
                    self.events.put({"type": "tool_end", "name": item["name"], "duration_ms": item["duration_ms"]})
                    break

    def on_tool_error(self, *args, **kwargs) -> None:
        with self._lock:
            for item in reversed(self.tool_calls):
                if item["duration_ms"] is None:
                    self.events.put({"type": "tool_error", "name": item["name"]})
                    break
        self.on_tool_end(*args, **kwargs)

    def on_llm_new_token(self, token: str, *args, **kwargs) -> None:
        if not token:
            return
        if self._streaming_final_answer:
            self._emit_final_token(token)
            return
        self._buffer += token
        for marker in self.final_answer_markers:
            marker_index = self._buffer.find(marker)
            if marker_index == -1:
                continue
            self._streaming_final_answer = True
            self._flush_reasoning_line()
            tail = self._buffer[marker_index + len(marker):]
            if tail:
                self._emit_final_token(tail)
            break
        else:
            self._process_reasoning_token(token)

    def timings(self, request_start: float) -> dict:
        with self._lock:
            llm_calls = [{"index": index + 1, "duration_ms": item["duration_ms"]} for index, item in enumerate(self.llm_calls)]
            tool_calls = [
                {
                    "index": index + 1,
                    "name": item["name"],
                    "input": item["input"],
                    "duration_ms": item["duration_ms"],
                }
                for index, item in enumerate(self.tool_calls)
            ]
        return {
            "time_to_first_final_token_ms": round((self.first_final_token_at - request_start) * 1000, 2)
            if self.first_final_token_at is not None
            else None,
            "llm_calls": llm_calls,
            "tool_calls": tool_calls,
        }

    def _emit_final_token(self, token: str) -> None:
        self.has_emitted = True
        if self.first_final_token_at is None:
            self.first_final_token_at = time.perf_counter()
        self.events.put({"type": "token", "content": token})

    def _process_reasoning_token(self, token: str) -> None:
        self._reasoning_line_buffer += token
        while "\n" in self._reasoning_line_buffer:
            line, self._reasoning_line_buffer = self._reasoning_line_buffer.split("\n", 1)
            self._emit_reasoning_line(line)

    def _flush_reasoning_line(self) -> None:
        if self._reasoning_line_buffer.strip():
            self._emit_reasoning_line(self._reasoning_line_buffer)
        self._reasoning_line_buffer = ""

    def _emit_reasoning_line(self, line: str) -> None:
        normalized = line.strip()
        if re.match(r"(?i)^Thought\s*[:：]", normalized):
            self._emit_status("整理当前信息，准备下一步。")
            return
        if re.match(r"(?i)^Action\s*[:：]", normalized):
            self._emit_status("准备调用合适的工具。")
            return
        if re.match(r"(?i)^Observation\s*[:：]", normalized):
            self._emit_status("已收到工具结果，继续整理答案。")

    def _emit_status(self, content: str) -> None:
        if content in self._status_messages:
            return
        self._status_messages.add(content)
        self.events.put({"type": "reasoning", "content": content})


def normalized_message(message: str) -> str:
    value = message.strip()
    if not value:
        raise HTTPException(status_code=400, detail="Message is empty")
    return value


def message_with_context(message: str, sources: list[dict]) -> str:
    if not sources:
        return message
    evidence_blocks = []
    for index, source in enumerate(sources, start=1):
        evidence_blocks.append(f"[{index}] {source.get('citation') or source.get('title') or source.get('source')}\n{str(source.get('text', '')).strip()[:1800]}")
    return (
        f"{message}\n\n"
        "以下是当前工作区知识库与会话附件中检索到的证据。请优先基于这些证据回答；如果证据不足，请明确说明。\n\n"
        + "\n\n".join(evidence_blocks)
    )


def search_workspace_sources(current_runtime: AppRuntime, workspace_id: str, query: str, top_k: int = 4) -> list[dict]:
    try:
        kb = current_runtime.workspace_kb(workspace_id)
        results = kb.search(query, top_k=top_k, debug=True)
    except RuntimeError:
        return []
    document_map = {item["filename"]: item for item in current_runtime.store.list_workspace_documents(workspace_id)}
    return [workspace_rag_result_payload(workspace_id, document_map, result) for result in results]


def load_existing_session(store, user_id: str, workspace_id: str, session_id: str) -> dict:
    if not store.session_exists(user_id, workspace_id, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        return store.load_session(user_id, workspace_id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Session not found") from exc


def load_existing_session_by_id(store, user_id: str, session_id: str) -> dict:
    workspaces = store.list_workspaces(user_id)
    for workspace in workspaces:
        if store.session_exists(user_id, workspace["id"], session_id):
            return store.load_session(user_id, workspace["id"], session_id)
    raise HTTPException(status_code=404, detail="Session not found")


def stream_chat_turn(
    current_runtime: AppRuntime,
    user: dict,
    session: dict,
    user_message: str,
    *,
    attachment_ids: list[str] | None = None,
    persist_user: bool,
    user_message_id: str | None = None,
) -> StreamingResponse:
    request_start = time.perf_counter()
    attachment_ids = attachment_ids or []
    workspace_id = session["workspace_id"]
    history = current_runtime.store.build_chat_history(session, exclude_message_id=user_message_id)

    def generate():
        handler = FinalAnswerStreamHandler()
        result_holder: dict = {}
        yield encode_stream_event({"type": "start"})

        attachment_sources: list[dict] = []

        attachment_sources = current_runtime.store.search_attachment_chunks(
            user["id"],
            workspace_id,
            session["id"],
            user_message,
            attachment_ids=attachment_ids or None,
        )
        if attachment_sources:
            yield encode_stream_event({"type": "reasoning", "content": f"同时命中了 {len(attachment_sources)} 条会话附件证据。"})

        agent_input = message_with_context(user_message, attachment_sources)
        prepare_done = time.perf_counter()

        def invoke_agent() -> None:
            try:
                reset_tool_call_state()
                bind_workspace_rag_context(current_runtime, workspace_id)
                result = current_runtime.stream_agent.invoke(
                    {"input": agent_input, "chat_history": history},
                    config={"callbacks": [handler]},
                )
                result_holder["answer"] = strip_thinking(result["output"])
                result_holder["sources"] = dedupe_sources([*attachment_sources, *collect_tool_evidence()])
            except Exception as exc:
                result_holder["error"] = f"Agent invocation failed: {exc}"
            finally:
                clear_workspace_rag_context()
                handler.events.put(None)

        worker = threading.Thread(target=invoke_agent, daemon=True)
        worker.start()

        while True:
            event = handler.events.get()
            if event is None:
                break
            yield encode_stream_event(event)

        worker.join()
        agent_done = time.perf_counter()
        if result_holder.get("error"):
            yield encode_stream_event({"type": "error", "message": result_holder["error"]})
            return

        answer = str(result_holder.get("answer", ""))
        sources = result_holder.get("sources", [])
        if answer and not handler.has_emitted:
            yield encode_stream_event({"type": "token", "content": answer})

        yield encode_stream_event({"type": "reasoning", "content": "保存对话并更新记忆。"})
        if persist_user:
            current_runtime.store.append_message(session, "user", user_message, attachment_ids=attachment_ids)
        else:
            session.update(current_runtime.store.load_session(user["id"], workspace_id, session["id"]))
        current_runtime.store.append_message(session, "assistant", answer, sources=sources)
        messages_saved = time.perf_counter()
        memory_compressed = current_runtime.store.compress_long_term_memory(session, current_runtime.compress_llm)
        memory_done = time.perf_counter()
        current_runtime.store.save_session(session)
        latest_session = current_runtime.store.load_session(user["id"], workspace_id, session["id"])
        persist_done = time.perf_counter()
        timings = {
            "prepare_ms": round((prepare_done - request_start) * 1000, 2),
            **handler.timings(request_start),
            "agent_total_ms": round((agent_done - request_start) * 1000, 2),
            "save_messages_ms": round((messages_saved - agent_done) * 1000, 2),
            "memory_compress_ms": round((memory_done - messages_saved) * 1000, 2),
            "persist_reload_ms": round((persist_done - memory_done) * 1000, 2),
            "request_total_ms": round((persist_done - request_start) * 1000, 2),
        }
        yield encode_stream_event({**chat_payload(latest_session, answer, memory_compressed), "type": "done", "timings": timings})

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def encode_stream_event(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"
