from pathlib import Path

from app.core.engine import (
    HashEmbedder,
    KnowledgeBase,
    bm25_scores,
    build_bm25_index,
    build_document_chunks,
    read_docx_text,
    read_pdf_text,
    split_text,
    strip_thinking,
    tokenize_search,
)
from app.rag import VersionedKnowledgeBase


def test_strip_thinking_removes_think_blocks() -> None:
    assert strip_thinking("<think>hidden</think>\nvisible") == "visible"


def test_strip_thinking_keeps_only_final_answer() -> None:
    raw = "Thought: use a tool\nAction: calculate\nObservation: 4\nFinal Answer: 结果是 4"
    assert strip_thinking(raw) == "结果是 4"


def test_split_text_validates_overlap() -> None:
    try:
        split_text("hello", chunk_size=10, overlap=10)
    except ValueError as exc:
        assert "overlap" in str(exc)
    else:
        raise AssertionError("Expected overlap validation error")


def test_knowledge_base_rebuild_updates_deleted_docs_and_cache(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "a.md").write_text("alpha beta gamma", encoding="utf-8")
    (docs_dir / "b.md").write_text("delta epsilon zeta", encoding="utf-8")

    kb = KnowledgeBase(
        docs_dir=docs_dir,
        chroma_path=tmp_path / "chroma",
        embedder=HashEmbedder(dimensions=32),
    )
    kb.rebuild()
    assert set(kb._doc_hashes) == {"a.md", "b.md"}

    kb._query_cache["alpha:4"] = []
    (docs_dir / "b.md").unlink()
    (docs_dir / "a.md").write_text("alpha beta changed", encoding="utf-8")

    kb.rebuild()

    assert set(kb._doc_hashes) == {"a.md"}
    assert kb._query_cache == {}


def test_markdown_chunker_keeps_heading_and_code_context() -> None:
    text = "# 标题\n\n说明 MCP 的 RAG。\n\n```python\nprint('keep')\n```\n"
    chunks = build_document_chunks("doc.md", text)

    assert chunks
    assert chunks[0].heading == "标题"
    assert "print('keep')" in chunks[0].parent_text


def test_bm25_scores_chinese_keyword_hits() -> None:
    chunks = [
        {"tokens": tokenize_search("RAG 检索 MCP 知识库")},
        {"tokens": tokenize_search("天气 查询 工具")},
    ]
    index = build_bm25_index(chunks)
    scores = bm25_scores(tokenize_search("知识库检索"), index)

    assert scores[0] > scores[1]


def test_knowledge_base_hybrid_search_returns_scores_and_citations(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "rag.md").write_text("# RAG\n\nMCP 使用 Chroma 和 BM25 做混合检索。", encoding="utf-8")

    kb = KnowledgeBase(
        docs_dir=docs_dir,
        chroma_path=tmp_path / "chroma",
        embedder=HashEmbedder(dimensions=32),
    )
    kb.rebuild()
    results = kb.search("BM25 混合检索", top_k=3)

    assert results
    assert results[0].citation == "rag.md#chunk-0"
    assert results[0].fused_score > 0


def test_knowledge_base_rebuild_batches_chroma_writes(tmp_path: Path, monkeypatch) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    long_text = ("alpha beta gamma delta epsilon\n" * 4000).strip()
    (docs_dir / "oversized.md").write_text(long_text, encoding="utf-8")

    kb = KnowledgeBase(
        docs_dir=docs_dir,
        chroma_path=tmp_path / "chroma",
        embedder=HashEmbedder(dimensions=32),
    )

    monkeypatch.setattr(kb.client, "get_max_batch_size", lambda: 2)
    batch_sizes: list[int] = []
    original_add = kb.collection.add

    def tracked_add(*, ids, documents, metadatas, embeddings):
        batch_sizes.append(len(ids))
        return original_add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    monkeypatch.setattr(kb.collection, "add", tracked_add)

    kb.rebuild()

    assert len(batch_sizes) > 1
    assert max(batch_sizes) <= 2
    assert sum(batch_sizes) == len(kb._bm25_index.get("chunks") or [])


def test_knowledge_base_upsert_batches_chroma_writes(tmp_path: Path, monkeypatch) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()

    kb = KnowledgeBase(
        docs_dir=docs_dir,
        chroma_path=tmp_path / "chroma",
        embedder=HashEmbedder(dimensions=32),
    )

    monkeypatch.setattr(kb.client, "get_max_batch_size", lambda: 3)
    batch_sizes: list[int] = []
    original_add = kb.collection.add

    def tracked_add(*, ids, documents, metadatas, embeddings):
        batch_sizes.append(len(ids))
        return original_add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

    monkeypatch.setattr(kb.collection, "add", tracked_add)

    text = ("incremental rag text block\n" * 3000).strip()
    result = kb.upsert_document("incremental.md", text, force=True)

    assert result["indexed"] is True
    assert result["chunks"] > 3
    assert len(batch_sizes) > 1
    assert max(batch_sizes) <= 3
    assert sum(batch_sizes) == result["chunks"]


def test_versioned_knowledge_base_keeps_old_active_index_after_failed_rebuild(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "rag.md").write_text("# RAG\n\nalpha beta", encoding="utf-8")
    kb = VersionedKnowledgeBase(
        docs_dir=docs_dir,
        index_root=tmp_path / "index",
        embedder=HashEmbedder(dimensions=32),
    )

    first = kb.rebuild(version="v1")
    assert first["index_version"] == "v1"
    assert kb.search("alpha", top_k=1)[0].citation == "rag.md#chunk-0"

    (docs_dir / "rag.md").unlink()
    try:
        kb.rebuild(version="v2")
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected rebuild without documents to fail")

    assert kb.active_manifest()["version"] == "v1"
    assert kb.search("alpha", top_k=1)[0].citation == "rag.md#chunk-0"


def test_load_documents_supports_docx_and_pdf(tmp_path: Path) -> None:
    from docx import Document
    from pypdf import PdfWriter

    docx_path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph("DOCX RAG 内容")
    document.save(docx_path)

    pdf_path = tmp_path / "empty.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf_path.open("wb") as file:
        writer.write(file)

    assert "DOCX RAG 内容" in read_docx_text(docx_path)
    assert read_pdf_text(pdf_path) == ""
