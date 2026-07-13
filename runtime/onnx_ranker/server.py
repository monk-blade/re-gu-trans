#!/usr/bin/env python3
"""Unix-socket ONNX (or NPZ) ranker sidecar for Rime Gujarati IME."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_META = ROOT / "models" / "ranker_meta.json"
DEFAULT_ONNX = ROOT / "models" / "gu_ranker.onnx"
DEFAULT_NPZ = ROOT / "models" / "gu_ranker.npz"
DEFAULT_SOCK = Path.home() / "Library" / "Rime" / "run" / "gu_ranker.sock"


class Ranker:
    def __init__(self, meta_path: Path, onnx_path: Path, npz_path: Path):
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))
        self.roman_stoi = self.meta["roman_stoi"]
        self.gu_stoi = self.meta["gu_stoi"]
        self.max_roman = int(self.meta["max_roman"])
        self.max_gu = int(self.meta["max_gu"])
        self.session = None
        self.weights = None

        if onnx_path.exists():
            try:
                import onnxruntime as ort

                self.session = ort.InferenceSession(
                    str(onnx_path), providers=["CPUExecutionProvider"]
                )
                print(f"loaded onnx {onnx_path}", file=sys.stderr)
            except Exception as e:
                print(f"onnx load failed: {e}; falling back to npz", file=sys.stderr)

        if self.session is None:
            data = np.load(npz_path)
            self.weights = {k: data[k] for k in data.files}
            print(f"loaded npz {npz_path}", file=sys.stderr)

    def encode(self, text: str, stoi: dict, max_len: int) -> np.ndarray:
        ids = np.zeros(max_len, dtype=np.int64)
        for i, ch in enumerate(text[:max_len]):
            ids[i] = stoi.get(ch, 1)
        return ids

    def score_batch(self, roman: str, cands: list[str]) -> list[float]:
        if not cands:
            return []
        r = self.encode(roman.lower(), self.roman_stoi, self.max_roman)
        r_batch = np.stack([r] * len(cands))
        g_batch = np.stack([self.encode(c, self.gu_stoi, self.max_gu) for c in cands])

        if self.session is not None:
            out = self.session.run(None, {"roman_ids": r_batch, "gu_ids": g_batch})[0]
            return [float(x[0]) for x in out]

        # numpy forward
        E_r, E_g = self.weights["E_r"], self.weights["E_g"]
        W1, b1, W2, b2 = self.weights["W1"], self.weights["b1"], self.weights["W2"], self.weights["b2"]
        r_emb = E_r[r_batch]
        g_emb = E_g[g_batch]
        r_pool = r_emb.mean(axis=1)
        g_pool = g_emb.mean(axis=1)
        x = np.concatenate([r_pool, g_pool], axis=1)
        h = np.tanh(x @ W1 + b1)
        s = (h @ W2 + b2).reshape(-1)
        return [float(v) for v in s]


def handle_client(conn: socket.socket, ranker: Ranker) -> None:
    try:
        data = b""
        conn.settimeout(1.0)
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
        if not data:
            return
        line = data.split(b"\n", 1)[0].decode("utf-8")
        req = json.loads(line)
        scores = ranker.score_batch(req.get("input", ""), list(req.get("cands") or []))
        resp = json.dumps({"scores": scores}, ensure_ascii=False) + "\n"
        conn.sendall(resp.encode("utf-8"))
    except Exception as e:
        try:
            conn.sendall((json.dumps({"error": str(e), "scores": []}) + "\n").encode())
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def serve(sock_path: Path, ranker: Ranker) -> None:
    sock_path.parent.mkdir(parents=True, exist_ok=True)
    if sock_path.exists():
        sock_path.unlink()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(sock_path))
    server.listen(32)
    print(f"listening on {sock_path}", file=sys.stderr)

    def shutdown(*_args):
        try:
            server.close()
        finally:
            if sock_path.exists():
                sock_path.unlink()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle_client, args=(conn, ranker), daemon=True).start()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sock", type=Path, default=DEFAULT_SOCK)
    ap.add_argument("--meta", type=Path, default=DEFAULT_META)
    ap.add_argument("--onnx", type=Path, default=DEFAULT_ONNX)
    ap.add_argument("--npz", type=Path, default=DEFAULT_NPZ)
    args = ap.parse_args()
    ranker = Ranker(args.meta, args.onnx, args.npz)
    serve(args.sock, ranker)


if __name__ == "__main__":
    main()
