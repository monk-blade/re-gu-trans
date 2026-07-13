#!/usr/bin/env python3
"""CLI client for gu_ranker sidecar — used by qjs translator via std.popen."""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

DEFAULT_SOCK = Path.home() / "Library" / "Rime" / "run" / "gu_ranker.sock"


def ask(sock_path: Path, payload: dict, timeout: float = 0.05) -> dict:
    data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock_path))
        s.sendall(data)
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    if not buf:
        return {"scores": []}
    return json.loads(buf.split(b"\n", 1)[0].decode("utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sock", type=Path, default=DEFAULT_SOCK)
    ap.add_argument("--json", type=str, default="")
    ap.add_argument("--stdin", action="store_true")
    args = ap.parse_args()

    if args.stdin:
        raw = sys.stdin.read()
    else:
        raw = args.json
    if not raw:
        print(json.dumps({"scores": []}))
        return
    payload = json.loads(raw)
    timeout_ms = float(payload.get("timeout_ms") or 50)
    try:
        resp = ask(args.sock, payload, timeout=max(timeout_ms / 1000.0, 0.01))
    except Exception as e:
        resp = {"scores": [], "error": str(e)}
    print(json.dumps(resp, ensure_ascii=False))


if __name__ == "__main__":
    main()
