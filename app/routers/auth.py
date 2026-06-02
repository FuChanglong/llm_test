from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import AUTH_COOKIE_NAME
from app.core.deps import clear_auth_cookie, require_user, runtime, set_auth_cookie
from app.schemas import LoginRequest, RegisterRequest
from app.services.payloads import user_payload

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(request: Request, response: Response, payload: RegisterRequest) -> dict:
    store = runtime(request).store
    try:
        result = store.create_user(payload.username, payload.password, payload.display_name, email=payload.email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    auth_session = store.create_auth_session(result["id"])
    set_auth_cookie(response, auth_session["token"])
    workspace = store.get_workspace(result["id"], result["default_workspace_id"])
    return {"user": user_payload(result), "workspaces": [workspace], "current_workspace_id": workspace["id"]}


@router.post("/login")
def login(request: Request, response: Response, payload: LoginRequest) -> dict:
    store = runtime(request).store
    try:
        user = store.authenticate_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    auth_session = store.create_auth_session(user["id"])
    set_auth_cookie(response, auth_session["token"])
    workspaces = store.list_workspaces(user["id"])
    current_workspace = workspaces[0]["id"] if workspaces else None
    return {"user": user_payload(user), "workspaces": workspaces, "current_workspace_id": current_workspace}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(AUTH_COOKIE_NAME, "")
    runtime(request).store.delete_auth_session(token)
    clear_auth_cookie(response)
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    user = require_user(request)
    workspaces = runtime(request).store.list_workspaces(user["id"])
    current_workspace = workspaces[0]["id"] if workspaces else None
    return {"user": user_payload(user), "workspaces": workspaces, "current_workspace_id": current_workspace}
