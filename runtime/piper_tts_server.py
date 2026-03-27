from __future__ import annotations

import json
import subprocess
import wave
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import config


class SpeechRequest(BaseModel):
    input: str
    model: str | None = None
    voice: str | None = None
    response_format: str | None = "wav"


app = FastAPI(title="Teddy Piper TTS", version="1.0")

_model_config = json.loads(config.PIPER_CONFIG.read_text(encoding="utf-8"))
_sample_rate = int(_model_config["audio"]["sample_rate"])


@app.get("/health")
def health() -> dict:
    return {
        "ok": True,
        "model": str(config.PIPER_MODEL),
        "sample_rate": _sample_rate,
    }


@app.post("/v1/audio/speech")
def synthesize(request: SpeechRequest) -> Response:
    text = request.input.strip()
    if not text:
        raise HTTPException(status_code=400, detail="input is required")

    command = [
        str(config.PIPER_EXE),
        "--model",
        str(config.PIPER_MODEL),
        "--config",
        str(config.PIPER_CONFIG),
        "--espeak_data",
        str(config.PIPER_ESPEAK_DATA),
        "--output_raw",
        "--quiet",
    ]

    try:
        result = subprocess.run(
            command,
            input=(text + "\n").encode("utf-8"),
            capture_output=True,
            timeout=30,
            check=False,
            cwd=str(config.PIPER_ROOT),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="piper synthesis timed out") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="piper executable not found") from exc

    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip() or "piper failed"
        raise HTTPException(status_code=500, detail=detail)

    if not result.stdout:
        raise HTTPException(status_code=500, detail="piper returned no audio")

    wav_bytes = pcm_to_wav(result.stdout, sample_rate=_sample_rate)
    return Response(content=wav_bytes, media_type="audio/wav")


def pcm_to_wav(pcm_bytes: bytes, sample_rate: int) -> bytes:
    with BytesIO() as wav_buffer:
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        return wav_buffer.getvalue()
