from __future__ import annotations

from fastapi import HTTPException, Request, Response

from app.core.config import AUTH_COOKIE_NAME, settings
from app.core.runtime import AppRuntime


def runtime(request: Request) -> AppRuntime:
    return request.app.state.runtime


def require_user(request: Request) -> dict:
    token = request.cookies.get(AUTH_COOKIE_NAME, "")
    user = runtime(request).store.get_user_by_session_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_workspace_user(request: Request, workspace_id: str) -> dict:
    user = require_user(request)
    try:
        runtime(request).store.ensure_workspace_access(user["id"], workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return user


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.cookie_max_age_seconds,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
