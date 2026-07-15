#!/usr/bin/env python3
"""Batch adapter for the production JavaScript candidate pipeline.

Python evaluation scripts may orchestrate fixtures and compute metrics, but they
must not mirror the ranking algorithm.  Candidate menus come from engine.js via
js_production_runner.mjs.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "eval" / "js_production_runner.mjs"


class ProductionRankError(RuntimeError):
    pass


def canonical_native(text: str) -> str:
    """Metric equivalence for orthography canonicalized by production JS."""
    value = str(text or "").replace("અા", "આ")
    for matra in "ાિીુૂેૈોૌ":
        value = value.replace(matra + "ઇ", matra + "ઈ")
    return value


def rank_many(
    romans: list[str], mode: str = "trie", disable_family: str | None = None
) -> list[dict]:
    if mode not in {"text", "trie"}:
        raise ValueError(f"unsupported production rank mode: {mode}")
    if not romans:
        return []

    normalized = [str(roman).strip().lower() for roman in romans]
    with tempfile.TemporaryDirectory(prefix="akshar-production-rank-") as temp:
        temp_dir = Path(temp)
        source = temp_dir / "fixtures.jsonl"
        output = temp_dir / "menus.jsonl"
        source.write_text(
            "".join(
                json.dumps({"roman": roman}, ensure_ascii=False) + "\n"
                for roman in normalized
            ),
            encoding="utf-8",
        )
        child_env = os.environ.copy()
        if disable_family:
            child_env["AKSHAR_DISABLE_FAMILY"] = disable_family
        process = subprocess.run(
            ["node", str(RUNNER), mode, str(source), str(output)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=child_env,
        )
        if process.returncode:
            raise ProductionRankError(
                "production JavaScript ranking failed:\n"
                + process.stdout
                + process.stderr
            )
        rows = [
            json.loads(line)
            for line in output.read_text(encoding="utf-8").splitlines()
            if line
        ]

    if len(rows) != len(normalized):
        raise ProductionRankError(
            f"production runner returned {len(rows)} rows for {len(normalized)} inputs"
        )
    for index, (roman, row) in enumerate(zip(normalized, rows, strict=True)):
        if row.get("roman") != roman:
            raise ProductionRankError(
                f"production result {index} changed input {roman!r} to {row.get('roman')!r}"
            )
        if not row.get("finite"):
            raise ProductionRankError(f"non-finite candidate quality for {roman!r}")
    return rows


def top_six_many(
    romans: list[str], mode: str = "trie", disable_family: str | None = None
) -> list[list[str]]:
    return [
        list(row.get("top6") or [])
        for row in rank_many(romans, mode, disable_family=disable_family)
    ]
