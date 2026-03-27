from __future__ import annotations

import audioop
import io
import json
import queue
import re
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from typing import Any

import sounddevice as sd
from vosk import KaldiRecognizer, Model

from . import config


class SpeechInputError(RuntimeError):
    """Raised when Teddy cannot listen on the configured microphone."""


_wake_model: Model | None = None


@dataclass
class SpeechResult:
    text: str
    heard_speech: bool
    capture_seconds: float = 0.0
    stt_seconds: float = 0.0
    total_seconds: float = 0.0
    empty_reason: str = ""
    fallback_used: bool = False


@dataclass
class WakeWordResult:
    phrase: str
    detect_seconds: float
    return_gap_seconds: float
    source: str
    trailing_text: str = ""


def listen_once(
    announce: bool = False,
    *,
    initial_timeout_seconds: float | None = None,
    max_listen_seconds: float | None = None,
    speech_end_seconds: float | None = None,
) -> SpeechResult:
    audio_queue: queue.Queue[bytes] = queue.Queue()

    def callback(indata: bytes, frames: int, time_info, status) -> None:
        if status:
            # Keep going unless opening the device fails outright.
            pass
        audio_queue.put(bytes(indata))

    device = config.AUDIO_INPUT_DEVICE
    if device is None or device < 0:
        raise SpeechInputError("No default input microphone is configured.")

    try:
        device_info = sd.query_devices(device)
    except Exception as exc:
        raise SpeechInputError(f"Could not open input device {device}.") from exc

    if announce:
        print(f"Listening on {device_info['name']}... speak now.")

    speech_detected = False
    silence_started: float | None = None
    started_at = time.monotonic()
    frames: list[bytes] = []
    preroll: list[bytes] = []
    soft_buffer: list[bytes] = []
    max_rms = 0
    soft_hot_chunks = 0
    fallback_used = False
    initial_timeout = (
        config.STT_INITIAL_TIMEOUT_SECONDS
        if initial_timeout_seconds is None
        else initial_timeout_seconds
    )
    max_listen = config.STT_MAX_LISTEN_SECONDS if max_listen_seconds is None else max_listen_seconds
    speech_end = config.STT_SPEECH_END_SECONDS if speech_end_seconds is None else speech_end_seconds

    try:
        with sd.RawInputStream(
            samplerate=config.STT_SAMPLE_RATE,
            blocksize=config.STT_BLOCK_SIZE,
            device=device,
            dtype="int16",
            channels=1,
            callback=callback,
        ):
            while True:
                elapsed = time.monotonic() - started_at
                if elapsed > max_listen:
                    break

                try:
                    chunk = audio_queue.get(timeout=0.25)
                except queue.Empty:
                    chunk = b""

                if chunk:
                    rms = audioop.rms(chunk, 2)
                    max_rms = max(max_rms, rms)
                    if not speech_detected:
                        soft_buffer.append(chunk)
                        if len(soft_buffer) > config.STT_SOFT_BUFFER_CHUNKS:
                            soft_buffer.pop(0)
                        preroll.append(chunk)
                        if len(preroll) > config.STT_PREROLL_CHUNKS:
                            preroll.pop(0)
                        if rms >= config.STT_SOFT_RMS_THRESHOLD:
                            soft_hot_chunks += 1

                        if rms >= config.STT_RMS_THRESHOLD:
                            speech_detected = True
                            frames.extend(preroll)
                            silence_started = None
                    else:
                        frames.append(chunk)
                        if rms >= config.STT_RMS_THRESHOLD:
                            silence_started = None
                        else:
                            if silence_started is None:
                                silence_started = time.monotonic()
                            elif time.monotonic() - silence_started >= speech_end:
                                break
                elif speech_detected:
                    if silence_started is None:
                        silence_started = time.monotonic()
                    elif time.monotonic() - silence_started >= speech_end:
                        if silence_started is None:
                            silence_started = time.monotonic()
                        break

                if not speech_detected and elapsed >= initial_timeout:
                    break
    except Exception as exc:
        raise SpeechInputError(f"Microphone capture failed: {exc}") from exc

    capture_elapsed = time.monotonic() - started_at
    if not frames:
        if (
            soft_buffer
            and max_rms >= config.STT_SOFT_RMS_THRESHOLD
            and soft_hot_chunks >= config.STT_SOFT_MIN_HOT_CHUNKS
        ):
            frames = list(soft_buffer)
            speech_detected = True
            fallback_used = True
        else:
            return SpeechResult(
                text="",
                heard_speech=False,
                capture_seconds=capture_elapsed,
                stt_seconds=0.0,
                total_seconds=capture_elapsed,
                empty_reason="timeout",
                fallback_used=False,
            )

    wav_bytes = frames_to_wav_bytes(frames)
    stt_started = time.monotonic()
    payload = transcribe_wav_bytes(wav_bytes)
    stt_elapsed = time.monotonic() - stt_started
    text = str(payload.get("text", "")).strip()
    empty_reason = "" if text else "empty_transcript"
    heard_speech = speech_detected
    if fallback_used and _is_low_value_fallback_transcript(text):
        text = ""
        empty_reason = "low_value_fallback"
        heard_speech = False
    return SpeechResult(
        text=text,
        heard_speech=heard_speech,
        capture_seconds=capture_elapsed,
        stt_seconds=stt_elapsed,
        total_seconds=capture_elapsed + stt_elapsed,
        empty_reason=empty_reason,
        fallback_used=fallback_used,
    )


def wait_for_wake_word() -> str:
    return wait_for_wake_word_result().phrase


def wait_for_wake_word_result() -> WakeWordResult:
    audio_queue: queue.Queue[bytes] = queue.Queue()
    started_at = time.perf_counter()

    def callback(indata: bytes, frames: int, time_info, status) -> None:
        if status:
            pass
        audio_queue.put(bytes(indata))

    device = config.AUDIO_INPUT_DEVICE
    if device is None or device < 0:
        raise SpeechInputError("No default input microphone is configured.")

    try:
        sd.query_devices(device)
    except Exception as exc:
        raise SpeechInputError(f"Could not open input device {device}.") from exc

    recognizer = KaldiRecognizer(
        _get_wake_model(),
        config.STT_SAMPLE_RATE,
        json.dumps(list(config.WAKE_PHRASES)),
    )
    recognizer.SetWords(False)

    try:
        with sd.RawInputStream(
            samplerate=config.STT_SAMPLE_RATE,
            blocksize=config.WAKE_BLOCK_SIZE,
            device=device,
            dtype="int16",
            channels=1,
            callback=callback,
        ):
            while True:
                try:
                    chunk = audio_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if not chunk:
                    continue

                if not recognizer.AcceptWaveform(chunk):
                    partial_payload = json.loads(recognizer.PartialResult())
                    partial_text = str(partial_payload.get("partial", ""))
                    matched = match_wake_phrase(partial_text)
                    if matched is not None:
                        phrase, trailing_text = matched
                        matched_at = time.perf_counter()
                        return WakeWordResult(
                            phrase=phrase,
                            detect_seconds=matched_at - started_at,
                            return_gap_seconds=time.perf_counter() - matched_at,
                            source="partial",
                            trailing_text=trailing_text,
                        )
                    continue

                payload = json.loads(recognizer.Result())
                text = str(payload.get("text", ""))
                matched = match_wake_phrase(text)
                if matched is not None:
                    phrase, trailing_text = matched
                    matched_at = time.perf_counter()
                    return WakeWordResult(
                        phrase=phrase,
                        detect_seconds=matched_at - started_at,
                        return_gap_seconds=time.perf_counter() - matched_at,
                        source="final",
                        trailing_text=trailing_text,
                    )
    except Exception as exc:
        raise SpeechInputError(f"Wake-word detection failed: {exc}") from exc


def frames_to_wav_bytes(frames: list[bytes]) -> bytes:
    with io.BytesIO() as wav_buffer:
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(config.STT_SAMPLE_RATE)
            wav_file.writeframes(b"".join(frames))
        return wav_buffer.getvalue()


def transcribe_wav_bytes(wav_bytes: bytes) -> dict[str, Any]:
    request = urllib.request.Request(
        config.STT_BASE_URL.rstrip("/") + config.STT_PATH,
        data=wav_bytes,
        headers={"Content-Type": "audio/wav"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SpeechInputError(f"STT HTTP error: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SpeechInputError("STT service is unavailable.") from exc


def load_model() -> bool:
    return config.VOSK_MODEL_PATH.exists()


def prewarm_wake_model() -> None:
    _get_wake_model()


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def extract_wake_text(text: str) -> str | None:
    candidate = text.strip()
    if not candidate:
        return None

    for phrase in sorted(config.WAKE_PHRASES, key=len, reverse=True):
        pattern = re.compile(rf"^\s*{re.escape(phrase)}(?:[\s,!.?;:-]+|$)(.*)$", re.I)
        match = pattern.match(candidate)
        if not match:
            continue
        return match.group(1).strip()

    return None


def match_wake_phrase(text: str) -> tuple[str, str] | None:
    candidate = " ".join(text.strip().split())
    if not candidate:
        return None

    for phrase in sorted(config.WAKE_PHRASES, key=len, reverse=True):
        pattern = re.compile(rf"^\s*{re.escape(phrase)}(?:[\s,!.?;:-]+|$)(.*)$", re.I)
        match = pattern.match(candidate)
        if not match:
            continue
        trailing_text = " ".join(match.group(1).strip().split())
        return (phrase, trailing_text)

    normalized = normalize_text(candidate)
    if normalized in config.WAKE_PHRASES:
        return (normalized, "")
    return None


def _is_low_value_fallback_transcript(text: str) -> bool:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return True

    if not re.search(r"[a-zA-Z0-9]", cleaned):
        return True

    words = re.findall(r"[a-zA-Z0-9']+", cleaned.lower())
    if not words:
        return True

    if len(set(words)) == 1 and len(words) >= 2 and len(words[0]) <= 3:
        return True

    return False


def _get_wake_model() -> Model:
    global _wake_model
    if _wake_model is None:
        if not config.VOSK_MODEL_PATH.exists():
            raise SpeechInputError(
                f"Wake-word model not found at {config.VOSK_MODEL_PATH}."
            )
        _wake_model = Model(str(config.VOSK_MODEL_PATH))
    return _wake_model
