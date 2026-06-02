from __future__ import annotations

import os

from app.main import app, create_app
from app.services.attachments import analyze_attachment as analyze_attachment_service
from app.services.canvas import canvas_prompt
from app.services.chat import FinalAnswerStreamHandler, message_with_context
from app.services.files import analyze_table_attachment, safe_attachment_filename, safe_image_filename, safe_rag_filename
from app.services.images import normalize_image_result
from app.services.payloads import dedupe_sources
from app.services.research import summarize_research

__all__ = [
    "FinalAnswerStreamHandler",
    "analyze_attachment_service",
    "analyze_table_attachment",
    "app",
    "canvas_prompt",
    "create_app",
    "dedupe_sources",
    "message_with_context",
    "normalize_image_result",
    "safe_attachment_filename",
    "safe_image_filename",
    "safe_rag_filename",
    "summarize_research",
]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api_server:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8001")),
        reload=False,
    )
