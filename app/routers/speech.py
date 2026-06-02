from __future__ import annotations

import inspect

from fastapi import APIRouter, Request, Response

from app.core.deps import require_user
from app.schemas import SpeechSynthesisRequest
from app.services.speech import synthesize_speech

router = APIRouter(prefix="/speech", tags=["speech"])


@router.post("/synthesize")
async def speech_synthesize(request: Request, payload: SpeechSynthesisRequest) -> Response:
    require_user(request)
    parameters = inspect.signature(synthesize_speech).parameters
    if "voice" not in parameters and "rate" not in parameters:
        return await synthesize_speech(payload.text)
    return await synthesize_speech(payload.text, voice=payload.voice, rate=payload.rate)
