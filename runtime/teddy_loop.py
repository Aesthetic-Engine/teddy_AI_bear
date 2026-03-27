from __future__ import annotations

import argparse
import queue
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field

from . import (
    audio_player,
    config,
    lipsync,
    memory_archivist,
    memory_db,
    memory_store,
    mouth_client,
    openai_client,
    speech_input,
    tts_client,
)


@dataclass
class TurnResult:
    exit_code: int
    reply_text: str = ""
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class ConversationSession:
    turns: list[dict[str, str]] = field(default_factory=list)
    recent_turns: list[dict[str, str]] = field(default_factory=list)
    working_bullets: list[str] = field(default_factory=list)
    active: bool = False
    deadline: float = 0.0
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def start(self) -> None:
        self.session_id = uuid.uuid4().hex
        self.active = True
        self.bump_deadline()

    def bump_deadline(self) -> None:
        self.deadline = time.monotonic() + config.SESSION_IDLE_TIMEOUT_SECONDS

    def add_turn(self, speaker: str, text: str) -> None:
        collapsed = " ".join(text.strip().split())
        if not collapsed:
            return

        self.turns.append({"speaker": speaker, "text": collapsed})
        self.recent_turns.append({"speaker": speaker, "text": collapsed})
        while len(self.turns) > config.SESSION_MAX_TRANSCRIPT_ENTRIES:
            self.turns.pop(0)
        while transcript_char_count(self.turns) > config.SESSION_MAX_TRANSCRIPT_CHARS:
            if not self.turns:
                break
            self.turns.pop(0)
        while len(self.recent_turns) > config.MEMORY_RECENT_TURNS_MAX_COUNT:
            self.recent_turns.pop(0)
        while transcript_char_count(self.recent_turns) > config.MEMORY_RECENT_TURNS_MAX_CHARS:
            if not self.recent_turns:
                break
            self.recent_turns.pop(0)

    def remaining_seconds(self) -> float:
        if not self.active:
            return 0.0
        return max(0.0, self.deadline - time.monotonic())

    def should_summarize(self) -> bool:
        return len(self.turns) >= config.SESSION_MIN_TRANSCRIPT_ENTRIES

    def clear(self) -> None:
        self.turns.clear()
        self.recent_turns.clear()
        self.working_bullets.clear()
        self.active = False
        self.deadline = 0.0

    def update_working_context(self, user_text: str, reply_text: str) -> None:
        user_bullet = first_clause(user_text, 120)
        reply_bullet = first_clause(reply_text, 140)
        for bullet in (
            f"User is focused on: {user_bullet}",
            f"Teddy most recently said: {reply_bullet}",
        ):
            if bullet in self.working_bullets:
                continue
            self.working_bullets.append(bullet)
        while len(self.working_bullets) > config.MEMORY_WORKING_MAX_BULLETS:
            self.working_bullets.pop(0)

    def working_summary(self) -> str:
        return "\n".join(f"- {bullet}" for bullet in self.working_bullets)

    def as_prompt_context(self) -> dict:
        return {
            "session_id": self.session_id,
            "recent_turns": list(self.recent_turns),
            "working_summary": self.working_summary(),
        }


@dataclass
class PlaybackSegment:
    audio_bytes: bytes
    viseme_cues: list[lipsync.VisemeCue] | None = None


@dataclass
class WakeAckResult:
    exit_code: int
    metrics: dict[str, float] = field(default_factory=dict)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teddy MVP local loop")
    parser.add_argument("--once", action="store_true", help="Run a single turn and exit")
    parser.add_argument("--text", default="", help="Input text for --once mode")
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print Teddy's reply without TTS or mouth movement",
    )
    parser.add_argument(
        "--auto-listen",
        action="store_true",
        help="Use the default microphone for automatic turn-taking",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        help="Print per-turn timing information",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        verify_core_files()
        memory_db.init_db()
        prewarm_runtime_assets()
    except RuntimeError as exc:
        print(f"Teddy startup error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Teddy memory startup error: {exc}", file=sys.stderr)
        return 1

    if args.once:
        if not args.text.strip():
            print("Teddy startup error: --text is required with --once.", file=sys.stderr)
            return 1
        return run_turn(args.text, print_only=args.print_only, profile=args.profile).exit_code

    if args.auto_listen:
        return run_auto_listen(args)

    print("Teddy is awake. Type a message and press Enter. Type 'exit' to stop.")
    while True:
        try:
            user_text = input("User> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit"}:
            return 0

        result = run_turn(
            user_text,
            print_only=args.print_only,
            profile=args.profile,
        )
        if result.exit_code != 0:
            return result.exit_code


def run_turn(
    user_text: str,
    print_only: bool,
    profile: bool,
    speech_result: speech_input.SpeechResult | None = None,
    session: ConversationSession | None = None,
) -> TurnResult:
    total_started = time.perf_counter()
    openai_elapsed = 0.0
    memory_select_elapsed = 0.0
    instruction_build_elapsed = 0.0
    first_audio_elapsed = 0.0
    tts_elapsed = 0.0
    playback_elapsed = 0.0
    reply_text = ""
    tts_thread: threading.Thread | None = None
    playback_thread: threading.Thread | None = None
    tts_error: Exception | None = None
    playback_error: Exception | None = None
    spoken_ready = threading.Event()
    stop_event = threading.Event()
    queued_segments: queue.Queue[str | None] = queue.Queue()
    queued_audio: queue.Queue[PlaybackSegment | None] = queue.Queue()
    mouth_enabled = config.ENABLE_MOUTH
    openai_metrics: dict[str, float] = {}

    if mouth_enabled and not mouth_client.is_available():
        print("Teddy mouth warning: mouth bridge is unavailable, so voice will run without motion.")
        mouth_enabled = False

    def tts_worker() -> None:
        nonlocal tts_elapsed, tts_error

        while not stop_event.is_set():
            segment = queued_segments.get()
            if segment is None:
                queued_audio.put(None)
                break

            try:
                tts_started = time.perf_counter()
                audio_bytes = tts_client.synthesize_to_wav_bytes(segment)
                tts_elapsed += time.perf_counter() - tts_started
                viseme_cues: list[lipsync.VisemeCue] | None = None
                use_viseme = (
                    mouth_enabled
                    and config.MOUTH_SYNC_MODE == "viseme"
                    and config.MOUTH_STREAMING_SYNC_MODE == "viseme"
                )
                if use_viseme:
                    try:
                        viseme_cues = lipsync.generate_viseme_cues(audio_bytes, segment)
                    except lipsync.LipSyncError as exc:
                        print(
                            f"Teddy mouth warning: {exc} Falling back to audio-driven sync.",
                            file=sys.stderr,
                        )
                queued_audio.put(
                    PlaybackSegment(audio_bytes=audio_bytes, viseme_cues=viseme_cues)
                )
            except Exception as exc:
                tts_error = exc
                stop_event.set()
                queued_audio.put(None)
                break

    def playback_worker() -> None:
        nonlocal first_audio_elapsed, playback_elapsed, playback_error

        while not stop_event.is_set():
            segment = queued_audio.get()
            if segment is None:
                break

            try:
                playback_started = time.perf_counter()
                if not spoken_ready.is_set():
                    first_audio_elapsed = playback_started - total_started
                    spoken_ready.set()
                mouth_sync = (
                    mouth_client.create_sync(segment.viseme_cues) if mouth_enabled else None
                )
                try:
                    audio_player.play_wav_bytes_persistent(
                        segment.audio_bytes,
                        chunk_callback=mouth_sync.on_audio_chunk if mouth_sync else None,
                    )
                finally:
                    if mouth_sync is not None:
                        mouth_sync.finish()
                playback_elapsed += time.perf_counter() - playback_started
            except Exception as exc:
                playback_error = exc
                stop_event.set()
                spoken_ready.set()
                break

    try:
        if not print_only:
            tts_thread = threading.Thread(
                target=tts_worker,
                daemon=True,
                name="teddy-tts-queue",
            )
            playback_thread = threading.Thread(
                target=playback_worker,
                daemon=True,
                name="teddy-speech-queue",
            )
            tts_thread.start()
            playback_thread.start()

        started = time.perf_counter()
        reply_parts: list[str] = []
        pending_text = ""
        for delta in openai_client.stream_reply_text(
            user_text,
            session_context=session.as_prompt_context() if session else None,
            profile_metrics=openai_metrics,
        ):
            reply_parts.append(delta)
            pending_text += delta
            completed_sentences, pending_text = pop_complete_sentences(pending_text)
            if not print_only:
                for sentence in completed_sentences:
                    queued_segments.put(sentence)

        reply_text = "".join(reply_parts).strip()
        openai_elapsed = time.perf_counter() - started
        memory_select_elapsed = openai_metrics.get("memory_select", 0.0)
        instruction_build_elapsed = openai_metrics.get("instruction_build", 0.0)
        if openai_metrics.get("openai"):
            openai_elapsed = openai_metrics["openai"]
        print(f"Teddy> {reply_text}")
    except openai_client.OpenAIError as exc:
        stop_event.set()
        if tts_thread is not None:
            queued_segments.put(None)
            tts_thread.join()
        if playback_thread is not None:
            queued_audio.put(None)
            playback_thread.join()
        print(f"Teddy reply error: {exc}", file=sys.stderr)
        return TurnResult(exit_code=1, metrics=dict(openai_metrics))

    if not print_only:
        try:
            trailing_segment = pending_text.strip()
            if trailing_segment:
                queued_segments.put(trailing_segment)
            queued_segments.put(None)
            if tts_thread is not None:
                tts_thread.join()
            if tts_error is not None:
                if isinstance(tts_error, tts_client.TtsError):
                    print(f"Teddy speech error: {tts_error}", file=sys.stderr)
                else:
                    print(f"Teddy audio error: {tts_error}", file=sys.stderr)
                return TurnResult(exit_code=1, metrics=dict(openai_metrics))
            if playback_thread is not None:
                playback_thread.join()
            if playback_error is not None:
                if isinstance(playback_error, tts_client.TtsError):
                    print(f"Teddy speech error: {playback_error}", file=sys.stderr)
                else:
                    print(f"Teddy audio error: {playback_error}", file=sys.stderr)
                return TurnResult(exit_code=1, metrics=dict(openai_metrics))
        except Exception as exc:
            print(f"Teddy audio error: {exc}", file=sys.stderr)
            return TurnResult(exit_code=1, metrics=dict(openai_metrics))

    if config.MEMORY_USE_LEGACY_FILES:
        try:
            memory_store.append_daily_note(
                topic=derive_topic(user_text),
                key_fact=derive_key_fact(reply_text),
                follow_up="Continue this thread if the user returns to it.",
                durable_candidate=False,
            )
        except Exception as exc:
            print(f"Teddy memory warning: {exc}", file=sys.stderr)

    total_elapsed = time.perf_counter() - total_started
    first_audio = first_audio_elapsed if first_audio_elapsed else (openai_elapsed + tts_elapsed)
    metrics = {
        "first_audio": first_audio,
        "stt_capture": speech_result.capture_seconds if speech_result else 0.0,
        "stt_request": speech_result.stt_seconds if speech_result else 0.0,
        "memory_select": memory_select_elapsed,
        "instruction_build": instruction_build_elapsed,
        "instruction_length": openai_metrics.get("instruction_length", 0.0),
        "input_length": openai_metrics.get("input_length", 0.0),
        "openai": openai_elapsed,
        "tts": tts_elapsed,
        "playback": playback_elapsed,
        "total": total_elapsed,
    }
    if profile or config.PROFILE_TURNS:
        print(
            "[profile] "
            f"first_audio={metrics['first_audio']:.3f}s "
            f"stt_capture={metrics['stt_capture']:.3f}s "
            f"stt_request={metrics['stt_request']:.3f}s "
            f"memory_select={metrics['memory_select']:.3f}s "
            f"instruction_build={metrics['instruction_build']:.3f}s "
            f"openai={metrics['openai']:.3f}s "
            f"tts={metrics['tts']:.3f}s "
            f"playback={metrics['playback']:.3f}s "
            f"total={metrics['total']:.3f}s"
        )

    return TurnResult(exit_code=0, reply_text=reply_text, metrics=metrics)


def run_auto_listen(args: argparse.Namespace) -> int:
    session = ConversationSession()
    pending_wake_text = ""
    print("Teddy is awake. Say 'hey teddy' to begin. Press Ctrl+C to stop.")

    while True:
        try:
            if not session.active:
                wake_result = speech_input.wait_for_wake_word_result()
                pending_wake_text = (
                    wake_result.trailing_text.strip()
                    if should_carry_wake_trailing_text(wake_result)
                    else ""
                )
                session.start()
                print("Teddy is listening.")
                ack_result = speak_wake_ack(print_only=args.print_only)
                if args.profile or config.PROFILE_TURNS:
                    total_post_match = wake_result.return_gap_seconds + ack_result.metrics.get(
                        "play_start", 0.0
                    )
                    print(
                        "[wake-profile] "
                        f"detect={wake_result.detect_seconds:.3f}s "
                        f"source={wake_result.source} "
                        f"match_to_return={wake_result.return_gap_seconds:.3f}s "
                        f"audio_ready={ack_result.metrics.get('audio_ready', 0.0):.3f}s "
                        f"play_start={ack_result.metrics.get('play_start', 0.0):.3f}s "
                        f"total_post_match={total_post_match:.3f}s"
                    )
                if ack_result.exit_code != 0:
                    summarize_session_if_needed(session)
                    return ack_result.exit_code
                session.bump_deadline()
                continue

            remaining = session.remaining_seconds()
            if remaining <= 0:
                summarize_session_if_needed(session)
                session.clear()
                pending_wake_text = ""
                continue

            speech: speech_input.SpeechResult
            if pending_wake_text:
                continuation_window = min(
                    remaining,
                    max(0.35, config.WAKE_TRAILING_CONTINUATION_SECONDS),
                )
                continuation = speech_input.listen_once(
                    initial_timeout_seconds=continuation_window,
                    max_listen_seconds=continuation_window + config.STT_SPEECH_END_SECONDS,
                )
                combined_text = merge_recognized_text(pending_wake_text, continuation.text)
                if continuation.text.strip():
                    speech = speech_input.SpeechResult(
                        text=combined_text,
                        heard_speech=True,
                        capture_seconds=continuation.capture_seconds,
                        stt_seconds=continuation.stt_seconds,
                        total_seconds=continuation.total_seconds,
                        empty_reason=continuation.empty_reason,
                    )
                elif is_substantive_wake_trailing_text(pending_wake_text):
                    speech = speech_input.SpeechResult(
                        text=pending_wake_text,
                        heard_speech=True,
                        capture_seconds=continuation.capture_seconds,
                        stt_seconds=continuation.stt_seconds,
                        total_seconds=continuation.total_seconds,
                        empty_reason="",
                    )
                else:
                    speech = continuation
                pending_wake_text = ""
            else:
                initial_timeout = min(remaining, config.STT_INITIAL_TIMEOUT_SECONDS)
                speech = speech_input.listen_once(
                    initial_timeout_seconds=initial_timeout,
                    max_listen_seconds=remaining + config.STT_SPEECH_END_SECONDS + 1.0,
                )
            if not speech.text:
                if speech.heard_speech:
                    print("Teddy heard something, but couldn't make it out.")
                if session.remaining_seconds() <= 0:
                    summarize_session_if_needed(session)
                    session.clear()
                    pending_wake_text = ""
                continue

            print(f"User> {speech.text}")
            result = run_turn(
                speech.text,
                print_only=args.print_only,
                profile=args.profile,
                speech_result=speech,
                session=session,
            )
            if result.exit_code != 0:
                summarize_session_if_needed(session)
                return result.exit_code
            session.add_turn("User", speech.text)
            session.add_turn("Teddy", result.reply_text)
            session.update_working_context(speech.text, result.reply_text)
            session.bump_deadline()
        except speech_input.SpeechInputError as exc:
            print(f"Teddy microphone error: {exc}", file=sys.stderr)
            summarize_session_if_needed(session)
            return 1
        except KeyboardInterrupt:
            print()
            summarize_session_if_needed(session)
            return 0


def verify_core_files() -> None:
    missing = [str(path) for path in config.CORE_WORKSPACE_FILES if not path.exists()]
    if missing:
        raise RuntimeError("Missing core workspace files: " + ", ".join(missing))


def merge_recognized_text(prefix: str, suffix: str) -> str:
    first = " ".join(prefix.strip().split())
    second = " ".join(suffix.strip().split())
    if not first:
        return second
    if not second:
        return first

    lowered_first = first.lower()
    lowered_second = second.lower()
    if lowered_second.startswith(lowered_first):
        return second
    if lowered_first.endswith(lowered_second):
        return first

    max_overlap = min(len(lowered_first), len(lowered_second))
    for size in range(max_overlap, 0, -1):
        if lowered_first.endswith(lowered_second[:size]):
            return (first + second[size:]).strip()
    return f"{first} {second}".strip()


def should_carry_wake_trailing_text(wake_result: speech_input.WakeWordResult) -> bool:
    trailing = " ".join(wake_result.trailing_text.strip().split())
    if not trailing:
        return False
    if wake_result.source == "final":
        return True
    return is_substantive_wake_trailing_text(trailing)


def is_substantive_wake_trailing_text(text: str) -> bool:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return False
    words = re.findall(r"[a-zA-Z0-9']+", cleaned)
    if len(words) >= 3:
        return True
    if len(words) >= 2 and sum(len(word) for word in words) >= 10:
        return True
    return False


def summarize_session_if_needed(session: ConversationSession) -> None:
    if not session.should_summarize():
        return

    try:
        result = memory_archivist.archive_session(session.turns)
        if config.MEMORY_USE_LEGACY_FILES:
            summary = openai_client.summarize_session(session.turns)
            memory_store.write_session_summary(summary, len(session.turns))
        if config.PROFILE_TURNS:
            print(
                "[memory] "
                f"facts={result.facts_written} "
                f"episode={'yes' if result.episode_written else 'no'} "
                f"working_bullets={result.working_bullets_written}"
            )
    except Exception as exc:
        print(f"Teddy memory warning: {exc}", file=sys.stderr)


def prewarm_runtime_assets() -> None:
    """Best-effort warmup so the first wake acknowledgement is faster."""
    try:
        speech_input.prewarm_wake_model()
    except Exception as exc:
        print(f"Teddy wake-model warning: {exc}", file=sys.stderr)

    try:
        tts_client.prewarm_tts()
    except Exception as exc:
        print(f"Teddy warmup warning: {exc}", file=sys.stderr)

    try:
        wake_wav = tts_client.get_cached_wake_ack_wav()
        audio_player.prewarm_persistent_output_for_wav_bytes(wake_wav)
    except Exception as exc:
        print(f"Teddy wake-cache warning: {exc}", file=sys.stderr)


def speak_wake_ack(print_only: bool) -> WakeAckResult:
    """Play a cached wake acknowledgement with a live-TTS fallback."""
    spoken_text = " ".join(config.WAKE_ACKNOWLEDGEMENT.strip().split())
    if not spoken_text:
        return WakeAckResult(exit_code=0)

    print(f"Teddy> {spoken_text}")
    if print_only:
        return WakeAckResult(exit_code=0)

    started = time.perf_counter()
    if config.WAKE_ACK_DELAY_SECONDS > 0:
        time.sleep(config.WAKE_ACK_DELAY_SECONDS)
    mouth_enabled = config.ENABLE_MOUTH and config.WAKE_ACK_ENABLE_MOUTH
    if mouth_enabled and not mouth_client.is_available():
        print("Teddy mouth warning: mouth bridge is unavailable, so voice will run without motion.")
        mouth_enabled = False

    try:
        audio_bytes = tts_client.get_cached_wake_ack_wav()
        audio_ready = time.perf_counter() - started
        # For the wake acknowledgement, prefer the cheap audio-driven mouth path.
        # This keeps the mouth moving without paying Rhubarb/viseme latency before
        # the first audible acknowledgement starts.
        mouth_sync = mouth_client.create_audio_sync() if mouth_enabled else None
        try:
            playback_started = time.perf_counter()
            audio_player.play_wav_bytes(
                audio_bytes,
                chunk_callback=mouth_sync.on_audio_chunk if mouth_sync else None,
            )
            play_start = time.perf_counter() - playback_started
        finally:
            if mouth_sync is not None:
                mouth_sync.finish()
        return WakeAckResult(
            exit_code=0,
            metrics={
                "audio_ready": audio_ready,
                "play_start": play_start,
            },
        )
    except Exception:
        fallback_code = speak_text(spoken_text, print_only=False)
        return WakeAckResult(exit_code=fallback_code)


def speak_text(text: str, print_only: bool) -> int:
    spoken_text = " ".join(text.strip().split())
    if not spoken_text:
        return 0

    print(f"Teddy> {spoken_text}")
    if print_only:
        return 0

    mouth_enabled = config.ENABLE_MOUTH
    if mouth_enabled and not mouth_client.is_available():
        print("Teddy mouth warning: mouth bridge is unavailable, so voice will run without motion.")
        mouth_enabled = False

    try:
        audio_bytes = tts_client.synthesize_to_wav_bytes(spoken_text)
        viseme_cues: list[lipsync.VisemeCue] | None = None
        if mouth_enabled and config.MOUTH_SYNC_MODE == "viseme":
            try:
                viseme_cues = lipsync.generate_viseme_cues(audio_bytes, spoken_text)
            except lipsync.LipSyncError as exc:
                print(
                    f"Teddy mouth warning: {exc} Falling back to audio-driven sync.",
                    file=sys.stderr,
                )
        mouth_sync = mouth_client.create_sync(viseme_cues) if mouth_enabled else None
        try:
            audio_player.play_wav_bytes(
                audio_bytes,
                chunk_callback=mouth_sync.on_audio_chunk if mouth_sync else None,
            )
        finally:
            if mouth_sync is not None:
                mouth_sync.finish()
        return 0
    except tts_client.TtsError as exc:
        print(f"Teddy speech error: {exc}", file=sys.stderr)
    except audio_player.AudioPlaybackError as exc:
        print(f"Teddy audio error: {exc}", file=sys.stderr)
    except Exception as exc:
        print(f"Teddy audio error: {exc}", file=sys.stderr)
    return 1


def derive_topic(user_text: str) -> str:
    return first_clause(user_text, 90)


def derive_key_fact(reply_text: str) -> str:
    return first_clause(reply_text, 120)


def first_clause(text: str, limit: int) -> str:
    raw = " ".join(text.strip().split())
    if not raw:
        return "none"

    for separator in (". ", "? ", "! ", "; "):
        if separator in raw:
            raw = raw.split(separator, 1)[0]
            break

    if len(raw) <= limit:
        return raw
    return raw[: limit - 3].rstrip() + "..."


def pop_complete_sentences(text: str) -> tuple[list[str], str]:
    pending = text.lstrip()
    sentences: list[str] = []

    while pending:
        match = re.match(r"(.+?[.!?][\"')\]]*)(?:(?:\s+)|$)", pending, re.S)
        if not match:
            break
        sentence = match.group(1).strip()
        if sentence:
            sentences.append(sentence)
        pending = pending[match.end() :].lstrip()

    return sentences, pending


def transcript_char_count(turns: list[dict[str, str]]) -> int:
    return sum(len(turn.get("speaker", "")) + len(turn.get("text", "")) for turn in turns)


if __name__ == "__main__":
    raise SystemExit(main())
