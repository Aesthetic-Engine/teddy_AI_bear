from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SeedFact:
    category: str
    fact: str
    confidence: float = 0.95


@dataclass
class SeedEpisode:
    topic: str
    summary: str
    importance_score: int = 7
    emotional_valence: str = "neutral"


@dataclass
class FaultInjection:
    mode: str
    notes: str = ""


@dataclass
class TestCase:
    id: str
    suite: str
    subsystem: str
    category: str
    prompts: list[str]
    expected_keywords: list[str] = field(default_factory=list)
    expected_any_keywords: list[str] = field(default_factory=list)
    forbidden_keywords: list[str] = field(default_factory=list)
    max_reply_chars: int | None = None
    seed_facts: list[SeedFact] = field(default_factory=list)
    seed_episodes: list[SeedEpisode] = field(default_factory=list)
    archive_after_run: bool = False
    expected_active_facts: list[str] = field(default_factory=list)
    unexpected_active_facts: list[str] = field(default_factory=list)
    expected_episode_keywords: list[str] = field(default_factory=list)
    fault_injection: FaultInjection | None = None
    expected_exit_code: int = 0
    expected_warning_substrings: list[str] = field(default_factory=list)
    mode: str = "conversation"
    enable_audio: bool = False
    max_openai_seconds: float = 5.0
    max_total_seconds: float = 6.0
    max_first_audio_seconds: float | None = None
    judge_required: bool = True
    notes: str = ""


def get_stage_one_cases() -> list[TestCase]:
    return [
        TestCase(
            id="spoken_brevity",
            suite="stage1",
            subsystem="persona",
            category="persona",
            prompts=["In one short sentence, why does memory matter for Teddy?"],
            expected_any_keywords=["memory", "remember", "continuity"],
            max_reply_chars=180,
            notes="Checks short spoken-style response and basic relevance.",
        ),
        TestCase(
            id="identity_check",
            suite="stage1",
            subsystem="persona",
            category="persona",
            prompts=["What are you, in one or two short sentences?"],
            expected_any_keywords=["teddy", "bear"],
            forbidden_keywords=["markdown", "policy"],
            notes="Checks identity continuity and non-corporate tone.",
        ),
        TestCase(
            id="memory_recall_preference",
            suite="stage1",
            subsystem="memory_integrity",
            category="memory",
            prompts=["Do I prefer PlayStation or Nintendo 64?"],
            expected_keywords=["playstation"],
            forbidden_keywords=["don't know", "not sure"],
            seed_facts=[
                SeedFact("preference", "User prefers PlayStation over Nintendo 64."),
            ],
            notes="Checks durable fact recall from structured memory.",
        ),
        TestCase(
            id="memory_no_hallucination",
            suite="stage1",
            subsystem="memory_integrity",
            category="memory",
            prompts=["What game system do I prefer?"],
            expected_any_keywords=["don't know", "not sure", "tell me", "you haven't"],
            forbidden_keywords=["playstation", "nintendo 64"],
            notes="Checks that Teddy does not invent absent preferences.",
        ),
        TestCase(
            id="episodic_recall",
            suite="stage1",
            subsystem="memory_integrity",
            category="memory",
            prompts=["Do you remember what we were working on?"],
            expected_any_keywords=["memory", "continuity", "project teddy"],
            seed_episodes=[
                SeedEpisode(
                    topic="memory redesign",
                    summary="The user and Teddy worked on a structured memory rewrite to improve continuity and reduce prompt bloat.",
                    importance_score=9,
                    emotional_valence="focused",
                )
            ],
            notes="Checks episodic retrieval for explicit past-reference prompts.",
        ),
        TestCase(
            id="followup_continuity",
            suite="stage1",
            subsystem="continuity",
            category="continuity",
            prompts=[
                "We are redesigning your memory system so you can keep continuity without getting bloated.",
                "And what matters most there?",
            ],
            expected_any_keywords=[
                "continuity",
                "memory",
                "context",
                "identity",
                "relationship",
                "ongoing work",
                "relevance",
                "restraint",
                "consistent",
                "recognize",
                "trust",
            ],
            notes="Checks same-session follow-up handling with recent-turn context.",
        ),
        TestCase(
            id="technical_help",
            suite="stage1",
            subsystem="helpfulness",
            category="helpfulness",
            prompts=["Give me two short practical ways to reduce Teddy's response latency."],
            expected_any_keywords=[
                "latency",
                "prewarm",
                "cache",
                "profile",
                "faster",
                "stream",
                "startup",
                "warm",
            ],
            notes="Checks technical usefulness and directness.",
        ),
    ]


def get_stage_two_cases() -> list[TestCase]:
    return [
        TestCase(
            id="fact_update_preference",
            suite="stage2",
            subsystem="memory_integrity",
            category="memory_evolution",
            prompts=[
                "I used to prefer PlayStation over Nintendo 64, but that changed. I prefer Nintendo 64 now. Please remember that.",
                "What game system do I prefer now?",
            ],
            seed_facts=[
                SeedFact("preference", "User prefers PlayStation over Nintendo 64."),
            ],
            archive_after_run=True,
            expected_keywords=["nintendo 64"],
            expected_active_facts=["nintendo 64"],
            unexpected_active_facts=["playstation over nintendo 64"],
            notes="Checks preference updates and contradiction resolution.",
        ),
        TestCase(
            id="ignore_ephemeral_chatter",
            suite="stage2",
            subsystem="selective_forgetting",
            category="forgetting",
            prompts=[
                "I'm going to stretch my legs for a minute, and it looks like rain outside.",
                "By the way, I prefer black coffee.",
                "Can you remember what matters from this conversation?",
            ],
            archive_after_run=True,
            expected_any_keywords=["black coffee", "coffee"],
            expected_active_facts=["black coffee"],
            unexpected_active_facts=["stretch my legs", "rain outside"],
            notes="Checks that salient facts persist but transient chatter is dropped.",
        ),
        TestCase(
            id="failure_openai_unavailable",
            suite="stage2",
            subsystem="failure_recovery",
            category="failure",
            prompts=["Please answer this if you can."],
            fault_injection=FaultInjection(mode="openai_unavailable"),
            expected_exit_code=1,
            expected_warning_substrings=["Teddy reply error:"],
            judge_required=False,
            notes="Checks graceful failure when the OpenAI path is unavailable.",
        ),
        TestCase(
            id="failure_tts_unavailable",
            suite="stage2",
            subsystem="failure_recovery",
            category="failure",
            prompts=["Please say this line aloud."],
            fault_injection=FaultInjection(mode="tts_unavailable"),
            expected_exit_code=1,
            expected_warning_substrings=["Teddy speech error:"],
            mode="speak_text",
            judge_required=False,
            notes="Checks graceful failure when TTS fails.",
        ),
        TestCase(
            id="failure_stt_unavailable",
            suite="stage2",
            subsystem="failure_recovery",
            category="failure",
            prompts=["This case probes STT availability."],
            fault_injection=FaultInjection(mode="stt_unavailable"),
            expected_exit_code=1,
            expected_warning_substrings=["STT service is unavailable."],
            mode="stt_probe",
            judge_required=False,
            notes="Checks clean failure when STT is unavailable.",
        ),
        TestCase(
            id="failure_mouth_bridge_unavailable",
            suite="stage2",
            subsystem="failure_recovery",
            category="failure",
            prompts=["The mouth bridge may be unavailable, but Teddy should still work."],
            fault_injection=FaultInjection(mode="mouth_unavailable"),
            expected_exit_code=0,
            expected_warning_substrings=["Teddy mouth warning:"],
            mode="speak_text",
            judge_required=False,
            notes="Checks voice-only fallback when the mouth bridge is unavailable.",
        ),
        TestCase(
            id="failure_wake_cache_miss",
            suite="stage2",
            subsystem="failure_recovery",
            category="failure",
            prompts=["Wake cache refresh path"],
            fault_injection=FaultInjection(mode="wake_cache_miss"),
            expected_exit_code=0,
            mode="wake_ack",
            judge_required=False,
            notes="Checks wake acknowledgement still works when the cache must be regenerated.",
        ),
        TestCase(
            id="endurance_10_turns_technical",
            suite="stage2",
            subsystem="continuity",
            category="endurance",
            prompts=[
                "We need a memory system that stays lean.",
                "It should remember facts, but not hoard junk.",
                "It also needs to stay fast.",
                "And it should update preferences cleanly.",
                "I want Teddy to feel continuous over months.",
                "But I do not want recursive summary drift.",
                "We also need selective forgetting.",
                "And graceful failure when services go down.",
                "Wake performance still matters too.",
                "What are the three main pillars we settled on?",
            ],
            expected_any_keywords=["memory", "continuity", "forget", "latency", "failure", "relevance"],
            notes="Checks long multi-turn continuity and retention of a technical thread.",
        ),
        TestCase(
            id="response_latency_short_sentences",
            suite="stage2",
            subsystem="continuity",
            category="responsiveness",
            prompts=["In three short sentences, what matters most about Teddy's memory system?"],
            expected_any_keywords=["memory", "durable", "remember", "matters", "user"],
            max_first_audio_seconds=3.5,
            max_total_seconds=16.0,
            notes="Checks that a normal memory-related answer starts speaking quickly.",
        ),
        TestCase(
            id="wake_ack_fast_path",
            suite="stage2",
            subsystem="wake_embodiment",
            category="wake",
            prompts=["Wake acknowledgement benchmark"],
            mode="wake_ack",
            enable_audio=True,
            judge_required=False,
            notes="Measures cached wake-ack latency and wake-profile-like metrics.",
        ),
        TestCase(
            id="uncertainty_required",
            suite="stage2",
            subsystem="ambiguity_and_pressure",
            category="ambiguity",
            prompts=["I prefer black coffee.", "Do I usually drink it hot or iced?"],
            archive_after_run=True,
            expected_any_keywords=["don't know", "not sure", "you haven't", "tell me"],
            forbidden_keywords=["you do", "definitely"],
            notes="Checks honest uncertainty on a near-match memory question.",
        ),
        TestCase(
            id="prompt_pressure_continuity",
            suite="stage2",
            subsystem="ambiguity_and_pressure",
            category="pressure",
            prompts=[
                (
                    "We have a memory system, a wake path, a mouth path, a grading suite, and a long "
                    "retrospective. The memory system needs continuity, selective forgetting, low latency, "
                    "clean updates, and stable identity. The wake path needs to feel human and alive. "
                    "The grading suite needs to catch regressions without making Teddy brittle. With all of "
                    "that in mind, what matters most?"
                )
            ],
            expected_any_keywords=["relevance", "identity", "continuity", "trust", "memory"],
            max_openai_seconds=10.0,
            max_total_seconds=10.0,
            notes="Checks pressure handling under a dense prompt without hostile user behavior.",
        ),
    ]


def get_test_cases(suite: str = "stage1") -> list[TestCase]:
    if suite == "stage1":
        return get_stage_one_cases()
    if suite == "stage2":
        return get_stage_two_cases()
    if suite == "all":
        return [*get_stage_one_cases(), *get_stage_two_cases()]
    raise ValueError(f"Unknown suite: {suite}")

