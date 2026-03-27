from __future__ import annotations

import audioop
import io
import threading
import time
import wave
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import sounddevice as sd

from . import config


class AudioPlaybackError(RuntimeError):
    """Raised when Teddy cannot play audio on the configured device."""


class _PersistentOutputManager:
    """Keeps a RawOutputStream warm for the wake-ack fast path."""

    def __init__(self) -> None:
        self._stream: sd.RawOutputStream | None = None
        self._device_index: int | None = None
        self._sample_rate: int | None = None
        self._channels: int | None = None
        self._dtype: str | None = None
        self._silence_chunk: bytes = b""
        self._lock = threading.RLock()
        self._active_playback = False
        self._keepalive_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def prewarm_for_wav_bytes(self, wav_bytes: bytes) -> None:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            dtype, _, _ = _resolve_dtype(sample_width)
            self._ensure_stream(sample_rate, channels, dtype)

    def play_wav_bytes(
        self,
        wav_bytes: bytes,
        chunk_callback: Callable[[bytes, int, int, int], None] | None = None,
    ) -> tuple[float, float]:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
            return self._play_wav_handle(wav_file, chunk_callback=chunk_callback)

    def _play_wav_handle(
        self,
        wav_file: wave.Wave_read,
        chunk_callback: Callable[[bytes, int, int, int], None] | None = None,
    ) -> tuple[float, float]:
        duration = _wav_duration_from_handle(wav_file)
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        dtype, callback_width, convert_24 = _resolve_dtype(sample_width)

        play_started = time.perf_counter()
        with self._lock:
            self._active_playback = True
            self._ensure_stream(sample_rate, channels, dtype)
            assert self._stream is not None

            first_write_at: float | None = None
            try:
                while True:
                    chunk = wav_file.readframes(
                        config.MOUTH_AUDIO_CHUNK_FRAMES if chunk_callback else 4096
                    )
                    if not chunk:
                        break
                    callback_chunk = chunk
                    output_chunk = chunk
                    if convert_24:
                        output_chunk = audioop.lin2lin(chunk, 3, 4)
                        callback_chunk = output_chunk
                    if chunk_callback is not None:
                        chunk_callback(callback_chunk, callback_width, sample_rate, channels)
                    if first_write_at is None:
                        first_write_at = time.perf_counter()
                    self._stream.write(output_chunk)
            finally:
                self._active_playback = False

        play_start_delay = (first_write_at or time.perf_counter()) - play_started
        return duration, play_start_delay

    def _ensure_stream(self, sample_rate: int, channels: int, dtype: str) -> None:
        device_index = resolve_output_device()
        needs_reopen = (
            self._stream is None
            or self._device_index != device_index
            or self._sample_rate != sample_rate
            or self._channels != channels
            or self._dtype != dtype
        )
        if not needs_reopen:
            return

        self.close()
        self._stream = sd.RawOutputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype=dtype,
            device=device_index,
        )
        self._stream.start()
        self._device_index = device_index
        self._sample_rate = sample_rate
        self._channels = channels
        self._dtype = dtype
        bytes_per_sample = int(dtype.replace("int", "")) // 8
        frames = max(1, int(sample_rate * config.WAKE_KEEPALIVE_INTERVAL_SECONDS))
        self._silence_chunk = b"\x00" * frames * channels * bytes_per_sample
        self._start_keepalive_thread()

    def _start_keepalive_thread(self) -> None:
        if self._keepalive_thread is not None and self._keepalive_thread.is_alive():
            return
        self._stop_event.clear()
        self._keepalive_thread = threading.Thread(
            target=self._keepalive_loop,
            daemon=True,
            name="teddy-wake-output-keepalive",
        )
        self._keepalive_thread.start()

    def _keepalive_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(config.WAKE_KEEPALIVE_INTERVAL_SECONDS)
            if not config.WAKE_OUTPUT_KEEPALIVE:
                continue
            if self._active_playback or self._stream is None or not self._silence_chunk:
                continue
            with self._lock:
                if self._active_playback or self._stream is None:
                    continue
                try:
                    self._stream.write(self._silence_chunk)
                except Exception:
                    # Wake keepalive is best-effort. If it fails, reopen later on demand.
                    self.close()

    def close(self) -> None:
        self._stop_event.set()
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:
                pass
            try:
                self._stream.close()
            except Exception:
                pass
        self._stream = None
        self._device_index = None
        self._sample_rate = None
        self._channels = None
        self._dtype = None
        self._silence_chunk = b""


_persistent_output_manager = _PersistentOutputManager()


def get_wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        return _wav_duration_from_handle(wav_file)


def play_wav(
    path: Path,
    chunk_callback: Callable[[bytes, int, int, int], None] | None = None,
) -> float:
    with wave.open(str(path), "rb") as wav_file:
        return _play_wav_handle(wav_file, chunk_callback=chunk_callback)


def get_wav_duration_bytes(wav_bytes: bytes) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        return _wav_duration_from_handle(wav_file)


def play_wav_bytes(
    wav_bytes: bytes,
    chunk_callback: Callable[[bytes, int, int, int], None] | None = None,
) -> float:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        return _play_wav_handle(wav_file, chunk_callback=chunk_callback)


def prewarm_persistent_output_for_wav_bytes(wav_bytes: bytes) -> None:
    """Open a long-lived output stream matching the wake-ack WAV format."""
    _persistent_output_manager.prewarm_for_wav_bytes(wav_bytes)


def play_wav_bytes_persistent(
    wav_bytes: bytes,
    chunk_callback: Callable[[bytes, int, int, int], None] | None = None,
) -> tuple[float, float]:
    """Play bytes through the long-lived wake-ack output stream.

    Returns (duration_seconds, play_start_delay_seconds).
    """
    return _persistent_output_manager.play_wav_bytes(wav_bytes, chunk_callback=chunk_callback)


@lru_cache(maxsize=1)
def resolve_output_device() -> int:
    target = config.AUDIO_OUTPUT_DEVICE.strip().lower()
    devices = sd.query_devices()

    exact_match = None
    partial_match = None
    for index, device in enumerate(devices):
        if device["max_output_channels"] <= 0:
            continue

        name = str(device["name"])
        lowered = name.lower()
        if lowered == target:
            exact_match = index
            break
        if target and target in lowered and partial_match is None:
            partial_match = index

    if exact_match is not None:
        return exact_match
    if partial_match is not None:
        return partial_match

    raise AudioPlaybackError(
        f"Configured audio output device not found: '{config.AUDIO_OUTPUT_DEVICE}'"
    )


def _wav_duration_from_handle(wav_file: wave.Wave_read) -> float:
    frames = wav_file.getnframes()
    frame_rate = wav_file.getframerate()
    if frame_rate <= 0:
        return 0.0
    return frames / float(frame_rate)


def _play_wav_handle(
    wav_file: wave.Wave_read,
    chunk_callback: Callable[[bytes, int, int, int], None] | None = None,
) -> float:
    duration = _wav_duration_from_handle(wav_file)
    device_index = resolve_output_device()
    sample_rate = wav_file.getframerate()
    channels = wav_file.getnchannels()
    sample_width = wav_file.getsampwidth()
    dtype, callback_width, convert_24 = _resolve_dtype(sample_width)
    with sd.RawOutputStream(
        samplerate=sample_rate,
        channels=channels,
        dtype=dtype,
        device=device_index,
    ) as stream:
        while True:
            chunk = wav_file.readframes(config.MOUTH_AUDIO_CHUNK_FRAMES if chunk_callback else 4096)
            if not chunk:
                break
            callback_chunk = chunk
            output_chunk = chunk
            if convert_24:
                output_chunk = audioop.lin2lin(chunk, 3, 4)
                callback_chunk = output_chunk
            if chunk_callback is not None:
                chunk_callback(callback_chunk, callback_width, sample_rate, channels)
            stream.write(output_chunk)
    return duration


def _resolve_dtype(sample_width: int) -> tuple[str, int, bool]:
    if sample_width not in (1, 2, 3, 4):
        raise AudioPlaybackError(f"Unsupported WAV sample width: {sample_width}")
    if sample_width == 3:
        return "int32", 4, True
    return f"int{sample_width * 8}", sample_width, False
