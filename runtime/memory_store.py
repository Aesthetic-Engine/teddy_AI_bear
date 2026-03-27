from __future__ import annotations

from datetime import datetime
from pathlib import Path

from . import config


def append_daily_note(
    topic: str,
    key_fact: str,
    follow_up: str,
    durable_candidate: bool,
) -> Path:
    config.MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now()
    note_path = config.MEMORY_DIR / f"{today:%Y-%m-%d}.md"
    if not note_path.exists():
        note_path.write_text(f"# {today:%Y-%m-%d}\n\n## Notes\n", encoding="utf-8")

    durable_value = "yes" if durable_candidate else "no"
    entry = (
        f"- [{today:%H:%M}] topic: {sanitize(topic, 100)}\n"
        f"  - key fact: {sanitize(key_fact, 140)}\n"
        f"  - next useful follow-up: {sanitize(follow_up, 140)}\n"
        f"  - durable memory candidate: {durable_value}\n"
    )

    with note_path.open("a", encoding="utf-8") as handle:
        if note_path.stat().st_size > 0:
            handle.write("\n")
        handle.write(entry)

    return note_path


def write_session_summary(summary_text: str, transcript_entries: int) -> Path:
    config.SESSION_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    now = datetime.now()
    summary_path = config.SESSION_MEMORY_DIR / f"{now:%Y%m%d-%H%M%S}.md"
    body = normalize_summary(summary_text, config.SESSION_SUMMARY_MAX_CHARS)
    summary_path.write_text(
        (
            f"# Session Summary {now:%Y-%m-%d %H:%M:%S}\n\n"
            f"- transcript entries: {transcript_entries}\n\n"
            f"{body}\n"
        ),
        encoding="utf-8",
    )
    return summary_path


def read_bounded_daily_memory() -> str:
    today_path = config.MEMORY_DIR / f"{datetime.now():%Y-%m-%d}.md"
    if not today_path.exists():
        return ""
    return _read_tail(today_path, config.DAILY_MEMORY_MAX_CHARS)


def read_recent_session_summaries() -> str:
    if not config.SESSION_MEMORY_DIR.exists():
        return ""

    summary_paths = sorted(config.SESSION_MEMORY_DIR.glob("*.md"))
    if not summary_paths:
        return ""

    selected = summary_paths[-config.RECENT_SESSION_SUMMARY_COUNT :]
    sections: list[str] = []
    remaining = config.RECENT_SESSION_MEMORY_MAX_CHARS
    for path in selected:
        text = path.read_text(encoding="utf-8").strip()
        if not text or remaining <= 0:
            continue
        if len(text) > remaining:
            text = text[:remaining].rstrip() + "..."
        sections.append(text)
        remaining -= len(text)

    return "\n\n".join(sections).strip()


def sanitize(value: str, limit: int) -> str:
    collapsed = " ".join(value.strip().split())
    if not collapsed:
        return "none"
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def _read_tail(path: Path, max_chars: int) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= max_chars:
        return text
    return "...\n" + text[-max_chars:].lstrip()


def normalize_summary(value: str, limit: int) -> str:
    lines = [line.rstrip() for line in value.strip().splitlines() if line.strip()]
    normalized = "\n".join(lines)
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."
