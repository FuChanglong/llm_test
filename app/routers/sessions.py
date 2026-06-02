from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from app.core.deps import require_workspace_user, runtime
from app.schemas import SessionCreateRequest
from app.services.chat import load_existing_session
from app.services.payloads import session_payload

router = APIRouter(prefix="/workspaces/{workspace_id}/sessions", tags=["sessions"])


@router.get("")
def list_sessions(request: Request, workspace_id: str) -> list[dict]:
    user = require_workspace_user(request, workspace_id)
    return runtime(request).store.list_sessions(user["id"], workspace_id)


@router.post("")
def create_session(request: Request, workspace_id: str, payload: SessionCreateRequest) -> dict:
    user = require_workspace_user(request, workspace_id)
    session = runtime(request).store.create_session(user["id"], workspace_id, title=payload.title)
    return session_payload(session)


@router.get("/{session_id}")
def get_session(request: Request, workspace_id: str, session_id: str) -> dict:
    user = require_workspace_user(request, workspace_id)
    session = load_existing_session(runtime(request).store, user["id"], workspace_id, session_id)
    return session_payload(session)


@router.delete("/{session_id}")
def delete_session(request: Request, workspace_id: str, session_id: str) -> dict:
    user = require_workspace_user(request, workspace_id)
    store = runtime(request).store
    if not store.session_exists(user["id"], workspace_id, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    store.delete_session(user["id"], workspace_id, session_id)
    return {"ok": True}


@router.get("/{session_id}/export")
def export_session(request: Request, workspace_id: str, session_id: str, format: str = "markdown"):
    user = require_workspace_user(request, workspace_id)
    store = runtime(request).store
    if not store.session_exists(user["id"], workspace_id, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    if format == "json":
        return JSONResponse(session_payload(store.load_session(user["id"], workspace_id, session_id)))
    if format in {"markdown", "md"}:
        markdown = store.export_session_markdown(user["id"], workspace_id, session_id)
        return PlainTextResponse(
            markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{session_id}.md"'},
        )
    raise HTTPException(status_code=400, detail="Unsupported export format")
