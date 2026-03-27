from __future__ import annotations

import audioop
import io
import json
import urllib.error
import urllib.request
import wave
from pathlib import Path
from uuid import uuid4

import pyttsx3

from . import config


class TtsError(RuntimeError):
    """Raised when Teddy cannot synthesize speech."""


def synthesize_to_wav_bytes(text: str) -> bytes:
    try:
        return _synthesize_via_http(text)
    except TtsError:
        return _synthesize_via_pyttsx3(text)


def synthesize_to_wav(text: str) -> Path:
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    output_path = config.TMP_DIR / f"teddy-{uuid4().hex[:8]}.wav"
    output_path.write_bytes(synthesize_to_wav_bytes(text))
    return output_path


def prewarm_tts() -> None:
    """Warm the TTS path once so the first spoken line is faster."""
    _ = synthesize_to_wav_bytes("Ready.")


def get_cached_wake_ack_wav(force_refresh: bool = False) -> bytes:
    """Return cached WAV bytes for Teddy's fixed wake acknowledgement.

    The wake phrase is stable, so pre-baking it removes the cold TTS hit
    between wake-word detection and the first spoken acknowledgement.
    """
    config.WAKE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = config.WAKE_ACK_CACHE_PATH
    if not force_refresh and cache_path.exists() and cache_path.stat().st_size > 44:
        cached = cache_path.read_bytes()
        if _is_valid_wake_ack_wav(cached):
            return cached

    wav_bytes = synthesize_to_wav_bytes(config.WAKE_ACKNOWLEDGEMENT)
    cache_path.write_bytes(wav_bytes)
    return wav_bytes


def _synthesize_via_http(text: str) -> bytes:
    url = config.TTS_BASE_URL.rstrip("/") + config.TTS_PATH
    payload = json.dumps(
        {
            "model": config.TTS_MODEL,
            "voice": config.TTS_VOICE,
            "input": text,
            "response_format": "wav",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=config.TTS_TIMEOUT_SECONDS) as response:
            audio_bytes = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TtsError(f"Local TTS HTTP error: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TtsError("Local TTS endpoint is unavailable.") from exc

    if not audio_bytes.startswith(b"RIFF"):
        raise TtsError("Local TTS did not return WAV audio.")

    return audio_bytes


def _synthesize_via_pyttsx3(text: str) -> bytes:
    config.TMP_DIR.mkdir(parents=True, exist_ok=True)
    output_path = config.TMP_DIR / f"teddy-{uuid4().hex[:8]}.wav"
    try:
        engine = pyttsx3.init()
        _configure_pyttsx3_voice(engine)
        engine.save_to_file(text, str(output_path))
        engine.runAndWait()
        engine.stop()
    except Exception as exc:
        raise TtsError(f"Windows speech fallback failed: {exc}") from exc

    if not output_path.exists() or output_path.stat().st_size <= 44:
        raise TtsError("Windows speech fallback failed to generate a valid WAV file.")

    wav_bytes = output_path.read_bytes()
    output_path.unlink(missing_ok=True)
    return wav_bytes


def _configure_pyttsx3_voice(engine: pyttsx3.Engine) -> None:
    voices = engine.getProperty("voices")
    if config.SAPI_VOICE:
        target = config.SAPI_VOICE.strip().lower()
        for voice in voices:
            name = getattr(voice, "name", "")
            if name and name.strip().lower() == target:
                engine.setProperty("voice", voice.id)
                break

    engine.setProperty("rate", 155)


def _is_valid_wake_ack_wav(wav_bytes: bytes) -> bool:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            frame_rate = wav_file.getframerate()
            frame_count = wav_file.getnframes()
            sample_width = wav_file.getsampwidth()
            frames = wav_file.readframes(frame_count)
    except Exception:
        return False

    if frame_rate <= 0 or frame_count <= 0 or sample_width <= 0:
        return False

    duration_seconds = frame_count / float(frame_rate)
    if duration_seconds < 0.75:
        return False

    try:
        rms = audioop.rms(frames, sample_width) if frames else 0
    except Exception:
        return False
    return rms > 50
