"""Import-time shim so fairseq 0.12.2 loads under Python 3.11.

fairseq's hydra config registration (``fairseq.dataclass.initialize.hydra_init``)
walks every dataclass field default for the sole purpose of populating hydra's
CLI config store. We only need to load a checkpoint and run inference, so the
registration step is replaced with a no-op before ``fairseq`` is imported.
The venv's fairseq/hydra packages also needed their mutable dataclass
defaults converted to ``field(default_factory=...)`` (a one-time patch
already applied in .venv-indicxlit) to satisfy Python 3.11's dataclasses
module; this shim only handles the remaining hydra_init() call.
"""
from __future__ import annotations

import sys
import types

if "fairseq.dataclass.initialize" not in sys.modules:
    _shim = types.ModuleType("fairseq.dataclass.initialize")
    _shim.hydra_init = lambda cfg_name="config": None
    _shim.add_defaults = lambda cfg: None
    sys.modules["fairseq.dataclass.initialize"] = _shim
