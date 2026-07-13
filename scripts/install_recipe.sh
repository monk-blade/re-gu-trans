#!/usr/bin/env bash
# Install re-gu-trans into the local Rime user dir (plum-free recipe runner).
# Prefer Release packages when available; this mirrors recipes/re-gu-trans.recipe.yaml.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Reuse sync_rime.sh detection + copy + reload
exec "$ROOT/scripts/sync_rime.sh"
