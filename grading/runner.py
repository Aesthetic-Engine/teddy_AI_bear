from __future__ import annotations

import argparse
import io
import json
import struct
import urllib.error
import uuid
import wave
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from unittest import mock

from grading.cases import TestCase, get_test_cases
from grading.judge import JudgeResult, judge_reply
from grading.report import make_report_payload, write_json_report, write_markdown_report
from runtime import audio_player, config, memory_archivist, memory_db, openai_client, speech_input, tts_client
from runtime.teddy_loop import (
    ConversationSession,
    prewarm_runtime_assets,
    run_turn,
    speak_text,
    speak_wake_ack,
    verify_core_files,
)


DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent


@dataclass
class CaseOutcome:
    exit_code: int
    reply_text: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    transcript: list[dict] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    archived_state: dict = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Teddy grading suite")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--case", default="", help="Run a single case id")
    parser.add_argument(
        "--suite",
        default="stage1",
        choices=["stage1", "stage2", "all"],
        help="Which grading suite to run.",
    )
    parser.add_argument(
        "--include-embodiment",
        action="store_true",
        help="Allow stage-two wake and embodiment cases that touch the live audio path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    run_dir = output_root / "artifacts" / datetime.now().strftime("%Y-%m-%d") / run_id
    report_dir = output_root / "reports" / datetime.now().strftime("%Y-%m-%d")

    verify_core_files()
    warm_openai_path()

    cases = get_test_cases(args.suite)
    if args.case:
        cases = [case for case in cases if case.id == args.case]
        if not cases:
            raise SystemExit(f"Unknown case id: {args.case}")

    case_results: list[dict] = []
    for case in cases:
        result = run_case(
            case,
            run_dir,
            use_judge=not args.no_judge,
            allow_audio_cases=args.include_embodiment,
        )
        case_results.append(result)

    payload = make_report_payload(run_id, case_results, suite=args.suite)
    json_path = report_dir / f"teddy-report-{run_id}.json"
    md_path = report_dir / f"teddy-report-{run_id}.md"
    write_json_report(json_path, payload)
    write_markdown_report(md_path, payload)

    print(f"Report written: {md_path}")
    print(f"JSON written: {json_path}")
    print(f"Overall grade: {payload['overall']['grade']} ({payload['overall']['score']}/100)")
    return 0


def run_case(case: TestCase, run_dir: Path, use_judge: bool, allow_audio_cases: bool) -> dict:
    case_dir = run_dir / case.id
    case_dir.mkdir(parents=True, exist_ok=True)

    db_path = case_dir / "memory.sqlite3"
    configure_isolated_memory(db_path)
    seed_case_memory(case)

    if case.enable_audio and not allow_audio_cases:
        outcome = CaseOutcome(
            exit_code=0,
            skipped=True,
            skip_reason="Embodiment case skipped. Re-run with --include-embodiment to execute it.",
        )
    else:
        session = ConversationSession()
        session.start()
        with apply_fault_injection(case, case_dir):
            outcome = execute_case(case, session)
        if case.archive_after_run and session.turns:
            outcome.archived_state = archive_and_inspect(session.turns)
        else:
            outcome.archived_state = inspect_memory_state()

    deterministic_failures = evaluate_case(case, outcome)
    deterministic_score = max(0, 100 - (len(deterministic_failures) * 20))
    latency_score = score_latency(case, outcome.metrics) if not outcome.skipped else 0

    judge = JudgeResult(score=0, verdict="skipped", notes="Judge skipped.", prompt_tweak="none")
    judge_score = 0
    if use_judge and case.judge_required and not outcome.skipped and outcome.exit_code == 0:
        judge = judge_reply(
            case_id=case.id,
            category=case.category,
            prompts=case.prompts,
            reply_text=outcome.reply_text,
            deterministic_failures=deterministic_failures,
        )
        judge_score = judge.score * 10

    if use_judge and case.judge_required and judge.verdict not in {"skipped", "judge_unavailable"}:
        total_score = round(
            (deterministic_score * 0.50) + (latency_score * 0.20) + (judge_score * 0.30)
        )
    else:
        total_score = round((deterministic_score * 0.75) + (latency_score * 0.25))
    passed = (
        not outcome.skipped
        and not deterministic_failures
        and outcome.exit_code == case.expected_exit_code
        and (judge.verdict != "fail")
    )

    raw_artifact = {
        "id": case.id,
        "suite": case.suite,
        "subsystem": case.subsystem,
        "category": case.category,
        "prompts": case.prompts,
        "transcript": outcome.transcript,
        "reply_text": outcome.reply_text,
        "metrics": outcome.metrics,
        "stdout": outcome.stdout,
        "stderr": outcome.stderr,
        "archived_state": outcome.archived_state,
        "skipped": outcome.skipped,
        "skip_reason": outcome.skip_reason,
        "deterministic_failures": deterministic_failures,
        "deterministic_score": deterministic_score,
        "latency_score": latency_score,
        "judge": {
            "score": judge.score,
            "verdict": judge.verdict,
            "notes": judge.notes,
            "prompt_tweak": judge.prompt_tweak,
        },
        "judge_score": judge_score,
        "total_score": total_score,
        "passed": passed,
    }
    (case_dir / "result.json").write_text(json.dumps(raw_artifact, indent=2), encoding="utf-8")
    return raw_artifact


def execute_case(case: TestCase, session: ConversationSession) -> CaseOutcome:
    if case.mode == "conversation":
        return execute_conversation_case(case, session)
    if case.mode == "speak_text":
        return execute_speak_text_case(case)
    if case.mode == "wake_ack":
        return execute_wake_ack_case()
    if case.mode == "stt_probe":
        return execute_stt_probe_case()
    raise ValueError(f"Unsupported case mode: {case.mode}")


def execute_conversation_case(case: TestCase, session: ConversationSession) -> CaseOutcome:
    transcript: list[dict] = []
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    reply_text = ""
    metrics: dict[str, float] = {}
    exit_code = 0

    for prompt in case.prompts:
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            result = run_turn(
                prompt,
                print_only=True,
                profile=False,
                session=session,
            )
        turn_stdout = stdout_buffer.getvalue()
        turn_stderr = stderr_buffer.getvalue()
        transcript.append(
            {
                "prompt": prompt,
                "stdout": turn_stdout,
                "stderr": turn_stderr,
                "reply": result.reply_text,
                "exit_code": result.exit_code,
                "metrics": result.metrics,
            }
        )
        stdout_parts.append(turn_stdout)
        stderr_parts.append(turn_stderr)
        reply_text = result.reply_text
        metrics = result.metrics
        exit_code = result.exit_code
        if result.exit_code != 0:
            break
        session.add_turn("User", prompt)
        session.add_turn("Teddy", result.reply_text)
        session.update_working_context(prompt, result.reply_text)

    return CaseOutcome(
        exit_code=exit_code,
        reply_text=reply_text,
        metrics=metrics,
        transcript=transcript,
        stdout="".join(stdout_parts),
        stderr="".join(stderr_parts),
    )


def execute_speak_text_case(case: TestCase) -> CaseOutcome:
    spoken_text = case.prompts[0] if case.prompts else ""
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = speak_text(spoken_text, print_only=False)
    return CaseOutcome(
        exit_code=exit_code,
        reply_text=spoken_text,
        transcript=[{"prompt": spoken_text, "reply": spoken_text, "exit_code": exit_code}],
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
    )


def execute_wake_ack_case() -> CaseOutcome:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        prewarm_runtime_assets()
        result = speak_wake_ack(print_only=False)
    return CaseOutcome(
        exit_code=result.exit_code,
        reply_text=config.WAKE_ACKNOWLEDGEMENT,
        metrics=result.metrics,
        transcript=[
            {
                "prompt": "<wake>",
                "reply": config.WAKE_ACKNOWLEDGEMENT,
                "exit_code": result.exit_code,
                "metrics": result.metrics,
            }
        ],
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
    )


def execute_stt_probe_case() -> CaseOutcome:
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        try:
            speech_input.transcribe_wav_bytes(make_silent_wav_bytes())
            exit_code = 0
        except speech_input.SpeechInputError as exc:
            print(str(exc), file=stderr_buffer)
            exit_code = 1
    return CaseOutcome(
        exit_code=exit_code,
        transcript=[{"prompt": "<stt_probe>", "reply": "", "exit_code": exit_code}],
        stdout=stdout_buffer.getvalue(),
        stderr=stderr_buffer.getvalue(),
    )


def configure_isolated_memory(db_path: Path) -> None:
    config.MEMORY_DB_PATH = db_path
    config.MEMORY_USE_LEGACY_FILES = False
    memory_db.init_db()


def warm_openai_path() -> None:
    """Best-effort warmup so the first grading case is not unfairly cold."""
    try:
        _ = openai_client.generate_reply("Reply with one short word: ready.")
    except Exception:
        pass


def seed_case_memory(case: TestCase) -> None:
    for fact in case.seed_facts:
        memory_db.upsert_fact(fact.category, fact.fact, fact.confidence)
    for episode in case.seed_episodes:
        memory_db.append_episode(
            topic=episode.topic,
            summary=episode.summary,
            importance_score=episode.importance_score,
            emotional_valence=episode.emotional_valence,
        )


def archive_and_inspect(transcript_entries: list[dict[str, str]]) -> dict:
    try:
        result = memory_archivist.archive_session(transcript_entries)
        state = inspect_memory_state()
        state["archivist"] = {
            "facts_written": result.facts_written,
            "episode_written": result.episode_written,
            "working_bullets_written": result.working_bullets_written,
        }
        return state
    except Exception as exc:
        state = inspect_memory_state()
        state["archivist_error"] = str(exc)
        return state


def inspect_memory_state() -> dict:
    active_facts = memory_db.get_active_facts()
    episodes = memory_db.query_episodes([], max_count=5, max_chars=2000)
    return {
        "active_facts": active_facts,
        "active_facts_text": "\n".join(
            f"{item['category']}: {item['fact']}" for item in active_facts
        ),
        "episodes": episodes,
        "episodes_text": "\n".join(
            f"{item['topic']}: {item['summary']}" for item in episodes
        ),
    }


def evaluate_case(case: TestCase, outcome: CaseOutcome) -> list[str]:
    failures: list[str] = []
    reply_text = outcome.reply_text or ""
    metrics = outcome.metrics or {}
    lowered = normalize_for_checks(reply_text)

    if outcome.skipped:
        return failures

    if outcome.exit_code != case.expected_exit_code:
        failures.append(f"exit_code_mismatch:{outcome.exit_code}")

    combined_output = f"{outcome.stdout}\n{outcome.stderr}".lower()
    for warning in case.expected_warning_substrings:
        if warning.lower() not in combined_output:
            failures.append(f"missing_warning:{warning}")

    if case.expected_exit_code == 0 and not reply_text.strip():
        failures.append("empty_reply")

    if case.expected_exit_code == 0:
        for keyword in case.expected_keywords:
            if normalize_for_checks(keyword) not in lowered:
                failures.append(f"missing_keyword:{keyword}")

        if case.expected_any_keywords and not any(
            normalize_for_checks(k) in lowered for k in case.expected_any_keywords
        ):
            failures.append("missing_any_keyword")

        for keyword in case.forbidden_keywords:
            if normalize_for_checks(keyword) in lowered:
                failures.append(f"forbidden_keyword:{keyword}")

        if case.max_reply_chars is not None and len(reply_text) > case.max_reply_chars:
            failures.append("reply_too_long")

    if case.expected_active_facts:
        facts_text = str(outcome.archived_state.get("active_facts_text", "")).lower()
        for keyword in case.expected_active_facts:
            if keyword.lower() not in facts_text:
                failures.append(f"missing_active_fact:{keyword}")

    if case.unexpected_active_facts:
        facts_text = str(outcome.archived_state.get("active_facts_text", "")).lower()
        for keyword in case.unexpected_active_facts:
            if keyword.lower() in facts_text:
                failures.append(f"unexpected_active_fact:{keyword}")

    if case.expected_episode_keywords:
        episodes_text = str(outcome.archived_state.get("episodes_text", "")).lower()
        for keyword in case.expected_episode_keywords:
            if keyword.lower() not in episodes_text:
                failures.append(f"missing_episode_keyword:{keyword}")

    if metrics.get("memory_select", 0.0) > 0.150:
        failures.append("memory_select_slow")
    if metrics.get("instruction_build", 0.0) > 0.100:
        failures.append("instruction_build_slow")
    if metrics.get("openai", 0.0) > case.max_openai_seconds:
        failures.append("openai_slow")
    if (
        case.max_first_audio_seconds is not None
        and metrics.get("first_audio", 0.0) > case.max_first_audio_seconds
    ):
        failures.append("first_audio_slow")
    if metrics.get("instruction_length", 0.0) > config.MEMORY_INSTRUCTION_TARGET_MAX_CHARS:
        failures.append("instruction_budget_exceeded")
    if case.mode == "wake_ack":
        if metrics.get("audio_ready", 0.0) > 1.5:
            failures.append("wake_audio_ready_slow")
        if metrics.get("play_start", 0.0) > 0.25:
            failures.append("wake_play_start_slow")

    return failures


def score_latency(case: TestCase, metrics: dict[str, float]) -> int:
    score = 100
    if metrics.get("memory_select", 0.0) > 0.150:
        score -= 20
    if metrics.get("instruction_build", 0.0) > 0.100:
        score -= 15
    if metrics.get("openai", 0.0) > case.max_openai_seconds:
        score -= 35
    if (
        case.max_first_audio_seconds is not None
        and metrics.get("first_audio", 0.0) > case.max_first_audio_seconds
    ):
        score -= 25
    if metrics.get("total", 0.0) > case.max_total_seconds:
        score -= 20
    if case.mode == "wake_ack":
        if metrics.get("audio_ready", 0.0) > 1.5:
            score -= 35
        if metrics.get("play_start", 0.0) > 0.25:
            score -= 25
    return max(0, score)


def apply_fault_injection(case: TestCase, case_dir: Path):
    stack = ExitStack()
    fault = case.fault_injection
    if fault is None:
        return stack

    if fault.mode == "openai_unavailable":
        stack.enter_context(mock.patch.object(openai_client, "_client", None))
        stack.enter_context(mock.patch.object(openai_client, "_get_client", side_effect=RuntimeError("simulated openai outage")))
    elif fault.mode == "tts_unavailable":
        stack.enter_context(
            mock.patch.object(
                tts_client,
                "synthesize_to_wav_bytes",
                side_effect=tts_client.TtsError("simulated tts outage"),
            )
        )
    elif fault.mode == "stt_unavailable":
        stack.enter_context(
            mock.patch.object(
                speech_input.urllib.request,
                "urlopen",
                side_effect=urllib.error.URLError("simulated stt outage"),
            )
        )
    elif fault.mode == "mouth_unavailable":
        stack.enter_context(mock.patch.object(config, "ENABLE_MOUTH", True))
        stack.enter_context(mock.patch("runtime.teddy_loop.mouth_client.is_available", return_value=False))
        stack.enter_context(
            mock.patch.object(tts_client, "synthesize_to_wav_bytes", return_value=make_silent_wav_bytes())
        )
        stack.enter_context(mock.patch.object(audio_player, "play_wav_bytes", return_value=0.05))
    elif fault.mode == "wake_cache_miss":
        isolated_cache_dir = case_dir / "wake-cache"
        isolated_cache_path = isolated_cache_dir / "wake-ack.wav"
        stack.enter_context(mock.patch.object(config, "WAKE_CACHE_DIR", isolated_cache_dir))
        stack.enter_context(mock.patch.object(config, "WAKE_ACK_CACHE_PATH", isolated_cache_path))
        isolated_cache_dir.mkdir(parents=True, exist_ok=True)
        if isolated_cache_path.exists():
            isolated_cache_path.unlink()
        stack.enter_context(
            mock.patch.object(tts_client, "synthesize_to_wav_bytes", return_value=make_silent_wav_bytes())
        )
        stack.enter_context(
            mock.patch.object(audio_player, "play_wav_bytes_persistent", return_value=(0.05, 0.01))
        )
        stack.enter_context(
            mock.patch.object(audio_player, "prewarm_persistent_output_for_wav_bytes", return_value=None)
        )
    else:
        raise ValueError(f"Unsupported fault mode: {fault.mode}")
    return stack


def make_silent_wav_bytes(duration_seconds: float = 0.12, sample_rate: int = 22050) -> bytes:
    frame_count = max(1, int(duration_seconds * sample_rate))
    payload = b"".join(struct.pack("<h", 0) for _ in range(frame_count))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(payload)
    return buffer.getvalue()


def normalize_for_checks(text: str) -> str:
    normalized = text.lower()
    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


if __name__ == "__main__":
    raise SystemExit(main())

