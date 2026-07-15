#!/usr/bin/env python3
"""Production-JS reference gate for the Apple/Microsoft-style examples."""
from __future__ import annotations

import json
from pathlib import Path

from production_rank import top_six_many

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "eval" / "apple_class_reference.jsonl"
OUT = ROOT / "eval" / "apple_class_reference_summary.json"


def main() -> int:
    cases = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line]
    menus = top_six_many([case["roman"] for case in cases])
    failures = []
    results = []
    for case, menu in zip(cases, menus, strict=True):
        reasons = []
        if not menu or menu[0] != case["expected_top1"]:
            reasons.append(f"top1={menu[0] if menu else None!r}")
        for item in case.get("required_top6", []):
            if item not in menu:
                reasons.append(f"missing={item!r}")
        if menu and menu[0] in case.get("forbidden_top1", []):
            reasons.append(f"forbidden_top1={menu[0]!r}")
        for item in case.get("forbidden_top6", []):
            if item in menu:
                reasons.append(f"forbidden={item!r}")
        results.append({"roman": case["roman"], "top6": menu, "ok": not reasons})
        if reasons:
            failures.append({"roman": case["roman"], "reasons": reasons, "top6": menu})
    payload = {"report": "apple_class_reference", "total": len(cases), "passed": len(cases) - len(failures), "ok": not failures, "results": results, "failures": failures}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
