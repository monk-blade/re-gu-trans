#!/usr/bin/env bash
# Local helper: stage payload and print packaging commands.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck source=common.sh
source "$ROOT/scripts/package/common.sh"
VERSION="$(resolve_version)"
echo "version=$VERSION"
echo "librime_qjs=$LIBRIME_QJS_TAG librime=$LIBRIME_TAG"
echo
echo "Build commands:"
echo "  VERSION=$VERSION ./scripts/package/linux/build_packages.sh"
echo "  VERSION=$VERSION ./scripts/package/macos/build_pkg.sh"
echo "  VERSION=$VERSION ./scripts/package/windows/build_zip.sh"
"$ROOT/scripts/package/stage_payload.sh" "$ROOT/dist/payload" generic
