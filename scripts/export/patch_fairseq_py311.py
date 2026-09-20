#!/usr/bin/env python3
"""Patch installed fairseq/hydra-core packages for Python 3.11 compatibility.

fairseq 0.12.2 (and the hydra-core/omegaconf versions it pins) declare
dataclass fields with a mutable instance as their default, e.g.
``common: CommonConfig = CommonConfig()``. Python 3.11's dataclasses module
rejects this (`ValueError: mutable default ... use default_factory`), so
importing fairseq at all fails out of the box. This rewrites those fields to
``field(default_factory=CommonConfig)`` in place, and fixes one non-matching
special case in fairseq's TransformerConfig (`quant_noise`).

Idempotent: safe to run again on an already-patched install.
Run once after `pip install fairseq==0.12.2` and before importing fairseq;
see eval/_fairseq_py311_compat.py for the remaining hydra_init() no-op shim
needed at import time.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

MUTABLE_DEFAULT = re.compile(r"^(\s*)(\w+): (\w+) = \3\(\)\s*$", re.M)


def patch_tree(root: Path) -> int:
    total = 0
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        new_text, count = MUTABLE_DEFAULT.subn(
            lambda m: f"{m.group(1)}{m.group(2)}: {m.group(3)} = field(default_factory={m.group(3)})",
            text,
        )
        if not count:
            continue
        if "from dataclasses import" in new_text and "field" not in new_text.split(
            "from dataclasses import", 1
        )[1].split("\n", 1)[0]:
            new_text = re.sub(
                r"from dataclasses import ([^\n]+)",
                lambda m: f"from dataclasses import {m.group(1)}, field",
                new_text,
                count=1,
            )
        path.write_text(new_text, encoding="utf-8")
        total += count
        print(f"patched {count} field(s) in {path}")
    return total


def patch_quant_noise(fairseq_root: Path) -> None:
    path = fairseq_root / "models" / "transformer" / "transformer_config.py"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    old = "quant_noise: QuantNoiseConfig = field(default=QuantNoiseConfig())"
    new = "quant_noise: QuantNoiseConfig = field(default_factory=QuantNoiseConfig)"
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")
        print(f"patched quant_noise default in {path}")


def find_package_root(name: str) -> Path:
    spec = importlib.util.find_spec(name)
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit(f"{name} is not installed in this environment")
    return Path(next(iter(spec.submodule_search_locations)))


def main() -> int:
    fairseq_root = find_package_root("fairseq")
    hydra_root = find_package_root("hydra")
    total = patch_tree(fairseq_root)
    patch_quant_noise(fairseq_root)
    total += patch_tree(hydra_root / "conf")
    print(f"done: {total} field(s) patched across fairseq + hydra-core")
    return 0


if __name__ == "__main__":
    sys.exit(main())
