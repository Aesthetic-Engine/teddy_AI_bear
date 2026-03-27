from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Sequence

from openai import OpenAI

from . import config, memory_db, openai_client


class MemoryArchivistError(RuntimeError):
    """Raised when Teddy cannot extract structured memory from a session."""


@dataclass
class ArchivistResult:
    facts_written: int = 0
    episode_written: bool = False
    working_bullets_written: int = 0


def archive_session(transcript_entries: Sequence[dict[str, str]]) -> ArchivistResult:
    """Extract structured memory from a completed session and persist it."""
    transcript = openai_client.build_session_transcript(transcript_entries)
    if not transcript:
        raise MemoryArchivistError("Session transcript is empty.")

    try:
        payload = _extract_session_memory(transcript)
    except MemoryArchivistError:
        payload = _heuristic_session_memory(transcript_entries)
    result = ArchivistResult()

    for item in payload.get("user_facts", []):
        category = str(item.get("category", "")).strip()
        fact = str(item.get("fact", "")).strip()
        confidence = _coerce_confidence(item.get("confidence", 0.9))
        if not category or not fact:
            continue
        memory_db.upsert_fact(category, fact, confidence)
        result.facts_written += 1

    episode = payload.get("episode") or {}
    topic = str(episode.get("topic", "")).strip()
    summary = str(episode.get("summary", "")).strip()
    if topic and summary:
        memory_db.append_episode(
            topic=topic,
            summary=summary,
            importance_score=_coerce_importance(episode.get("importance_score", 5)),
            emotional_valence=str(episode.get("emotional_valence", "neutral")).strip() or "neutral",
        )
        result.episode_written = True

    bullets = [
        str(item).strip()
        for item in payload.get("working_memory", [])
        if str(item).strip()
    ][: config.MEMORY_WORKING_MAX_BULLETS]
    if bullets:
        memory_db.set_working_memory(config.MEMORY_PERSISTENT_WORKING_KEY, bullets)
        result.working_bullets_written = len(bullets)

    memory_db.prune_episodes()
    return result


def _extract_session_memory(transcript: str) -> dict[str, Any]:
    prompt = (
        "Analyze this Teddy conversation and extract structured memory.\n"
        "Return strict JSON only with this shape:\n"
        "{\n"
        '  "user_facts": [{"category": "preference", "fact": "User prefers...", "confidence": 0.95}],\n'
        '  "episode": {"topic": "short topic", "summary": "exactly one or two sentences", "importance_score": 1-10, "emotional_valence": "neutral"},\n'
        '  "working_memory": ["short bullet", "short bullet"]\n'
        "}\n"
        "Rules:\n"
        "- Extract only durable, generalized user facts.\n"
        "- Ignore operational commands, filler, ASR noise, and transient states.\n"
        "- Ignore weather, bathroom or body logistics, brief errands, short departures, and casual one-off situational details unless the user explicitly says they will matter later.\n"
        "- Episode summary must be extractive, concrete, and never markdown.\n"
        "- Episode summaries should center durable outcomes, corrections, decisions, or ongoing work rather than fleeting scene-setting.\n"
        "- Working memory bullets should be short and useful for a later follow-up.\n"
        "- If no durable facts exist, return an empty user_facts array.\n"
        "- If the session has no lasting narrative value, still return a minimal episode.\n\n"
        f"Transcript:\n{transcript}"
    )

    if not config.OPENAI_API_KEY:
        raise MemoryArchivistError("OPENAI_API_KEY is not set.")

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = _get_client().responses.create(
                model=config.MEMORY_ARCHIVIST_MODEL,
                instructions="You are Teddy's memory archivist. Return strict JSON only.",
                input=prompt,
                max_output_tokens=config.MEMORY_ARCHIVIST_MAX_OUTPUT_TOKENS,
                reasoning={"effort": "low"},
            )
            break
        except Exception as exc:
            last_exc = exc
            if attempt >= 3 or not _is_retryable(exc):
                detail = str(exc).strip() or exc.__class__.__name__
                raise MemoryArchivistError(f"OpenAI archivist request failed: {detail}") from exc
            time.sleep(0.35 * attempt)
    else:
        raise MemoryArchivistError("OpenAI archivist request failed: unknown error")

    text = openai_client.extract_text(response.model_dump())
    if not text:
        raise MemoryArchivistError("OpenAI returned no archivist output.")

    cleaned = _strip_code_fences(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise MemoryArchivistError(f"Archivist returned invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise MemoryArchivistError("Archivist returned a non-object JSON payload.")
    return payload


def _heuristic_session_memory(transcript_entries: Sequence[dict[str, str]]) -> dict[str, Any]:
    user_turns = [
        " ".join(str(entry.get("text", "")).strip().split())
        for entry in transcript_entries
        if str(entry.get("speaker", "")).strip().lower() not in {"teddy", "assistant"}
    ]
    teddy_turns = [
        " ".join(str(entry.get("text", "")).strip().split())
        for entry in transcript_entries
        if str(entry.get("speaker", "")).strip().lower() in {"teddy", "assistant"}
    ]

    facts: list[dict[str, Any]] = []
    for turn in user_turns:
        match = re.search(r"\bi prefer\s+(.+?)(?:[.!?]|$)", turn, re.I)
        if not match:
            continue
        preference = _clean_fact_fragment(match.group(1))
        if not preference:
            continue
        facts.append(
            {
                "category": "preference",
                "fact": f"User prefers {preference}.",
                "confidence": 0.78,
            }
        )

    durable_user_turns = [turn for turn in user_turns if not _is_ephemeral_turn(turn)]
    topic_source = (
        next((text for text in reversed(durable_user_turns) if text), "")
        or next((text for text in reversed(user_turns) if text), "")
        or "recent conversation"
    )
    topic = _short_phrase(topic_source, 40) or "recent conversation"
    preferred_summary_turns = durable_user_turns[-2:] or user_turns[-1:]
    user_summary = _short_phrase(" ".join(preferred_summary_turns), 220)
    teddy_summary = _short_phrase(" ".join(teddy_turns[-1:]), 180)
    summary_parts = [part for part in (user_summary, teddy_summary) if part]
    episode_summary = " ".join(summary_parts).strip() or "The user and Teddy had a short conversation."

    working_memory = []
    for turn in preferred_summary_turns:
        short = _short_phrase(turn, 120)
        if short:
            working_memory.append(short)

    return {
        "user_facts": facts[:3],
        "episode": {
            "topic": topic,
            "summary": episode_summary[:600],
            "importance_score": 4 if facts else 3,
            "emotional_valence": "neutral",
        },
        "working_memory": working_memory[: config.MEMORY_WORKING_MAX_BULLETS],
    }


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _coerce_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.9


def _coerce_importance(value: Any) -> int:
    try:
        return max(1, min(10, int(value)))
    except Exception:
        return 5


def _is_retryable(exc: Exception) -> bool:
    detail = str(exc).strip().lower()
    hints = (
        "processing your request",
        "server error",
        "timeout",
        "temporarily unavailable",
        "connection",
        "rate limit",
        "overloaded",
        "internalservererror",
    )
    return any(hint in detail for hint in hints)


def _clean_fact_fragment(text: str) -> str:
    cleaned = re.sub(r"\b(?:now|please remember that|please keep that in mind)\b", "", text, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.;:-")
    return cleaned[:220]


def _short_phrase(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _is_ephemeral_turn(text: str) -> bool:
    lowered = text.strip().lower()
    if not lowered:
        return True
    ephemeral_patterns = (
        r"\bit'?s raining\b",
        r"\brain\b",
        r"\bweather\b",
        r"\bstretch my legs\b",
        r"\bgoing to stretch\b",
        r"\bfor a minute\b",
        r"\bbe right back\b",
        r"\bgoing to the bathroom\b",
        r"\bbathroom\b",
        r"\bheaded out\b",
        r"\bstepping out\b",
    )
    return any(re.search(pattern, lowered) for pattern in ephemeral_patterns)


def _get_client() -> OpenAI:
    return OpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        timeout=config.OPENAI_TIMEOUT_SECONDS,
    )

