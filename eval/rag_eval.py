from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.engine import DocumentChunk, atomic_write_json
from app.core.runtime import AppRuntime


HIT_KS = (1, 3, 5, 10)
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
QUERY_STYLE_PLAN = (
    "definition",
    "requirement",
    "numeric",
    "scope",
    "procedure",
    "exception",
    "comparison",
    "fact",
)


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    workspace_id: str
    source: str
    chunk_id: int
    parent_id: int
    heading: str
    module: str
    question: str
    expected_answer: str
    evidence_quote: str
    query_style: str


class DeepSeekQuestionGenerator:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        timeout: float = 90.0,
    ) -> None:
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required when generating a dataset")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def generate_for_chunk(
        self,
        *,
        client: httpx.AsyncClient,
        workspace_id: str,
        chunk: DocumentChunk,
        module: str,
        questions_per_chunk: int,
        retries: int = 3,
    ) -> list[EvalQuestion]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": self._user_prompt(
                        source=chunk.source,
                        chunk_id=chunk.chunk_id,
                        heading=chunk.heading,
                        module=module,
                        text=chunk.text,
                        questions_per_chunk=questions_per_chunk,
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
        }

        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                rows = _extract_questions(content)
                return self._rows_to_questions(
                    rows=rows,
                    workspace_id=workspace_id,
                    chunk=chunk,
                    module=module,
                    questions_per_chunk=questions_per_chunk,
                )
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    await asyncio.sleep(min(8.0, 0.8 * attempt))

        print(f"[WARN] generation failed after {retries} retries: source={chunk.source} chunk_id={chunk.chunk_id} error={last_error}")
        return []

    @staticmethod
    def _rows_to_questions(
        *,
        rows: list[dict[str, Any]],
        workspace_id: str,
        chunk: DocumentChunk,
        module: str,
        questions_per_chunk: int,
    ) -> list[EvalQuestion]:
        questions: list[EvalQuestion] = []
        for row in rows:
            question = _clean_text(row.get("question", ""))
            expected_answer = _clean_text(row.get("expected_answer", ""))
            evidence_quote = _clean_text(row.get("evidence_quote", ""))[:120]
            query_style = _clean_text(row.get("query_style", "")) or "fact"
            if not _valid_generated_question(
                question=question,
                expected_answer=expected_answer,
                evidence_quote=evidence_quote,
                source=chunk.source,
                chunk_text=chunk.text,
            ):
                continue
            index = len(questions) + 1
            questions.append(
                EvalQuestion(
                    id=f"{workspace_id}:{chunk.source}:{chunk.chunk_id}:{index}",
                    workspace_id=workspace_id,
                    source=chunk.source,
                    chunk_id=chunk.chunk_id,
                    parent_id=chunk.parent_id,
                    heading=chunk.heading,
                    module=module,
                    question=question,
                    expected_answer=expected_answer,
                    evidence_quote=evidence_quote,
                    query_style=query_style,
                )
            )
            if len(questions) >= questions_per_chunk:
                break
        return questions

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是严谨的 RAG 检索评测集设计器。你的目标不是考模型生成能力，而是构造能检验检索是否"
            "找回目标 chunk 的自然语言查询。只能依据给定 chunk 出题，不能引入外部知识或同一文档其他段落。"
            "每个问题必须有明确答案锚点，并且答案应能由 evidence_quote 直接支撑。"
            "禁止生成：泛泛总结题、是/否题、带 source/chunk/该片段等评测内部定位词的问题、照抄整句的问题、"
            "多个独立答案混在一起的问题、依赖图片/表格但 chunk 中没有文字证据的问题。"
            "优先生成：定义解释、技术要求、数值范围、适用对象、操作/试验步骤、例外条件、相邻概念区别、"
            "跨两句以内归纳的问题。必须只输出 JSON 对象，格式为 {\"questions\": [...] }。"
        )

    @staticmethod
    def _user_prompt(
        *,
        source: str,
        chunk_id: int,
        heading: str,
        module: str,
        text: str,
        questions_per_chunk: int,
    ) -> str:
        planned_styles = _planned_query_styles(source=source, chunk_id=chunk_id, count=questions_per_chunk)
        return (
            f"请为下面 chunk 生成 {questions_per_chunk} 个中文检索评测问题。\n"
            f"计划题型：{', '.join(planned_styles)}。如果 chunk 不支持某个题型，可以换成 fact，但不要重复问同一个事实。\n\n"
            "硬性规则：\n"
            "1. question 必须像真实用户检索词或问句，长度 12 到 80 个中文字符；\n"
            "2. question 可以出现用户真实会输入的标准号或文档名，但不能出现 source、chunk、上文、本文、该段、这个片段等评测内部定位词；\n"
            "3. question 不要照抄 evidence_quote，至少改写核心表达；\n"
            "4. expected_answer 必须短而具体，不能写“根据文本可知”这类套话；\n"
            "5. evidence_quote 必须从 chunk_text 原文摘取，最多 80 个中文字符；\n"
            "6. query_style 只能是 definition、requirement、numeric、scope、procedure、exception、comparison、fact；\n"
            "7. 多个问题之间要覆盖不同信息点，不要只改写同一个问题。\n\n"
            f"内部标注 source: {source}\n"
            f"内部标注 chunk_id: {chunk_id}\n"
            f"module: {module}\n"
            f"heading: {heading or '无'}\n"
            f"chunk_text:\n{text[:2500]}\n\n"
            "输出 JSON：{\"questions\":[{\"question\":\"...\",\"expected_answer\":\"...\","
            "\"evidence_quote\":\"...\",\"query_style\":\"requirement\"}]}"
        )


async def run_generate_dataset(
    *,
    runtime: AppRuntime,
    workspace_id: str,
    sample_size: int,
    questions_per_chunk: int,
    seed: int,
    output_path: Path,
    generator: DeepSeekQuestionGenerator,
    max_concurrency: int = 500,
    target_questions: int | None = 1000,
) -> list[EvalQuestion]:
    kb = runtime.workspace_kb(workspace_id)
    chunks = _select_chunks(kb.indexed_chunks(), sample_size=sample_size, seed=seed)
    if not chunks:
        raise RuntimeError(f"No indexed chunks found for workspace {workspace_id}")

    max_concurrency = max(1, min(max_concurrency, len(chunks)))
    semaphore = asyncio.Semaphore(max_concurrency)
    dataset: list[EvalQuestion] = []

    limits = httpx.Limits(
        max_connections=max_concurrency,
        max_keepalive_connections=max_concurrency,
    )
    timeout = httpx.Timeout(generator.timeout)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        async def worker(chunk: DocumentChunk) -> list[EvalQuestion]:
            async with semaphore:
                return await generator.generate_for_chunk(
                    client=client,
                    workspace_id=workspace_id,
                    chunk=chunk,
                    module=infer_module(chunk.source),
                    questions_per_chunk=questions_per_chunk,
                )

        tasks = [asyncio.create_task(worker(chunk)) for chunk in chunks]
        try:
            for done_count, task in enumerate(asyncio.as_completed(tasks), start=1):
                rows = await task
                dataset.extend(rows)
                if done_count % 50 == 0 or done_count == len(tasks):
                    print(f"[progress] finished_chunks={done_count}/{len(tasks)} generated_questions={len(dataset)}")
                if target_questions is not None and len(dataset) >= target_questions:
                    for pending in tasks:
                        if not pending.done():
                            pending.cancel()
                    break
        finally:
            await asyncio.gather(*tasks, return_exceptions=True)

    if target_questions is not None:
        dataset = dataset[:target_questions]
    write_jsonl(output_path, [asdict(item) for item in dataset])
    return dataset


def run_eval(*, runtime: AppRuntime, workspace_id: str, questions: list[EvalQuestion], output_path: Path) -> dict[str, Any]:
    kb = runtime.workspace_kb(workspace_id)
    cases: list[dict[str, Any]] = []
    for item in questions:
        component_results = kb.search_components(item.question, top_k=max(HIT_KS))
        case = asdict(item)
        case["hits"] = {}
        for component, results in component_results.items():
            exact_rank = _rank(results, source=item.source, chunk_id=item.chunk_id)
            source_rank = _rank(results, source=item.source, chunk_id=None)
            case["hits"][component] = {
                "exact_rank": exact_rank,
                "source_rank": source_rank,
                "exact": {f"hit@{k}": _hit(exact_rank, k) for k in HIT_KS},
                "source": {f"source_hit@{k}": _hit(source_rank, k) for k in HIT_KS},
            }
            case[f"{component}_top"] = [_result_key(result) for result in results[: max(HIT_KS)]]
        cases.append(case)

    report = {
        "workspace_id": workspace_id,
        "created_at": int(time.time()),
        "total_questions": len(cases),
        "metrics": _summarize(cases),
        "cases": cases,
    }
    atomic_write_json(output_path, report)
    return report


def load_dataset(path: Path) -> list[EvalQuestion]:
    questions: list[EvalQuestion] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        questions.append(EvalQuestion(**payload))
    return questions


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
    os.replace(tmp_path, path)


def infer_module(source: str) -> str:
    name = source.lower()
    rules = [
        ("制动", "brake"),
        ("离合", "clutch"),
        ("联轴", "coupling"),
        ("齿轮", "gear"),
        ("轴承", "bearing"),
        ("液压", "hydraulic"),
        ("弹簧", "spring"),
        ("机械安全", "safety"),
        ("安全", "safety"),
        ("机械制图", "drawing"),
        ("技术制图", "drawing"),
        ("粗糙度", "surface_roughness"),
        ("密封", "seal"),
        ("包装", "packaging"),
        ("道路施工", "road_machinery"),
        ("农业机械", "agricultural_machinery"),
        ("机械加工", "machining"),
    ]
    for keyword, module in rules:
        if keyword in name:
            return module
    match = re.match(r"^(gb(?:_t)?_\d+(?:\.\d+)?)", name)
    return match.group(1) if match else "other"


def _planned_query_styles(*, source: str, chunk_id: int, count: int) -> list[str]:
    start = (sum(ord(char) for char in source) + chunk_id) % len(QUERY_STYLE_PLAN)
    return [QUERY_STYLE_PLAN[(start + offset) % len(QUERY_STYLE_PLAN)] for offset in range(max(1, count))]


def _valid_generated_question(
    *,
    question: str,
    expected_answer: str,
    evidence_quote: str,
    source: str,
    chunk_text: str,
) -> bool:
    if len(question) < 8 or len(question) > 120:
        return False
    if len(expected_answer) < 2:
        return False
    if not evidence_quote or len(evidence_quote) > 120:
        return False
    if _contains_leaked_locator(question, source):
        return False
    if _normalized(evidence_quote) and _normalized(evidence_quote) in _normalized(question):
        return False
    if _normalized(evidence_quote) not in _normalized(chunk_text):
        return False
    boilerplate = ("根据文本", "根据材料", "文中提到", "该段", "这个片段")
    if any(text in expected_answer for text in boilerplate):
        return False
    return True


def _contains_leaked_locator(question: str, source: str) -> bool:
    _ = source
    normalized_question = question.lower()
    leak_terms = ("chunk", "source", "文件名", "该chunk", "该片段", "这个片段", "上述内容", "上文", "本文")
    return any(term in normalized_question for term in leak_terms)


def _normalized(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _select_chunks(chunks: list[DocumentChunk], *, sample_size: int, seed: int) -> list[DocumentChunk]:
    eligible = [chunk for chunk in chunks if len(chunk.text.strip()) >= 120]
    grouped: dict[str, list[DocumentChunk]] = {}
    rng = random.Random(seed)
    for chunk in eligible:
        grouped.setdefault(infer_module(chunk.source), []).append(chunk)
    for values in grouped.values():
        rng.shuffle(values)

    selected: list[DocumentChunk] = []
    modules = sorted(grouped)
    while len(selected) < sample_size and modules:
        next_modules: list[str] = []
        for module in modules:
            values = grouped[module]
            if values and len(selected) < sample_size:
                selected.append(values.pop())
            if values:
                next_modules.append(module)
        modules = next_modules
    return selected


def _extract_questions(content: str) -> list[dict[str, Any]]:
    raw = content.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    payload = json.loads(raw)
    rows = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("DeepSeek response did not contain a questions list")
    return [row for row in rows if isinstance(row, dict)]


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _rank(results: list[Any], *, source: str, chunk_id: int | None) -> int | None:
    for index, result in enumerate(results, start=1):
        if result.source != source:
            continue
        if chunk_id is None or result.chunk_id == chunk_id:
            return index
    return None


def _hit(rank: int | None, k: int) -> bool:
    return rank is not None and rank <= k


def _result_key(result: Any) -> dict[str, Any]:
    return {
        "source": result.source,
        "chunk_id": result.chunk_id,
        "citation": result.citation,
        "dense_score": round(result.dense_score, 6),
        "sparse_score": round(result.sparse_score, 6),
        "fused_score": round(result.fused_score, 6),
        "rerank_score": round(result.rerank_score, 6) if result.rerank_score is not None else None,
    }


def _summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": {component: _component_summary(cases, component) for component in ("final", "dense", "sparse")},
        "by_module": {
            module: {component: _component_summary(rows, component) for component in ("final", "dense", "sparse")}
            for module, rows in _group_cases(cases, "module").items()
        },
        "by_source": {
            source: {"final": _component_summary(rows, "final")}
            for source, rows in _group_cases(cases, "source").items()
        },
    }


def _component_summary(cases: list[dict[str, Any]], component: str) -> dict[str, float | int]:
    total = len(cases)
    summary: dict[str, float | int] = {"total": total}
    for k in HIT_KS:
        exact_count = sum(1 for case in cases if case["hits"][component]["exact"][f"hit@{k}"])
        source_count = sum(1 for case in cases if case["hits"][component]["source"][f"source_hit@{k}"])
        summary[f"hit@{k}"] = round(exact_count / total, 4) if total else 0.0
        summary[f"source_hit@{k}"] = round(source_count / total, 4) if total else 0.0
    return summary


def _group_cases(cases: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        grouped.setdefault(str(case.get(key) or "unknown"), []).append(case)
    return dict(sorted(grouped.items()))


def _default_output_dir(runtime: AppRuntime, workspace_id: str) -> Path:
    return runtime.store.workspace_root / workspace_id / "evals"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and evaluate workspace RAG retrieval datasets.")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--questions-per-chunk", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--eval-only", action="store_true")
    parser.add_argument("--target-questions", type=int, default=1000)
    parser.add_argument("--max-concurrency", type=int, default=500)
    parser.add_argument("--deepseek-base-url", default=os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL))
    parser.add_argument("--deepseek-model", default=os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.generate_only and args.eval_only:
        raise SystemExit("--generate-only and --eval-only cannot be used together")

    runtime = AppRuntime()
    output_dir = args.output_dir or _default_output_dir(runtime, args.workspace_id)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    dataset_path = args.dataset or output_dir / f"rag_eval_dataset_{timestamp}.jsonl"
    report_path = output_dir / f"rag_eval_report_{timestamp}.json"

    if args.eval_only:
        questions = load_dataset(dataset_path)
    else:
        generator = DeepSeekQuestionGenerator(
            api_key="sk-701d90ee507f4e2eae4932c22e774ee7",
            base_url=args.deepseek_base_url,
            model=args.deepseek_model,
            timeout=float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "90")),
        )
        questions = asyncio.run(
            run_generate_dataset(
                runtime=runtime,
                workspace_id=args.workspace_id,
                sample_size=max(1, args.sample_size),
                questions_per_chunk=max(1, min(args.questions_per_chunk, 5)),
                seed=args.seed,
                output_path=dataset_path,
                generator=generator,
                max_concurrency=max(1, args.max_concurrency),
                target_questions=max(1, args.target_questions),
            )
        )

    print(f"dataset: {dataset_path}")
    if args.generate_only:
        print(f"questions: {len(questions)}")
        return

    report = run_eval(runtime=runtime, workspace_id=args.workspace_id, questions=questions, output_path=report_path)
    print(f"report: {report_path}")
    print(json.dumps(report["metrics"]["overall"]["final"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
