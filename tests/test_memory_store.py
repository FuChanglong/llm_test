import json
from pathlib import Path

import app.storage.memory_store as memory_store
from langchain_core.messages import AIMessage, HumanMessage, messages_to_dict

from app.storage.memory_store import MissingSessionError, PersistentMemoryStore


def bootstrap_user_workspace(store: PersistentMemoryStore) -> tuple[dict, dict]:
    result = store.create_user("alice", "password123", "Alice")
    user = store.get_user(result["id"])
    workspace = store.get_workspace(user["id"], result["default_workspace_id"])
    return user, workspace


def test_memory_store_rejects_invalid_and_missing_session_ids(tmp_path: Path) -> None:
    store = PersistentMemoryStore(memory_dir=str(tmp_path))
    user, workspace = bootstrap_user_workspace(store)

    assert not store.session_exists(user["id"], workspace["id"], "../bad")
    try:
        store.load_session(user["id"], workspace["id"], "abc123def456")
    except MissingSessionError:
        pass
    else:
        raise AssertionError("Expected missing session error")


def test_memory_store_round_trips_messages(tmp_path: Path) -> None:
    store = PersistentMemoryStore(memory_dir=str(tmp_path))
    user, workspace = bootstrap_user_workspace(store)
    session = store.create_session(user["id"], workspace["id"])

    store.append_message(session, "user", "hello")
    store.append_message(session, "assistant", "hi")
    store.save_session(session)

    loaded = store.load_session(user["id"], workspace["id"], session["id"])
    assert loaded["title"] == "hello"
    assert all(message["id"] for message in loaded["messages"])
    assert [message["role"] for message in loaded["messages"]] == ["user", "assistant"]


def test_memory_store_migrates_split_json_sessions(tmp_path: Path) -> None:
    session_id = "abc123def456"
    sessions_dir = tmp_path / "sessions"
    messages_dir = tmp_path / "messages"
    sessions_dir.mkdir()
    messages_dir.mkdir()
    (sessions_dir / f"{session_id}.json").write_text(
        json.dumps(
            {
                "id": session_id,
                "title": "legacy",
                "summary": "old summary",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:01",
            }
        ),
        encoding="utf-8",
    )
    (messages_dir / f"{session_id}.json").write_text(
        json.dumps(messages_to_dict([HumanMessage(content="hello"), AIMessage(content="hi")])),
        encoding="utf-8",
    )

    store = PersistentMemoryStore(memory_dir=str(tmp_path))
    legacy_user = store.get_user_by_session_token("")  # type: ignore[assignment]
    assert legacy_user is None
    legacy_account = store.authenticate_user("local", "local-demo")
    workspace = store.get_first_workspace(legacy_account["id"])
    assert workspace is not None
    loaded = store.load_session(legacy_account["id"], workspace["id"], session_id)

    assert loaded["title"] == "legacy"
    assert loaded["summary"] == "old summary"
    assert [message["content"] for message in loaded["messages"]] == ["hello", "hi"]


def test_sources_edit_regenerate_and_export(tmp_path: Path) -> None:
    store = PersistentMemoryStore(memory_dir=str(tmp_path))
    user, workspace = bootstrap_user_workspace(store)
    session = store.create_session(user["id"], workspace["id"])
    user_message = store.append_message(session, "user", "old question")
    assistant = store.append_message(
        session,
        "assistant",
        "answer",
        sources=[
            {
                "kind": "rag",
                "source": "rag.md",
                "citation": "rag.md#chunk-1",
                "text": "evidence",
                "fused_score": 0.9,
                "title": "rag.md",
                "preview_url": "/preview",
            }
        ],
    )

    loaded = store.load_session(user["id"], workspace["id"], session["id"])
    assert loaded["messages"][1]["sources"][0]["citation"] == "rag.md#chunk-1"
    assert "rag.md#chunk-1" in store.export_session_markdown(user["id"], workspace["id"], session["id"])

    store.update_user_message_and_truncate(user["id"], workspace["id"], session["id"], user_message["id"], "new question")
    loaded = store.load_session(user["id"], workspace["id"], session["id"])
    assert [message["content"] for message in loaded["messages"]] == ["new question"]

    assistant = store.append_message(session, "assistant", "new answer")
    store.truncate_from_message(user["id"], workspace["id"], session["id"], assistant["id"])
    assert store.load_session(user["id"], workspace["id"], session["id"])["messages"][-1]["role"] == "user"


def test_attachment_chunks_are_session_scoped(tmp_path: Path) -> None:
    store = PersistentMemoryStore(memory_dir=str(tmp_path))
    user, workspace = bootstrap_user_workspace(store)
    first = store.create_session(user["id"], workspace["id"])
    second = store.create_session(user["id"], workspace["id"])
    first_attachment = store.create_attachment(user["id"], workspace["id"], first["id"], "first.txt", tmp_path / "first.txt")
    second_attachment = store.create_attachment(user["id"], workspace["id"], second["id"], "second.txt", tmp_path / "second.txt")
    store.replace_attachment_chunks(
        first_attachment["id"],
        [{"chunk_id": 0, "heading": "", "text": "alpha project evidence", "char_start": 0, "char_end": 22}],
    )
    store.replace_attachment_chunks(
        second_attachment["id"],
        [{"chunk_id": 0, "heading": "", "text": "beta project evidence", "char_start": 0, "char_end": 21}],
    )

    first_hits = store.search_attachment_chunks(user["id"], workspace["id"], first["id"], "alpha")
    second_hits = store.search_attachment_chunks(user["id"], workspace["id"], second["id"], "alpha")

    assert first_hits[0]["source"] == "first.txt"
    assert second_hits == []


def test_memory_compression_failure_keeps_messages(tmp_path: Path, monkeypatch) -> None:
    class Prompt:
        def __or__(self, _llm):
            return self

        def invoke(self, _payload):
            raise RuntimeError("boom")

    monkeypatch.setattr(memory_store.ChatPromptTemplate, "from_messages", staticmethod(lambda _messages: Prompt()))

    store = PersistentMemoryStore(memory_dir=str(tmp_path))
    user, workspace = bootstrap_user_workspace(store)
    store.compress_trigger = 2
    store.keep_recent = 1
    session = store.create_session(user["id"], workspace["id"])
    store.append_message(session, "user", "one")
    store.append_message(session, "assistant", "two")
    store.append_message(session, "user", "three")

    assert store.compress_long_term_memory(session, object()) is False
    assert "memory_error" in session
    assert store.message_count(user["id"], workspace["id"], session["id"]) == 3
