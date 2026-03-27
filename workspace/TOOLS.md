# TOOLS.md - Teddy Local Runtime Notes

This file is a template for the local runtime paths and device names Teddy may use on the host machine.

## Local Services

- Text model: `OpenAI gpt-5.4-mini` via `OPENAI_API_KEY`
- Local STT URL: `http://127.0.0.1:8000`
- Local STT engine: `faster-whisper` with `small.en`
- Local TTS URL: `http://127.0.0.1:5000`
- Local TTS engine: `Piper`
- Teddy mouth bridge URL: `http://127.0.0.1:8765`
- Teddy speech output device: `(set this to your preferred output device if needed)`
- Teddy default microphone: `(set this to your preferred microphone if needed)`

## Local Paths

- Teddy workspace: `(repo root)/workspace`
- Mouth bridge script: `(repo root)/bridge/teddy_mouth_bridge.py`
- Mouth bridge launcher: `(repo root)/bridge/Start-TeddyMouthBridge.ps1`
- Mouth bridge tester: `(repo root)/bridge/Test-TeddyMouthBridge.ps1`

## Hardware

- Teddy mouth controller serial port: `(set this to your Arduino serial port, for example COM7)`
- Teddy mouth controller baud rate: `9600`
- Command format: `ANGLE <n>` plus newline
- Confirmed safe command range from current firmware: `4` to `12`

## Security Intent

- Keep all Teddy-facing services on `127.0.0.1`
- Do not expose Teddy services to the LAN
- Outbound internet for Teddy processes should be limited to what the configured runtime actually needs
