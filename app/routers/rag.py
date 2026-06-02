from __future__ import annotations

from fastapi import APIRouter, File, Request, UploadFile

from app.core.deps import require_workspace_user, runtime
from app.schemas import RagSearchRequest
from app.schemas import RagDeleteRequest
from app.services.rag import (
    delete_workspace_document,
    delete_workspace_documents,
    document_response,
    rebuild_workspace_index,
    search_workspace_rag,
    start_workspace_rebuild,
    upload_workspace_document,
    workspace_documents_payload,
    workspace_rebuild_status,
)

router = APIRouter(prefix="/workspaces/{workspace_id}", tags=["rag"])


@router.get("/rag/documents")
def list_rag_documents(request: Request, workspace_id: str) -> dict:
    require_workspace_user(request, workspace_id)
    return {"documents": workspace_documents_payload(runtime(request), workspace_id)}


@router.post("/rag/rebuild")
def rebuild_rag_index(request: Request, workspace_id: str) -> dict:
    require_workspace_user(request, workspace_id)
    return {"ok": True, "rebuild": start_workspace_rebuild(runtime(request), workspace_id)}


@router.get("/rag/rebuild/status")
def rag_rebuild_status(request: Request, workspace_id: str) -> dict:
    require_workspace_user(request, workspace_id)
    return {"rebuild": workspace_rebuild_status(runtime(request), workspace_id)}


@router.post("/rag/upload")
async def upload_rag_document(request: Request, workspace_id: str, file: UploadFile = File(...)) -> dict:
    require_workspace_user(request, workspace_id)
    return await upload_workspace_document(runtime(request), workspace_id, file)


@router.delete("/rag/documents/{document_id}")
def delete_rag_document(request: Request, workspace_id: str, document_id: str) -> dict:
    require_workspace_user(request, workspace_id)
    return delete_workspace_document(runtime(request), workspace_id, document_id)


@router.post("/rag/documents/delete")
def delete_rag_documents(request: Request, workspace_id: str, payload: RagDeleteRequest) -> dict:
    require_workspace_user(request, workspace_id)
    return delete_workspace_documents(runtime(request), workspace_id, payload.document_ids)


@router.post("/rag/search")
def search_rag(request: Request, workspace_id: str, payload: RagSearchRequest) -> dict:
    require_workspace_user(request, workspace_id)
    return search_workspace_rag(runtime(request), workspace_id, payload.query, payload.top_k)


@router.get("/documents/{document_id}")
def workspace_document_preview(request: Request, workspace_id: str, document_id: str, mode: str = "preview"):
    require_workspace_user(request, workspace_id)
    return document_response(runtime(request), workspace_id, document_id, mode)
