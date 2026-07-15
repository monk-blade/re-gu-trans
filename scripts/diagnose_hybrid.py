#!/usr/bin/env python3
"""Print native-model n-best and production merge/rank evidence for one Roman word."""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "eval/js_production_runner.mjs"


def native_candidates(model_dir: Path, roman: str, count: int) -> list[dict]:
    names = {"Darwin": "librime-gujarati-model.dylib", "Linux": "librime-gujarati-model.so", "Windows": "rime-gujarati-model.dll"}
    library = model_dir / names[platform.system()]
    if not library.exists():
        raise SystemExit(f"missing native model plugin: {library}")
    plugin = ctypes.CDLL(str(library.resolve()))
    plugin.akshar_gu_transliterate_nbest.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    plugin.akshar_gu_transliterate_nbest.restype = ctypes.c_char_p
    raw = plugin.akshar_gu_transliterate_nbest(str(model_dir.resolve()).encode(), roman.encode(), count)
    return json.loads(raw.decode())


def main() -> int:
    installed = Path.home() / "Library/Rime/gujarati-model"
    parser = argparse.ArgumentParser()
    parser.add_argument("roman")
    parser.add_argument("--model-dir", type=Path, default=installed if installed.exists() else ROOT / "dist/gujarati-model-pack-macos")
    parser.add_argument("--count", type=int, default=4)
    args = parser.parse_args()
    roman = args.roman.strip().lower()
    candidates = native_candidates(args.model_dir, roman, max(1, min(8, args.count)))
    best = max((float(item["logProb"]) for item in candidates), default=0)
    fixtures = {roman: [dict(item, logProb=float(item["logProb"]) - best) for item in candidates]}
    with tempfile.TemporaryDirectory(prefix="akshar-diagnose-") as temp:
        root = Path(temp)
        source, fixture, output = root / "input.jsonl", root / "neural.json", root / "output.jsonl"
        source.write_text(json.dumps({"roman": roman}) + "\n", encoding="utf-8")
        fixture.write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env.update({"NEURAL_FIXTURES": str(fixture), "DEBUG_RANK": "1", "DEBUG_PATHS": "1"})
        process = subprocess.run(
            ["node", str(RUNNER), "trie", str(source), str(output)],
            cwd=ROOT, env=env, text=True, capture_output=True, check=False,
        )
        if process.returncode:
            raise SystemExit(process.stdout + process.stderr)
        production = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    print(json.dumps({"roman": roman, "model_nbest": candidates, "production": production}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
