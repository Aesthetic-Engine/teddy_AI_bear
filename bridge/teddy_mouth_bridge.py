#!/usr/bin/env python3
"""
Minimal Teddy mouth bridge.

- Talks to the confirmed Teddy mouth controller on COM7
- Uses the confirmed protocol: "ANGLE <n>\\n" at 9600 baud
- Supports either one-shot CLI commands or a localhost-only HTTP server
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

import serial


DEFAULT_PORT = "COM7"
DEFAULT_BAUD = 9600
MIN_ANGLE = 4
MAX_ANGLE = 12


def clamp_angle(value: int) -> int:
    return max(MIN_ANGLE, min(MAX_ANGLE, value))


class TeddySerial:
    def __init__(self, port: str, baud: int) -> None:
        self.port_name = port
        self.baud = baud
        self._lock = threading.Lock()
        self._serial: Optional[serial.Serial] = None

    def open(self) -> None:
        if self._serial and self._serial.is_open:
            return

        ser = serial.Serial(
            self.port_name,
            self.baud,
            timeout=1.2,
            write_timeout=1.2,
        )
        ser.dtr = True
        ser.rts = False
        self._serial = ser

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()

    def send_angle(self, angle: int) -> str:
        angle = clamp_angle(angle)
        command = f"ANGLE {angle}\n"

        with self._lock:
            self.open()
            assert self._serial is not None

            # Drain any prior buffered text so the caller gets a clean reply.
            if self._serial.in_waiting:
                self._serial.read(self._serial.in_waiting)

            self._serial.write(command.encode("ascii"))
            self._serial.flush()

            reply = ""
            if self._serial.in_waiting:
                reply = self._serial.read(self._serial.in_waiting).decode(
                    "ascii", errors="replace"
                )
            else:
                reply = self._serial.readline().decode("ascii", errors="replace")

            return reply.strip()


def make_handler(bridge: TeddySerial):
    class TeddyHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, format: str, *args) -> None:
            # Keep console noise minimal.
            return

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "port": bridge.port_name,
                        "baud": bridge.baud,
                        "angle_range": [MIN_ANGLE, MAX_ANGLE],
                    },
                )
                return

            if parsed.path == "/mouth":
                query = parse_qs(parsed.query)
                angle_values = query.get("angle", [])
                if not angle_values:
                    self._send_json(400, {"ok": False, "error": "angle is required"})
                    return

                try:
                    angle = int(angle_values[0])
                except ValueError:
                    self._send_json(400, {"ok": False, "error": "angle must be int"})
                    return

                try:
                    response = bridge.send_angle(angle)
                except Exception as exc:  # pragma: no cover - hardware path
                    self._send_json(500, {"ok": False, "error": str(exc)})
                    return

                self._send_json(
                    200,
                    {
                        "ok": True,
                        "angle": clamp_angle(angle),
                        "device_response": response,
                    },
                )
                return

            self._send_json(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/mouth":
                self._send_json(404, {"ok": False, "error": "not found"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0

            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                angle = int(payload["angle"])
            except Exception:
                self._send_json(400, {"ok": False, "error": "invalid JSON body"})
                return

            try:
                response = bridge.send_angle(angle)
            except Exception as exc:  # pragma: no cover - hardware path
                self._send_json(500, {"ok": False, "error": str(exc)})
                return

            self._send_json(
                200,
                {
                    "ok": True,
                    "angle": clamp_angle(angle),
                    "device_response": response,
                },
            )

    return TeddyHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teddy mouth bridge")
    parser.add_argument("--com", default=DEFAULT_PORT, help="Serial port name")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="Baud rate")

    sub = parser.add_subparsers(dest="mode", required=True)

    serve = sub.add_parser("serve", help="Run localhost-only HTTP bridge")
    serve.add_argument("--host", default="127.0.0.1", help="Bind host")
    serve.add_argument("--port", type=int, default=8765, help="Bind port")

    angle = sub.add_parser("angle", help="Send a single mouth angle")
    angle.add_argument("value", type=int, help="Target mouth angle")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bridge = TeddySerial(args.com, args.baud)

    if args.mode == "angle":
        try:
            reply = bridge.send_angle(args.value)
            print(
                json.dumps(
                    {
                        "ok": True,
                        "angle": clamp_angle(args.value),
                        "device_response": reply,
                    }
                )
            )
            return 0
        finally:
            bridge.close()

    if args.mode == "serve":
        server = ThreadingHTTPServer((args.host, args.port), make_handler(bridge))
        print(
            f"Teddy mouth bridge listening on http://{args.host}:{args.port} "
            f"for {args.com} at {args.baud} baud"
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
            bridge.close()
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
