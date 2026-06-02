from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.deps import require_user, runtime
from app.schemas import MemoryCreateRequest, MemoryUpdateRequest

router = APIRouter(prefix="/memory", tags=["memory"])


@router.get("")
def list_memories(request: Request) -> list[dict]:
    user = require_user(request)
    return runtime(request).store.list_memories(user["id"])


@router.post("")
def create_memory(request: Request, payload: MemoryCreateRequest) -> dict:
    user = require_user(request)
    return runtime(request).store.create_memory(user["id"], payload.content.strip(), enabled=payload.enabled)


@router.patch("/{memory_id}")
def update_memory(request: Request, memory_id: str, payload: MemoryUpdateRequest) -> dict:
    user = require_user(request)
    try:
        return runtime(request).store.update_memory(
            user["id"],
            memory_id,
            content=payload.content.strip() if payload.content is not None else None,
            enabled=payload.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{memory_id}")
def delete_memory(request: Request, memory_id: str) -> dict:
    user = require_user(request)
    runtime(request).store.delete_memory(user["id"], memory_id)
    return {"ok": True}

