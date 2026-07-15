#!/usr/bin/env bash
# Emit SHA-256 checksums for a staged payload / release directory.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"
DIR="${1:?usage: checksum_release.sh DIR}"
OUT="${2:-$DIR/SHA256SUMS}"
(
  cd "$DIR"
  while IFS= read -r -d '' file; do
    sha256_file "$file"
  done < <(find . -type f ! -name SHA256SUMS ! -name '*.sbom.json' -print0 | sort -z)
) >"$OUT"
echo "wrote $OUT"
