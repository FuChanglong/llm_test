from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.core.deps import require_user
from app.schemas import ImageGenerateRequest
from app.services.files import safe_image_filename
from app.services.images import openai_analyze_image, openai_edit_image, openai_generate_image

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/generate")
def generate_image(request: Request, payload: ImageGenerateRequest) -> dict:
    require_user(request)
    return openai_generate_image(payload.prompt, payload.size)


@router.post("/edit")
async def edit_image(request: Request, prompt: str = Form(...), size: str = Form(default="1024x1024"), image: UploadFile = File(...)) -> dict:
    require_user(request)
    filename = safe_image_filename(image.filename or "")
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    return openai_edit_image(prompt, size, filename, content)


@router.post("/analyze")
async def analyze_image(request: Request, prompt: str = Form(...), image: UploadFile = File(...)) -> dict:
    require_user(request)
    filename = safe_image_filename(image.filename or "")
    content = await image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    return openai_analyze_image(prompt, filename, content)
