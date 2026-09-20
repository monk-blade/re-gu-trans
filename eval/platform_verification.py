#!/usr/bin/env python3
"""Create one observed verification artifact for a built platform package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGE_SUFFIXES = {
    "linux": {".deb", ".rpm"},
    "macos": {".pkg", ".zip"},
    "windows": {".zip"},
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_bytes(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def run_sh(script: Path, *args: str, **kwargs) -> None:
    # The OS loader can exec a script directly via its shebang line on
    # Linux/macOS, but Windows has no such mechanism -- CreateProcess just
    # fails with WinError 193 ("not a valid Win32 application"). Every
    # platform in this matrix ships bash (Git Bash on Windows runners), so
    # invoke it explicitly instead of relying on shebang-based execution.
    subprocess.run(["bash", str(script), *args], check=True, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", required=True, choices=("macos", "linux", "windows"))
    parser.add_argument("--arch", required=True)
    parser.add_argument("--plugin", required=True, type=Path)
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--harness", default=ROOT / "eval" / "rime_harness_summary.json", type=Path)
    parser.add_argument(
        "--native-model-report",
        default=ROOT / "eval" / "native_model_plugin_summary.json",
        type=Path,
    )
    parser.add_argument("--package", action="append", default=[], type=Path)
    parser.add_argument("--model-pack", required=True, type=Path)
    parser.add_argument(
        "--model-token",
        default=None,
        help="Expected training-manifest.json model_version (e.g. indicxlit-fairseq-v1.0, "
        "gu-transformer-ctc-v4). Cross-checked against the pack's actual manifest instead of "
        "the pack filename, since a release now ships multiple model variants per platform.",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    harness = json.loads(args.harness.read_text(encoding="utf-8"))
    native_model = json.loads(args.native_model_report.read_text(encoding="utf-8"))
    caps = harness.get("capabilities") or {}
    bench = harness.get("benchmark") or {}
    required_caps = ("trie", "candidate_access", "commit_notifier", "write_file_atomic")
    if not harness.get("ok") or not harness.get("learning_persisted"):
        raise SystemExit("real-host learning verification missing")
    if not all(caps.get(name) for name in required_caps):
        raise SystemExit("required runtime capability missing")
    if not caps.get("neural_model") or not harness.get("neural_candidate_observed"):
        raise SystemExit("real-host neural inference verification missing")
    if bench.get("host") != "real-librime" or bench.get("query_p95_ms") is None:
        raise SystemExit("real-host benchmark missing")
    if not native_model.get("passed") or native_model.get("p95_ms") is None:
        raise SystemExit("native model plugin report missing or failed")

    run_sh(ROOT / "scripts" / "package" / "validate_payload.sh", str(args.payload), cwd=ROOT)
    plugin_hash = digest(args.plugin)
    package_results = []
    for package in args.package:
        child_env = os.environ.copy()
        child_env["EXPECTED_PLUGIN_SHA256"] = plugin_hash
        run_sh(ROOT / "scripts" / "package" / "validate_archive.sh", str(package), cwd=ROOT, env=child_env)
        package_results.append(
            {"name": package.name, "sha256": digest(package), "bytes": package.stat().st_size, "valid": True}
        )
    if not package_results:
        raise SystemExit("at least one extracted package verification is required")
    actual_suffixes = {Path(item["name"]).suffix.lower() for item in package_results}
    expected_suffixes = EXPECTED_PACKAGE_SUFFIXES[args.platform]
    if actual_suffixes != expected_suffixes:
        raise SystemExit(
            f"package formats mismatch for {args.platform}: "
            f"expected={sorted(expected_suffixes)} actual={sorted(actual_suffixes)}"
        )
    with tempfile.TemporaryDirectory(prefix="akshar-model-pack-") as temp:
        if args.model_pack.is_dir():
            extracted = args.model_pack
        else:
            with zipfile.ZipFile(args.model_pack) as archive:
                archive.extractall(temp)
            extracted = Path(temp)
        run_sh(ROOT / "scripts" / "package" / "validate_neural_model_pack.sh", str(extracted), cwd=ROOT)
        manifest = json.loads((extracted / "training-manifest.json").read_text(encoding="utf-8"))
        model_version = manifest.get("model_version")
    if args.model_token and args.model_token != model_version:
        raise SystemExit(
            f"model pack version {model_version!r} does not match expected {args.model_token!r}"
        )
    model_pack = {
        "name": args.model_pack.name,
        "model_version": model_version,
        "sha256": digest(args.model_pack) if args.model_pack.is_file() else None,
        "bytes": args.model_pack.stat().st_size if args.model_pack.is_file() else tree_bytes(args.model_pack),
        "validated": True,
    }

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
        "package_formats": sorted(actual_suffixes),
        "model_pack": model_pack,
        "native_model": native_model,
        "passed": three_selection,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
