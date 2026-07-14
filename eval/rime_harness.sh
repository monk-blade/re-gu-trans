#!/usr/bin/env bash
# Real librime integration harness. Requires a locally built librime tree whose
# build/lib/rime-plugins contains the patched QJS plugin.
#
# Usage (when frontends/deployers available):
#   REQUIRE_RIME_DEPLOYER=1 ./eval/rime_harness.sh
#
# Checks: real menu, numeric selection threshold, Latin slot, restart persistence.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REQUIRE_RIME_DEPLOYER="${REQUIRE_RIME_DEPLOYER:-0}"
STAGE="${TMPDIR:-/tmp}/akshar-rime-harness-$$"
PAYLOAD="$STAGE/payload"
USER="$STAGE/user"
SHARED="$STAGE/shared"
mkdir -p "$STAGE" "$SHARED"

cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

export REQUIRE_BINARY_TRIES=1
./scripts/package/stage_payload.sh "$PAYLOAD" generic
./scripts/package/validate_payload.sh "$PAYLOAD"

mkdir -p "$USER/js"
cp -f "$PAYLOAD/rime/gujarati.schema.yaml" "$USER/"
cp -f "$PAYLOAD/rime/js/"*.js "$USER/js/"
cp -f "$PAYLOAD/rime/js/"*.json "$USER/js/" 2>/dev/null || true
cp -f "$PAYLOAD/rime/js/"*.bin "$USER/js/"
cp -f "$PAYLOAD/rime/js/gujarati_translator.js" "$USER/"
cp -f "$PAYLOAD/rime/js/commit_on_punct_processor.js" "$USER/"
cat > "$USER/default.custom.yaml" <<'EOF'
patch:
  schema_list:
    - schema: gujarati
EOF

BUILD_ROOT="${RIME_BUILD_ROOT:-}"
if [[ -z "$BUILD_ROOT" ]]; then
  if [[ "$REQUIRE_RIME_DEPLOYER" == "1" ]]; then
    echo "FAIL: RIME_BUILD_ROOT is required for real integration" >&2
    exit 1
  fi
  echo "NOTE: real librime harness skipped; set RIME_BUILD_ROOT and REQUIRE_RIME_DEPLOYER=1"
  python3 - <<'PY'
from pathlib import Path
import json
report = {"harness": "rime_harness", "status": "skipped", "real_librime": False}
Path("eval/rime_harness_summary.json").write_text(json.dumps(report, indent=2) + "\n")
PY
  exit 0
fi

for preset in default.yaml symbols.yaml; do
  cp -f "$BUILD_ROOT/data/minimal/$preset" "$SHARED/$preset"
done
PLUGIN="$(find "$BUILD_ROOT/build/lib/rime-plugins" -maxdepth 1 -type f \( -name 'librime-qjs.so' -o -name 'librime-qjs.dylib' \) | head -1 || true)"
test -n "$PLUGIN" || { echo "FAIL: patched QJS plugin missing from build tree" >&2; exit 1; }
./scripts/package/verify_qjs_plugin.sh "$PLUGIN"

DRIVER="$STAGE/rime_session_driver"
"${CXX:-c++}" -std=c++17 eval/rime_session_driver.cc \
  -I"$BUILD_ROOT/src" \
  -L"$BUILD_ROOT/build/lib" \
  -Wl,-rpath,"$BUILD_ROOT/build/lib" \
  -lrime -o "$DRIVER"

RESULT="$($DRIVER "$SHARED" "$USER")"
echo "$RESULT"
python3 - "$RESULT" <<'PY'
from pathlib import Path
import json
import sys
report = json.loads(sys.argv[1].splitlines()[-1])
if not report.get("ok") or not report.get("real_librime") or not report.get("learning_persisted"):
    raise SystemExit("real librime acceptance failed")
report["harness"] = "rime_harness"
report["status"] = "passed"
Path("eval/rime_harness_summary.json").write_text(json.dumps(report, indent=2) + "\n")
PY

echo "RIME_HARNESS_OK"
