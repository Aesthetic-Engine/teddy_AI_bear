from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

from . import audio_player, config


VOICE_FILES = {
    "ryan": "en_US-ryan-high.onnx",
    "john": "en_US-john-medium.onnx",
    "norman": "en_US-norman-medium.onnx",
    "joe": "en_US-joe-medium.onnx",
    "sam": "en_US-sam-medium.onnx",
    "bryce": "en_US-bryce-medium.onnx",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teddy Piper voice bake-off")
    parser.add_argument(
        "--text",
        default="Hi, this is Teddy.",
        help="Preview text to speak for each voice",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.75,
        help="Pause between voice previews",
    )
    parser.add_argument(
        "--voices",
        nargs="*",
        default=None,
        help="Voice ids to preview in order",
    )
    parser.add_argument(
        "--models-dir",
        type=Path,
        help="Directory of Piper .onnx models to preview in filename order",
    )
    return parser.parse_args()


def resolve_voice_models(args: argparse.Namespace) -> list[tuple[str, Path]]:
    if args.models_dir is None:
        selected_voices = args.voices or ["ryan", "john", "norman", "joe", "sam", "bryce"]
        voice_models: list[tuple[str, Path]] = []
        for voice_id in selected_voices:
            if voice_id not in VOICE_FILES:
                raise SystemExit(f"Unknown voice '{voice_id}'.")
            voice_models.append(
                (voice_id, config.RUNTIME_ROOT / "tts" / "voices" / VOICE_FILES[voice_id])
            )
        return voice_models

    if not args.models_dir.exists():
        raise SystemExit(f"Models directory not found: {args.models_dir}")

    available_models = {
        path.stem: path for path in sorted(args.models_dir.glob("*.onnx"), key=lambda item: item.name.lower())
    }
    if not available_models:
        raise SystemExit(f"No .onnx voices found in {args.models_dir}")

    selected_voices = args.voices if args.voices else list(available_models.keys())
    missing_voices = [voice_id for voice_id in selected_voices if voice_id not in available_models]
    if missing_voices:
        raise SystemExit(
            f"Voice(s) not found in {args.models_dir}: {', '.join(missing_voices)}"
        )

    return [(voice_id, available_models[voice_id]) for voice_id in selected_voices]


def main() -> int:
    args = parse_args()
    text_bytes = (args.text.strip() + "\n").encode("utf-8")
    voice_models = resolve_voice_models(args)

    for voice_id, model_path in voice_models:
        config_path = Path(str(model_path) + ".json")
        wav_path = config.TMP_DIR / f"voice-preview-{voice_id}.wav"

        if wav_path.exists():
            wav_path.unlink()

        cmd = [
            str(config.PIPER_EXE),
            "--model",
            str(model_path),
            "--config",
            str(config_path),
            "--espeak_data",
            str(config.PIPER_ESPEAK_DATA),
            "--output_file",
            str(wav_path),
            "--quiet",
        ]

        result = subprocess.run(
            cmd,
            input=text_bytes,
            capture_output=True,
            check=False,
            cwd=str(config.PIPER_ROOT),
        )
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            raise SystemExit(f"Piper failed for {voice_id}: {detail}")

        print(f"Playing {voice_id}: {wav_path}")
        audio_player.play_wav(wav_path)
        time.sleep(max(0.0, args.pause_seconds))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
