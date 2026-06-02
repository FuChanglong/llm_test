from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import API_PREFIX, settings
from app.core.errors import install_error_handlers
from app.core.runtime import AppRuntime
from app.routers import attachments, auth, canvas, chat, images, memory, rag, research, sessions, speech, workspaces


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.runtime = AppRuntime()
        try:
            yield
        finally:
            app.state.runtime.close()

    app = FastAPI(title="LLM MCP Demo API", version="3.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    register_routes(app)
    return app


def register_routes(app: FastAPI) -> None:
    @app.get(f"{API_PREFIX}/health")
    def health() -> dict:
        return {"ok": True}

    routers = [
        auth.router,
        workspaces.router,
        sessions.router,
        rag.router,
        chat.router,
        attachments.router,
        memory.router,
        canvas.router,
        research.router,
        images.router,
        speech.router,
    ]
    for router in routers:
        app.include_router(router, prefix=API_PREFIX)


app = create_app()
