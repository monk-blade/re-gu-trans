# archive/ — inactive snapshots

Files here are **not** on the IME hot path. Packages, `sync_rime.sh`, and schema **2.9+** do not load them.

| Folder | Contents |
|--------|----------|
| `apple-extracts/` | Local Apple probe leftovers (Marisa dump, mappings, SP lexicon). Gitignored when large. Used only by rare rebuild scripts (`distill_apple_lexicon.py`, `extract_proprietary_gu_natives.py`). |
| `legacy-rime/` | Old table-dict era assets (`gujarati_apple.dict.yaml`, root TSV mirrors, minimal translator stub). |
| `tools/` | Research binaries (e.g. `probe_tl`). |
| `onnx-era/` | Dropped ONNX ranker training dumps. |

Do not move active `rime/js/**`, schema, or CI data into this tree without updating every consumer.
