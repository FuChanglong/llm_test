from __future__ import annotations

import os
import re
from io import BytesIO

from fastapi import HTTPException, Response

async def synthesize_speech(text: str, *, voice: str | None = None, rate: float | None = None) -> Response:
    try:
        import edge_tts
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="edge-tts package is required for speech synthesis") from exc

    selected_voice = voice.strip() if voice else os.getenv("EDGE_TTS_VOICE", "zh-CN-XiaoxiaoNeural")
    speaking_rate = edge_tts_rate(rate) if rate is not None else os.getenv("EDGE_TTS_RATE", "+0%")
    volume = os.getenv("EDGE_TTS_VOLUME", "+0%")
    pitch = os.getenv("EDGE_TTS_PITCH", "+0Hz")
    plain_text = normalize_tts_text(text)

    audio = BytesIO()
    communicate = edge_tts.Communicate(text=plain_text, voice=selected_voice, rate=speaking_rate, volume=volume, pitch=pitch)
    try:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio.write(chunk["data"])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Speech synthesis failed: {exc}") from exc
    return Response(content=audio.getvalue(), media_type="audio/mpeg")


def normalize_tts_text(text: str) -> str:
    content = str(text or "").strip()
    if not content:
        return ""

    content = re.sub(r"```[\s\S]*?```", _replace_code_block, content)
    content = re.sub(r"`([^`]+)`", r"\1", content)
    content = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", content)
    content = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", content)
    content = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", content)
    content = re.sub(r"(?m)^\s*>\s?", "", content)
    content = re.sub(r"(?m)^\s*[-*+]\s+", "", content)
    content = re.sub(r"(?m)^\s*\d+\.\s+", "", content)
    content = re.sub(r"[*_~]+", "", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    content = re.sub(r"[ \t]+", " ", content)
    return content.strip()


def _replace_code_block(match: re.Match[str]) -> str:
    block = match.group(0)
    lines = [line for line in block.splitlines() if line and not line.startswith("```")]
    if not lines:
        return ""
    return "\n".join(lines)


def edge_tts_rate(rate: float) -> str:
    normalized = max(0.5, min(2.0, float(rate)))
    percentage = int(round((normalized - 1.0) * 100))
    return f"{percentage:+d}%"
