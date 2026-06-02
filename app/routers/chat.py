from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.core.deps import require_user, runtime
from app.schemas import ChatEditRequest, ChatRegenerateRequest, ChatRequest
from app.services.chat import load_existing_session_by_id, normalized_message, stream_chat_turn

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/stream")
def chat_stream(request: Request, payload: ChatRequest) -> StreamingResponse:
    user = require_user(request)
    session = load_existing_session_by_id(runtime(request).store, user["id"], payload.session_id)
    return stream_chat_turn(runtime(request), user, session, normalized_message(payload.message), attachment_ids=payload.attachment_ids, persist_user=True)


@router.post("/edit/stream")
def chat_edit_stream(request: Request, payload: ChatEditRequest) -> StreamingResponse:
    user = require_user(request)
    store = runtime(request).store
    session = load_existing_session_by_id(store, user["id"], payload.session_id)
    try:
        session = store.update_user_message_and_truncate(
            user["id"],
            session["workspace_id"],
            session["id"],
            payload.message_id,
            normalized_message(payload.message),
            payload.attachment_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return stream_chat_turn(
        runtime(request),
        user,
        session,
        normalized_message(payload.message),
        attachment_ids=payload.attachment_ids,
        persist_user=False,
        user_message_id=payload.message_id,
    )


@router.post("/regenerate/stream")
def chat_regenerate_stream(request: Request, payload: ChatRegenerateRequest) -> StreamingResponse:
    user = require_user(request)
    store = runtime(request).store
    session = load_existing_session_by_id(store, user["id"], payload.session_id)
    try:
        previous_user = store.previous_user_message(user["id"], session["workspace_id"], session["id"], payload.message_id)
        session = store.truncate_from_message(user["id"], session["workspace_id"], session["id"], payload.message_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    attachment_ids = [item["id"] for item in previous_user.get("attachments", [])]
    return stream_chat_turn(
        runtime(request),
        user,
        session,
        previous_user["content"],
        attachment_ids=attachment_ids,
        persist_user=False,
        user_message_id=previous_user["id"],
    )

