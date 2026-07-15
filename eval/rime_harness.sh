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
NEURAL_EXPECTED=0
if [[ -n "${NEURAL_MODEL_PACK:-}" ]]; then
  for model_file in gujarati_xlit.int8.onnx vocab.tsv; do
    test -f "$NEURAL_MODEL_PACK/$model_file" || {
      echo "FAIL: neural model pack lacks $model_file" >&2
      exit 1
    }
  done
  mkdir -p "$USER/gujarati-model"
  cp -R "$NEURAL_MODEL_PACK/." "$USER/gujarati-model/"
  NEURAL_EXPECTED=1
fi
cat > "$USER/default.custom.yaml" <<'EOF'
patch:
  schema_list:
    - schema: gujarati
EOF
REQUIRED_MISSING="${EXPECT_NEURAL_REQUIRED_MISSING:-0}"
if [[ "$REQUIRED_MISSING" == "1" ]]; then
  test "$NEURAL_EXPECTED" == "0" || {
    echo "FAIL: required-missing mode cannot install a model pack" >&2
    exit 1
  }
  cat > "$USER/gujarati.custom.yaml" <<'EOF'
patch:
  translator/neural_mode: required
EOF
fi

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
PLUGIN="${RIME_PLUGIN:-}"
if [[ -z "$PLUGIN" && -d "$BUILD_ROOT/build/lib/rime-plugins" ]]; then
  PLUGIN="$(find "$BUILD_ROOT/build/lib/rime-plugins" -maxdepth 1 -type f \( -name 'librime-qjs.so' -o -name 'librime-qjs.dylib' \) | head -1 || true)"
fi
test -n "$PLUGIN" || { echo "FAIL: patched QJS plugin missing from build tree" >&2; exit 1; }
./scripts/package/verify_qjs_plugin.sh "$PLUGIN"

DRIVER="$STAGE/rime_session_driver"
if [[ "${OS:-}" == "Windows_NT" ]]; then
  RIME_LIB="$(find "$BUILD_ROOT/build" -type f -iname 'rime.lib' | head -1)"
  RIME_DLL="$(find "$BUILD_ROOT/build" -type f -iname 'rime.dll' | head -1)"
  test -n "$RIME_LIB" -a -n "$RIME_DLL"
  cl /nologo /EHsc /std:c++17 /I"$BUILD_ROOT/src" eval/rime_session_driver.cc \
    /link /LIBPATH:"$(dirname "$RIME_LIB")" rime.lib /OUT:"$DRIVER.exe"
  DRIVER="$DRIVER.exe"
  export PATH="$(dirname "$RIME_DLL"):$PATH"
else
  "${CXX:-c++}" -std=c++17 eval/rime_session_driver.cc \
    -I"$BUILD_ROOT/src" \
    -L"$BUILD_ROOT/build/lib" \
    -Wl,-rpath,"$BUILD_ROOT/build/lib" \
    -lrime -o "$DRIVER"
fi

DRIVER_LOG="$STAGE/rime-session.log"
DRIVER_ARGS=("$SHARED" "$USER")
if [[ "$REQUIRED_MISSING" == "1" ]]; then DRIVER_ARGS+=(required-missing); fi
RESULT="$($DRIVER "${DRIVER_ARGS[@]}" 2>"$DRIVER_LOG")"
cat "$DRIVER_LOG" >&2
NEURAL_OBSERVED=0
if grep -E '\$qjs\$ runtime capabilities active=.*neural_model' "$DRIVER_LOG" >/dev/null; then
  NEURAL_OBSERVED=1
fi
echo "$RESULT"
python3 - "$RESULT" "$NEURAL_EXPECTED" "$NEURAL_OBSERVED" <<'PY'
from pathlib import Path
import json
import sys
report = json.loads(sys.argv[1].splitlines()[-1])
neural_expected = sys.argv[2] == "1"
neural_observed = sys.argv[3] == "1"
if report.get("required_model_missing_blocked"):
    report.update({"harness": "rime_harness", "mode": "required-missing", "status": "passed"})
    Path("eval/rime_harness_summary.json").write_text(json.dumps(report, indent=2) + "\n")
    raise SystemExit(0)
caps = report.get("capabilities") or {}
caps["neural_model"] = neural_observed
report["capabilities"] = caps
bench = report.get("benchmark") or {}
if not report.get("ok") or not report.get("real_librime") or not report.get("learning_persisted"):
    raise SystemExit("real librime acceptance failed")
if not all(caps.get(k) for k in ("trie", "candidate_access", "commit_notifier", "write_file_atomic")):
    raise SystemExit("real librime capability probe failed")
if bench.get("host") != "real-librime" or not bench.get("cases") or bench.get("query_p95_ms") is None:
    raise SystemExit("real librime benchmark missing")
if bench["query_p95_ms"] > 5:
    raise SystemExit("real librime query P95 exceeds 5 ms")
if neural_expected != neural_observed:
    raise SystemExit("real librime neural capability does not match installed model pack")
if neural_expected and not report.get("neural_candidate_observed"):
    raise SystemExit("real librime model is available but its held-out probe candidate was not produced")
report["harness"] = "rime_harness"
report["mode"] = "hybrid" if neural_observed else "core-only"
report["status"] = "passed"
Path("eval/rime_harness_summary.json").write_text(json.dumps(report, indent=2) + "\n")
PY

echo "RIME_HARNESS_OK"
