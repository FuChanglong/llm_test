from __future__ import annotations

from fastapi import HTTPException

from app.core.engine import strip_thinking


def canvas_prompt(mode: str, instruction: str, content: str) -> str:
    labels = {"polish": "润色", "summarize": "总结", "rewrite": "改写", "expand": "扩写"}
    return (
        f"你是中文文档编辑助手。请对下面文本执行“{labels.get(mode, mode)}”。\n"
        f"用户补充要求: {instruction}\n\n要求: 只输出处理后的正文，不要输出解释、标题或 JSON。\n\n文本:\n{content}"
    )


def transform_canvas(llm, mode: str, instruction: str, content: str) -> dict:
    prompt = canvas_prompt(mode, instruction, content)
    try:
        response = llm.invoke(prompt)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Canvas transform failed: {exc}") from exc
    return {"content": strip_thinking(str(response.content))}
