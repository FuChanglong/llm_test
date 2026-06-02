from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.deps import require_user, require_workspace_user, runtime
from app.schemas import WorkspaceCreateRequest, WorkspaceInviteJoinRequest, WorkspaceJoinRequest
from app.services.workspace import workspace_overview

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("")
def list_workspaces(request: Request) -> list[dict]:
    user = require_user(request)
    return runtime(request).store.list_workspaces(user["id"])


@router.post("")
def create_workspace(request: Request, payload: WorkspaceCreateRequest) -> dict:
    user = require_user(request)
    return runtime(request).store.create_workspace(user["id"], payload.name)


@router.post("/join")
def join_workspace_by_invite(request: Request, payload: WorkspaceInviteJoinRequest) -> dict:
    user = require_user(request)
    try:
        return runtime(request).store.join_workspace_by_invite_code(user["id"], payload.invite_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{workspace_id}/overview")
def get_workspace_overview(request: Request, workspace_id: str) -> dict:
    user = require_workspace_user(request, workspace_id)
    return workspace_overview(runtime(request), user["id"], workspace_id)


@router.post("/{workspace_id}/join")
def join_workspace(request: Request, workspace_id: str, payload: WorkspaceJoinRequest) -> dict:
    user = require_user(request)
    try:
        return runtime(request).store.join_workspace(user["id"], workspace_id, payload.invite_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
