import sqlite3
from pathlib import Path

from app.storage import AppStore
from app.storage.store import SCHEMA_VERSION


def test_app_store_initializes_versioned_schema(tmp_path: Path) -> None:
    store = AppStore(memory_dir=str(tmp_path), db_path=str(tmp_path / "chat.sqlite3"))

    with sqlite3.connect(store.db_path) as conn:
        row = conn.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone()

    assert row == (SCHEMA_VERSION,)
    assert store.attachments_dir.name == "v1_attachments"
    assert store.workspace_root.name == "v1_workspaces"


def test_app_store_resets_unversioned_legacy_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "chat.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT)")
        conn.execute("INSERT INTO users (id, username) VALUES ('old', 'legacy')")

    store = AppStore(memory_dir=str(tmp_path), db_path=str(db_path))

    with sqlite3.connect(store.db_path) as conn:
        legacy = conn.execute("SELECT 1 FROM users WHERE id = 'old'").fetchone()
        version = conn.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone()

    assert legacy is None
    assert version == (SCHEMA_VERSION,)


def test_rag_index_jobs_are_persisted_and_recovered(tmp_path: Path) -> None:
    store = AppStore(memory_dir=str(tmp_path), db_path=str(tmp_path / "chat.sqlite3"))
    user = store.create_user("alice", "password123", "Alice")
    workspace = store.get_first_workspace(user["id"])
    assert workspace is not None

    job = store.create_rag_index_job(workspace["id"], total=2, index_version="v1")
    assert store.running_rag_index_job(workspace["id"])["id"] == job["id"]

    updated = store.update_rag_index_job(
        workspace["id"],
        job["id"],
        status="running",
        stage="embedding",
        current=1,
        processed=1,
    )
    assert updated["stage"] == "embedding"
    assert store.latest_rag_index_job(workspace["id"])["current"] == 1

    store.mark_interrupted_rag_index_jobs()
    recovered = store.get_rag_index_job(workspace["id"], job["id"])
    assert recovered["status"] == "error"
    assert "重启中断" in recovered["message"]
