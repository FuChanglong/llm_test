from __future__ import annotations

import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable

from app.core.engine import BaseEmbedder, KnowledgeBase, atomic_write_json


class VersionedKnowledgeBase:
    """Workspace RAG index wrapper with atomic active-index switching.

    The existing KnowledgeBase still owns chunking, Chroma writes and retrieval.
    This wrapper changes the persistence contract: rebuilds are written into a
    staging directory and become visible only after the active manifest is
    atomically replaced.
    """

    def __init__(self, docs_dir: Path, index_root: Path, embedder: BaseEmbedder | None = None) -> None:
        self.docs_dir = docs_dir
        self.index_root = index_root
        self.index_root.mkdir(parents=True, exist_ok=True)
        self.versions_dir = self.index_root / "versions"
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.index_root / "active_index.json"
        self.embedder = embedder
        self._active_kb: KnowledgeBase | None = None
        self._active_key: str | None = None
        self._lock = threading.RLock()

    def rebuild(self, version: str | None = None, progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        with self._lock:
            index_version = version or f"{int(time.time())}"
            staging_path = self.versions_dir / f".{index_version}.tmp"
            final_path = self.versions_dir / index_version
            if staging_path.exists():
                shutil.rmtree(staging_path)
            if final_path.exists():
                shutil.rmtree(final_path)
            staging_path.mkdir(parents=True, exist_ok=True)

            kb = KnowledgeBase(self.docs_dir, staging_path, embedder=self.embedder)
            kb.rebuild(progress=progress)

            total_chunks = len(kb._bm25_index.get("chunks") or [])
            total_documents = len(kb._doc_hashes)
            staging_path.rename(final_path)
            self._write_active_manifest(index_version, f"versions/{index_version}", total_documents, total_chunks)
            self._active_kb = None
            self._active_key = None
            return {
                "index_version": index_version,
                "total_documents": total_documents,
                "total_chunks": total_chunks,
            }

    def search(self, query: str, top_k: int | None = None, debug: bool = False):
        return self._active().search(query, top_k=top_k, debug=debug)

    def indexed_chunks(self):
        return self._active().indexed_chunks()

    def search_components(self, query: str, top_k: int = 10):
        return self._active().search_components(query, top_k=top_k)

    def document_status(self) -> list[dict[str, Any]]:
        return self._active().document_status()

    def upsert_document(self, source: str, text: str, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            result = self._active().upsert_document(source, text, force=force)
            self._persist_current_manifest()
            return result

    def delete_document(self, source: str) -> None:
        with self._lock:
            self._active().delete_document(source)
            self._persist_current_manifest()

    def active_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"version": "legacy", "path": ".", "legacy": True}
        try:
            import json

            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {"version": "legacy", "path": ".", "legacy": True}
        except Exception:
            return {"version": "legacy", "path": ".", "legacy": True}

    def _active(self) -> KnowledgeBase:
        manifest = self.active_manifest()
        key = str(manifest.get("path") or ".")
        if self._active_kb is not None and self._active_key == key:
            return self._active_kb
        active_path = self.index_root / key
        active_path.mkdir(parents=True, exist_ok=True)
        self._active_kb = KnowledgeBase(self.docs_dir, active_path, embedder=self.embedder)
        self._active_key = key
        return self._active_kb

    def _persist_current_manifest(self) -> None:
        kb = self._active()
        manifest = self.active_manifest()
        path = str(manifest.get("path") or ".")
        version = str(manifest.get("version") or f"incremental-{int(time.time())}")
        if version == "legacy":
            version = f"incremental-{int(time.time())}"
        total_chunks = len(kb._bm25_index.get("chunks") or [])
        total_documents = len(kb._doc_hashes)
        self._write_active_manifest(version, path, total_documents, total_chunks)

    def _write_active_manifest(self, version: str, path: str, total_documents: int, total_chunks: int) -> None:
        atomic_write_json(
            self.manifest_path,
            {
                "version": version,
                "path": path,
                "total_documents": total_documents,
                "total_chunks": total_chunks,
                "updated_at": int(time.time()),
            },
        )
