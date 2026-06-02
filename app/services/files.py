from __future__ import annotations

import json
import os
import time
import hashlib
from pathlib import Path

from fastapi import HTTPException

from app.core.config import ATTACHMENT_ALLOWED_SUFFIXES, RAG_ALLOWED_SUFFIXES
from app.core.engine import build_document_chunks, read_document_text


def safe_rag_filename(filename: str) -> str:
    return _safe_filename(filename, RAG_ALLOWED_SUFFIXES, "document")


def safe_attachment_filename(filename: str) -> str:
    return _safe_filename(filename, ATTACHMENT_ALLOWED_SUFFIXES, "attachment")


def safe_image_filename(filename: str) -> str:
    return _safe_filename(filename, {".png", ".jpg", ".jpeg", ".webp"}, "image")


def _safe_filename(filename: str, allowed: set[str], label: str) -> str:
    name = Path(filename).name.strip()
    suffix = Path(name).suffix.lower()
    if not name or suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported {label} type. Allowed: {', '.join(sorted(allowed))}")
    return name


def unique_upload_path(directory: Path, filename: str) -> Path:
    target = directory / filename
    if not target.exists():
        return target
    return directory / f"{target.stem}-{int(time.time() * 1000)}{target.suffix}"


def atomic_write_upload(directory: Path, filename: str, content: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = unique_upload_path(directory, filename)
    tmp = target.with_name(f".{target.name}.{int(time.time() * 1000)}.tmp")
    tmp.write_bytes(content)
    os.replace(tmp, target)
    return target


async def atomic_write_upload_stream(directory: Path, filename: str, upload_file, chunk_size: int = 1024 * 1024) -> tuple[Path, int, str]:
    directory.mkdir(parents=True, exist_ok=True)
    target = unique_upload_path(directory, filename)
    tmp = target.with_name(f".{target.name}.{int(time.time() * 1000)}.tmp")
    digest = hashlib.sha256()
    size = 0
    try:
        with tmp.open("wb") as handle:
            while True:
                chunk = await upload_file.read(chunk_size)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if size <= 0:
            tmp.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        os.replace(tmp, target)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return target, size, digest.hexdigest()


def attachment_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".xlsx", ".xls"}:
        return table_summary_text(path)
    text = read_document_text(path)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Attachment contains no extractable text")
    return text


def table_summary_text(path: Path) -> str:
    data = analyze_table_attachment(path)
    lines = [
        f"表格文件: {path.name}",
        f"行数: {data['rows']}",
        f"列数: {len(data['columns'])}",
        "列: " + ", ".join(data["columns"]),
        "缺失值: " + json.dumps(data["missing_values"], ensure_ascii=False),
        "样例行:",
        json.dumps(data["sample_rows"], ensure_ascii=False, indent=2),
    ]
    return "\n".join(lines)


def analyze_table_attachment(path: Path) -> dict:
    try:
        import pandas as pd
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="pandas is required for table analysis") from exc
    suffix = path.suffix.lower()
    try:
        if suffix == ".csv":
            frame = pd.read_csv(path)
        elif suffix in {".xlsx", ".xls"}:
            frame = pd.read_excel(path)
        else:
            raise HTTPException(status_code=400, detail="Only CSV/XLSX attachments can be analyzed")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read table: {exc}") from exc
    numeric = frame.select_dtypes(include="number")
    numeric_summary = json.loads(numeric.describe().fillna("").to_json(force_ascii=False)) if not numeric.empty else {}
    return {
        "filename": path.name,
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "column_types": {str(column): str(dtype) for column, dtype in frame.dtypes.items()},
        "missing_values": {str(column): int(value) for column, value in frame.isna().sum().items()},
        "numeric_summary": numeric_summary,
        "sample_rows": json.loads(frame.head(8).fillna("").to_json(orient="records", force_ascii=False)),
    }


def build_chunks_for_path(path: Path) -> tuple[str, list[dict]]:
    text = attachment_text(path)
    chunks = [
        {
            "chunk_id": chunk.chunk_id,
            "heading": chunk.heading,
            "text": chunk.text,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
        }
        for chunk in build_document_chunks(path.name, text)
    ]
    return text, chunks


def attachment_path(attachment: dict) -> str:
    path = str(attachment.get("path", ""))
    if not path:
        raise HTTPException(status_code=500, detail="Attachment path is missing")
    return path


def guess_preview_media_type(path: Path) -> str:
    return {".txt": "text/plain; charset=utf-8", ".md": "text/markdown; charset=utf-8", ".pdf": "application/pdf"}.get(path.suffix.lower(), "application/octet-stream")
