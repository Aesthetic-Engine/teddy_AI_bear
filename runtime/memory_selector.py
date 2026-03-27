from __future__ import annotations

import re
import time
from dataclasses import dataclass

from . import config, memory_db


@dataclass
class SelectedMemory:
    user_profile: str = ""
    working_memory: str = ""
    episodes: str = ""


def select_memory(user_text: str, session_context: dict | None = None) -> tuple[SelectedMemory, float]:
    """Fast deterministic memory selection for the hot path.

    Returns the selected memory sections and elapsed seconds.
    """
    started = time.perf_counter()
    session_context = session_context or {}

    profile = memory_db.compile_user_profile(config.MEMORY_PROFILE_MAX_CHARS)
    if len(profile) > config.MEMORY_PROFILE_HARD_MAX_CHARS:
        profile = profile[: config.MEMORY_PROFILE_HARD_MAX_CHARS].rstrip() + "..."

    session_id = session_context.get("session_id", "")
    working = ""
    working = memory_db.get_combined_working_memory(
        session_id,
        max_chars=config.MEMORY_WORKING_MAX_CHARS,
    )

    episodes = ""
    if should_pull_episodes(user_text):
        keywords = extract_keywords(user_text)
        selected = memory_db.query_episodes(
            keywords,
            max_count=config.MEMORY_EPISODE_MAX_COUNT,
            max_chars=config.MEMORY_EPISODE_MAX_CHARS,
        )
        episodes = memory_db.format_episodes(selected)

    return (
        SelectedMemory(
            user_profile=profile,
            working_memory=working,
            episodes=episodes,
        ),
        time.perf_counter() - started,
    )


def should_pull_episodes(user_text: str) -> bool:
    text = user_text.lower()
    return any(term in text for term in config.MEMORY_EPISODE_TRIGGER_TERMS)


def extract_keywords(user_text: str) -> list[str]:
    """Very cheap keyword extraction for SQL LIKE matching."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9'-]{2,}", user_text.lower())
    stop_words = {
        "the",
        "and",
        "that",
        "with",
        "what",
        "when",
        "where",
        "which",
        "your",
        "have",
        "from",
        "this",
        "about",
        "would",
        "could",
        "should",
        "remember",
        "please",
        "tell",
    }
    seen: set[str] = set()
    keywords: list[str] = []
    for word in words:
        if word in stop_words or word in seen:
            continue
        seen.add(word)
        keywords.append(word)
        if len(keywords) >= 8:
            break
    return keywords

