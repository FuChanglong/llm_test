from __future__ import annotations

from typing import Any


def user_payload(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "email": user.get("email") or "",
        "display_name": user["display_name"],
    }


def session_payload(session: dict) -> dict:
    return {
        "id": session["id"],
        "workspace_id": session["workspace_id"],
        "title": session["title"],
        "summary": session.get("summary", ""),
        "messages": session["messages"],
        "updated_at": session["updated_at"],
    }


def chat_payload(session: dict, answer: str, memory_compressed: bool) -> dict:
    return {
        "session_id": session["id"],
        "workspace_id": session["workspace_id"],
        "title": session["title"],
        "summary": session.get("summary", ""),
        "reply": answer,
        "messages": session["messages"],
        "updated_at": session["updated_at"],
        "memory_compressed": memory_compressed,
    }


def dedupe_sources(sources: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for source in sources:
        key = source_dedupe_key(source)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped[:10]


def source_dedupe_key(source: dict) -> str:
    kind = str(source.get("kind") or "")
    if kind == "rag":
        return str(
            source.get("document_id")
            or source.get("preview_url")
            or source.get("download_url")
            or source.get("title")
            or source.get("source")
            or ""
        )
    return str(
        source.get("document_id")
        or source.get("citation")
        or source.get("preview_url")
        or source.get("source")
        or ""
    )


def workspace_rag_result_payload(workspace_id: str, document_map: dict[str, dict], result: Any) -> dict:
    document = document_map.get(result.source, {})
    preview_url = f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}?mode=preview" if document else None
    download_url = f"/api/v1/workspaces/{workspace_id}/documents/{document['id']}?mode=download" if document else None
    return {
        "kind": "rag",
        "source": result.source,
        "chunk_id": result.chunk_id,
        "parent_id": result.chunk.parent_id,
        "heading": result.heading,
        "citation": result.citation,
        "distance": result.distance,
        "dense_score": round(result.dense_score, 6),
        "sparse_score": round(result.sparse_score, 6),
        "fused_score": round(result.fused_score, 6),
        "rerank_score": round(result.rerank_score, 6) if result.rerank_score is not None else None,
        "text": result.text,
        "snippet": result.text[:500],
        "document_id": document.get("id"),
        "title": document.get("filename", result.source),
        "preview_url": preview_url,
        "download_url": download_url,
        "collapsed_excerpt": result.text[:180],
    }
