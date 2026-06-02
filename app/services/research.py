from __future__ import annotations

import re
from html import unescape
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

from app.core.engine import strip_thinking


def run_web_search(query: str, max_results: int) -> dict:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="Web search requires the ddgs package") from exc
    try:
        results = DDGS().text(query, max_results=max_results)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Web search failed: {exc}") from exc
    items = []
    seen_urls: set[str] = set()
    for item in results:
        url = str(item.get("href") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        items.append({"title": item.get("title") or url, "snippet": item.get("body") or "", "url": url, "domain": urlparse(url).netloc})
    return {"query": query, "results": items}


def fetch_webpage_text(url: str) -> str:
    try:
        response = httpx.get(url, follow_redirects=True, timeout=15.0, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except Exception:
        return ""
    if "text/html" not in response.headers.get("content-type", ""):
        return ""
    html_text = response.text
    html_text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html_text)
    html_text = re.sub(r"(?is)<style.*?>.*?</style>", " ", html_text)
    html_text = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", html_text)
    text = re.sub(r"(?is)<[^>]+>", " ", html_text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()[:12000]


def summarize_research(llm: Any, query: str, sources: list[dict]) -> str:
    if not sources:
        return "未抓取到可用网页内容。"
    blocks = []
    for index, item in enumerate(sources, start=1):
        blocks.append(f"[{index}] 标题: {item['title']}\nURL: {item['url']}\n摘要: {item.get('snippet', '')}\n正文片段: {item['content']}")
    prompt = (
        "你是 Deep Research 助手。请根据以下网页资料，用中文输出一份结构化研究摘要。\n"
        "要求：先给出 4-8 条要点结论，然后给出综合分析，最后列出引用来源 [序号] 标题 - URL。只使用提供资料，不要编造。\n\n"
        f"研究问题: {query}\n\n"
        + "\n\n".join(blocks)
    )
    try:
        response = llm.invoke(prompt)
        return strip_thinking(str(response.content))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Research summarization failed: {exc}") from exc


def deep_research(llm: Any, query: str, max_results: int, max_pages: int) -> dict:
    search_payload = run_web_search(query, max_results)
    search_results = list(search_payload.get("results", []))
    page_summaries = []
    for item in search_results[:max_pages]:
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        text = fetch_webpage_text(url)
        if not text:
            continue
        page_summaries.append(
            {
                "title": item.get("title") or url,
                "url": url,
                "snippet": item.get("snippet") or "",
                "content": text[:6000],
            }
        )
    summary = summarize_research(llm, query, page_summaries)
    return {"query": query, "summary": summary, "sources": page_summaries, "search_results": search_results}

