#!/usr/bin/env python3
"""Create one observed verification artifact for a built platform package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=("macos", "linux", "windows"))
    parser.add_argument("--arch", required=True)
    parser.add_argument("--plugin", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--harness", default=ROOT / "eval" / "rime_harness_summary.json", type=Path)
    parser.add_argument("--package", action="append", default=[], type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    harness = json.loads(args.harness.read_text(encoding="utf-8"))
    caps = harness.get("capabilities") or {}
    bench = harness.get("benchmark") or {}
    required_caps = ("trie", "candidate_access", "commit_notifier", "write_file_atomic")
    if not harness.get("ok") or not harness.get("learning_persisted"):
        raise SystemExit("real-host learning verification missing")
    if not all(caps.get(name) for name in required_caps):
        raise SystemExit("required runtime capability missing")
    if bench.get("host") != "real-librime" or bench.get("query_p95_ms") is None:
        raise SystemExit("real-host benchmark missing")

    subprocess.run(
        [str(ROOT / "scripts" / "package" / "validate_payload.sh"), str(args.payload)],
        cwd=ROOT,
        check=True,
    )
    plugin_hash = digest(args.plugin)
    package_results = []
    for package in args.package:
        child_env = os.environ.copy()
        child_env["EXPECTED_PLUGIN_SHA256"] = plugin_hash
        subprocess.run(
            [str(ROOT / "scripts" / "package" / "validate_archive.sh"), str(package)],
            cwd=ROOT,
            check=True,
            env=child_env,
        )
        package_results.append(
            {"name": package.name, "sha256": digest(package), "bytes": package.stat().st_size, "valid": True}
        )
    if not package_results:
        raise SystemExit("at least one extracted package verification is required")

    three_selection = harness.get("three_selection_observed") is True
    report = {
        "schema": 1,
        "platform": args.platform,
        "arch": args.arch,
        "librime": os.environ.get("LIBRIME_TAG", "1.16.1"),
        "librime_qjs": os.environ.get("LIBRIME_QJS_TAG", "v1.3.0"),
        "plugin": {"path": args.plugin.name, "sha256": plugin_hash},
        "capabilities": caps,
        "optional_capabilities": {"neural_model": caps.get("neural_model") is True},
        "learning": {
            "three_selection": three_selection,
            "restart_persisted": harness.get("learning_persisted") is True,
            "latin_slot": harness.get("latin_slot"),
        },
        "benchmark": bench,
        "payload": {"bytes": tree_bytes(args.payload), "binary_only": True, "validated": True},
        "packages": package_results,
        "passed": three_selection,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
