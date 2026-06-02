from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, get_buffer_string, messages_from_dict
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.core.config import default_chat_db_path, default_chat_memory_dir
from app.core.engine import atomic_write_json, tokenize_search


SESSION_ID_RE = re.compile(r"^[0-9a-f]{12}$")
ID_RE = re.compile(r"^[0-9a-f]{12}$")
USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_LEGACY_USERNAME = "local"
DEFAULT_LEGACY_DISPLAY_NAME = "Local User"
DEFAULT_WORKSPACE_NAME = "Shared Workspace"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid4().hex[:12]


def random_token() -> str:
    return secrets.token_urlsafe(32)


def normalize_email(email: str | None) -> str:
    value = (email or "").strip().lower()
    if not value:
        return ""
    if not EMAIL_RE.fullmatch(value):
        raise ValueError("Email is invalid")
    return value


class MissingSessionError(FileNotFoundError):
    pass


class PersistentMemoryStore:
    """SQLite-backed users, workspaces, sessions, local memory, attachments, and shared docs."""

    def __init__(self, memory_dir: str | None = None, db_path: str | None = None) -> None:
        self.memory_dir = Path(memory_dir) if memory_dir else default_chat_memory_dir()
        self.db_path = Path(db_path) if db_path else default_chat_db_path(self.memory_dir)
        self.attachments_dir = self.memory_dir / "attachments"
        self.workspace_root = self.memory_dir / "workspaces"
        self.sessions_dir = self.memory_dir / "sessions"
        self.messages_dir = self.memory_dir / "messages"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.compress_trigger = int(os.getenv("MEMORY_COMPRESS_TRIGGER", "30"))
        self.keep_recent = int(os.getenv("MEMORY_KEEP_RECENT", "12"))
        self.max_token_limit = int(os.getenv("MEMORY_MAX_TOKEN_LIMIT", "2000"))
        self._lock = threading.RLock()
        self._init_db()
        self._migrate_legacy_sessions()

    def list_sessions(self, user_id: str, workspace_id: str) -> list[dict]:
        self.ensure_workspace_access(user_id, workspace_id)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, workspace_id, title, updated_at
                FROM sessions
                WHERE user_id = ? AND workspace_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id, workspace_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_session(self, user_id: str, workspace_id: str, title: str | None = None) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        session_id = new_id()
        timestamp = now_iso()
        metadata = {
            "id": session_id,
            "user_id": user_id,
            "workspace_id": workspace_id,
            "title": (title or "新会话").strip() or "新会话",
            "summary": "",
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, user_id, workspace_id, title, summary, created_at, updated_at)
                VALUES (:id, :user_id, :workspace_id, :title, :summary, :created_at, :updated_at)
                """,
                metadata,
            )
        return {**metadata, "messages": []}

    def load_session(self, user_id: str, workspace_id: str, session_id: str) -> dict:
        self._validate_session_id(session_id)
        self.ensure_workspace_access(user_id, workspace_id)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM sessions
                WHERE id = ? AND user_id = ? AND workspace_id = ?
                """,
                (session_id, user_id, workspace_id),
            ).fetchone()
            if row is None:
                raise MissingSessionError(session_id)
        session = dict(row)
        session["messages"] = self._public_messages(session_id)
        return session

    def save_session(self, session: dict) -> None:
        timestamp = now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET title = ?, summary = ?, updated_at = ?
                WHERE id = ?
                """,
                (session.get("title", "新会话"), session.get("summary", ""), timestamp, session["id"]),
            )
        latest = self.load_session(session["user_id"], session["workspace_id"], session["id"])
        session.update(latest)

    def delete_session(self, user_id: str, workspace_id: str, session_id: str) -> None:
        self._validate_session_id(session_id)
        self.ensure_workspace_access(user_id, workspace_id)
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM sessions WHERE id = ? AND user_id = ? AND workspace_id = ?",
                (session_id, user_id, workspace_id),
            )

    def session_exists(self, user_id: str, workspace_id: str, session_id: str) -> bool:
        if not self.is_valid_session_id(session_id):
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE id = ? AND user_id = ? AND workspace_id = ?",
                (session_id, user_id, workspace_id),
            ).fetchone()
        return row is not None

    def append_message(
        self,
        session: dict,
        role: str,
        content: str,
        *,
        status: str = "done",
        sources: list[dict] | None = None,
        attachment_ids: list[str] | None = None,
        message_id: str | None = None,
        timestamp: str | None = None,
    ) -> dict:
        session_id = session["id"]
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported message role: {role}")
        timestamp = timestamp or now_iso()
        message_id = message_id or new_id()
        self._validate_short_id(message_id, "message id")
        with self._lock, self._connect() as conn:
            position = self._next_position(conn, session_id)
            conn.execute(
                """
                INSERT INTO messages (id, session_id, role, content, time, status, position, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, session_id, role, content, timestamp, status, position, "{}"),
            )
            if role == "user" and session.get("title", "新会话") in {"新会话", "新的对话"}:
                session["title"] = self._infer_title(content)
            if attachment_ids:
                self._link_attachments(conn, session["user_id"], session_id, message_id, attachment_ids)
            if sources:
                self._insert_sources(conn, message_id, sources)
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                (session.get("title", "新会话"), timestamp, session_id),
            )
        latest = self.load_session(session["user_id"], session["workspace_id"], session_id)
        session.update(latest)
        return self.get_message(session["user_id"], session["workspace_id"], session_id, message_id)

    def get_message(self, user_id: str, workspace_id: str, session_id: str, message_id: str) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        self._validate_session_id(session_id)
        self._validate_short_id(message_id, "message id")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT m.*
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE m.session_id = ? AND m.id = ? AND s.user_id = ? AND s.workspace_id = ?
                """,
                (session_id, message_id, user_id, workspace_id),
            ).fetchone()
            if row is None:
                raise ValueError("Message not found")
            return self._message_to_public(conn, row)

    def update_user_message_and_truncate(
        self,
        user_id: str,
        workspace_id: str,
        session_id: str,
        message_id: str,
        content: str,
        attachment_ids: list[str] | None = None,
    ) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        self._validate_session_id(session_id)
        self._validate_short_id(message_id, "message id")
        timestamp = now_iso()
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT m.*
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE m.session_id = ? AND m.id = ? AND s.user_id = ? AND s.workspace_id = ?
                """,
                (session_id, message_id, user_id, workspace_id),
            ).fetchone()
            if row is None or row["role"] != "user":
                raise ValueError("User message not found")
            conn.execute(
                "DELETE FROM messages WHERE session_id = ? AND position > ?",
                (session_id, int(row["position"])),
            )
            conn.execute(
                "UPDATE messages SET content = ?, time = ?, status = ? WHERE id = ?",
                (content, timestamp, "done", message_id),
                )
            conn.execute(
                "UPDATE attachments SET message_id = NULL WHERE user_id = ? AND session_id = ? AND message_id = ?",
                (user_id, session_id, message_id),
            )
            if attachment_ids:
                self._link_attachments(conn, user_id, session_id, message_id, attachment_ids)
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (timestamp, session_id))
        return self.load_session(user_id, workspace_id, session_id)

    def truncate_from_message(self, user_id: str, workspace_id: str, session_id: str, message_id: str) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        self._validate_session_id(session_id)
        self._validate_short_id(message_id, "message id")
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT m.*
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE m.session_id = ? AND m.id = ? AND s.user_id = ? AND s.workspace_id = ?
                """,
                (session_id, message_id, user_id, workspace_id),
            ).fetchone()
            if row is None:
                raise ValueError("Message not found")
            conn.execute(
                "DELETE FROM messages WHERE session_id = ? AND position >= ?",
                (session_id, int(row["position"])),
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now_iso(), session_id))
        return self.load_session(user_id, workspace_id, session_id)

    def previous_user_message(self, user_id: str, workspace_id: str, session_id: str, assistant_message_id: str) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        self._validate_session_id(session_id)
        self._validate_short_id(assistant_message_id, "message id")
        with self._connect() as conn:
            assistant = conn.execute(
                """
                SELECT m.position, m.role
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE m.session_id = ? AND m.id = ? AND s.user_id = ? AND s.workspace_id = ?
                """,
                (session_id, assistant_message_id, user_id, workspace_id),
            ).fetchone()
            if assistant is None or assistant["role"] != "assistant":
                raise ValueError("Assistant message not found")
            row = conn.execute(
                """
                SELECT *
                FROM messages
                WHERE session_id = ? AND role = 'user' AND position < ?
                ORDER BY position DESC
                LIMIT 1
                """,
                (session_id, int(assistant["position"])),
            ).fetchone()
            if row is None:
                raise ValueError("Previous user message not found")
            return self._message_to_public(conn, row)

    def build_chat_history(self, session: dict, exclude_message_id: str | None = None) -> str:
        session_id = session["id"]
        with self._connect() as conn:
            summary = (
                conn.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,)).fetchone() or {"summary": ""}
            )["summary"]
            if exclude_message_id:
                self._validate_short_id(exclude_message_id, "message id")
                rows = conn.execute(
                    """
                    SELECT role, content, time
                    FROM messages
                    WHERE session_id = ? AND id != ?
                    ORDER BY position DESC
                    LIMIT ?
                    """,
                    (session_id, exclude_message_id, self.keep_recent),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT role, content, time
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY position DESC
                    LIMIT ?
                    """,
                    (session_id, self.keep_recent),
                ).fetchall()
            memories = conn.execute(
                """
                SELECT content
                FROM memories
                WHERE user_id = ? AND enabled = 1
                ORDER BY updated_at DESC, created_at DESC
                """,
                (session["user_id"],),
            ).fetchall()

        parts: list[str] = []
        if memories:
            parts.append("固定记忆:\n" + "\n".join(f"- {row['content']}" for row in memories))
        if summary:
            parts.append(f"长期记忆摘要: {summary}")
        messages = [
            HumanMessage(content=row["content"], additional_kwargs={"time": row["time"]})
            if row["role"] == "user"
            else AIMessage(content=row["content"], additional_kwargs={"time": row["time"]})
            for row in reversed(rows)
        ]
        if messages:
            parts.append(get_buffer_string(messages, human_prefix="用户", ai_prefix="助手"))
        return "\n".join(parts) if parts else "暂无历史。"

    def compress_long_term_memory(self, session: dict, llm: ChatOpenAI) -> bool:
        session_id = session["id"]
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content, time
                FROM messages
                WHERE session_id = ?
                ORDER BY position
                """,
                (session_id,),
            ).fetchall()
            old_summary = (
                conn.execute("SELECT summary FROM sessions WHERE id = ?", (session_id,)).fetchone() or {"summary": ""}
            )["summary"]
        if len(rows) <= self.compress_trigger:
            session["messages"] = self._public_messages(session_id)
            return False

        old_rows = rows[: -self.keep_recent]
        old_messages = [
            HumanMessage(content=row["content"], additional_kwargs={"time": row["time"]})
            if row["role"] == "user"
            else AIMessage(content=row["content"], additional_kwargs={"time": row["time"]})
            for row in old_rows
        ]
        summary_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是对话长期记忆压缩器。请把历史对话压缩成简洁、事实准确、可供后续检索的中文摘要。"
                    "保留用户偏好、关键事实、任务目标、已做结论和待办事项。",
                ),
                (
                    "human",
                    "已有摘要:\n{summary}\n\n新增历史对话:\n{new_lines}\n\n请输出新的摘要。",
                ),
            ]
        )
        try:
            response = (summary_prompt | llm).invoke(
                {
                    "summary": old_summary or "无",
                    "new_lines": get_buffer_string(old_messages, human_prefix="用户", ai_prefix="助手"),
                }
            )
        except Exception as exc:
            session["memory_error"] = str(exc)
            session["messages"] = self._public_messages(session_id)
            return False

        session["summary"] = str(response.content).strip()
        self.save_session(session)
        return True

    def message_count(self, user_id: str, workspace_id: str, session_id: str) -> int:
        self.ensure_workspace_access(user_id, workspace_id)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE m.session_id = ? AND s.user_id = ? AND s.workspace_id = ?
                """,
                (session_id, user_id, workspace_id),
            ).fetchone()
        return int(row["count"])

    def create_attachment(
        self,
        user_id: str,
        workspace_id: str,
        session_id: str,
        filename: str,
        path: Path,
        *,
        mime_type: str = "",
        size: int = 0,
        status: str = "ready",
    ) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        attachment_id = new_id()
        timestamp = now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO attachments (
                    id, user_id, workspace_id, session_id, filename, path, mime_type, size, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (attachment_id, user_id, workspace_id, session_id, filename, str(path), mime_type, size, status, timestamp),
            )
        return self.get_attachment(user_id, workspace_id, session_id, attachment_id)

    def get_attachment(self, user_id: str, workspace_id: str, session_id: str, attachment_id: str) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        self._validate_short_id(attachment_id, "attachment id")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM attachments
                WHERE id = ? AND user_id = ? AND workspace_id = ? AND session_id = ?
                """,
                (attachment_id, user_id, workspace_id, session_id),
            ).fetchone()
            if row is None:
                raise ValueError("Attachment not found")
            return self._attachment_to_public(conn, row)

    def get_attachments(self, user_id: str, workspace_id: str, session_id: str, attachment_ids: list[str] | None = None) -> list[dict]:
        self.ensure_workspace_access(user_id, workspace_id)
        with self._connect() as conn:
            if attachment_ids:
                placeholders = ",".join("?" for _ in attachment_ids)
                rows = conn.execute(
                    f"""
                    SELECT *
                    FROM attachments
                    WHERE user_id = ? AND workspace_id = ? AND session_id = ? AND id IN ({placeholders})
                    ORDER BY created_at
                    """,
                    (user_id, workspace_id, session_id, *attachment_ids),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT *
                    FROM attachments
                    WHERE user_id = ? AND workspace_id = ? AND session_id = ?
                    ORDER BY created_at
                    """,
                    (user_id, workspace_id, session_id),
                ).fetchall()
            return [self._attachment_to_public(conn, row) for row in rows]

    def replace_attachment_chunks(self, attachment_id: str, chunks: list[dict]) -> None:
        self._validate_short_id(attachment_id, "attachment id")
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM attachment_chunks WHERE attachment_id = ?", (attachment_id,))
            for chunk in chunks:
                conn.execute(
                    """
                    INSERT INTO attachment_chunks (
                        id, attachment_id, chunk_id, heading, text, char_start, char_end, tokens_json
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id(),
                        attachment_id,
                        int(chunk.get("chunk_id", 0)),
                        str(chunk.get("heading", "")),
                        str(chunk.get("text", "")),
                        int(chunk.get("char_start", 0)),
                        int(chunk.get("char_end", 0)),
                        json.dumps(tokenize_search(str(chunk.get("text", ""))), ensure_ascii=False),
                    ),
                )
            conn.execute("UPDATE attachments SET status = ?, error = NULL WHERE id = ?", ("ready", attachment_id))

    def mark_attachment_error(self, attachment_id: str, error: str) -> None:
        self._validate_short_id(attachment_id, "attachment id")
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE attachments SET status = ?, error = ? WHERE id = ?",
                ("error", error[:500], attachment_id),
            )

    def delete_attachment(self, user_id: str, workspace_id: str, session_id: str, attachment_id: str) -> None:
        self.ensure_workspace_access(user_id, workspace_id)
        self._validate_short_id(attachment_id, "attachment id")
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                DELETE FROM attachments
                WHERE id = ? AND user_id = ? AND workspace_id = ? AND session_id = ?
                """,
                (attachment_id, user_id, workspace_id, session_id),
            )

    def search_attachment_chunks(
        self,
        user_id: str,
        workspace_id: str,
        session_id: str,
        query: str,
        *,
        attachment_ids: list[str] | None = None,
        top_k: int = 4,
    ) -> list[dict]:
        self.ensure_workspace_access(user_id, workspace_id)
        query_tokens = set(tokenize_search(query))
        with self._connect() as conn:
            params: list[str] = [user_id, workspace_id, session_id]
            attachment_filter = ""
            if attachment_ids:
                attachment_filter = "AND a.id IN (" + ",".join("?" for _ in attachment_ids) + ")"
                params.extend(attachment_ids)
            rows = conn.execute(
                f"""
                SELECT
                    c.*, a.filename, a.id AS attachment_id
                FROM attachment_chunks c
                JOIN attachments a ON a.id = c.attachment_id
                WHERE a.user_id = ? AND a.workspace_id = ? AND a.session_id = ? {attachment_filter}
                """,
                params,
            ).fetchall()
        scored: list[dict] = []
        for row in rows:
            tokens = set(json.loads(row["tokens_json"] or "[]"))
            score = len(query_tokens & tokens) / max(len(query_tokens), 1) if query_tokens else 0.0
            if score > 0 or attachment_ids:
                scored.append(
                    {
                        "kind": "attachment",
                        "source": row["filename"],
                        "attachment_id": row["attachment_id"],
                        "chunk_id": row["chunk_id"],
                        "parent_id": row["chunk_id"],
                        "heading": row["heading"],
                        "citation": f"{row['filename']}#attachment-{row['chunk_id']}",
                        "dense_score": 0.0,
                        "sparse_score": round(score, 6),
                        "fused_score": round(score, 6),
                        "rerank_score": None,
                        "text": row["text"],
                        "collapsed_excerpt": str(row["text"])[:180],
                    }
                )
        scored.sort(key=lambda item: item["fused_score"], reverse=True)
        return scored[:top_k]

    def list_memories(self, user_id: str, enabled_only: bool = False) -> list[dict]:
        query = "SELECT * FROM memories WHERE user_id = ?"
        params: list[Any] = [user_id]
        if enabled_only:
            query += " AND enabled = 1"
        query += " ORDER BY updated_at DESC, created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._memory_to_public(row) for row in rows]

    def create_memory(self, user_id: str, content: str, enabled: bool = True) -> dict:
        memory_id = new_id()
        timestamp = now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (id, user_id, content, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory_id, user_id, content, 1 if enabled else 0, timestamp, timestamp),
            )
        return self.get_memory(user_id, memory_id)

    def get_memory(self, user_id: str, memory_id: str) -> dict:
        self._validate_short_id(memory_id, "memory id")
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id)).fetchone()
            if row is None:
                raise ValueError("Memory not found")
        return self._memory_to_public(row)

    def update_memory(self, user_id: str, memory_id: str, *, content: str | None = None, enabled: bool | None = None) -> dict:
        current = self.get_memory(user_id, memory_id)
        next_content = current["content"] if content is None else content
        next_enabled = current["enabled"] if enabled is None else enabled
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE memories SET content = ?, enabled = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (next_content, 1 if next_enabled else 0, now_iso(), memory_id, user_id),
            )
        return self.get_memory(user_id, memory_id)

    def delete_memory(self, user_id: str, memory_id: str) -> None:
        self._validate_short_id(memory_id, "memory id")
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM memories WHERE id = ? AND user_id = ?", (memory_id, user_id))

    def get_canvas(self, user_id: str, workspace_id: str, session_id: str) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT c.*
                FROM canvas_docs c
                JOIN sessions s ON s.id = c.session_id
                WHERE c.session_id = ? AND s.user_id = ? AND s.workspace_id = ?
                """,
                (session_id, user_id, workspace_id),
            ).fetchone()
            if row is None:
                timestamp = now_iso()
                canvas_id = new_id()
                conn.execute(
                    """
                    INSERT INTO canvas_docs (id, session_id, title, content, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (canvas_id, session_id, "未命名文档", "", timestamp, timestamp),
                )
                row = conn.execute("SELECT * FROM canvas_docs WHERE id = ?", (canvas_id,)).fetchone()
        return dict(row)

    def update_canvas(self, user_id: str, workspace_id: str, session_id: str, *, title: str | None = None, content: str | None = None) -> dict:
        current = self.get_canvas(user_id, workspace_id, session_id)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE canvas_docs
                SET title = ?, content = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    current["title"] if title is None else title,
                    current["content"] if content is None else content,
                    now_iso(),
                    current["id"],
                ),
            )
        return self.get_canvas(user_id, workspace_id, session_id)

    def export_session_markdown(self, user_id: str, workspace_id: str, session_id: str) -> str:
        session = self.load_session(user_id, workspace_id, session_id)
        lines = [f"# {session['title']}", ""]
        if session.get("summary"):
            lines.extend(["## 长期记忆摘要", "", session["summary"], ""])
        for message in session["messages"]:
            role = "用户" if message["role"] == "user" else "助手"
            lines.extend([f"## {role} · {message.get('time', '')}", "", message["content"], ""])
            if message.get("sources"):
                lines.append("来源:")
                for source in message["sources"]:
                    lines.append(f"- {source.get('citation') or source.get('title') or source.get('source')}")
                lines.append("")
        return "\n".join(lines).strip() + "\n"

    def create_user(self, username: str, password: str, display_name: str | None = None, email: str | None = None) -> dict:
        username = username.strip()
        self._validate_username(username)
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")
        user_id = new_id()
        timestamp = now_iso()
        display_name = (display_name or username).strip() or username
        normalized_email = normalize_email(email)
        password_hash = hash_password(password)
        with self._lock, self._connect() as conn:
            if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                raise ValueError("Username already exists")
            if normalized_email and conn.execute("SELECT 1 FROM users WHERE email = ?", (normalized_email,)).fetchone():
                raise ValueError("Email already exists")
            conn.execute(
                """
                INSERT INTO users (id, username, email, display_name, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, normalized_email, display_name, password_hash, timestamp, timestamp),
            )
        workspace = self.create_workspace(user_id, DEFAULT_WORKSPACE_NAME)
        return {**self.get_user(user_id), "default_workspace_id": workspace["id"]}

    def get_user(self, user_id: str) -> dict:
        self._validate_short_id(user_id, "user id")
        with self._connect() as conn:
            row = conn.execute("SELECT id, username, email, display_name, created_at, updated_at FROM users WHERE id = ?", (user_id,)).fetchone()
            if row is None:
                raise ValueError("User not found")
        return dict(row)

    def authenticate_user(self, username: str, password: str) -> dict:
        identifier = username.strip()
        email_identifier = normalize_email(identifier) if "@" in identifier else ""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? OR email = ?",
                (identifier, email_identifier),
            ).fetchone()
            if row is None or not verify_password(password, row["password_hash"]):
                raise ValueError("Invalid username or password")
            return dict(row)

    def create_auth_session(self, user_id: str) -> dict:
        token = random_token()
        session_id = new_id()
        timestamp = now_iso()
        token_hash = hash_token(token)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO auth_sessions (id, user_id, token_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, user_id, token_hash, timestamp, timestamp),
            )
        return {"id": session_id, "token": token}

    def get_user_by_session_token(self, token: str) -> dict | None:
        if not token:
            return None
        token_hash = hash_token(token)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.email, u.display_name, u.created_at, u.updated_at, s.id AS auth_session_id
                FROM auth_sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE auth_sessions SET updated_at = ? WHERE id = ?", (now_iso(), row["auth_session_id"]))
            return {
                "id": row["id"],
                "username": row["username"],
                "email": row["email"],
                "display_name": row["display_name"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

    def delete_auth_session(self, token: str) -> None:
        if not token:
            return
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (hash_token(token),))

    def list_workspaces(self, user_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT w.id, w.name, w.invite_code, w.created_at, w.updated_at, wm.role
                FROM workspaces w
                JOIN workspace_members wm ON wm.workspace_id = w.id
                WHERE wm.user_id = ?
                ORDER BY w.updated_at DESC, w.created_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_workspace(self, owner_user_id: str, name: str) -> dict:
        name = name.strip() or DEFAULT_WORKSPACE_NAME
        workspace_id = new_id()
        timestamp = now_iso()
        invite_code = new_id()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workspaces (id, name, invite_code, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workspace_id, name, invite_code, timestamp, timestamp),
            )
            conn.execute(
                """
                INSERT INTO workspace_members (id, workspace_id, user_id, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_id(), workspace_id, owner_user_id, "owner", timestamp),
            )
        return self.get_workspace(owner_user_id, workspace_id)

    def join_workspace(self, user_id: str, workspace_id: str, invite_code: str | None = None) -> dict:
        self._validate_short_id(workspace_id, "workspace id")
        with self._lock, self._connect() as conn:
            workspace = conn.execute("SELECT * FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
            if workspace is None:
                raise ValueError("Workspace not found")
            if invite_code and workspace["invite_code"] != invite_code:
                raise ValueError("Invalid invite code")
            existing = conn.execute(
                "SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
                (workspace_id, user_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO workspace_members (id, workspace_id, user_id, role, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (new_id(), workspace_id, user_id, "member", now_iso()),
                )
        return self.get_workspace(user_id, workspace_id)

    def join_workspace_by_invite_code(self, user_id: str, invite_code: str) -> dict:
        code = invite_code.strip()
        if not code:
            raise ValueError("Invite code is required")
        with self._connect() as conn:
            workspace = conn.execute("SELECT id FROM workspaces WHERE invite_code = ?", (code,)).fetchone()
            if workspace is None:
                raise ValueError("Workspace not found")
        return self.join_workspace(user_id, workspace["id"], code)

    def get_workspace(self, user_id: str, workspace_id: str) -> dict:
        self.ensure_workspace_access(user_id, workspace_id)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT w.id, w.name, w.invite_code, w.created_at, w.updated_at, wm.role
                FROM workspaces w
                JOIN workspace_members wm ON wm.workspace_id = w.id
                WHERE w.id = ? AND wm.user_id = ?
                """,
                (workspace_id, user_id),
            ).fetchone()
            if row is None:
                raise ValueError("Workspace not found")
        return dict(row)

    def get_first_workspace(self, user_id: str) -> dict | None:
        items = self.list_workspaces(user_id)
        return items[0] if items else None

    def ensure_workspace_access(self, user_id: str, workspace_id: str) -> None:
        self._validate_short_id(user_id, "user id")
        self._validate_short_id(workspace_id, "workspace id")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
                (workspace_id, user_id),
            ).fetchone()
            if row is None:
                raise ValueError("Workspace access denied")

    def create_workspace_document(
        self,
        workspace_id: str,
        filename: str,
        path: Path,
        *,
        mime_type: str = "",
        size: int = 0,
        status: str = "ready",
        characters: int = 0,
        chunks: int = 0,
        content_hash: str = "",
    ) -> dict:
        workspace_path = self.workspace_docs_dir(workspace_id)
        workspace_path.mkdir(parents=True, exist_ok=True)
        document_id = new_id()
        timestamp = now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workspace_documents (
                    id, workspace_id, filename, path, mime_type, size, status, error, characters, chunks, content_hash, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    workspace_id,
                    filename,
                    str(path),
                    mime_type,
                    size,
                    status,
                    None,
                    characters,
                    chunks,
                    content_hash,
                    timestamp,
                    timestamp,
                ),
            )
        return self.get_workspace_document(workspace_id, document_id)

    def update_workspace_document(self, workspace_id: str, document_id: str, **fields: Any) -> dict:
        allowed = {"status", "characters", "chunks", "error", "mime_type", "size", "path", "filename", "content_hash"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_workspace_document(workspace_id, document_id)
        updates["updated_at"] = now_iso()
        columns = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [document_id, workspace_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE workspace_documents SET {columns} WHERE id = ? AND workspace_id = ?",
                values,
            )
        return self.get_workspace_document(workspace_id, document_id)

    def list_workspace_documents(self, workspace_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM workspace_documents
                WHERE workspace_id = ?
                ORDER BY created_at DESC
                """,
                (workspace_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_workspace_document_by_filename(self, workspace_id: str, filename: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_documents WHERE workspace_id = ? AND filename = ?",
                (workspace_id, filename),
            ).fetchone()
        return dict(row) if row is not None else None

    def get_workspace_document(self, workspace_id: str, document_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workspace_documents WHERE id = ? AND workspace_id = ?",
                (document_id, workspace_id),
            ).fetchone()
            if row is None:
                raise ValueError("Document not found")
        return dict(row)

    def delete_workspace_document(self, workspace_id: str, document_id: str) -> dict:
        document = self.get_workspace_document(workspace_id, document_id)
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM workspace_documents WHERE id = ? AND workspace_id = ?", (document_id, workspace_id))
        return document

    def create_rag_index_job(self, workspace_id: str, *, total: int = 0, index_version: str = "") -> dict:
        self._validate_short_id(workspace_id, "workspace id")
        job_id = new_id()
        timestamp = now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rag_index_jobs (
                    id, workspace_id, status, stage, message, current, total, processed, failed,
                    total_documents, total_chunks, current_document, index_version, mode, error,
                    created_at, updated_at, finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    workspace_id,
                    "queued",
                    "queued",
                    "等待处理",
                    0,
                    total,
                    0,
                    0,
                    total,
                    0,
                    "",
                    index_version,
                    "background-thread/single-worker",
                    None,
                    timestamp,
                    timestamp,
                    None,
                ),
            )
        return self.get_rag_index_job(workspace_id, job_id)

    def update_rag_index_job(self, workspace_id: str, job_id: str, **fields: Any) -> dict:
        allowed = {
            "status",
            "stage",
            "message",
            "current",
            "total",
            "processed",
            "failed",
            "total_documents",
            "total_chunks",
            "current_document",
            "index_version",
            "mode",
            "error",
            "finished_at",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return self.get_rag_index_job(workspace_id, job_id)
        updates["updated_at"] = now_iso()
        columns = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [job_id, workspace_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE rag_index_jobs SET {columns} WHERE id = ? AND workspace_id = ?",
                values,
            )
        return self.get_rag_index_job(workspace_id, job_id)

    def get_rag_index_job(self, workspace_id: str, job_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM rag_index_jobs WHERE id = ? AND workspace_id = ?",
                (job_id, workspace_id),
            ).fetchone()
        if row is None:
            raise ValueError("RAG index job not found")
        return dict(row)

    def latest_rag_index_job(self, workspace_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM rag_index_jobs
                WHERE workspace_id = ?
                ORDER BY updated_at DESC, rowid DESC
                LIMIT 1
                """,
                (workspace_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def running_rag_index_job(self, workspace_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM rag_index_jobs
                WHERE workspace_id = ? AND status IN ('queued', 'running')
                ORDER BY updated_at DESC, rowid DESC
                LIMIT 1
                """,
                (workspace_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def mark_interrupted_rag_index_jobs(self) -> None:
        timestamp = now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE rag_index_jobs
                SET status = 'error',
                    stage = 'error',
                    message = '索引任务因服务重启中断，可重新触发重建',
                    error = 'Interrupted by service restart',
                    updated_at = ?,
                    finished_at = ?
                WHERE status IN ('queued', 'running')
                """,
                (timestamp, timestamp),
            )

    def workspace_docs_dir(self, workspace_id: str) -> Path:
        self._validate_short_id(workspace_id, "workspace id")
        return self.workspace_root / workspace_id / "documents"

    def workspace_chroma_dir(self, workspace_id: str) -> Path:
        self._validate_short_id(workspace_id, "workspace id")
        return self.workspace_root / workspace_id / "chroma"

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    email TEXT,
                    display_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    invite_code TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workspace_members (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    role TEXT NOT NULL DEFAULT 'member',
                    created_at TEXT NOT NULL,
                    UNIQUE(workspace_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    workspace_id TEXT,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'done',
                    position INTEGER NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(session_id, position)
                );

                CREATE TABLE IF NOT EXISTS message_sources (
                    id TEXT PRIMARY KEY,
                    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL DEFAULT 'rag',
                    source TEXT NOT NULL,
                    chunk_id INTEGER,
                    parent_id INTEGER,
                    heading TEXT,
                    citation TEXT,
                    dense_score REAL,
                    sparse_score REAL,
                    fused_score REAL,
                    rerank_score REAL,
                    text TEXT,
                    document_id TEXT,
                    preview_url TEXT,
                    download_url TEXT,
                    title TEXT,
                    collapsed_excerpt TEXT
                );

                CREATE TABLE IF NOT EXISTS attachments (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    workspace_id TEXT,
                    session_id TEXT,
                    message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    mime_type TEXT NOT NULL DEFAULT '',
                    size INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ready',
                    error TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS attachment_chunks (
                    id TEXT PRIMARY KEY,
                    attachment_id TEXT NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
                    chunk_id INTEGER NOT NULL,
                    heading TEXT,
                    text TEXT NOT NULL,
                    char_start INTEGER NOT NULL DEFAULT 0,
                    char_end INTEGER NOT NULL DEFAULT 0,
                    tokens_json TEXT NOT NULL DEFAULT '[]'
                );

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    content TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS canvas_docs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE REFERENCES sessions(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT '未命名文档',
                    content TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS workspace_documents (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    mime_type TEXT NOT NULL DEFAULT '',
                    size INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'ready',
                    error TEXT,
                    characters INTEGER NOT NULL DEFAULT 0,
                    chunks INTEGER NOT NULL DEFAULT 0,
                    content_hash TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rag_index_jobs (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    message TEXT NOT NULL,
                    current INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    processed INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    total_documents INTEGER NOT NULL DEFAULT 0,
                    total_chunks INTEGER NOT NULL DEFAULT 0,
                    current_document TEXT NOT NULL DEFAULT '',
                    index_version TEXT NOT NULL DEFAULT '',
                    mode TEXT NOT NULL DEFAULT 'background-thread/single-worker',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finished_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_messages_session_position ON messages(session_id, position);
                CREATE INDEX IF NOT EXISTS idx_sources_message ON message_sources(message_id);
                CREATE INDEX IF NOT EXISTS idx_attachments_session ON attachments(session_id);
                CREATE INDEX IF NOT EXISTS idx_attachment_chunks_attachment ON attachment_chunks(attachment_id);
                CREATE INDEX IF NOT EXISTS idx_workspace_documents_workspace ON workspace_documents(workspace_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_rag_jobs_workspace_updated ON rag_index_jobs(workspace_id, updated_at DESC);
                """
            )
            self._ensure_legacy_columns(conn)
            self._bootstrap_legacy_scope(conn)

    def _ensure_legacy_columns(self, conn: sqlite3.Connection) -> None:
        ensure_column(conn, "users", "email", "TEXT")
        ensure_column(conn, "sessions", "user_id", "TEXT")
        ensure_column(conn, "sessions", "workspace_id", "TEXT")
        ensure_column(conn, "attachments", "user_id", "TEXT")
        ensure_column(conn, "attachments", "workspace_id", "TEXT")
        ensure_column(conn, "attachments", "session_id", "TEXT")
        ensure_column(conn, "memories", "user_id", "TEXT")
        ensure_column(conn, "message_sources", "document_id", "TEXT")
        ensure_column(conn, "message_sources", "preview_url", "TEXT")
        ensure_column(conn, "message_sources", "download_url", "TEXT")
        ensure_column(conn, "message_sources", "title", "TEXT")
        ensure_column(conn, "message_sources", "collapsed_excerpt", "TEXT")
        ensure_column(conn, "workspace_documents", "content_hash", "TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email) WHERE email IS NOT NULL AND email != ''")

    def _bootstrap_legacy_scope(self, conn: sqlite3.Connection) -> None:
        user = conn.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_LEGACY_USERNAME,)).fetchone()
        if user is None:
            legacy_user_id = new_id()
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO users (id, username, display_name, password_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (legacy_user_id, DEFAULT_LEGACY_USERNAME, DEFAULT_LEGACY_DISPLAY_NAME, hash_password("local-demo"), timestamp, timestamp),
            )
        else:
            legacy_user_id = user["id"]

        workspace = conn.execute("SELECT id FROM workspaces ORDER BY created_at LIMIT 1").fetchone()
        if workspace is None:
            legacy_workspace_id = new_id()
            timestamp = now_iso()
            conn.execute(
                """
                INSERT INTO workspaces (id, name, invite_code, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (legacy_workspace_id, DEFAULT_WORKSPACE_NAME, new_id(), timestamp, timestamp),
            )
        else:
            legacy_workspace_id = workspace["id"]

        member = conn.execute(
            "SELECT 1 FROM workspace_members WHERE workspace_id = ? AND user_id = ?",
            (legacy_workspace_id, legacy_user_id),
        ).fetchone()
        if member is None:
            conn.execute(
                """
                INSERT INTO workspace_members (id, workspace_id, user_id, role, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_id(), legacy_workspace_id, legacy_user_id, "owner", now_iso()),
            )
        conn.execute("UPDATE sessions SET user_id = COALESCE(user_id, ?), workspace_id = COALESCE(workspace_id, ?)", (legacy_user_id, legacy_workspace_id))
        conn.execute("UPDATE attachments SET user_id = COALESCE(user_id, ?), workspace_id = COALESCE(workspace_id, ?)", (legacy_user_id, legacy_workspace_id))
        conn.execute("UPDATE memories SET user_id = COALESCE(user_id, ?)", (legacy_user_id,))

    def _migrate_legacy_sessions(self) -> None:
        with self._lock:
            with self._connect() as conn:
                legacy_user_id = conn.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_LEGACY_USERNAME,)).fetchone()["id"]
                legacy_workspace_id = conn.execute("SELECT id FROM workspaces ORDER BY created_at LIMIT 1").fetchone()["id"]
            for path in sorted(self.sessions_dir.glob("*.json")):
                self._migrate_split_session(path, legacy_user_id, legacy_workspace_id)
            for path in sorted(self.memory_dir.glob("*.json")):
                self._migrate_legacy_session(path, legacy_user_id, legacy_workspace_id)

    def _migrate_split_session(self, metadata_path: Path, user_id: str, workspace_id: str) -> None:
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        session_id = str(metadata.get("id", metadata_path.stem))
        if not self.is_valid_session_id(session_id):
            return
        message_path = self.messages_dir / f"{session_id}.json"
        messages = []
        if message_path.exists():
            try:
                messages = messages_from_dict(json.loads(message_path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, TypeError):
                messages = []
        self._insert_legacy_session(metadata, messages, user_id, workspace_id)

    def _migrate_legacy_session(self, path: Path, user_id: str, workspace_id: str) -> None:
        try:
            legacy = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if not isinstance(legacy, dict):
            return
        session_id = str(legacy.get("id", path.stem))
        if not self.is_valid_session_id(session_id):
            return
        messages = []
        for item in legacy.get("messages", []):
            role = item.get("role")
            content = item.get("content", "")
            kwargs = {"time": item.get("time", "")}
            if role == "user":
                messages.append(HumanMessage(content=content, additional_kwargs=kwargs))
            elif role == "assistant":
                messages.append(AIMessage(content=content, additional_kwargs=kwargs))
        self._insert_legacy_session(legacy, messages, user_id, workspace_id)

    def _insert_legacy_session(self, metadata: dict, messages: list[Any], user_id: str, workspace_id: str) -> None:
        session_id = str(metadata["id"])
        timestamp = metadata.get("updated_at") or now_iso()
        with self._connect() as conn:
            existing = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if existing:
                return
            conn.execute(
                """
                INSERT INTO sessions (id, user_id, workspace_id, title, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user_id,
                    workspace_id,
                    metadata.get("title", "新会话"),
                    metadata.get("summary", ""),
                    metadata.get("created_at", timestamp),
                    timestamp,
                ),
            )
            for position, message in enumerate(messages):
                role = "user" if message.type == "human" else "assistant"
                conn.execute(
                    """
                    INSERT INTO messages (id, session_id, role, content, time, status, position, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id(),
                        session_id,
                        role,
                        str(message.content),
                        message.additional_kwargs.get("time", timestamp),
                        "done",
                        position,
                        "{}",
                    ),
                )

    def _public_messages(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY position",
                (session_id,),
            ).fetchall()
            return [self._message_to_public(conn, row) for row in rows]

    def _message_to_public(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        message = {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "time": row["time"],
            "status": row["status"],
        }
        sources = conn.execute("SELECT * FROM message_sources WHERE message_id = ? ORDER BY rowid", (row["id"],)).fetchall()
        if sources:
            message["sources"] = [self._source_to_public(source) for source in sources]
        attachments = conn.execute("SELECT * FROM attachments WHERE message_id = ? ORDER BY created_at", (row["id"],)).fetchall()
        if attachments:
            message["attachments"] = [self._attachment_to_public(conn, attachment) for attachment in attachments]
        return message

    def _insert_sources(self, conn: sqlite3.Connection, message_id: str, sources: list[dict]) -> None:
        conn.execute("DELETE FROM message_sources WHERE message_id = ?", (message_id,))
        for source in sources:
            conn.execute(
                """
                INSERT INTO message_sources (
                    id, message_id, kind, source, chunk_id, parent_id, heading, citation,
                    dense_score, sparse_score, fused_score, rerank_score, text, document_id,
                    preview_url, download_url, title, collapsed_excerpt
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id(),
                    message_id,
                    source.get("kind", "rag"),
                    source.get("source", ""),
                    source.get("chunk_id"),
                    source.get("parent_id"),
                    source.get("heading", ""),
                    source.get("citation", ""),
                    source.get("dense_score"),
                    source.get("sparse_score"),
                    source.get("fused_score"),
                    source.get("rerank_score"),
                    source.get("text", ""),
                    source.get("document_id"),
                    source.get("preview_url"),
                    source.get("download_url"),
                    source.get("title"),
                    source.get("collapsed_excerpt") or str(source.get("text", ""))[:180],
                ),
            )

    def _link_attachments(self, conn: sqlite3.Connection, user_id: str, session_id: str, message_id: str, attachment_ids: list[str]) -> None:
        for attachment_id in attachment_ids:
            self._validate_short_id(attachment_id, "attachment id")
            conn.execute(
                """
                UPDATE attachments
                SET message_id = ?
                WHERE user_id = ? AND session_id = ? AND id = ?
                """,
                (message_id, user_id, session_id, attachment_id),
            )

    def _attachment_to_public(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict:
        count_row = conn.execute("SELECT COUNT(*) AS count FROM attachment_chunks WHERE attachment_id = ?", (row["id"],)).fetchone()
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "workspace_id": row["workspace_id"],
            "message_id": row["message_id"],
            "filename": row["filename"],
            "path": row["path"],
            "mime_type": row["mime_type"],
            "size": row["size"],
            "status": row["status"],
            "error": row["error"],
            "created_at": row["created_at"],
            "chunks": int(count_row["count"]),
        }

    @staticmethod
    def _source_to_public(row: sqlite3.Row) -> dict:
        return {
            "kind": row["kind"],
            "source": row["source"],
            "chunk_id": row["chunk_id"],
            "parent_id": row["parent_id"],
            "heading": row["heading"],
            "citation": row["citation"],
            "dense_score": row["dense_score"],
            "sparse_score": row["sparse_score"],
            "fused_score": row["fused_score"],
            "rerank_score": row["rerank_score"],
            "text": row["text"],
            "document_id": row["document_id"],
            "preview_url": row["preview_url"],
            "download_url": row["download_url"],
            "title": row["title"],
            "collapsed_excerpt": row["collapsed_excerpt"],
        }

    @staticmethod
    def _memory_to_public(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "content": row["content"],
            "enabled": bool(row["enabled"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _next_position(conn: sqlite3.Connection, session_id: str) -> int:
        row = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 AS next_position FROM messages WHERE session_id = ?", (session_id,)).fetchone()
        return int(row["next_position"])

    @staticmethod
    def is_valid_session_id(session_id: str) -> bool:
        return bool(SESSION_ID_RE.fullmatch(session_id))

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not PersistentMemoryStore.is_valid_session_id(session_id):
            raise ValueError(f"Invalid session id: {session_id}")

    @staticmethod
    def _validate_short_id(value: str, label: str) -> None:
        if not ID_RE.fullmatch(value):
            raise ValueError(f"Invalid {label}: {value}")

    @staticmethod
    def _validate_username(username: str) -> None:
        if not USERNAME_RE.fullmatch(username):
            raise ValueError("Username must be 3-32 chars and contain only letters, numbers, ., _, -")

    @staticmethod
    def _infer_title(text: str) -> str:
        return text.strip().replace("\n", " ")[:24] or "新会话"


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150_000)
    return "pbkdf2_sha256$150000$" + base64.b64encode(salt).decode("ascii") + "$" + base64.b64encode(digest).decode("ascii")


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$", 3)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    salt = base64.b64decode(salt_b64.encode("ascii"))
    expected = base64.b64decode(digest_b64.encode("ascii"))
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def write_legacy_json(path: Path, data: object) -> None:
    atomic_write_json(path, data)
