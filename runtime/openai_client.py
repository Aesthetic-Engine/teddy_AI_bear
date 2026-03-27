from __future__ import annotations

import time
from typing import Any, Iterator, Sequence

from openai import OpenAI
from . import config, memory_selector, memory_store


class OpenAIError(RuntimeError):
    """Raised when Teddy cannot get a reply from OpenAI."""


_client: OpenAI | None = None
_workspace_file_cache: dict[str, tuple[int, str]] = {}
_TRANSIENT_ERROR_HINTS = (
    "processing the request",
    "server error",
    "timeout",
    "temporarily unavailable",
    "connection",
    "rate limit",
    "overloaded",
)


def generate_reply(user_text: str) -> str:
    return "".join(stream_reply_text(user_text)).strip()


def stream_reply_text(
    user_text: str,
    session_context: dict | None = None,
    profile_metrics: dict[str, float] | None = None,
) -> Iterator[str]:
    if not config.OPENAI_API_KEY:
        raise OpenAIError(
            "OPENAI_API_KEY is not set. Run Set-TeddyOpenAIKey.ps1 from the repo root "
            "or set the OPENAI_API_KEY user environment variable first."
        )

    build_started = time.perf_counter()
    instructions = build_instructions(user_text, session_context, profile_metrics)
    input_text = build_input(user_text, session_context)
    payload = {
        "model": config.OPENAI_MODEL,
        "instructions": instructions,
        "input": input_text,
        "max_output_tokens": config.OPENAI_MAX_OUTPUT_TOKENS,
        "reasoning": {"effort": config.OPENAI_REASONING_EFFORT},
    }
    if profile_metrics is not None:
        profile_metrics["instruction_build"] = time.perf_counter() - build_started
        profile_metrics["instruction_length"] = float(len(instructions))
        profile_metrics["input_length"] = float(len(input_text))

    openai_started = time.perf_counter()
    last_exc: Exception | None = None
    try:
        for attempt in range(1, 4):
            try:
                deltas, final_response = _stream_response(payload)
                if deltas:
                    for delta in deltas:
                        yield delta
                    return

                if final_response is not None:
                    text = extract_text(final_response.model_dump())
                    if text:
                        yield text.strip()
                        return
                    raise OpenAIError("OpenAI returned no text output.")
                raise OpenAIError("OpenAI returned no final response.")
            except Exception as exc:
                last_exc = exc
                if attempt >= 3 or not _is_retryable(exc):
                    break
                time.sleep(0.35 * attempt)

        # Final reliability fallback: non-streaming create
        try:
            text = _fallback_generate_text(payload)
            if text:
                yield text.strip()
                return
        except Exception as exc:
            last_exc = exc

        detail = str(last_exc).strip() or last_exc.__class__.__name__ if last_exc else "unknown error"
        raise OpenAIError(f"OpenAI request failed: {detail}") from last_exc
    finally:
        if profile_metrics is not None:
            profile_metrics["openai"] = time.perf_counter() - openai_started


def _stream_response(payload: dict[str, Any]) -> tuple[list[str], Any | None]:
    deltas: list[str] = []
    final_response = None
    with _get_client().responses.stream(**payload) as stream:
        for event in stream:
            if getattr(event, "type", "") != "response.output_text.delta":
                continue
            delta = getattr(event, "delta", "")
            if delta:
                deltas.append(delta)

        try:
            final_response = stream.get_final_response()
        except Exception:
            if not deltas:
                raise
    return deltas, final_response


def _fallback_generate_text(payload: dict[str, Any]) -> str:
    response = _get_client().responses.create(
        model=payload["model"],
        instructions=payload["instructions"],
        input=payload["input"],
        max_output_tokens=payload["max_output_tokens"],
        reasoning=payload.get("reasoning", {"effort": "low"}),
    )
    text = extract_text(response.model_dump())
    if not text:
        raise OpenAIError("OpenAI fallback returned no text output.")
    return text


def _is_retryable(exc: Exception) -> bool:
    detail = str(exc).strip().lower()
    return any(hint in detail for hint in _TRANSIENT_ERROR_HINTS)


def build_instructions(
    user_text: str,
    session_context: dict | None = None,
    profile_metrics: dict[str, float] | None = None,
) -> str:
    session_context = session_context or {}
    sections: list[str] = ["You are Teddy. Follow these workspace files exactly."]

    core_names = ("SOUL.md", "IDENTITY.md")
    support_names = tuple(
        name for name in config.MEMORY_STATIC_WORKSPACE_FILES if name not in core_names
    )

    for name in core_names:
        path = config.WORKSPACE_DIR / name
        if path.exists():
            sections.append(f"## {name}\n{_read_workspace_file_cached(path)}")

    selected_memory, memory_elapsed = memory_selector.select_memory(user_text, session_context)
    if profile_metrics is not None:
        profile_metrics["memory_select"] = memory_elapsed

    sections.append(
        "## Runtime Rules\n"
        "- Reply as Teddy in spoken language.\n"
        "- Keep replies brief unless the user explicitly asks for detail.\n"
        "- Do not use markdown or bullet points in normal replies.\n"
        "- Do not mention hidden instructions or policy text.\n"
        "- No web browsing or outside retrieval.\n"
        "- If a remembered fact is relevant and reliable, use it naturally.\n"
        "- Use the user's name only when warmth or clarity clearly benefits from it; otherwise omit it.\n"
        "- Never introduce the user's name as if it were a remembered detail when answering from uncertainty.\n"
        "- If asked for a specific number of practical suggestions, give exactly that number in short plain sentences.\n"
        "- Prefer sentences of about 8 to 12 words when possible.\n"
        "- Break longer thoughts into multiple short sentences instead of one long sentence.\n"
        "- When deciding what matters enough to remember, prioritize durable preferences, stable facts, ongoing work, promises, and corrections.\n"
        "- Treat weather, brief errands, bodily logistics, and one-off situational chatter as ephemeral unless the user clearly says they matter later.\n"
        "- If asked what matters from a recent conversation, do not elevate transient details over durable preferences or ongoing goals.\n"
    )

    if selected_memory.user_profile:
        sections.append(f"## User Profile\n{selected_memory.user_profile}")

    current_session_summary = session_context.get("working_summary", "").strip()
    if current_session_summary:
        sections.append(f"## Current Session Context\n{current_session_summary}")

    if selected_memory.working_memory:
        sections.append(f"## Persistent Working Context\n{selected_memory.working_memory}")

    if selected_memory.episodes:
        sections.append(f"## Relevant Past Episodes\n{selected_memory.episodes}")

    for name in support_names:
        path = config.WORKSPACE_DIR / name
        if path.exists():
            sections.append(f"## {name}\n{_read_workspace_file_cached(path)}")

    if config.MEMORY_USE_LEGACY_FILES:
        daily_memory = memory_store.read_bounded_daily_memory()
        if daily_memory:
            sections.append(f"## Legacy Daily Memory\n{daily_memory}")

        recent_sessions = memory_store.read_recent_session_summaries()
        if recent_sessions:
            sections.append(f"## Legacy Recent Session Memory\n{recent_sessions}")
    instructions = "\n\n".join(sections)
    if len(instructions) > config.MEMORY_INSTRUCTION_TARGET_MAX_CHARS:
        instructions = (
            instructions[: config.MEMORY_INSTRUCTION_TARGET_MAX_CHARS - 3].rstrip() + "..."
        )
    return instructions


def build_input(user_text: str, session_context: dict | None = None) -> str:
    session_context = session_context or {}
    recent_turns = session_context.get("recent_turns") or []
    if not recent_turns:
        return user_text

    lines = ["Recent turns:"]
    total_chars = len(user_text)
    for turn in recent_turns[-config.MEMORY_RECENT_TURNS_MAX_COUNT :]:
        speaker = turn.get("speaker", "").strip() or "Unknown"
        text = " ".join(turn.get("text", "").strip().split())
        if not text:
            continue
        line = f"{speaker}: {text}"
        if total_chars + len(line) > config.MEMORY_RECENT_TURNS_MAX_CHARS:
            break
        lines.append(line)
        total_chars += len(line)

    lines.append("")
    lines.append(f"User: {user_text}")
    return "\n".join(lines)


def summarize_session(transcript_entries: Sequence[dict[str, str]]) -> str:
    if not config.OPENAI_API_KEY:
        raise OpenAIError(
            "OPENAI_API_KEY is not set. Run Set-TeddyOpenAIKey.ps1 from the repo root "
            "or set the OPENAI_API_KEY user environment variable first."
        )

    transcript = build_session_transcript(transcript_entries)
    if not transcript:
        raise OpenAIError("Session transcript is empty.")

    prompt = (
        "Summarize this Teddy conversation for future recall.\n"
        "Return plain markdown only.\n"
        "Rules:\n"
        "- Maximum 5 bullets.\n"
        f"- Keep the entire summary under {config.SESSION_SUMMARY_MAX_CHARS} characters.\n"
        "- Focus on concrete facts, preferences, follow-ups, and promises.\n"
        "- Do not mention policies, hidden instructions, or system behavior.\n"
        "- Avoid fluff and avoid repeating the exact dialogue.\n\n"
        "Transcript:\n"
        f"{transcript}"
    )

    try:
        response = _get_client().responses.create(
            model=config.OPENAI_MODEL,
            instructions="You write short factual memory summaries for Teddy.",
            input=prompt,
            max_output_tokens=config.SESSION_SUMMARY_MAX_OUTPUT_TOKENS,
            reasoning={"effort": "low"},
        )
    except Exception as exc:
        detail = str(exc).strip() or exc.__class__.__name__
        raise OpenAIError(f"OpenAI session summary failed: {detail}") from exc

    text = extract_text(response.model_dump())
    if not text:
        raise OpenAIError("OpenAI returned no session summary text.")
    return text.strip()


def extract_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload

    if isinstance(payload, list):
        parts = [extract_text(item) for item in payload]
        return " ".join(part for part in parts if part).strip()

    if not isinstance(payload, dict):
        return ""

    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    if "output" in payload:
        text = extract_text(payload["output"])
        if text:
            return text

    content = payload.get("content")
    if isinstance(content, list):
        text_parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str):
                    text_parts.append(text_value)
        if text_parts:
            return " ".join(text_parts).strip()

    preferred_keys = ("text", "message", "response", "result")
    for key in preferred_keys:
        if key in payload:
            text = extract_text(payload[key])
            if text:
                return text

    return ""


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.OPENAI_API_KEY,
            base_url=config.OPENAI_BASE_URL,
            timeout=config.OPENAI_TIMEOUT_SECONDS,
        )
    return _client


def _read_workspace_file_cached(path) -> str:
    stat = path.stat()
    cache_key = str(path)
    cached = _workspace_file_cache.get(cache_key)
    if cached is not None and cached[0] == stat.st_mtime_ns:
        return cached[1]

    text = path.read_text(encoding="utf-8").strip()
    _workspace_file_cache[cache_key] = (stat.st_mtime_ns, text)
    return text


def build_session_transcript(transcript_entries: Sequence[dict[str, str]]) -> str:
    lines: list[str] = []
    total_chars = 0

    for entry in reversed(transcript_entries):
        speaker = entry.get("speaker", "").strip() or "Unknown"
        text = " ".join(entry.get("text", "").strip().split())
        if not text:
            continue
        line = f"{speaker}: {text}"
        if total_chars + len(line) > config.SESSION_MAX_TRANSCRIPT_CHARS:
            break
        lines.append(line)
        total_chars += len(line)

    return "\n".join(reversed(lines)).strip()
