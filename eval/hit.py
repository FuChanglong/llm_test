from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


HIT_KS = (1, 3, 5, 10)
DEFAULT_COMPONENTS = ("final", "dense", "sparse")


def find_project_root(start: Path) -> Path:
    """
    从当前脚本位置向上找项目根目录。
    根目录需要包含 app/core/runtime.py。
    """
    current = start.resolve()
    if current.is_file():
        current = current.parent

    for path in [current, *current.parents]:
        if (path / "app" / "core" / "runtime.py").exists():
            return path

    raise RuntimeError(
        "找不到项目根目录：没有发现 app/core/runtime.py。\n"
        "请把本脚本放到项目根目录或 eval/ 目录下运行。"
    )


def setup_import_path() -> Path:
    project_root = find_project_root(Path(__file__))
    sys.path.insert(0, str(project_root))
    return project_root


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"第 {line_no} 行不是合法 JSON：{e}") from e

            if not isinstance(row, dict):
                raise ValueError(f"第 {line_no} 行不是 JSON 对象")

            required = ("question", "source", "chunk_id")
            missing = [key for key in required if key not in row]
            if missing:
                raise ValueError(f"第 {line_no} 行缺少字段：{missing}")

            rows.append(row)
    return rows


def get_value(obj: Any, key: str, default: Any = None) -> Any:
    """
    同时兼容对象属性和 dict。
    检索结果一般是对象，但这里做得更稳一点。
    """
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def result_to_dict(result: Any) -> dict[str, Any]:
    rerank_score = get_value(result, "rerank_score")
    return {
        "source": get_value(result, "source"),
        "chunk_id": get_value(result, "chunk_id"),
        "citation": get_value(result, "citation"),
        "dense_score": safe_round(get_value(result, "dense_score")),
        "sparse_score": safe_round(get_value(result, "sparse_score")),
        "fused_score": safe_round(get_value(result, "fused_score")),
        "rerank_score": safe_round(rerank_score) if rerank_score is not None else None,
    }


def safe_round(value: Any, ndigits: int = 6) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except Exception:
        return None


def rank_exact(results: list[Any], *, target_source: str, target_chunk_id: int) -> int | None:
    """
    exact hit：source 和 chunk_id 都必须一致。
    """
    for rank, result in enumerate(results, start=1):
        source = get_value(result, "source")
        chunk_id = get_value(result, "chunk_id")
        if source == target_source and int(chunk_id) == int(target_chunk_id):
            return rank
    return None


def rank_source(results: list[Any], *, target_source: str) -> int | None:
    """
    source hit：只要求命中文件 source，不要求 chunk_id 一致。
    """
    for rank, result in enumerate(results, start=1):
        source = get_value(result, "source")
        if source == target_source:
            return rank
    return None


def is_hit(rank: int | None, k: int) -> bool:
    return rank is not None and rank <= k


def eval_hitk(
    *,
    workspace_id: str,
    dataset_path: Path,
    output_path: Path,
    top_k: int = 10,
    limit: int | None = None,
    save_cases: bool = True,
) -> dict[str, Any]:
    project_root = setup_import_path()

    # 必须在 setup_import_path() 之后导入项目代码
    from app.core.runtime import AppRuntime  # noqa: WPS433

    runtime = AppRuntime()
    kb = runtime.workspace_kb(workspace_id)

    questions = load_jsonl(dataset_path)
    if limit is not None:
        questions = questions[: max(0, limit)]

    if not questions:
        raise RuntimeError("dataset 为空，无法测评")

    max_k = max(max(HIT_KS), top_k)
    cases: list[dict[str, Any]] = []
    component_names: set[str] = set(DEFAULT_COMPONENTS)

    start_time = time.time()

    for idx, item in enumerate(questions, start=1):
        question = str(item["question"])
        target_source = str(item["source"])
        target_chunk_id = int(item["chunk_id"])

        component_results = kb.search_components(question, top_k=max_k)
        component_names.update(component_results.keys())

        case = {
            "id": item.get("id"),
            "question": question,
            "expected_answer": item.get("expected_answer"),
            "evidence_quote": item.get("evidence_quote"),
            "source": target_source,
            "chunk_id": target_chunk_id,
            "module": item.get("module", "unknown"),
            "hits": {},
        }

        for component, results in component_results.items():
            results = list(results or [])
            exact_rank = rank_exact(
                results,
                target_source=target_source,
                target_chunk_id=target_chunk_id,
            )
            source_rank = rank_source(results, target_source=target_source)

            case["hits"][component] = {
                "exact_rank": exact_rank,
                "source_rank": source_rank,
                "exact": {f"hit@{k}": is_hit(exact_rank, k) for k in HIT_KS},
                "source": {f"source_hit@{k}": is_hit(source_rank, k) for k in HIT_KS},
            }
            case[f"{component}_top"] = [result_to_dict(r) for r in results[:max(HIT_KS)]]

        cases.append(case)

        if idx == 1 or idx % 50 == 0 or idx == len(questions):
            elapsed = time.time() - start_time
            print(f"[{idx}/{len(questions)}] evaluated, elapsed={elapsed:.1f}s")

    report = {
        "workspace_id": workspace_id,
        "dataset": str(dataset_path),
        "project_root": str(project_root),
        "created_at": int(time.time()),
        "total_questions": len(questions),
        "metrics": summarize(cases, sorted(component_names)),
    }

    if save_cases:
        report["cases"] = cases

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(output_path)

    return report


def summarize(cases: list[dict[str, Any]], components: list[str]) -> dict[str, Any]:
    return {
        "overall": {
            component: summarize_component(cases, component)
            for component in components
            if any(component in case["hits"] for case in cases)
        },
        "by_module": summarize_by_field(cases, components, field="module"),
        "by_source": summarize_by_field(cases, components, field="source"),
    }


def summarize_by_field(cases: list[dict[str, Any]], components: list[str], *, field: str) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        grouped.setdefault(str(case.get(field) or "unknown"), []).append(case)

    return {
        name: {
            component: summarize_component(rows, component)
            for component in components
            if any(component in row["hits"] for row in rows)
        }
        for name, rows in sorted(grouped.items())
    }


def summarize_component(cases: list[dict[str, Any]], component: str) -> dict[str, float | int]:
    valid_cases = [case for case in cases if component in case["hits"]]
    total = len(valid_cases)
    summary: dict[str, float | int] = {"total": total}

    for k in HIT_KS:
        exact_count = sum(
            1
            for case in valid_cases
            if case["hits"][component]["exact"][f"hit@{k}"]
        )
        source_count = sum(
            1
            for case in valid_cases
            if case["hits"][component]["source"][f"source_hit@{k}"]
        )
        summary[f"hit@{k}"] = round(exact_count / total, 4) if total else 0.0
        summary[f"source_hit@{k}"] = round(source_count / total, 4) if total else 0.0

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval Hit@K from a generated jsonl dataset.")
    parser.add_argument("--workspace-id", required=True, help="workspace id，例如 b2f553a11510")
    parser.add_argument("--dataset", required=True, type=Path, help="生成好的 rag_eval_dataset_xxx.jsonl")
    parser.add_argument("--output", type=Path, default=None, help="输出 report json 路径")
    parser.add_argument("--top-k", type=int, default=10, help="检索 top_k，默认 10")
    parser.add_argument("--limit", type=int, default=None, help="只测前 N 条，调试用")
    parser.add_argument("--no-save-cases", action="store_true", help="只保存整体指标，不保存每条 case 明细")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_path = args.dataset.resolve()

    output_path = args.output
    if output_path is None:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = dataset_path.parent / f"rag_hitk_report_{timestamp}.json"

    report = eval_hitk(
        workspace_id=args.workspace_id,
        dataset_path=dataset_path,
        output_path=output_path.resolve(),
        top_k=args.top_k,
        limit=args.limit,
        save_cases=not args.no_save_cases,
    )

    print("\n===== Final Hit@K =====")
    final_metrics = report["metrics"]["overall"].get("final")
    if final_metrics is None:
        print("没有 final 组件，实际组件如下：")
        print(json.dumps(report["metrics"]["overall"], ensure_ascii=False, indent=2))
    else:
        print(json.dumps(final_metrics, ensure_ascii=False, indent=2))

    print(f"\nreport saved to: {output_path}")


if __name__ == "__main__":
    main()
