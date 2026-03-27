from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def write_json_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_markdown_report(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    run_id = payload["run_id"]
    suite = payload.get("suite", "stage1")
    created_at = payload["created_at"]
    overall = payload["overall"]
    cases = payload["cases"]
    subsystems = payload.get("subsystems", [])

    lines: list[str] = [
        "# Teddy Report Card",
        "",
        f"- Run ID: `{run_id}`",
        f"- Suite: `{suite}`",
        f"- Created: `{created_at}`",
        f"- Overall Grade: **{overall['grade']}**",
        f"- Overall Score: **{overall['score']}/100**",
        f"- Passed: `{overall['passed']}` / `{overall['graded_total']}` graded cases",
        f"- Skipped: `{overall['skipped']}`",
        "",
        "## Summary",
        "",
        f"- Latency Score: **{overall['latency_score']}/100**",
        f"- Deterministic Score: **{overall['deterministic_score']}/100**",
        f"- Judge Score: **{overall['judge_score']}/100**",
        "",
        "## Subsystem Rollups",
        "",
        "| Subsystem | Cases | Pass | Score | Grade |",
        "|-----------|-------|------|-------|-------|",
    ]

    for subsystem in subsystems:
        lines.append(
            f"| `{subsystem['name']}` | `{subsystem['total']}` | "
            f"`{subsystem['passed']}` | `{subsystem['score']}` | `{subsystem['grade']}` |"
        )

    lines.extend(
        [
            "",
            "## Case Table",
            "",
            "| Case | Suite | Subsystem | Pass | Skip | Det Score | Judge | Total |",
            "|------|-------|-----------|------|------|-----------|-------|-------|",
        ]
    )

    for case in cases:
        lines.append(
            f"| `{case['id']}` | `{case.get('suite', 'stage1')}` | "
            f"`{case.get('subsystem', case['category'])}` | "
            f"`{'yes' if case['passed'] else 'no'}` | "
            f"`{'yes' if case.get('skipped') else 'no'}` | "
            f"`{case['deterministic_score']}` | "
            f"`{case['judge_score']}` | "
            f"`{case['total_score']}` |"
        )

    lines.extend(["", "## Findings", ""])

    for case in cases:
        lines.extend(
            [
                f"### `{case['id']}`",
                "",
                f"- Suite: `{case.get('suite', 'stage1')}`",
                f"- Subsystem: `{case.get('subsystem', case['category'])}`",
                f"- Category: `{case['category']}`",
                f"- Passed: `{'yes' if case['passed'] else 'no'}`",
                f"- Skipped: `{'yes' if case.get('skipped') else 'no'}`",
                f"- Skip reason: {case.get('skip_reason', 'n/a')}",
                f"- Prompt(s): `{case['prompts']}`",
                f"- Reply: `{case['reply_text']}`",
                f"- Deterministic failures: `{case['deterministic_failures'] or ['none']}`",
                f"- Metrics: `{case['metrics']}`",
                f"- Archived state: `{case.get('archived_state', {})}`",
                f"- Judge verdict: `{case['judge']['verdict']}`",
                f"- Judge notes: {case['judge']['notes']}",
                f"- Suggested prompt tweak: {case['judge']['prompt_tweak']}",
                "",
            ]
        )

    path.write_text("\n".join(lines), encoding="utf-8")


def compute_overall(cases: list[dict]) -> dict:
    graded_cases = [case for case in cases if not case.get("skipped")]
    judged_cases = [
        case
        for case in graded_cases
        if case["judge"]["verdict"] not in {"skipped", "judge_unavailable"}
    ]
    total = len(cases)
    graded_total = len(graded_cases)
    skipped = total - graded_total
    passed = sum(1 for c in graded_cases if c["passed"])
    det = round(sum(c["deterministic_score"] for c in graded_cases) / max(1, graded_total))
    judge = round(sum(c["judge_score"] for c in judged_cases) / max(1, len(judged_cases)))
    latency = round(sum(c["latency_score"] for c in graded_cases) / max(1, graded_total))
    judge_active = bool(judged_cases)
    if judge_active:
        score = round((det * 0.45) + (judge * 0.35) + (latency * 0.20))
    else:
        score = round((det * 0.70) + (latency * 0.30))

    if score >= 90:
        grade = "A"
    elif score >= 80:
        grade = "B"
    elif score >= 70:
        grade = "C"
    elif score >= 60:
        grade = "D"
    else:
        grade = "F"

    return {
        "score": score,
        "grade": grade,
        "passed": passed,
        "total": total,
        "graded_total": graded_total,
        "skipped": skipped,
        "deterministic_score": det,
        "judge_score": judge,
        "latency_score": latency,
    }


def compute_subsystems(cases: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        buckets[case.get("subsystem", case["category"])].append(case)

    rows: list[dict] = []
    for name, bucket in sorted(buckets.items()):
        overall = compute_overall(bucket)
        rows.append(
            {
                "name": name,
                "total": overall["graded_total"],
                "passed": overall["passed"],
                "score": overall["score"],
                "grade": overall["grade"],
            }
        )
    return rows


def make_report_payload(run_id: str, cases: list[dict], suite: str = "stage1") -> dict:
    return {
        "run_id": run_id,
        "suite": suite,
        "created_at": datetime.now().isoformat(),
        "overall": compute_overall(cases),
        "subsystems": compute_subsystems(cases),
        "cases": cases,
    }

