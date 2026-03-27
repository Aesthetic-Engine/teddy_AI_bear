from __future__ import annotations

import audioop
import io
import wave
from typing import Any

import ctranslate2
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from faster_whisper import WhisperModel

from . import config


app = FastAPI(title="Teddy Faster-Whisper STT", version="1.0")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "model": config.FASTER_WHISPER_MODEL,
        "device": _resolve_device(),
        "compute_type": _resolve_compute_type(),
    }


@app.post("/v1/transcribe")
async def transcribe(request: Request) -> dict[str, Any]:
    audio_bytes = await request.body()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="audio body is required")

    try:
        audio = _wav_bytes_to_float32(audio_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid wav data: {exc}") from exc

    segments, info = _model.transcribe(
        audio,
        language=config.FASTER_WHISPER_LANGUAGE,
        beam_size=config.FASTER_WHISPER_BEAM_SIZE,
        vad_filter=False,
    )
    text = " ".join(segment.text.strip() for segment in segments if segment.text.strip()).strip()
    return {
        "text": text,
        "language": getattr(info, "language", config.FASTER_WHISPER_LANGUAGE),
        "duration": getattr(info, "duration", None),
    }


def _wav_bytes_to_float32(audio_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(audio_bytes), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width != 2:
        raise ValueError(f"unsupported sample width {sample_width}")
    if channels == 2:
        frames = audioop.tomono(frames, 2, 0.5, 0.5)
        channels = 1
    if channels != 1:
        raise ValueError(f"unsupported channel count {channels}")
    if frame_rate != config.STT_SAMPLE_RATE:
        frames, _ = audioop.ratecv(
            frames,
            sample_width,
            channels,
            frame_rate,
            config.STT_SAMPLE_RATE,
            None,
        )

    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def _resolve_device() -> str:
    if config.FASTER_WHISPER_DEVICE != "auto":
        return config.FASTER_WHISPER_DEVICE

    try:
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _resolve_compute_type() -> str:
    if config.FASTER_WHISPER_COMPUTE_TYPE != "auto":
        return config.FASTER_WHISPER_COMPUTE_TYPE
    return "int8_float16" if _resolve_device() == "cuda" else "int8"


_model = WhisperModel(
    config.FASTER_WHISPER_MODEL,
    device=_resolve_device(),
    compute_type=_resolve_compute_type(),
)
