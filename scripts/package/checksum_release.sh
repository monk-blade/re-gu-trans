#!/usr/bin/env bash
# Emit SHA-256 checksums for a staged payload / release directory.
set -euo pipefail
DIR="${1:?usage: checksum_release.sh DIR}"
OUT="${2:-$DIR/SHA256SUMS}"
(
  cd "$DIR"
  find . -type f ! -name SHA256SUMS ! -name '*.sbom.json' -print0 |
    sort -z |
    xargs -0 shasum -a 256
) >"$OUT"
echo "wrote $OUT"
