from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.deps import require_user, runtime
from app.schemas import DeepResearchRequest, WebSearchRequest
from app.services.research import deep_research, run_web_search

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/search")
def search_web(request: Request, payload: WebSearchRequest) -> dict:
    require_user(request)
    return run_web_search(payload.query, payload.max_results)


@router.post("/deep")
def deep_research_route(request: Request, payload: DeepResearchRequest) -> dict:
    require_user(request)
    return deep_research(runtime(request).compress_llm, payload.query, payload.max_results, payload.max_pages)

