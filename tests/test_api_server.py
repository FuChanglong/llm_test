from fastapi.testclient import TestClient
import time

from api_server import (
    FinalAnswerStreamHandler,
    create_app,
    dedupe_sources,
    message_with_context,
    normalize_image_result,
    safe_attachment_filename,
    safe_rag_filename,
    summarize_research,
)
from app.routers import speech as speech_router


def register_and_workspace(client: TestClient) -> tuple[dict, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "password": "password123", "display_name": "Alice"},
    )
    assert response.status_code == 200
    payload = response.json()
    return payload["user"], payload["current_workspace_id"]


def create_session(client: TestClient, workspace_id: str) -> str:
    response = client.post(f"/api/v1/workspaces/{workspace_id}/sessions", json={})
    assert response.status_code == 200
    return response.json()["id"]


def test_health_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_auth_required_for_workspace_session_route() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/workspaces/abc123def456/sessions")
    assert response.status_code == 401
    assert response.json()["error"] == {"code": "unauthorized", "message": "Authentication required"}


def test_stream_handler_emits_safe_progress_not_raw_thought() -> None:
    handler = FinalAnswerStreamHandler()
    handler.on_llm_start()
    handler.on_llm_new_token("Thought: I should search private reasoning\n")
    handler.on_llm_new_token("Final Answer: 你好")

    events = []
    while not handler.events.empty():
        events.append(handler.events.get())

    assert {"type": "reasoning", "content": "分析问题，判断是否需要调用工具。"} in events
    assert {"type": "reasoning", "content": "整理当前信息，准备下一步。"} in events
    assert {"type": "token", "content": " 你好"} in events
    assert all("private reasoning" not in str(event) for event in events)


def test_stream_handler_hides_langchain_exception_tool() -> None:
    handler = FinalAnswerStreamHandler()
    handler.on_tool_start({"name": "_Exception"}, "parser error")
    handler.on_tool_end("ignored")

    events = []
    while not handler.events.empty():
        events.append(handler.events.get())

    assert events == [{"type": "reasoning", "content": "模型输出格式有误，正在纠正。"}]


def test_safe_rag_filename_rejects_unsupported_suffix() -> None:
    try:
        safe_rag_filename("../bad.exe")
    except Exception as exc:
        assert "Unsupported document type" in str(exc)
    else:
        raise AssertionError("Expected unsupported suffix to be rejected")


def test_safe_attachment_filename_accepts_table_files() -> None:
    assert safe_attachment_filename("../data.csv") == "data.csv"


def test_message_with_context_injects_attachment_evidence() -> None:
    text = message_with_context(
        "请总结附件",
        [{"citation": "notes.txt#attachment-0", "text": "important evidence"}],
    )
    assert "请总结附件" in text
    assert "notes.txt#attachment-0" in text
    assert "important evidence" in text


def test_dedupe_sources_collapses_same_rag_document() -> None:
    sources = [
        {"kind": "rag", "document_id": "doc1", "citation": "file.pdf#chunk-1", "title": "file.pdf"},
        {"kind": "rag", "document_id": "doc1", "citation": "file.pdf#chunk-9", "title": "file.pdf"},
        {"kind": "rag", "document_id": "doc2", "citation": "other.pdf#chunk-1", "title": "other.pdf"},
    ]
    deduped = dedupe_sources(sources)
    assert len(deduped) == 2
    assert deduped[0]["document_id"] == "doc1"
    assert deduped[1]["document_id"] == "doc2"


def test_auth_workspace_memory_export_and_attachment_endpoints(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_DB_PATH", str(tmp_path / "chat.sqlite3"))

    with TestClient(create_app()) as client:
        _user, workspace_id = register_and_workspace(client)
        session_id = create_session(client, workspace_id)

        memory_response = client.post("/api/v1/memory", json={"content": "用户喜欢简洁回答"})
        assert memory_response.status_code == 200
        assert client.get("/api/v1/memory").json()[0]["content"] == "用户喜欢简洁回答"

        upload_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/sessions/{session_id}/attachments",
            files={"file": ("notes.txt", b"alpha project evidence", "text/plain")},
        )
        assert upload_response.status_code == 200
        attachment = upload_response.json()
        assert attachment["filename"] == "notes.txt"
        assert attachment["chunks"] >= 1

        export_response = client.get(f"/api/v1/workspaces/{workspace_id}/sessions/{session_id}/export?format=json")
        assert export_response.status_code == 200
        assert export_response.json()["id"] == session_id

        delete_response = client.delete(
            f"/api/v1/workspaces/{workspace_id}/sessions/{session_id}/attachments/{attachment['id']}"
        )
        assert delete_response.status_code == 200


def test_email_login_and_invite_code_join_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_DB_PATH", str(tmp_path / "chat.sqlite3"))

    with TestClient(create_app()) as client:
        alice_response = client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "password123", "display_name": "Alice"},
        )
        assert alice_response.status_code == 200
        alice_payload = alice_response.json()
        assert alice_payload["user"]["email"] == "alice@example.com"
        invite_code = alice_payload["workspaces"][0]["invite_code"]
        workspace_id = alice_payload["current_workspace_id"]

        client.post("/api/v1/auth/logout")
        bob_response = client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.com", "password": "password123", "display_name": "Bob"},
        )
        assert bob_response.status_code == 200

        join_response = client.post("/api/v1/workspaces/join", json={"invite_code": invite_code})
        assert join_response.status_code == 200
        assert join_response.json()["id"] == workspace_id
        assert join_response.json()["role"] == "member"

        client.post("/api/v1/auth/logout")
        login_response = client.post("/api/v1/auth/login", json={"username": "bob@example.com", "password": "password123"})
        assert login_response.status_code == 200
        assert any(item["id"] == workspace_id for item in login_response.json()["workspaces"])


def test_workspace_overview_reports_delivery_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_DB_PATH", str(tmp_path / "chat.sqlite3"))

    with TestClient(create_app()) as client:
        _user, workspace_id = register_and_workspace(client)
        create_session(client, workspace_id)
        client.post("/api/v1/memory", json={"content": "偏好简洁回答"})

        response = client.get(f"/api/v1/workspaces/{workspace_id}/overview")
        assert response.status_code == 200
        payload = response.json()
        assert payload["stats"]["sessions"] == 1
        assert payload["stats"]["documents"] == 0
        assert payload["stats"]["enabled_memories"] == 1
        assert any(item["key"] == "rag" for item in payload["capabilities"])
        assert payload["recommended_actions"][0]["key"] == "upload_docs"


def test_workspace_rag_upload_and_preview(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_DB_PATH", str(tmp_path / "chat.sqlite3"))

    with TestClient(create_app()) as client:
        _user, workspace_id = register_and_workspace(client)
        upload_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/rag/upload",
            files={"file": ("notes.md", b"# Demo\n\nalpha beta", "text/markdown")},
        )
        assert upload_response.status_code == 200
        payload = upload_response.json()
        document = payload["document"]
        assert payload["task"]["status"] in {"queued", "running", "complete"}

        deadline = time.time() + 5
        task = payload["task"]
        while time.time() < deadline and task["status"] in {"queued", "running"}:
            task_response = client.get(f"/api/v1/workspaces/{workspace_id}/rag/rebuild/status")
            assert task_response.status_code == 200
            task = task_response.json()["rebuild"]
            time.sleep(0.05)
        assert task["status"] == "complete"

        docs_response = client.get(f"/api/v1/workspaces/{workspace_id}/rag/documents")
        assert docs_response.status_code == 200
        docs = docs_response.json()["documents"]
        assert docs[0]["preview_url"].endswith("mode=preview")
        assert docs[0]["status"] == "indexed"

        preview_response = client.get(f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}?mode=preview")
        assert preview_response.status_code == 200


def test_workspace_rag_delete_uses_background_task(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_DB_PATH", str(tmp_path / "chat.sqlite3"))

    with TestClient(create_app()) as client:
        _user, workspace_id = register_and_workspace(client)
        upload_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/rag/upload",
            files={"file": ("notes.md", b"# Demo\n\nalpha beta", "text/markdown")},
        )
        assert upload_response.status_code == 200
        document = upload_response.json()["document"]

        deadline = time.time() + 5
        task = upload_response.json()["task"]
        while time.time() < deadline and task["status"] in {"queued", "running"}:
            task = client.get(f"/api/v1/workspaces/{workspace_id}/rag/rebuild/status").json()["rebuild"]
            time.sleep(0.05)
        assert task["status"] == "complete"

        delete_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/rag/documents/delete",
            json={"document_ids": [document["id"]]},
        )
        assert delete_response.status_code == 200
        delete_payload = delete_response.json()
        assert delete_payload["task"]["status"] in {"queued", "running", "complete"}
        if delete_payload["documents"]:
            assert delete_payload["documents"][0]["status"] in {"deleting", "indexed"}

        deadline = time.time() + 5
        delete_task = delete_payload["task"]
        while time.time() < deadline and delete_task["status"] in {"queued", "running"}:
            delete_task = client.get(f"/api/v1/workspaces/{workspace_id}/rag/rebuild/status").json()["rebuild"]
            time.sleep(0.05)
        assert delete_task["status"] == "complete"

        docs_response = client.get(f"/api/v1/workspaces/{workspace_id}/rag/documents")
        assert docs_response.status_code == 200
        assert docs_response.json()["documents"] == []
        assert not (tmp_path / "v1_workspaces" / workspace_id / "documents" / "notes.md").exists()


def test_workspace_rag_empty_upload_does_not_leave_document_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_DB_PATH", str(tmp_path / "chat.sqlite3"))

    with TestClient(create_app()) as client:
        _user, workspace_id = register_and_workspace(client)
        upload_response = client.post(
            f"/api/v1/workspaces/{workspace_id}/rag/upload",
            files={"file": ("empty.md", b"", "text/markdown")},
        )
        assert upload_response.status_code == 400
        docs_dir = tmp_path / "v1_workspaces" / workspace_id / "documents"
        if docs_dir.exists():
            assert list(docs_dir.iterdir()) == []


def test_summarize_research_uses_llm_response() -> None:
    class FakeLlm:
        def invoke(self, prompt: str):
            assert "研究问题" in prompt
            return type("Response", (), {"content": "研究摘要"})()

    summary = summarize_research(
        FakeLlm(),
        "测试问题",
        [{"title": "A", "url": "https://example.com", "snippet": "s", "content": "body"}],
    )
    assert summary == "研究摘要"


def test_normalize_image_result_supports_url_and_base64() -> None:
    payload = type(
        "ImageResult",
        (),
        {
            "data": [
                type("Item", (), {"url": "https://example.com/a.png", "b64_json": None})(),
                type("Item", (), {"url": None, "b64_json": "abc"})(),
            ]
        },
    )()

    normalized = normalize_image_result(payload, "prompt", "gpt-image-1")
    assert normalized["images"][0]["url"] == "https://example.com/a.png"
    assert normalized["images"][1]["data_url"].startswith("data:image/png;base64,")


def test_speech_synthesize_endpoint(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CHAT_MEMORY_DIR", str(tmp_path))
    monkeypatch.setenv("CHAT_DB_PATH", str(tmp_path / "chat.sqlite3"))

    async def fake_speech(_text: str):
        return speech_router.Response(content=b"mp3", media_type="audio/mpeg")

    monkeypatch.setattr(speech_router, "synthesize_speech", fake_speech)
    with TestClient(create_app()) as client:
        register_and_workspace(client)
        response = client.post("/api/v1/speech/synthesize", json={"text": "你好"})
    assert response.status_code == 200
    assert response.content == b"mp3"
    assert response.headers["content-type"].startswith("audio/mpeg")
