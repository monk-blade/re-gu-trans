#!/usr/bin/env python3
"""Exercise combined-bundle staging, verification, and checksum rejection."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), cwd=ROOT, text=True, capture_output=True, check=check
    )


def main() -> int:
    model = ROOT / "models" / "artifacts" / "gu-transformer-ctc-v3"
    stage_script = ROOT / "scripts" / "package" / "stage_combined_bundle.sh"
    installer = "install_bundle.sh"
    with tempfile.TemporaryDirectory(prefix="re-gu-trans-bundle-") as temp_name:
        temp = Path(temp_name)
        core = temp / "core"
        stage = temp / "stage"
        archive = temp / "bundle.tar.gz"
        core.mkdir()
        (core / "re-gu-trans-test.rpm").write_bytes(b"test core package")

        result = run(
            str(stage_script),
            "linux",
            str(core),
            str(model),
            str(stage),
            "2.9.0",
        )
        assert "COMBINED_BUNDLE_STAGED" in result.stdout
        manifest = json.loads((stage / "bundle-manifest.json").read_text())
        assert manifest["model_version"] == "gu-transformer-ctc-v3"
        verified = run(str(stage / installer), "--verify-only")
        assert "BUNDLE_VERIFY_OK" in verified.stdout

        (stage / "README.txt").write_text("tampered\n")
        rejected = run(str(stage / installer), "--verify-only", check=False)
        assert rejected.returncode != 0
        assert "checksum mismatch" in rejected.stderr

        run(
            str(ROOT / "scripts" / "package" / "build_combined_bundle.sh"),
            "linux",
            str(core),
            str(model),
            str(archive),
            "2.9.0",
        )
        assert archive.is_file() and archive.stat().st_size > 0

        extracted = temp / "extracted"
        extracted.mkdir()
        run("tar", "-xzf", str(archive), "-C", str(extracted))
        run(str(extracted / installer), "--verify-only", "--core-only")

    print(json.dumps({"report": "combined_bundle", "ok": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
