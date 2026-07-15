#!/usr/bin/env python3
"""Exercise a staged platform model plugin through its exported C ABI."""
from __future__ import annotations

import argparse
import ctypes
import json
import math
import os
import platform
import re
import statistics
import time
from pathlib import Path

GUJARATI = re.compile(r"^[\u0A80-\u0AFF\u200C\u200D]+$")
PROBES = (
    "yas", "aajdeevse", "chalshe", "bagicho", "parkhavyu", "samajdaarima",
    "javabdaarione", "gujaratimaa", "anubhavmathi", "vyavasthaapan",
    "lokshahivaadi", "mahatvapurn", "sambhaavnaao",
)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", type=Path)
    parser.add_argument("--output", type=Path, default=Path("eval/native_model_plugin_summary.json"))
    args = parser.parse_args()
    names = {
        "Darwin": "librime-gujarati-model.dylib",
        "Linux": "librime-gujarati-model.so",
        "Windows": "rime-gujarati-model.dll",
    }
    library = args.pack / names[platform.system()]
    if platform.system() == "Windows":
        os.add_dll_directory(str(args.pack.resolve()))
    plugin = ctypes.CDLL(str(library.resolve()))
    plugin.akshar_gu_model_version.restype = ctypes.c_char_p
    plugin.akshar_gu_transliterate_nbest.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    plugin.akshar_gu_transliterate_nbest.restype = ctypes.c_char_p
    model_root = str(args.pack.resolve()).encode()

    for invalid in ("", ".", "3.", "--", "a..b", "a b"):
        raw = plugin.akshar_gu_transliterate_nbest(model_root, invalid.encode(), 4)
        if json.loads(raw.decode()) != []:
            raise SystemExit(f"native model accepted invalid Roman input: {invalid!r}")

    timings: list[float] = []
    outputs: dict[str, list[dict]] = {}
    for index in range(1000):
        roman = PROBES[index % len(PROBES)]
        started = time.perf_counter()
        raw = plugin.akshar_gu_transliterate_nbest(model_root, roman.encode(), 4)
        timings.append((time.perf_counter() - started) * 1000)
        candidates = json.loads(raw.decode())
        if not isinstance(candidates, list) or not candidates:
            raise SystemExit(f"native model returned no candidates for {roman}")
        for candidate in candidates:
            if not GUJARATI.fullmatch(str(candidate.get("native") or "")):
                raise SystemExit(f"invalid Gujarati output for {roman}")
            if not math.isfinite(float(candidate.get("logProb"))):
                raise SystemExit(f"non-finite native score for {roman}")
        outputs.setdefault(roman, candidates)
    target = [item["native"] for item in outputs["aajdeevse"]]
    if "આજદિવસે" not in target:
        raise SystemExit("held-out native inference probe is missing")
    if "યસ" not in [item["native"] for item in outputs["yas"]]:
        raise SystemExit("yas n-best must contain યસ for hybrid arbitration")
    payload = {
        "report": "native_model_plugin",
        "platform": platform.system().lower(),
        "architecture": platform.machine(),
        "model_version": plugin.akshar_gu_model_version().decode(),
        "queries": len(timings),
        "p50_ms": round(statistics.median(timings), 3),
        "p95_ms": round(percentile(timings, 0.95), 3),
        "finite": True,
        "held_out_probe": True,
        "invalid_input_rejected": True,
        "yas_in_nbest": True,
    }
    payload["passed"] = payload["model_version"] == "gu-model-plugin-v2" and payload["p95_ms"] <= 10
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
