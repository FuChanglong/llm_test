from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.engine import get_embedder
from app.core.engine import read_document_text
from app.agent.langchain_agent import build_agent, build_llm, close_mcp_clients
from app.rag import VersionedKnowledgeBase

from app.storage import AppStore


@dataclass
class AppRuntime:
    store: AppStore = field(default_factory=AppStore)
    _agent: Any = None
    _stream_agent: Any = None
    _compress_llm: Any = None
    _workspace_kbs: dict[str, VersionedKnowledgeBase] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        self.store.mark_interrupted_rag_index_jobs()

    @property
    def agent(self):
        with self._lock:
            if self._agent is None:
                self._agent = build_agent(verbose=False)
            return self._agent

    @property
    def stream_agent(self):
        with self._lock:
            if self._stream_agent is None:
                self._stream_agent = build_agent(verbose=False, streaming=True)
            return self._stream_agent

    @property
    def compress_llm(self):
        with self._lock:
            if self._compress_llm is None:
                self._compress_llm = build_llm()
            return self._compress_llm

    def workspace_kb(self, workspace_id: str) -> VersionedKnowledgeBase:
        with self._lock:
            if workspace_id not in self._workspace_kbs:
                self._workspace_kbs[workspace_id] = VersionedKnowledgeBase(
                    docs_dir=self.store.workspace_docs_dir(workspace_id),
                    index_root=self.store.workspace_chroma_dir(workspace_id),
                    embedder=get_embedder(os.getenv("RAG_EMBEDDER_TYPE", os.getenv("EMBEDDER_TYPE", "hash"))),
                )
            return self._workspace_kbs[workspace_id]

    def reset_workspace_kb(self, workspace_id: str) -> VersionedKnowledgeBase:
        with self._lock:
            self._workspace_kbs.pop(workspace_id, None)
        return self.workspace_kb(workspace_id)

    def start_workspace_rebuild(self, workspace_id: str) -> dict[str, Any]:
        existing = self.store.running_rag_index_job(workspace_id)
        if existing:
            return self._rebuild_status_payload(existing)

        documents = self.store.list_workspace_documents(workspace_id)
        if not documents:
            return self.rebuild_status(workspace_id)

        job = self.store.create_rag_index_job(workspace_id, total=len(documents))
        job = self.store.update_rag_index_job(
            workspace_id,
            job["id"],
            status="running",
            stage="queued",
            message="等待处理",
            index_version=job["id"],
        )
        for document in documents:
            try:
                self.store.update_workspace_document(workspace_id, document["id"], status="queued", error=None)
            except Exception:
                continue
        thread = threading.Thread(target=self._run_workspace_rebuild, args=(workspace_id, job["id"]), daemon=True)
        thread.start()
        return self._rebuild_status_payload(self.store.get_rag_index_job(workspace_id, job["id"]))

    def enqueue_workspace_documents(
        self,
        workspace_id: str,
        document_ids: list[str],
        *,
        reset_progress: bool = False,
    ) -> dict[str, Any]:
        existing = self.store.running_rag_index_job(workspace_id)
        if existing:
            return self._rebuild_status_payload(existing)
        ids = [document_id for document_id in dict.fromkeys(document_ids) if document_id]
        if not ids:
            return self.rebuild_status(workspace_id)
        job = self.store.create_rag_index_job(workspace_id, total=len(ids))
        job = self.store.update_rag_index_job(
            workspace_id,
            job["id"],
            status="running",
            stage="queued",
            message="等待增量索引",
            index_version=job["id"],
            mode="background-thread/incremental",
        )
        for document_id in ids:
            try:
                self.store.update_workspace_document(workspace_id, document_id, status="queued", error=None)
            except Exception:
                continue
        thread = threading.Thread(target=self._run_workspace_incremental_index, args=(workspace_id, job["id"], ids), daemon=True)
        thread.start()
        return self._rebuild_status_payload(self.store.get_rag_index_job(workspace_id, job["id"]))

    def delete_workspace_documents(self, workspace_id: str, document_ids: list[str]) -> dict[str, Any]:
        existing = self.store.running_rag_index_job(workspace_id)
        if existing:
            return self._rebuild_status_payload(existing)
        ids = [document_id for document_id in dict.fromkeys(document_ids) if document_id]
        if not ids:
            return self.rebuild_status(workspace_id)
        job = self.store.create_rag_index_job(workspace_id, total=len(ids))
        job = self.store.update_rag_index_job(
            workspace_id,
            job["id"],
            status="running",
            stage="queued",
            message="等待删除文档",
            index_version=job["id"],
            mode="background-thread/delete",
        )
        for document_id in ids:
            try:
                self.store.update_workspace_document(workspace_id, document_id, status="deleting", error=None)
            except Exception:
                continue
        thread = threading.Thread(target=self._run_workspace_delete, args=(workspace_id, job["id"], ids), daemon=True)
        thread.start()
        return self._rebuild_status_payload(self.store.get_rag_index_job(workspace_id, job["id"]))

    def rebuild_status(self, workspace_id: str) -> dict[str, Any]:
        job = self.store.latest_rag_index_job(workspace_id)
        if not job:
            return {
                "id": None,
                "workspace_id": workspace_id,
                "status": "idle",
                "stage": "idle",
                "message": "未开始重建",
                "current": 0,
                "total": 0,
                "percent": 0,
                "total_documents": 0,
                "total_chunks": 0,
                "current_document": "",
                "index_version": "",
                "mode": "background-thread/single-worker",
                "batch_size": 0,
                "available_memory_mb": None,
                "elapsed_seconds": 0,
                "error": None,
            }
        return self._rebuild_status_payload(job)

    def _run_workspace_rebuild(self, workspace_id: str, job_id: str) -> None:
        kb = self.workspace_kb(workspace_id)
        documents = self.store.list_workspace_documents(workspace_id)
        total = len(documents)
        for document in documents:
            self.store.update_workspace_document(workspace_id, document["id"], status="processing", error=None)

        def progress(payload: dict[str, Any]) -> None:
            current = int(payload.get("current") or 0)
            stage = str(payload.get("stage") or "processing")
            message = str(payload.get("message") or "正在处理")
            current_document = str(payload.get("current_document") or "")
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="running",
                stage=stage,
                message=message,
                current=current,
                total=int(payload.get("total") or total),
                processed=current,
                total_documents=int(payload.get("total_documents") or total),
                total_chunks=int(payload.get("total_chunks") or 0),
                current_document=current_document,
            )

        try:
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="running",
                stage="processing",
                message="正在构建新的工作区索引",
                current=0,
                total=total,
                total_documents=total,
                error=None,
            )
            result = kb.rebuild(version=job_id, progress=progress)
            status_by_source = {item["source"]: item for item in kb.document_status()}
            failed = 0
            for document in documents:
                status = status_by_source.get(document["filename"])
                if not status or not status.get("indexed"):
                    failed += 1
                    self.store.update_workspace_document(
                        workspace_id,
                        document["id"],
                        status="error",
                        error="Document contains no extractable text",
                    )
                    continue
                self.store.update_workspace_document(
                    workspace_id,
                    document["id"],
                    status="indexed",
                    characters=int(status.get("characters") or 0),
                    chunks=int(status.get("chunks") or 0),
                    error=None,
                )
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="complete" if failed == 0 else "error",
                stage="complete" if failed == 0 else "error",
                message="处理完成" if failed == 0 else "部分文档没有可索引文本",
                current=total,
                total=total,
                processed=total,
                failed=failed,
                total_documents=int(result.get("total_documents") or total),
                total_chunks=int(result.get("total_chunks") or 0),
                current_document="",
                index_version=str(result.get("index_version") or job_id),
                error=None if failed == 0 else "Some documents contain no extractable text",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        except Exception as exc:
            error = str(exc)[:500]
            for document in documents:
                if document.get("status") in {"queued", "processing", "uploaded", "error"}:
                    self.store.update_workspace_document(workspace_id, document["id"], status="error", error=error)
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="error",
                stage="error",
                message="索引构建失败，已保留旧索引",
                failed=total,
                error=error,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )

    def _run_workspace_incremental_index(self, workspace_id: str, job_id: str, document_ids: list[str]) -> None:
        total = len(document_ids)
        kb = self.workspace_kb(workspace_id)
        processed = 0
        failed = 0
        total_chunks = 0
        try:
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="running",
                stage="indexing",
                message="正在增量索引新文档",
                total=total,
                total_documents=total,
                error=None,
            )
            for index, document_id in enumerate(document_ids, start=1):
                document = self.store.get_workspace_document(workspace_id, document_id)
                self.store.update_workspace_document(workspace_id, document_id, status="processing", error=None)
                self.store.update_rag_index_job(
                    workspace_id,
                    job_id,
                    status="running",
                    stage="indexing",
                    message=f"正在索引 {document['filename']}",
                    current=index - 1,
                    processed=processed,
                    failed=failed,
                    current_document=document["filename"],
                )
                try:
                    text = read_document_text(Path(document["path"]))
                    if not text.strip():
                        raise RuntimeError("Document contains no extractable text")
                    result = kb.upsert_document(document["filename"], text, force=True)
                    total_chunks += int(result.get("chunks") or 0)
                    self.store.update_workspace_document(
                        workspace_id,
                        document_id,
                        status="indexed",
                        characters=int(result.get("characters") or len(text)),
                        chunks=int(result.get("chunks") or 0),
                        error=None,
                    )
                    processed += 1
                except Exception as exc:
                    failed += 1
                    self.store.update_workspace_document(workspace_id, document_id, status="error", error=str(exc)[:500])
                self.store.update_rag_index_job(
                    workspace_id,
                    job_id,
                    status="running",
                    stage="indexing",
                    current=index,
                    processed=processed,
                    failed=failed,
                    total_chunks=total_chunks,
                )
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="complete" if failed == 0 else "error",
                stage="complete" if failed == 0 else "error",
                message="增量索引完成" if failed == 0 else "部分文档增量索引失败",
                current=total,
                total=total,
                processed=processed,
                failed=failed,
                current_document="",
                error=None if failed == 0 else "Some documents failed to index",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        except Exception as exc:
            error = str(exc)[:500]
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="error",
                stage="error",
                message="增量索引失败，已保留现有索引",
                failed=total,
                error=error,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )

    def _run_workspace_delete(self, workspace_id: str, job_id: str, document_ids: list[str]) -> None:
        total = len(document_ids)
        kb = self.workspace_kb(workspace_id)
        processed = 0
        failed = 0
        try:
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="running",
                stage="deleting",
                message="正在删除文档",
                total=total,
                total_documents=total,
                error=None,
            )
            for index, document_id in enumerate(document_ids, start=1):
                document = self.store.get_workspace_document(workspace_id, document_id)
                self.store.update_rag_index_job(
                    workspace_id,
                    job_id,
                    status="running",
                    stage="deleting",
                    message=f"正在删除 {document['filename']}",
                    current=index - 1,
                    processed=processed,
                    failed=failed,
                    current_document=document["filename"],
                )
                try:
                    path = Path(document["path"])
                    indexed_document = str(document.get("status") or "") in {"indexed", "ready"}
                    if indexed_document:
                        kb.delete_document(document["filename"])
                    else:
                        try:
                            kb.delete_document(document["filename"])
                        except Exception:
                            pass
                    if path.exists():
                        path.unlink()
                    self.store.delete_workspace_document(workspace_id, document_id)
                    processed += 1
                except Exception as exc:
                    failed += 1
                    try:
                        self.store.update_workspace_document(workspace_id, document_id, status="error", error=str(exc)[:500])
                    except Exception:
                        pass
                self.store.update_rag_index_job(
                    workspace_id,
                    job_id,
                    status="running",
                    stage="deleting",
                    current=index,
                    processed=processed,
                    failed=failed,
                )
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="complete" if failed == 0 else "error",
                stage="complete" if failed == 0 else "error",
                message="删除完成" if failed == 0 else "部分文档删除失败",
                current=total,
                total=total,
                processed=processed,
                failed=failed,
                current_document="",
                error=None if failed == 0 else "Some documents failed to delete",
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )
        except Exception as exc:
            error = str(exc)[:500]
            self.store.update_rag_index_job(
                workspace_id,
                job_id,
                status="error",
                stage="error",
                message="删除任务失败",
                failed=total,
                error=error,
                finished_at=datetime.now().isoformat(timespec="seconds"),
            )

    @staticmethod
    def _rebuild_status_payload(job: dict[str, Any]) -> dict[str, Any]:
        total = int(job.get("total") or 0)
        current = int(job.get("current") or 0)
        status = str(job.get("status") or "idle")
        percent = 100 if status == "complete" else int(min(95, max(0, current / total * 100))) if total else 5
        end_time = AppRuntime._parse_time(job.get("finished_at")) or time.time()
        started_at = AppRuntime._parse_time(job.get("created_at")) or end_time
        return {
            "id": job.get("id"),
            "workspace_id": job.get("workspace_id"),
            "status": status,
            "stage": job.get("stage"),
            "message": job.get("message"),
            "current": current,
            "total": total,
            "percent": percent,
            "total_documents": int(job.get("total_documents") or 0),
            "total_chunks": int(job.get("total_chunks") or 0),
            "current_document": job.get("current_document") or "",
            "index_version": job.get("index_version") or "",
            "mode": job.get("mode") or "background-thread/single-worker",
            "batch_size": 0,
            "available_memory_mb": None,
            "failed": int(job.get("failed") or 0),
            "processed": int(job.get("processed") or 0),
            "elapsed_seconds": int(max(0, end_time - started_at)),
            "error": job.get("error"),
        }

    @staticmethod
    def _parse_time(value: Any) -> float | None:
        if not value:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return datetime.fromisoformat(str(value)).timestamp()
        except ValueError:
            return None

    def close(self) -> None:
        close_mcp_clients()
