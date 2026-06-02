from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile

from app.core.deps import require_workspace_user, runtime
from app.schemas import AnalysisRequest
from app.services.attachments import analyze_attachment, delete_attachment, upload_attachment
from app.services.chat import load_existing_session

router = APIRouter(prefix="/workspaces/{workspace_id}/sessions/{session_id}", tags=["attachments"])


@router.post("/attachments")
async def upload_session_attachment(request: Request, workspace_id: str, session_id: str, file: UploadFile = File(...)) -> dict:
    user = require_workspace_user(request, workspace_id)
    session = load_existing_session(runtime(request).store, user["id"], workspace_id, session_id)
    return await upload_attachment(runtime(request), user, workspace_id, session, file)


@router.delete("/attachments/{attachment_id}")
def delete_session_attachment(request: Request, workspace_id: str, session_id: str, attachment_id: str) -> dict:
    user = require_workspace_user(request, workspace_id)
    return delete_attachment(runtime(request), user, workspace_id, session_id, attachment_id)


@router.post("/analysis")
def analyze_session_attachment(request: Request, workspace_id: str, session_id: str, payload: AnalysisRequest) -> dict:
    user = require_workspace_user(request, workspace_id)
    return analyze_attachment(runtime(request), user, workspace_id, session_id, payload.attachment_id)

