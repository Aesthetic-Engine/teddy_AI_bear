from __future__ import annotations

import os
from pathlib import Path

import sounddevice as sd

RUNTIME_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = RUNTIME_ROOT / "workspace"
PROMPTS_DIR = RUNTIME_ROOT / "prompts"
MEMORY_DIR = WORKSPACE_DIR / "memory"
SESSION_MEMORY_DIR = MEMORY_DIR / "sessions"
TMP_DIR = RUNTIME_ROOT / "tmp"
TOOLS_DIR = RUNTIME_ROOT / "tools"
MEMORY_DB_PATH = RUNTIME_ROOT / "memory" / "teddy_memory.sqlite3"
WAKE_CACHE_DIR = TMP_DIR / "wake-cache"
WAKE_ACK_CACHE_PATH = WAKE_CACHE_DIR / "wake-ack.wav"

OPENAI_BASE_URL = os.environ.get("TEDDY_OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("TEDDY_OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_REASONING_EFFORT = os.environ.get("TEDDY_OPENAI_REASONING_EFFORT", "low")
OPENAI_MAX_OUTPUT_TOKENS = int(os.environ.get("TEDDY_OPENAI_MAX_OUTPUT_TOKENS", "256"))
OPENAI_TIMEOUT_SECONDS = int(os.environ.get("TEDDY_OPENAI_TIMEOUT_SECONDS", "120"))
ENABLE_MOUTH = os.environ.get("TEDDY_ENABLE_MOUTH", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
AUDIO_OUTPUT_DEVICE = os.environ.get(
    "TEDDY_AUDIO_OUTPUT_DEVICE",
    "Speakers (Realtek(R) Audio)",
)
DEFAULT_INPUT_DEVICE = sd.default.device[0] if sd.default.device else None
AUDIO_INPUT_DEVICE = int(
    os.environ.get(
        "TEDDY_AUDIO_INPUT_DEVICE",
        str(DEFAULT_INPUT_DEVICE if DEFAULT_INPUT_DEVICE is not None else -1),
    )
)

TTS_BASE_URL = os.environ.get("TEDDY_TTS_URL", "http://127.0.0.1:5000")
TTS_PATH = os.environ.get("TEDDY_TTS_PATH", "/v1/audio/speech")
TTS_MODEL = os.environ.get("TEDDY_TTS_MODEL", "fallout4-dlc01robotcompanionmaledefault")
TTS_VOICE = os.environ.get("TEDDY_TTS_VOICE", "dlc01robotcompanionmaledefault")
TTS_TIMEOUT_SECONDS = int(os.environ.get("TEDDY_TTS_TIMEOUT_SECONDS", "120"))
SAPI_VOICE = os.environ.get("TEDDY_SAPI_VOICE", "")

PIPER_ROOT = RUNTIME_ROOT / "tts" / "piper" / "piper"
PIPER_EXE = Path(os.environ.get("TEDDY_PIPER_EXE", str(PIPER_ROOT / "piper.exe")))
PIPER_ESPEAK_DATA = Path(
    os.environ.get("TEDDY_PIPER_ESPEAK_DATA", str(PIPER_ROOT / "espeak-ng-data"))
)
PIPER_MODEL = Path(
    os.environ.get(
        "TEDDY_PIPER_MODEL",
        str(RUNTIME_ROOT / "tts" / "voices" / "fallout4-dlc01robotcompanionmaledefault.onnx"),
    )
)
PIPER_CONFIG = Path(
    os.environ.get("TEDDY_PIPER_CONFIG", str(PIPER_MODEL) + ".json")
)

VOSK_MODEL_PATH = Path(
    os.environ.get(
        "TEDDY_VOSK_MODEL_PATH",
        str(RUNTIME_ROOT / "models" / "vosk-model-small-en-us-0.15"),
    )
)
STT_SAMPLE_RATE = int(os.environ.get("TEDDY_STT_SAMPLE_RATE", "16000"))
STT_BLOCK_SIZE = int(os.environ.get("TEDDY_STT_BLOCK_SIZE", "4000"))
STT_MAX_LISTEN_SECONDS = float(os.environ.get("TEDDY_STT_MAX_LISTEN_SECONDS", "10"))
STT_INITIAL_TIMEOUT_SECONDS = float(
    os.environ.get("TEDDY_STT_INITIAL_TIMEOUT_SECONDS", "5")
)
STT_SPEECH_END_SECONDS = float(os.environ.get("TEDDY_STT_SPEECH_END_SECONDS", "1.8"))
STT_RMS_THRESHOLD = int(os.environ.get("TEDDY_STT_RMS_THRESHOLD", "350"))
STT_SOFT_RMS_THRESHOLD = int(os.environ.get("TEDDY_STT_SOFT_RMS_THRESHOLD", "220"))
STT_PREROLL_CHUNKS = int(os.environ.get("TEDDY_STT_PREROLL_CHUNKS", "2"))
STT_SOFT_BUFFER_CHUNKS = int(os.environ.get("TEDDY_STT_SOFT_BUFFER_CHUNKS", "12"))
STT_SOFT_MIN_HOT_CHUNKS = int(os.environ.get("TEDDY_STT_SOFT_MIN_HOT_CHUNKS", "2"))
STT_BASE_URL = os.environ.get("TEDDY_STT_URL", "http://127.0.0.1:8000")
STT_PATH = os.environ.get("TEDDY_STT_PATH", "/v1/transcribe")
FASTER_WHISPER_MODEL = os.environ.get("TEDDY_FASTER_WHISPER_MODEL", "small.en")
FASTER_WHISPER_DEVICE = os.environ.get("TEDDY_FASTER_WHISPER_DEVICE", "auto")
FASTER_WHISPER_COMPUTE_TYPE = os.environ.get("TEDDY_FASTER_WHISPER_COMPUTE_TYPE", "auto")
FASTER_WHISPER_BEAM_SIZE = int(os.environ.get("TEDDY_FASTER_WHISPER_BEAM_SIZE", "1"))
FASTER_WHISPER_LANGUAGE = os.environ.get("TEDDY_FASTER_WHISPER_LANGUAGE", "en")
WAKE_PHRASES = tuple(
    phrase.strip().lower()
    for phrase in os.environ.get(
        "TEDDY_WAKE_PHRASES",
        "teddy,hey teddy,hi teddy,okay teddy",
    ).split(",")
    if phrase.strip()
)
WAKE_BLOCK_SIZE = int(os.environ.get("TEDDY_WAKE_BLOCK_SIZE", "2000"))
WAKE_ACK_ENABLE_MOUTH = os.environ.get("TEDDY_WAKE_ACK_ENABLE_MOUTH", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WAKE_OUTPUT_KEEPALIVE = os.environ.get("TEDDY_WAKE_OUTPUT_KEEPALIVE", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WAKE_KEEPALIVE_INTERVAL_SECONDS = float(
    os.environ.get("TEDDY_WAKE_KEEPALIVE_INTERVAL_SECONDS", "0.20")
)
WAKE_ACK_DELAY_SECONDS = float(
    os.environ.get("TEDDY_WAKE_ACK_DELAY_SECONDS", "0.45")
)
WAKE_TRAILING_CONTINUATION_SECONDS = float(
    os.environ.get("TEDDY_WAKE_TRAILING_CONTINUATION_SECONDS", "1.2")
)
WAKE_ACKNOWLEDGEMENT = os.environ.get(
    "TEDDY_WAKE_ACKNOWLEDGEMENT",
    "Hello, how can I help?",
).strip()
SESSION_IDLE_TIMEOUT_SECONDS = float(
    os.environ.get("TEDDY_SESSION_IDLE_TIMEOUT_SECONDS", "20")
)
SESSION_MIN_TRANSCRIPT_ENTRIES = int(
    os.environ.get("TEDDY_SESSION_MIN_TRANSCRIPT_ENTRIES", "4")
)
SESSION_MAX_TRANSCRIPT_ENTRIES = int(
    os.environ.get("TEDDY_SESSION_MAX_TRANSCRIPT_ENTRIES", "24")
)
SESSION_MAX_TRANSCRIPT_CHARS = int(
    os.environ.get("TEDDY_SESSION_MAX_TRANSCRIPT_CHARS", "6000")
)
SESSION_SUMMARY_MAX_OUTPUT_TOKENS = int(
    os.environ.get("TEDDY_SESSION_SUMMARY_MAX_OUTPUT_TOKENS", "220")
)
SESSION_SUMMARY_MAX_CHARS = int(
    os.environ.get("TEDDY_SESSION_SUMMARY_MAX_CHARS", "1000")
)
RECENT_SESSION_SUMMARY_COUNT = int(
    os.environ.get("TEDDY_RECENT_SESSION_SUMMARY_COUNT", "2")
)
RECENT_SESSION_MEMORY_MAX_CHARS = int(
    os.environ.get("TEDDY_RECENT_SESSION_MEMORY_MAX_CHARS", "1800")
)
DAILY_MEMORY_MAX_CHARS = int(os.environ.get("TEDDY_DAILY_MEMORY_MAX_CHARS", "1800"))
PROFILE_TURNS = os.environ.get("TEDDY_PROFILE_TURNS", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

MEMORY_USE_LEGACY_FILES = os.environ.get("TEDDY_MEMORY_USE_LEGACY_FILES", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MEMORY_STATIC_WORKSPACE_FILES = tuple(
    name.strip()
    for name in os.environ.get(
        "TEDDY_MEMORY_STATIC_WORKSPACE_FILES",
        "SOUL.md,IDENTITY.md,USER.md,MEMORY.md",
    ).split(",")
    if name.strip()
)
MEMORY_PROFILE_MAX_CHARS = int(os.environ.get("TEDDY_MEMORY_PROFILE_MAX_CHARS", "1200"))
MEMORY_PROFILE_HARD_MAX_CHARS = int(
    os.environ.get("TEDDY_MEMORY_PROFILE_HARD_MAX_CHARS", "1800")
)
MEMORY_WORKING_MAX_CHARS = int(os.environ.get("TEDDY_MEMORY_WORKING_MAX_CHARS", "600"))
MEMORY_WORKING_MAX_BULLETS = int(os.environ.get("TEDDY_MEMORY_WORKING_MAX_BULLETS", "5"))
MEMORY_PERSISTENT_WORKING_KEY = os.environ.get(
    "TEDDY_MEMORY_PERSISTENT_WORKING_KEY",
    "__persistent__",
)
MEMORY_EPISODE_MAX_COUNT = int(os.environ.get("TEDDY_MEMORY_EPISODE_MAX_COUNT", "3"))
MEMORY_EPISODE_MAX_CHARS = int(os.environ.get("TEDDY_MEMORY_EPISODE_MAX_CHARS", "1600"))
MEMORY_RECENT_TURNS_MAX_COUNT = int(
    os.environ.get("TEDDY_MEMORY_RECENT_TURNS_MAX_COUNT", "6")
)
MEMORY_RECENT_TURNS_MAX_CHARS = int(
    os.environ.get("TEDDY_MEMORY_RECENT_TURNS_MAX_CHARS", "2000")
)
MEMORY_INSTRUCTION_TARGET_MAX_CHARS = int(
    os.environ.get("TEDDY_MEMORY_INSTRUCTION_TARGET_MAX_CHARS", "7200")
)
MEMORY_EPISODE_TRIGGER_TERMS = tuple(
    phrase.strip().lower()
    for phrase in os.environ.get(
        "TEDDY_MEMORY_EPISODE_TRIGGER_TERMS",
        "remember,earlier,before,last time,last week,yesterday,again,still,continue,history,project",
    ).split(",")
    if phrase.strip()
)
MEMORY_EPISODE_PRUNE_DAYS = int(os.environ.get("TEDDY_MEMORY_EPISODE_PRUNE_DAYS", "90"))
MEMORY_EPISODE_PRUNE_MIN_IMPORTANCE = int(
    os.environ.get("TEDDY_MEMORY_EPISODE_PRUNE_MIN_IMPORTANCE", "4")
)
MEMORY_ARCHIVIST_MODEL = os.environ.get("TEDDY_MEMORY_ARCHIVIST_MODEL", OPENAI_MODEL)
MEMORY_ARCHIVIST_MAX_OUTPUT_TOKENS = int(
    os.environ.get("TEDDY_MEMORY_ARCHIVIST_MAX_OUTPUT_TOKENS", "300")
)

MOUTH_BASE_URL = os.environ.get("TEDDY_MOUTH_URL", "http://127.0.0.1:8765")
MOUTH_OPEN_ANGLE = int(os.environ.get("TEDDY_MOUTH_OPEN_ANGLE", "12"))
MOUTH_CLOSED_ANGLE = int(os.environ.get("TEDDY_MOUTH_CLOSED_ANGLE", "4"))
MOUTH_PULSE_SECONDS = float(os.environ.get("TEDDY_MOUTH_PULSE_SECONDS", "0.18"))
MOUTH_SYNC_MODE = os.environ.get("TEDDY_MOUTH_SYNC_MODE", "viseme").strip().lower()
MOUTH_STREAMING_SYNC_MODE = os.environ.get("TEDDY_MOUTH_STREAMING_SYNC_MODE", "viseme").strip().lower()
MOUTH_AUDIO_CHUNK_FRAMES = int(os.environ.get("TEDDY_MOUTH_AUDIO_CHUNK_FRAMES", "1024"))
MOUTH_AUDIO_RMS_SILENCE = int(os.environ.get("TEDDY_MOUTH_AUDIO_RMS_SILENCE", "140"))
MOUTH_AUDIO_RMS_FULL = int(os.environ.get("TEDDY_MOUTH_AUDIO_RMS_FULL", "1400"))
MOUTH_MIN_OPEN_RATIO = float(os.environ.get("TEDDY_MOUTH_MIN_OPEN_RATIO", "0.18"))
MOUTH_SMOOTHING = float(os.environ.get("TEDDY_MOUTH_SMOOTHING", "0.55"))
MOUTH_COMMAND_INTERVAL_SECONDS = float(
    os.environ.get("TEDDY_MOUTH_COMMAND_INTERVAL_SECONDS", "0.05")
)
MOUTH_TRACE = os.environ.get("TEDDY_MOUTH_TRACE", "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
MOUTH_TRACE_DIR = Path(
    os.environ.get("TEDDY_MOUTH_TRACE_DIR", str(TMP_DIR / "mouth-traces"))
)
MOUTH_VISEME_NARROW_ANGLE = int(os.environ.get("TEDDY_MOUTH_VISEME_NARROW_ANGLE", "6"))
MOUTH_VISEME_MID_ANGLE = int(os.environ.get("TEDDY_MOUTH_VISEME_MID_ANGLE", "8"))
MOUTH_VISEME_LARGE_ANGLE = int(os.environ.get("TEDDY_MOUTH_VISEME_LARGE_ANGLE", "11"))
RHUBARB_ROOT = Path(
    os.environ.get(
        "TEDDY_RHUBARB_ROOT",
        str(TOOLS_DIR / "rhubarb" / "Rhubarb-Lip-Sync-1.14.0-Windows"),
    )
)
RHUBARB_EXE = Path(os.environ.get("TEDDY_RHUBARB_EXE", str(RHUBARB_ROOT / "rhubarb.exe")))
RHUBARB_RECOGNIZER = os.environ.get("TEDDY_RHUBARB_RECOGNIZER", "pocketSphinx")
RHUBARB_EXTENDED_SHAPES = os.environ.get("TEDDY_RHUBARB_EXTENDED_SHAPES", "GHX")
RHUBARB_TIMEOUT_SECONDS = int(os.environ.get("TEDDY_RHUBARB_TIMEOUT_SECONDS", "30"))

CORE_WORKSPACE_FILES = (
    WORKSPACE_DIR / "SOUL.md",
    WORKSPACE_DIR / "USER.md",
    WORKSPACE_DIR / "AGENTS.md",
    WORKSPACE_DIR / "IDENTITY.md",
    WORKSPACE_DIR / "MEMORY.md",
)
