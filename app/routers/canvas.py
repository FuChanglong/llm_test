from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.deps import require_workspace_user, runtime
from app.schemas import CanvasTransformRequest, CanvasUpdateRequest
from app.services.canvas import transform_canvas

router = APIRouter(prefix="/workspaces/{workspace_id}/sessions/{session_id}/canvas", tags=["canvas"])


@router.get("")
def get_canvas(request: Request, workspace_id: str, session_id: str) -> dict:
    user = require_workspace_user(request, workspace_id)
    return runtime(request).store.get_canvas(user["id"], workspace_id, session_id)


@router.put("")
def update_canvas(request: Request, workspace_id: str, session_id: str, payload: CanvasUpdateRequest) -> dict:
    user = require_workspace_user(request, workspace_id)
    return runtime(request).store.update_canvas(user["id"], workspace_id, session_id, title=payload.title, content=payload.content)


@router.post("/transform")
def transform_canvas_route(request: Request, workspace_id: str, session_id: str, payload: CanvasTransformRequest) -> dict:
    require_workspace_user(request, workspace_id)
    return transform_canvas(runtime(request).compress_llm, payload.mode, payload.instruction, payload.content)

