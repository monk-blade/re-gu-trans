#!/usr/bin/env python3
"""Aggregate observed platform reports; reject absent, null, or claimed-only data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = {"macos", "linux", "windows"}
CAPABILITIES = ("trie", "candidate_access", "commit_notifier", "write_file_atomic", "neural_model")
EXPECTED_FORMATS = {
    "linux": [".deb", ".rpm"],
    "macos": [".pkg", ".zip"],
    "windows": [".zip"],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reports", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.reports.rglob("verification-*.json")]
    if len(reports) != len(REQUIRED):
        raise SystemExit(f"expected exactly {len(REQUIRED)} platform reports, got {len(reports)}")
    by_platform = {report.get("platform"): report for report in reports}
    if set(by_platform) != REQUIRED:
        raise SystemExit(f"platform reports mismatch: expected={sorted(REQUIRED)} actual={sorted(by_platform)}")
    failures = []
    for platform, report in sorted(by_platform.items()):
        caps = report.get("capabilities") or {}
        bench = report.get("benchmark") or {}
        learning = report.get("learning") or {}
        payload = report.get("payload") or {}
        plugin = report.get("plugin") or {}
        model_pack = report.get("model_pack") or {}
        native_model = report.get("native_model") or {}
        if not report.get("passed") or not all(caps.get(name) is True for name in CAPABILITIES):
            failures.append(platform + ":capabilities")
        if not learning.get("three_selection") or not learning.get("restart_persisted") or learning.get("latin_slot") != 2:
            failures.append(platform + ":learning")
        if bench.get("host") != "real-librime" or bench.get("query_p95_ms") is None or bench["query_p95_ms"] > 5:
            failures.append(platform + ":benchmark")
        if (
            not payload.get("binary_only")
            or not payload.get("validated")
            or payload.get("bytes") is None
            or payload["bytes"] > 70 * 1024 * 1024
        ):
            failures.append(platform + ":payload")
        if len(str(plugin.get("sha256") or "")) != 64:
            failures.append(platform + ":plugin-hash")
        if not report.get("packages") or not all(item.get("valid") for item in report["packages"]):
            failures.append(platform + ":packages")
        if sorted(report.get("package_formats") or []) != EXPECTED_FORMATS[platform]:
            failures.append(platform + ":package-formats")
        if (
            not model_pack.get("validated")
            or model_pack.get("bytes") is None
            or model_pack["bytes"] > 35 * 1024 * 1024
            or len(str(model_pack.get("sha256") or "")) != 64
        ):
            failures.append(platform + ":model-pack")
        if not native_model.get("passed") or native_model.get("p95_ms") is None or native_model["p95_ms"] > 10:
            failures.append(platform + ":native-model")
    result = {"schema": 1, "platforms": by_platform, "failures": failures, "passed": not failures}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": not failures, "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
