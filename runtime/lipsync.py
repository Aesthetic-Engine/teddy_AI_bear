from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from . import config


class LipSyncError(RuntimeError):
    """Raised when Teddy cannot generate timed mouth cues."""


@dataclass(frozen=True)
class VisemeCue:
    start: float
    end: float
    value: str


def generate_viseme_cues(audio_bytes: bytes, dialog_text: str) -> list[VisemeCue]:
    if not audio_bytes.startswith(b"RIFF"):
        raise LipSyncError("Lip-sync sidecar expects WAV audio.")
    if not config.RHUBARB_EXE.exists():
        raise LipSyncError(f"Rhubarb executable not found at {config.RHUBARB_EXE}.")

    work_dir = config.TMP_DIR / f"rhubarb-{uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=True)

    audio_path = work_dir / "speech.wav"
    dialog_path = work_dir / "dialog.txt"
    output_path = work_dir / "mouth.json"

    try:
        audio_path.write_bytes(audio_bytes)
        dialog_path.write_text(dialog_text.strip() + "\n", encoding="utf-8")

        command = [
            str(config.RHUBARB_EXE),
            "-f",
            "json",
            "-o",
            str(output_path),
            "--recognizer",
            config.RHUBARB_RECOGNIZER,
            "--extendedShapes",
            config.RHUBARB_EXTENDED_SHAPES,
            "--dialogFile",
            str(dialog_path),
            str(audio_path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=config.RHUBARB_TIMEOUT_SECONDS,
                check=False,
                cwd=str(config.RHUBARB_ROOT),
            )
        except subprocess.TimeoutExpired as exc:
            raise LipSyncError("Rhubarb lip-sync timed out.") from exc
        except FileNotFoundError as exc:
            raise LipSyncError("Rhubarb executable is unavailable.") from exc

        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip() or "rhubarb failed"
            raise LipSyncError(f"Rhubarb error: {detail}")

        if not output_path.exists():
            raise LipSyncError("Rhubarb did not produce mouth cue output.")

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        mouth_cues = payload.get("mouthCues", [])
        cues: list[VisemeCue] = []
        for cue in mouth_cues:
            start = float(cue.get("start", 0.0))
            end = float(cue.get("end", start))
            value = str(cue.get("value", "X")).strip().upper() or "X"
            cues.append(VisemeCue(start=start, end=end, value=value))

        if not cues:
            raise LipSyncError("Rhubarb returned no mouth cues.")

        return cues
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
