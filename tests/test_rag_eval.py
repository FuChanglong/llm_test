from types import SimpleNamespace

from eval.rag_eval import EvalQuestion, _valid_generated_question, infer_module, run_eval


def _result(source: str, chunk_id: int):
    return SimpleNamespace(
        source=source,
        chunk_id=chunk_id,
        citation=f"{source}#chunk-{chunk_id}",
        dense_score=0.5,
        sparse_score=0.5,
        fused_score=0.5,
        rerank_score=None,
    )


class FakeKb:
    def search_components(self, query: str, top_k: int = 10):
        assert top_k == 10
        return {
            "final": [_result("a.pdf", 2), _result("target.pdf", 7)],
            "dense": [_result("target.pdf", 7)],
            "sparse": [_result("other.pdf", 1)],
        }


class FakeRuntime:
    def workspace_kb(self, workspace_id: str):
        assert workspace_id == "ws1"
        return FakeKb()


def test_run_eval_summarizes_component_and_source_hits(tmp_path) -> None:
    question = EvalQuestion(
        id="q1",
        workspace_id="ws1",
        source="target.pdf",
        chunk_id=7,
        parent_id=3,
        heading="",
        module="gear",
        question="目标问题是什么？",
        expected_answer="目标答案",
        evidence_quote="目标证据",
        query_style="fact",
    )

    report = run_eval(
        runtime=FakeRuntime(),
        workspace_id="ws1",
        questions=[question],
        output_path=tmp_path / "report.json",
    )

    assert report["metrics"]["overall"]["final"]["hit@1"] == 0.0
    assert report["metrics"]["overall"]["final"]["hit@3"] == 1.0
    assert report["metrics"]["overall"]["dense"]["hit@1"] == 1.0
    assert report["metrics"]["overall"]["sparse"]["source_hit@10"] == 0.0
    assert report["metrics"]["by_module"]["gear"]["final"]["hit@3"] == 1.0
    assert (tmp_path / "report.json").exists()


def test_infer_module_uses_domain_keywords() -> None:
    assert infer_module("GB_T_8542-2023_高速齿轮传动装置技术规范.pdf") == "gear"
    assert infer_module("GB_T_36520.3-2019_液压传动_聚氨酯密封件.pdf") == "hydraulic"


def test_generated_question_filter_rejects_locator_leaks() -> None:
    assert not _valid_generated_question(
        question="GB_T_8542-2023 这个 chunk 里齿轮有什么要求？",
        expected_answer="齿轮应满足技术要求",
        evidence_quote="齿轮应满足技术要求",
        source="GB_T_8542-2023_高速齿轮传动装置技术规范.pdf",
        chunk_text="齿轮应满足技术要求，并按规定进行检查。",
    )


def test_generated_question_filter_accepts_grounded_natural_question() -> None:
    assert _valid_generated_question(
        question="GB/T 8542-2023 中高速齿轮传动装置的齿轮需要满足什么技术要求？",
        expected_answer="齿轮应满足技术要求",
        evidence_quote="齿轮应满足技术要求",
        source="GB_T_8542-2023_高速齿轮传动装置技术规范.pdf",
        chunk_text="齿轮应满足技术要求，并按规定进行检查。",
    )
