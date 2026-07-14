#!/usr/bin/env python3
"""Fail if VERSION, schema version, and package metadata diverge.

Compares:
  VERSION file major.minor
  rime/gujarati.schema.yaml version:
  packaging/*.yaml version fields when present
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def major_minor(v: str) -> str:
    v = v.strip().strip("'\"")
    parts = re.split(r"[.\-+]", v)
    if len(parts) < 2:
        return v
    return f"{parts[0]}.{parts[1]}"


def main() -> int:
    ver_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    schema = (ROOT / "rime" / "gujarati.schema.yaml").read_text(encoding="utf-8")
    schema_v = None
    for line in schema.splitlines():
        if line.strip().startswith("version:"):
            schema_v = line.split(":", 1)[1].strip().strip("'\"")
            break
    if not schema_v:
        print("FAIL: schema version missing", file=sys.stderr)
        return 1

    vf = major_minor(ver_file)
    sf = major_minor(schema_v)
    errors = []
    if vf != sf:
        errors.append(f"VERSION {ver_file!r} ({vf}) != schema {schema_v!r} ({sf})")

    for path in sorted((ROOT / "packaging").glob("*.yaml")) if (ROOT / "packaging").exists() else []:
        text = path.read_text(encoding="utf-8")
        m = re.search(r"^version:\s*[\"']?([^\"'\s]+)", text, re.M)
        if not m:
            continue
        raw = m.group(1)
        if raw in ("__VERSION__", "${VERSION}", "VERSION"):
            continue  # packaging templates substituted at build time
        pf = major_minor(raw)
        if pf != vf:
            errors.append(f"{path.name} version {raw!r} ({pf}) != VERSION ({vf})")

    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(json_dumps := __import__("json").dumps({"version": ver_file, "schema": schema_v, "major_minor": vf}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
