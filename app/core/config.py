from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)


API_PREFIX = "/api/v1"
AUTH_COOKIE_NAME = "llm_demo_auth"
RAG_ALLOWED_SUFFIXES = {".md", ".txt", ".doc", ".docx", ".pdf"}
ATTACHMENT_ALLOWED_SUFFIXES = RAG_ALLOWED_SUFFIXES | {".csv", ".xlsx", ".xls"}
DEFAULT_CHAT_MEMORY_DIR = "chat_memory"
LEGACY_CHAT_MEMORY_DIR = ".chat_memory"
DEFAULT_CHAT_DB_NAME = "chat.sqlite3"


def resolve_data_dir(env_name: str, default_name: str, legacy_name: str) -> Path:
    configured = os.getenv(env_name)
    if configured:
        return Path(configured)
    default_path = PROJECT_ROOT / default_name
    legacy_path = PROJECT_ROOT / legacy_name
    if default_path.exists():
        return default_path
    if legacy_path.exists():
        try:
            legacy_path.rename(default_path)
            return default_path
        except OSError:
            return legacy_path
    return default_path


def default_chat_memory_dir() -> Path:
    return resolve_data_dir("CHAT_MEMORY_DIR", DEFAULT_CHAT_MEMORY_DIR, LEGACY_CHAT_MEMORY_DIR)


def default_chat_db_path(memory_dir: Path | None = None) -> Path:
    configured = os.getenv("CHAT_DB_PATH")
    if configured:
        return Path(configured)
    root = memory_dir or default_chat_memory_dir()
    return root / DEFAULT_CHAT_DB_NAME


@dataclass(frozen=True)
class Settings:
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8001"))
    cors_origins: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    )
    cookie_max_age_seconds: int = 60 * 60 * 24 * 14
    cookie_secure: bool = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"


settings = Settings()
