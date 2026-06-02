from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    email: str | None = Field(default=None, min_length=5, max_length=254)
    password: str = Field(min_length=6, max_length=200)
    display_name: str | None = Field(default=None, max_length=80)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=200)


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WorkspaceJoinRequest(BaseModel):
    invite_code: str | None = Field(default=None, min_length=1, max_length=32)


class WorkspaceInviteJoinRequest(BaseModel):
    invite_code: str = Field(min_length=1, max_length=32)


class SessionCreateRequest(BaseModel):
    title: str | None = None


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=4000)
    attachment_ids: list[str] = Field(default_factory=list)


class ChatEditRequest(ChatRequest):
    message_id: str


class ChatRegenerateRequest(BaseModel):
    session_id: str
    message_id: str


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    enabled: bool = True


class MemoryUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=2000)
    enabled: bool | None = None


class CanvasUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    content: str | None = Field(default=None, max_length=200000)


class CanvasTransformRequest(BaseModel):
    content: str = Field(min_length=1, max_length=200000)
    instruction: str = Field(min_length=1, max_length=1000)
    mode: str = Field(default="rewrite", pattern="^(polish|summarize|rewrite|expand)$")


class AnalysisRequest(BaseModel):
    attachment_id: str


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=10)


class DeepResearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=6, ge=1, le=10)
    max_pages: int = Field(default=3, ge=1, le=5)


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    size: str = Field(default="1024x1024", pattern=r"^\d+x\d+$")


class SpeechSynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    voice: str | None = Field(default=None, max_length=120)
    rate: float | None = Field(default=None, ge=0.5, le=2.0)


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=6, ge=1, le=20)


class RagDeleteRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=100)
