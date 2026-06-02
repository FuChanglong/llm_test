# Workspace RAG Eval

这个目录用于离线评估当前 workspace 的检索链路。

## 生成并评估

```bash
DEEPSEEK_API_KEY=your-key .venv/bin/python -m eval.rag_eval \
  --workspace-id b2f553a11510 \
  --sample-size 30 \
  --questions-per-chunk 2
```

默认输出到 `chat_memory/v1_workspaces/<workspace_id>/evals/`：

- `rag_eval_dataset_*.jsonl`：DeepSeek 基于 chunk 生成的问题集，每条问题记录目标 `source` 和 `chunk_id`。
- `rag_eval_report_*.json`：检索评估报告，包含 final、dense、sparse 的 hit@1/3/5/10，以及按 module/source 的准确率。

## 复用已有问题集

```bash
.venv/bin/python -m eval.rag_eval \
  --workspace-id b2f553a11510 \
  --eval-only \
  --dataset chat_memory/v1_workspaces/b2f553a11510/evals/rag_eval_dataset_xxx.jsonl
```

## 设计说明

问题生成只基于单个 chunk，要求模型产出真实用户问法、期望答案、短证据和 query style。评估时同时统计：

- `hit@k`：目标 chunk 是否进入前 k。
- `source_hit@k`：目标文档是否进入前 k，用于观察 chunk 粒度过严时的文档级命中。
- `final`：当前线上融合检索链路。
- `dense` / `sparse`：单独向量检索和 BM25 检索，方便定位哪个模块拖低准确率。
