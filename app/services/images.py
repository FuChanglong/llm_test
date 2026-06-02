from __future__ import annotations

import base64
import mimetypes
import os
from typing import Any

import httpx
from fastapi import HTTPException


DEFAULT_OMNI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_OMNI_MODEL = "qwen3.5-omni-plus-2026-03-15"


def _image_base_url() -> str | None:
    return os.getenv("IMAGE_BASE_URL") or os.getenv("VLLM_ALI_BASE_URL") or os.getenv("VLLM_BASE_URL")


def _image_api_key() -> str:
    return os.getenv("IMAGE_API_KEY") or os.getenv("VLLM_ALI_API_KEY") or os.getenv("VLLM_API_KEY", "EMPTY")


def _image_model() -> str:
    return os.getenv("IMAGE_MODEL") or os.getenv("VLLM_IMAGE_MODEL", "").strip()


def _dashscope_image_base_url() -> str:
    base_url = (_image_base_url() or DEFAULT_OMNI_BASE_URL).rstrip("/")
    if base_url.endswith("/compatible-mode/v1"):
        return f"{base_url[:-len('/compatible-mode/v1')]}/api/v1"
    return base_url


def _omni_base_url() -> str:
    return os.getenv("OMNI_BASE_URL") or os.getenv("VLLM_ALI_BASE_URL") or DEFAULT_OMNI_BASE_URL


def _omni_api_key() -> str:
    return os.getenv("OMNI_API_KEY") or os.getenv("VLLM_ALI_API_KEY", "").strip()


def _omni_model() -> str:
    return os.getenv("OMNI_MODEL") or os.getenv("VLLM_ALI_MODEL") or DEFAULT_OMNI_MODEL


def build_image_client():
    api_key = _image_api_key()
    if not api_key or api_key == "EMPTY":
        raise HTTPException(status_code=400, detail="IMAGE_API_KEY or VLLM_ALI_API_KEY is not configured")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="openai package is required for image APIs") from exc
    return OpenAI(
        base_url=_image_base_url(),
        api_key=api_key,
        timeout=float(os.getenv("IMAGE_TIMEOUT_SECONDS", os.getenv("VLLM_TIMEOUT_SECONDS", "120"))),
    )


def build_omni_client():
    api_key = _omni_api_key()
    if not api_key or api_key == "EMPTY":
        raise HTTPException(status_code=400, detail="OMNI_API_KEY is not configured")
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="openai package is required for multimodal APIs") from exc
    return OpenAI(
        base_url=_omni_base_url(),
        api_key=api_key,
        timeout=float(os.getenv("OMNI_TIMEOUT_SECONDS", os.getenv("VLLM_TIMEOUT_SECONDS", "120"))),
    )


def openai_generate_image(prompt: str, size: str) -> dict:
    model = _image_model()
    if not model:
        raise HTTPException(
            status_code=400,
            detail="IMAGE_MODEL or VLLM_IMAGE_MODEL is not configured for image generation",
        )
    return dashscope_generate_image(prompt=prompt, size=size, model=model)


def openai_edit_image(prompt: str, size: str, filename: str, content: bytes) -> dict:
    model = os.getenv("IMAGE_EDIT_MODEL") or _image_model()
    if not model:
        raise HTTPException(
            status_code=400,
            detail="IMAGE_EDIT_MODEL, IMAGE_MODEL or VLLM_IMAGE_MODEL is not configured for image editing",
        )
    mime_type = mimetypes.guess_type(filename)[0] or "image/png"
    image_data_url = f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"
    return dashscope_generate_image(prompt=prompt, size=size, model=model, image_inputs=[image_data_url])


def openai_analyze_image(prompt: str, filename: str, content: bytes) -> dict:
    client = build_omni_client()
    model = _omni_model()
    mime_type = mimetypes.guess_type(filename)[0] or "image/png"
    data_url = f"data:{mime_type};base64,{base64.b64encode(content).decode('ascii')}"
    try:
        result = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            temperature=float(os.getenv("OMNI_TEMPERATURE", "0.2")),
            max_tokens=int(os.getenv("OMNI_MAX_TOKENS", "900")),
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Image analysis failed: {exc}") from exc
    answer = ""
    if getattr(result, "choices", None):
        answer = str(getattr(result.choices[0].message, "content", "") or "").strip()
    return {"prompt": prompt, "model": model, "filename": filename, "answer": answer}


def normalize_image_result(result: Any, prompt: str, model: str) -> dict:
    images = []
    for item in getattr(result, "data", []) or []:
        url = getattr(item, "url", None)
        b64_json = getattr(item, "b64_json", None)
        if b64_json:
            images.append({"kind": "base64", "data_url": f"data:image/png;base64,{b64_json}"})
        elif url:
            images.append({"kind": "url", "url": url})
    return {"prompt": prompt, "model": model, "images": images}


def dashscope_generate_image(
    *,
    prompt: str,
    size: str,
    model: str,
    image_inputs: list[str] | None = None,
) -> dict:
    api_key = _image_api_key()
    if not api_key or api_key == "EMPTY":
        raise HTTPException(status_code=400, detail="IMAGE_API_KEY or VLLM_ALI_API_KEY is not configured")

    content: list[dict[str, str]] = []
    for image in image_inputs or []:
        content.append({"image": image})
    content.append({"text": prompt})

    payload = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": content,
                }
            ]
        },
        "parameters": {
            "size": normalize_dashscope_size(size),
            "watermark": False,
            "prompt_extend": True,
        },
    }
    if image_inputs:
        payload["parameters"]["negative_prompt"] = " "
    timeout = float(os.getenv("IMAGE_TIMEOUT_SECONDS", os.getenv("VLLM_TIMEOUT_SECONDS", "120")))
    try:
        response = httpx.post(
            f"{_dashscope_image_base_url()}/services/aigc/multimodal-generation/generation",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = extract_dashscope_error(exc.response)
        operation = "Image edit" if image_inputs else "Image generation"
        raise HTTPException(status_code=502, detail=f"{operation} failed: {detail}") from exc
    except Exception as exc:
        operation = "Image edit" if image_inputs else "Image generation"
        raise HTTPException(status_code=502, detail=f"{operation} failed: {exc}") from exc

    data = response.json()
    image_urls = extract_dashscope_image_urls(data)
    return {
        "prompt": prompt,
        "model": model,
        "images": [{"kind": "url", "url": url} for url in image_urls],
    }


def normalize_dashscope_size(size: str) -> str:
    return size.strip().lower().replace("x", "*")


def extract_dashscope_image_urls(payload: dict[str, Any]) -> list[str]:
    output = payload.get("output") if isinstance(payload, dict) else None
    choices = output.get("choices") if isinstance(output, dict) else None
    if not isinstance(choices, list):
        return []
    image_urls: list[str] = []
    for choice in choices:
        message = choice.get("message") if isinstance(choice, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for item in content:
            image_url = item.get("image") if isinstance(item, dict) else None
            if image_url:
                image_urls.append(str(image_url))
    return image_urls


def extract_dashscope_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text or f"HTTP {response.status_code}"
    code = payload.get("code")
    message = payload.get("message")
    if code and message:
        return f"{code}: {message}"
    if message:
        return str(message)
    return response.text or f"HTTP {response.status_code}"
