from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.runtime import AppRuntime
from app.services.files import (
    analyze_table_attachment,
    atomic_write_upload,
    attachment_path,
    build_chunks_for_path,
    safe_attachment_filename,
)


async def upload_attachment(current_runtime: AppRuntime, user: dict, workspace_id: str, session: dict, file: UploadFile) -> dict:
    filename = safe_attachment_filename(file.filename or "")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    session_dir = current_runtime.store.attachments_dir / user["id"] / session["id"]
    target = atomic_write_upload(session_dir, filename, content)
    attachment = current_runtime.store.create_attachment(
        user["id"],
        workspace_id,
        session["id"],
        filename=target.name,
        path=target,
        mime_type=file.content_type or mimetypes.guess_type(target.name)[0] or "",
        size=len(content),
        status="pending",
    )
    try:
        _text, chunks = build_chunks_for_path(target)
        current_runtime.store.replace_attachment_chunks(attachment["id"], chunks)
        return current_runtime.store.get_attachment(user["id"], workspace_id, session["id"], attachment["id"])
    except Exception as exc:
        current_runtime.store.mark_attachment_error(attachment["id"], str(exc))
        return current_runtime.store.get_attachment(user["id"], workspace_id, session["id"], attachment["id"])


def delete_attachment(current_runtime: AppRuntime, user: dict, workspace_id: str, session_id: str, attachment_id: str) -> dict:
    try:
        attachment = current_runtime.store.get_attachment(user["id"], workspace_id, session_id, attachment_id)
        current_runtime.store.delete_attachment(user["id"], workspace_id, session_id, attachment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    path = Path(attachment.get("path", ""))
    if path.exists():
        path.unlink()
    return {"ok": True}


def analyze_attachment(current_runtime: AppRuntime, user: dict, workspace_id: str, session_id: str, attachment_id: str) -> dict:
    try:
        attachment = current_runtime.store.get_attachment(user["id"], workspace_id, session_id, attachment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return analyze_table_attachment(Path(attachment_path(attachment)))
