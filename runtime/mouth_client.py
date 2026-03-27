from __future__ import annotations

import audioop
import json
import math
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import config
from .lipsync import VisemeCue

_TRACE_LOCK = threading.Lock()
_TRACE_PATH: Path | None = None


def is_available() -> bool:
    request = urllib.request.Request(
        config.MOUTH_BASE_URL.rstrip("/") + "/health",
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status == 200
    except urllib.error.URLError:
        return False

class AudioMouthSync:
    def __init__(self) -> None:
        self._current_angle = config.MOUTH_CLOSED_ANGLE
        self._smoothed_ratio = 0.0
        self._last_target_ratio = 0.0
        self._last_sent_at = 0.0
        self._closed_sent = False
        self._phase = 0.0

    def on_audio_chunk(
        self,
        chunk: bytes,
        sample_width: int,
        sample_rate: int,
        channels: int,
    ) -> None:
        if not chunk:
            self.finish()
            return

        rms = audioop.rms(chunk, sample_width)
        peak = audioop.max(chunk, sample_width)
        target_ratio = _combine_audio_ratios(rms, peak, sample_width)
        if target_ratio > 0:
            change = abs(target_ratio - self._last_target_ratio)
            self._phase += 0.9
            chatter = math.sin(self._phase) * min(0.14, 0.04 + change * 0.35)
            target_ratio = min(1.0, max(0.0, target_ratio + chatter))
        self._last_target_ratio = target_ratio
        self._smoothed_ratio = (
            self._smoothed_ratio
            + (target_ratio - self._smoothed_ratio) * config.MOUTH_SMOOTHING
        )
        target_angle = _ratio_to_angle(self._smoothed_ratio)
        self._send_if_needed(target_angle)

    def finish(self) -> None:
        self._smoothed_ratio = 0.0
        self._send_if_needed(config.MOUTH_CLOSED_ANGLE, force=True)
        self._closed_sent = True

    def _send_if_needed(self, angle: int, force: bool = False) -> None:
        now = time.monotonic()
        if not force:
            if angle == self._current_angle:
                return
            if now - self._last_sent_at < config.MOUTH_COMMAND_INTERVAL_SECONDS:
                return

        _send_angle(angle, {"driver": "audio", "smoothed_ratio": round(self._smoothed_ratio, 4)})
        self._current_angle = angle
        self._last_sent_at = now
        self._closed_sent = angle == config.MOUTH_CLOSED_ANGLE


class VisemeMouthSync:
    def __init__(self, cues: list[VisemeCue]) -> None:
        self._cues = sorted(cues, key=lambda cue: cue.start)
        self._cue_index = 0
        self._elapsed_seconds = 0.0
        self._current_angle = config.MOUTH_CLOSED_ANGLE
        self._closed_sent = False
        self._send_if_needed(config.MOUTH_CLOSED_ANGLE, force=True)

    def on_audio_chunk(
        self,
        chunk: bytes,
        sample_width: int,
        sample_rate: int,
        channels: int,
    ) -> None:
        if not chunk:
            self.finish()
            return

        frame_count = _chunk_frame_count(chunk, sample_width, channels)
        self._advance_to_elapsed(self._elapsed_seconds)
        current_viseme = self._current_viseme()
        self._send_if_needed(
            _viseme_to_angle(current_viseme),
            viseme=current_viseme,
            elapsed_seconds=self._elapsed_seconds,
        )
        if sample_rate > 0 and frame_count > 0:
            self._elapsed_seconds += frame_count / float(sample_rate)

    def finish(self) -> None:
        self._send_if_needed(config.MOUTH_CLOSED_ANGLE, force=True)
        self._closed_sent = True

    def _advance_to_elapsed(self, elapsed_seconds: float) -> None:
        while (
            self._cue_index + 1 < len(self._cues)
            and self._cues[self._cue_index + 1].start <= elapsed_seconds
        ):
            self._cue_index += 1

    def _current_viseme(self) -> str:
        if not self._cues:
            return "X"
        return self._cues[self._cue_index].value

    def _send_if_needed(
        self,
        angle: int,
        force: bool = False,
        viseme: str | None = None,
        elapsed_seconds: float | None = None,
    ) -> None:
        if not force and angle == self._current_angle:
            return
        metadata = {"driver": "viseme"}
        if viseme is not None:
            metadata["viseme"] = viseme
        if elapsed_seconds is not None:
            metadata["elapsed_seconds"] = round(elapsed_seconds, 4)
        _send_angle(angle, metadata)
        self._current_angle = angle
        self._closed_sent = angle == config.MOUTH_CLOSED_ANGLE


def create_audio_sync() -> AudioMouthSync:
    return AudioMouthSync()


def create_sync(viseme_cues: list[VisemeCue] | None = None) -> AudioMouthSync | VisemeMouthSync:
    if config.MOUTH_SYNC_MODE == "viseme" and viseme_cues:
        return VisemeMouthSync(viseme_cues)
    return AudioMouthSync()


def _send_angle(angle: int, metadata: dict | None = None) -> dict | None:
    url = config.MOUTH_BASE_URL.rstrip("/") + "/mouth"
    payload = json.dumps({"angle": angle}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            if response.status != 200:
                raise RuntimeError(f"mouth bridge returned {response.status}")
            body = response.read().decode("utf-8", errors="replace")
            response_payload = json.loads(body) if body else {}
            _write_trace_event(
                {
                    "timestamp": time.time(),
                    "requested_angle": angle,
                    "response": response_payload,
                    **(metadata or {}),
                }
            )
            return response_payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        _write_trace_event(
            {
                "timestamp": time.time(),
                "requested_angle": angle,
                "error": f"http {exc.code}",
                "detail": detail,
                **(metadata or {}),
            }
        )
        raise RuntimeError(f"mouth bridge HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        _write_trace_event(
            {
                "timestamp": time.time(),
                "requested_angle": angle,
                "error": "bridge unavailable",
                **(metadata or {}),
            }
        )
        raise RuntimeError("mouth bridge is unavailable") from exc


def _rms_to_ratio(rms: int) -> float:
    if rms <= config.MOUTH_AUDIO_RMS_SILENCE:
        return 0.0
    if rms >= config.MOUTH_AUDIO_RMS_FULL:
        return 1.0

    normalized = (rms - config.MOUTH_AUDIO_RMS_SILENCE) / float(
        config.MOUTH_AUDIO_RMS_FULL - config.MOUTH_AUDIO_RMS_SILENCE
    )
    eased = normalized ** 0.75
    if eased > 0:
        eased = max(config.MOUTH_MIN_OPEN_RATIO, eased)
    return min(1.0, max(0.0, eased))


def _peak_to_ratio(peak: int, sample_width: int) -> float:
    if sample_width <= 0:
        return 0.0
    peak_full_scale = float((2 ** (sample_width * 8 - 1)) - 1)
    if peak_full_scale <= 0:
        return 0.0
    normalized = min(1.0, max(0.0, peak / peak_full_scale))
    if normalized <= 0.01:
        return 0.0
    return normalized ** 0.45


def _combine_audio_ratios(rms: int, peak: int, sample_width: int) -> float:
    rms_ratio = _rms_to_ratio(rms)
    peak_ratio = _peak_to_ratio(peak, sample_width)
    combined = max(rms_ratio, (rms_ratio * 0.55) + (peak_ratio * 0.65))
    return min(1.0, max(0.0, combined))


def _ratio_to_angle(ratio: float) -> int:
    span = config.MOUTH_OPEN_ANGLE - config.MOUTH_CLOSED_ANGLE
    target = config.MOUTH_CLOSED_ANGLE + span * ratio
    return int(round(target))


def _viseme_to_angle(viseme: str) -> int:
    value = viseme.strip().upper() or "X"
    if value in {"A", "X"}:
        return config.MOUTH_CLOSED_ANGLE
    if value in {"B", "G"}:
        return config.MOUTH_VISEME_NARROW_ANGLE
    if value in {"C", "F"}:
        return config.MOUTH_VISEME_MID_ANGLE
    if value in {"E", "H"}:
        return config.MOUTH_VISEME_LARGE_ANGLE
    if value == "D":
        return config.MOUTH_OPEN_ANGLE
    return config.MOUTH_CLOSED_ANGLE


def _chunk_frame_count(chunk: bytes, sample_width: int, channels: int) -> int:
    frame_bytes = sample_width * max(1, channels)
    if frame_bytes <= 0:
        return 0
    return len(chunk) // frame_bytes


def _write_trace_event(event: dict) -> None:
    if not config.MOUTH_TRACE:
        return
    trace_path = _get_trace_path()
    with _TRACE_LOCK:
        with trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")


def _get_trace_path() -> Path:
    global _TRACE_PATH
    if _TRACE_PATH is not None:
        return _TRACE_PATH
    config.MOUTH_TRACE_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    _TRACE_PATH = config.MOUTH_TRACE_DIR / f"mouth-trace-{timestamp}.jsonl"
    return _TRACE_PATH
