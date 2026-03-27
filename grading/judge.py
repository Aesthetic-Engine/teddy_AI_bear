from __future__ import annotations

import os
import time
from dataclasses import dataclass

from openai import OpenAI

from runtime import config


@dataclass
class JudgeResult:
    score: int
    verdict: str
    notes: str
    prompt_tweak: str


def judge_reply(
    case_id: str,
    category: str,
    prompts: list[str],
    reply_text: str,
    deterministic_failures: list[str],
) -> JudgeResult:
    if not config.OPENAI_API_KEY:
        return JudgeResult(
            score=0,
            verdict="judge_unavailable",
            notes="OPENAI_API_KEY is not set, so the LLM judge could not run.",
            prompt_tweak="none",
        )

    client = OpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
        timeout=config.OPENAI_TIMEOUT_SECONDS,
    )
    judge_model = os.environ.get("TEDDY_GRADE_JUDGE_MODEL", config.OPENAI_MODEL)

    prompt = (
        "Grade this Teddy reply for a local embodied assistant.\n"
        "Return exactly four lines in this format:\n"
        "score: <1-10>\n"
        "verdict: <pass|mixed|fail>\n"
        "notes: <one concise paragraph>\n"
        "prompt_tweak: <one concise suggestion or 'none'>\n\n"
        f"Case ID: {case_id}\n"
        f"Category: {category}\n"
        f"Prompts: {prompts}\n"
        f"Reply: {reply_text}\n"
        f"Deterministic failures: {deterministic_failures or ['none']}\n\n"
        "Judge for:\n"
        "- Teddy voice consistency\n"
        "- helpfulness and clarity\n"
        "- natural use of memory/context\n"
        "- whether the answer likely needs prompt tuning\n"
        "- whether the answer stayed concise and spoken\n"
    )

    last_exc: Exception | None = None
    response = None
    for attempt in range(1, 4):
        try:
            response = client.responses.create(
                model=judge_model,
                instructions=(
                    "You are grading Teddy's behavior. Be strict, concise, and practical. "
                    "Do not write markdown. Follow the exact output format."
                ),
                input=prompt,
                max_output_tokens=220,
                reasoning={"effort": "low"},
            )
            break
        except Exception as exc:
            last_exc = exc
            if attempt >= 3 or not _is_retryable(exc):
                detail = str(exc).strip() or exc.__class__.__name__
                return JudgeResult(
                    score=0,
                    verdict="judge_unavailable",
                    notes=f"Judge request failed: {detail}",
                    prompt_tweak="none",
                )
            time.sleep(0.35 * attempt)

    if response is None:
        detail = str(last_exc).strip() if last_exc else "unknown error"
        return JudgeResult(
            score=0,
            verdict="judge_unavailable",
            notes=f"Judge request failed: {detail}",
            prompt_tweak="none",
        )

    text = extract_text(response)
    parsed = _parse_judge_output(text)
    return JudgeResult(
        score=parsed.get("score", 0),
        verdict=parsed.get("verdict", "fail"),
        notes=parsed.get("notes", text.strip()),
        prompt_tweak=parsed.get("prompt_tweak", "none"),
    )


def extract_text(response) -> str:
    data = response.model_dump()
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()
    output = data.get("output", [])
    parts: list[str] = []
    for item in output:
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return " ".join(parts).strip()


def _parse_judge_output(text: str) -> dict[str, str | int]:
    result: dict[str, str | int] = {}
    for raw_line in text.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "score":
            try:
                result["score"] = max(1, min(10, int(value)))
            except ValueError:
                result["score"] = 0
        elif key in {"verdict", "notes", "prompt_tweak"}:
            result[key] = value
    return result


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

