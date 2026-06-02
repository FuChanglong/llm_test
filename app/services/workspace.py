from __future__ import annotations

import os
from typing import Any

from app.core.runtime import AppRuntime


def workspace_overview(current_runtime: AppRuntime, user_id: str, workspace_id: str) -> dict[str, Any]:
    store = current_runtime.store
    store.ensure_workspace_access(user_id, workspace_id)

    sessions = store.list_sessions(user_id, workspace_id)
    documents = store.list_workspace_documents(workspace_id)
    memories = store.list_memories(user_id)
    rebuild = current_runtime.rebuild_status(workspace_id)
    document_counts = _document_counts(documents)

    return {
        "workspace_id": workspace_id,
        "stats": {
            "sessions": len(sessions),
            "documents": len(documents),
            "indexed_documents": document_counts["indexed"],
            "pending_documents": document_counts["pending"],
            "failed_documents": document_counts["failed"],
            "total_chunks": sum(int(item.get("chunks") or 0) for item in documents),
            "total_characters": sum(int(item.get("characters") or 0) for item in documents),
            "memories": len(memories),
            "enabled_memories": sum(1 for item in memories if item.get("enabled")),
        },
        "latest_activity": {
            "session_updated_at": sessions[0]["updated_at"] if sessions else None,
            "index_updated_at": rebuild.get("finished_at") or rebuild.get("updated_at"),
        },
        "rebuild": rebuild,
        "environment": {
            "model": os.getenv("VLLM_MODEL", "qwen-turbo"),
            "model_configured": _model_configured(),
            "embedder": os.getenv("RAG_EMBEDDER_TYPE", os.getenv("EMBEDDER_TYPE", "hash")),
        },
        "capabilities": _capabilities(document_counts, memories, rebuild),
        "recommended_actions": _recommended_actions(sessions, documents, document_counts, rebuild),
        "delivery_checks": _delivery_checks(
            sessions=sessions,
            document_counts=document_counts,
            rebuild=rebuild,
            memories=memories,
        ),
        "acceptance_script": _acceptance_script(
            sessions=sessions,
            documents=documents,
            document_counts=document_counts,
            memories=memories,
            rebuild=rebuild,
        ),
    }


def _document_counts(documents: list[dict]) -> dict[str, int]:
    indexed = 0
    pending = 0
    failed = 0
    for document in documents:
        status = str(document.get("status") or "")
        if status in {"indexed", "ready"}:
            indexed += 1
        elif status == "error":
            failed += 1
        else:
            pending += 1
    return {"indexed": indexed, "pending": pending, "failed": failed}


def _model_configured() -> bool:
    api_key = os.getenv("VLLM_API_KEY", "")
    return bool(api_key and api_key != "EMPTY")


def _capabilities(document_counts: dict[str, int], memories: list[dict], rebuild: dict[str, Any]) -> list[dict[str, str]]:
    rag_status = "ready" if document_counts["indexed"] > 0 else "needs_setup"
    if rebuild.get("status") in {"queued", "running"}:
        rag_status = "running"
    if document_counts["failed"] > 0:
        rag_status = "attention"
    research_status = "ready" if _research_configured() else "needs_setup"
    media_status = "ready" if _media_configured() else "needs_setup"
    return [
        {"key": "chat", "label": "流式多轮对话", "status": "ready", "description": "支持停止、重发、编辑消息和工具过程展示"},
        {"key": "team", "label": "团队工作区", "status": "ready", "description": "支持创建工作区、复制邀请码和成员加入"},
        {"key": "rag", "label": "工作区知识库", "status": rag_status, "description": "支持 PDF、Word、Markdown、TXT 的检索和引用"},
        {"key": "attachments", "label": "会话附件分析", "status": "ready", "description": "支持文档附件检索和 CSV/XLSX 本地分析"},
        {"key": "canvas", "label": "Canvas 写作区", "status": "ready", "description": "支持把回答转入长文编辑、润色、扩写和总结"},
        {
            "key": "memory",
            "label": "长期记忆",
            "status": "ready" if any(item.get("enabled") for item in memories) else "available",
            "description": "支持用户级固定记忆和长会话摘要压缩",
        },
        {"key": "research", "label": "联网研究", "status": research_status, "description": "支持搜索、网页归纳和研究摘要"},
        {"key": "media", "label": "图片与语音", "status": media_status, "description": "支持文生图、图像编辑、图像分析和回答朗读"},
        {"key": "export", "label": "会话导出", "status": "ready", "description": "支持 JSON 结构化会话导出"},
    ]


def _research_configured() -> bool:
    api_key = os.getenv("VLLM_API_KEY", "").strip()
    return bool(api_key and api_key != "EMPTY" and _ddgs_installed())


def _media_configured() -> bool:
    omni_key = (os.getenv("OMNI_API_KEY") or os.getenv("VLLM_ALI_API_KEY") or "").strip()
    image_key = (os.getenv("IMAGE_API_KEY") or os.getenv("VLLM_ALI_API_KEY") or os.getenv("VLLM_API_KEY") or "").strip()
    speech_ready = _edge_tts_installed()
    return bool((omni_key and omni_key != "EMPTY") or (image_key and image_key != "EMPTY") or speech_ready)


def _edge_tts_installed() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def _ddgs_installed() -> bool:
    try:
        import ddgs  # noqa: F401
    except ImportError:
        return False
    return True


def _recommended_actions(
    sessions: list[dict],
    documents: list[dict],
    document_counts: dict[str, int],
    rebuild: dict[str, Any],
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if not documents:
        actions.append(
            {
                "key": "upload_docs",
                "priority": "high",
                "title": "上传客户资料并建立知识库",
                "description": "知识库为空时，问答无法给出本地证据引用。",
            }
        )
    elif document_counts["pending"] > 0 and rebuild.get("status") not in {"queued", "running"}:
        actions.append(
            {
                "key": "rebuild_index",
                "priority": "high",
                "title": "重建知识库索引",
                "description": "存在待处理文档，需要完成索引后才能稳定检索。",
            }
        )
    if document_counts["failed"] > 0:
        actions.append(
            {
                "key": "fix_failed_docs",
                "priority": "medium",
                "title": "检查失败文档",
                "description": "失败文档通常是空文件、加密 PDF 或不可提取文本格式。",
            }
        )
    if not sessions:
        actions.append(
            {
                "key": "create_session",
                "priority": "medium",
                "title": "创建一轮验收会话",
                "description": "建议用客户真实问题验证检索、引用、导出和重发流程。",
            }
        )
    actions.append(
        {
            "key": "client_acceptance",
            "priority": "low",
            "title": "准备客户验收脚本",
            "description": "覆盖登录、上传、自动索引、问答引用、Canvas、记忆和导出。",
        }
    )
    return actions


def _delivery_checks(
    *,
    sessions: list[dict],
    document_counts: dict[str, int],
    rebuild: dict[str, Any],
    memories: list[dict],
) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = [
        {
            "key": "model",
            "label": "模型配置",
            "status": "pass" if _model_configured() else "fail",
            "detail": "聊天与研究摘要模型已配置。" if _model_configured() else "缺少 VLLM_API_KEY 或模型服务不可用。",
        },
        {
            "key": "research",
            "label": "联网研究",
            "status": "pass" if _research_configured() else "warn",
            "detail": "网页搜索与研究摘要可用。" if _research_configured() else "研究摘要模型或 ddgs 搜索依赖未完全就绪。",
        },
        {
            "key": "media",
            "label": "图片与朗读",
            "status": "pass" if _media_configured() else "warn",
            "detail": "图片分析/生成与回答朗读至少有一项可用。" if _media_configured() else "多模态或朗读依赖未完全配置。",
        },
        {
            "key": "documents",
            "label": "知识库索引",
            "status": "pass" if document_counts["indexed"] > 0 and rebuild.get("status") not in {"error"} else "fail",
            "detail": (
                f"已索引 {document_counts['indexed']} 份文档，可演示本地引用。"
                if document_counts["indexed"] > 0 and rebuild.get("status") != "error"
                else "尚无可用索引，验收时无法稳定展示引用。"
            ),
        },
        {
            "key": "failures",
            "label": "失败文档",
            "status": "pass" if document_counts["failed"] == 0 else "warn",
            "detail": "当前无失败文档。" if document_counts["failed"] == 0 else f"存在 {document_counts['failed']} 份失败文档，需提前解释或移除。",
        },
        {
            "key": "session",
            "label": "验收会话",
            "status": "pass" if len(sessions) > 0 else "warn",
            "detail": "已有历史会话，可直接复盘演示。" if sessions else "建议预先创建一轮演示会话，避免现场从空白开始。",
        },
        {
            "key": "memory",
            "label": "长期记忆",
            "status": "pass" if any(item.get("enabled") for item in memories) else "warn",
            "detail": "已有启用记忆，可演示长期偏好保存。" if any(item.get("enabled") for item in memories) else "暂无启用记忆，只能展示基础对话能力。",
        },
    ]
    return checks


def _acceptance_script(
    *,
    sessions: list[dict],
    documents: list[dict],
    document_counts: dict[str, int],
    memories: list[dict],
    rebuild: dict[str, Any],
) -> list[dict[str, str]]:
    session_hint = sessions[0]["title"] if sessions else "新建一轮演示会话"
    steps = [
        {
            "key": "login",
            "title": "1. 登录与工作区进入",
            "instruction": "使用演示账号登录，进入目标工作区，确认总览、会话列表和成员信息可正常加载。",
            "expected": "页面在 3 秒内完成首屏加载，当前工作区信息准确。",
        },
        {
            "key": "upload",
            "title": "2. 上传资料并触发索引",
            "instruction": "上传一份 PDF/Word/TXT 文档，观察状态从 uploaded/queued 进入 processing，再到 indexed。",
            "expected": (
                f"当前已索引 {document_counts['indexed']} 份文档。"
                if documents
                else "上传后可看到自动索引进度条和处理阶段。"
            ),
        },
        {
            "key": "chat",
            "title": "3. 用真实问题验证引用",
            "instruction": f"打开“{session_hint}”，输入一条必须依赖知识库的问题，观察回答、来源卡片、引用链接和重新生成按钮。",
            "expected": "回答包含可展开来源，点击来源可新开页查看原文，引用不应丢失。",
        },
        {
            "key": "canvas",
            "title": "4. 将回答转入 Canvas",
            "instruction": "把一段回答发送到 Canvas，继续进行润色、总结或扩写，确认编辑结果可保存并回显。",
            "expected": "Canvas 内容更新后立即可见，不会覆盖之前已保存内容。",
        },
        {
            "key": "memory",
            "title": "5. 演示长期记忆",
            "instruction": "保存一条偏好或术语说明到长期记忆，再发起新的问题，观察系统是否能复用这条记忆。",
            "expected": (
                f"当前已启用 {sum(1 for item in memories if item.get('enabled'))} 条记忆。"
                if memories
                else "保存后在记忆抽屉中可见，并可切换启用状态。"
            ),
        },
        {
            "key": "export",
            "title": "6. 导出会话与交付材料",
            "instruction": "导出一轮完整会话，确认消息、来源和附件信息都包含在内，便于客户留档。",
            "expected": "导出的 JSON 结构完整，至少包含 messages、sources、attachments。",
        },
    ]
    if rebuild.get("status") in {"queued", "running"}:
        steps.insert(
            2,
            {
                "key": "wait_index",
                "title": "3. 观察索引完成",
                "instruction": "在总览页保持刷新，等待后台索引任务完成后再进入问答演示。",
                "expected": "索引状态从 running/queued 变为 complete，失败数保持可控。",
            },
        )
    return steps
