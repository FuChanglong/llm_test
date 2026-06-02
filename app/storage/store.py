from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from app.core.config import default_chat_db_path, default_chat_memory_dir
from app.storage.memory_store import PersistentMemoryStore


SCHEMA_VERSION = "2026_05_v1"


class AppStore(PersistentMemoryStore):
    """Fresh v1 store.

    The old demo store migrated legacy JSON data implicitly. This store starts
    from a versioned SQLite schema and resets incompatible tables instead of
    migrating historical demo data.
    """

    def __init__(self, memory_dir: str | None = None, db_path: str | None = None) -> None:
        self.memory_dir = Path(memory_dir) if memory_dir else default_chat_memory_dir()
        self.db_path = Path(db_path) if db_path else default_chat_db_path(self.memory_dir)
        self.attachments_dir = self.memory_dir / "v1_attachments"
        self.workspace_root = self.memory_dir / "v1_workspaces"
        self.sessions_dir = self.memory_dir / "sessions"
        self.messages_dir = self.memory_dir / "messages"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.compress_trigger = int(os.getenv("MEMORY_COMPRESS_TRIGGER", "30"))
        self.keep_recent = int(os.getenv("MEMORY_KEEP_RECENT", "12"))
        self.max_token_limit = int(os.getenv("MEMORY_MAX_TOKEN_LIMIT", "2000"))

        import threading

        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            self._reset_incompatible_schema(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

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
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
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
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    message_id TEXT REFERENCES messages(id) ON DELETE SET NULL,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL,
                    mime_type TEXT NOT NULL DEFAULT '',
                    size INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
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
                    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
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
                    status TEXT NOT NULL DEFAULT 'pending',
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
            conn.execute(
                """
                INSERT INTO app_metadata (key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (SCHEMA_VERSION,),
            )

    def _reset_incompatible_schema(self, conn: sqlite3.Connection) -> None:
        version_row = self._metadata_version(conn)
        if version_row in {None, SCHEMA_VERSION}:
            if version_row is None and self._has_user_tables(conn):
                self._drop_app_tables(conn)
            return
        self._drop_app_tables(conn)

    def _metadata_version(self, conn: sqlite3.Connection) -> str | None:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'app_metadata'"
        ).fetchone()
        if table is None:
            return None
        row = conn.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone()
        return str(row["value"]) if row else None

    def _has_user_tables(self, conn: sqlite3.Connection) -> bool:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone()
        return row is not None

    def _drop_app_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            DROP TABLE IF EXISTS attachment_chunks;
            DROP TABLE IF EXISTS attachments;
            DROP TABLE IF EXISTS message_sources;
            DROP TABLE IF EXISTS messages;
            DROP TABLE IF EXISTS canvas_docs;
            DROP TABLE IF EXISTS sessions;
            DROP TABLE IF EXISTS memories;
            DROP TABLE IF EXISTS rag_index_jobs;
            DROP TABLE IF EXISTS workspace_documents;
            DROP TABLE IF EXISTS auth_sessions;
            DROP TABLE IF EXISTS workspace_members;
            DROP TABLE IF EXISTS workspaces;
            DROP TABLE IF EXISTS users;
            DROP TABLE IF EXISTS app_metadata;
            """
        )

    def _migrate_legacy_sessions(self) -> None:
        return None
