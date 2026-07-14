#!/usr/bin/env bash
# Shared helpers for packaging scripts.
# shellcheck disable=SC2034

set -euo pipefail

PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PACKAGE_ROOT

# Pin: HuangJian/librime-qjs v1.3.0 → librime 1.16.1
LIBRIME_QJS_TAG="${LIBRIME_QJS_TAG:-v1.3.0}"
LIBRIME_TAG="${LIBRIME_TAG:-1.16.1}"
export LIBRIME_QJS_TAG LIBRIME_TAG

# Direct asset URLs (bypass GitHub API rate limits in CI). Update when bumping LIBRIME_QJS_TAG.
QJS_MACOS_ARM64_URL="${QJS_MACOS_ARM64_URL:-https://github.com/HuangJian/librime-qjs/releases/download/v1.3.0/librime-qjs-7231b4a-macOS-ARM64.tar.bz2}"
QJS_WINDOWS_X64_URL="${QJS_WINDOWS_X64_URL:-https://github.com/HuangJian/librime-qjs/releases/download/v1.3.0/librime-qjs-7231b4a-Windows-clang-x64.7z}"
export QJS_MACOS_ARM64_URL QJS_WINDOWS_X64_URL

resolve_version() {
  if [[ -n "${VERSION:-}" ]]; then
    echo "${VERSION#v}"
    return
  fi
  if [[ -n "${GITHUB_REF_NAME:-}" && "${GITHUB_REF_NAME}" == v* ]]; then
    echo "${GITHUB_REF_NAME#v}"
    return
  fi
  if git -C "$PACKAGE_ROOT" describe --tags --exact-match 2>/dev/null | grep -q '^v'; then
    git -C "$PACKAGE_ROOT" describe --tags --exact-match | sed 's/^v//'
    return
  fi
  local schema_ver
  schema_ver="$(
    python3 - "$PACKAGE_ROOT/rime/gujarati.schema.yaml" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"(?m)^\s*version:\s*['\"]?([0-9]+(?:\.[0-9]+)*)", text)
print(m.group(1) if m else "0.0.0")
PY
  )"
  echo "${schema_ver:-0.0.0}-dev"
}

# Resolve a HuangJian/librime-qjs release asset URL.
# Args: macos-arm64 | windows-x64
# Prefers pinned direct URLs; falls back to GitHub API (with GITHUB_TOKEN when set).
resolve_qjs_asset_url() {
  local platform="$1"
  case "$platform" in
    macos-arm64)
      if [[ -n "${QJS_MACOS_ARM64_URL:-}" ]]; then
        echo "$QJS_MACOS_ARM64_URL"
        return
      fi
      ;;
    windows-x64)
      if [[ -n "${QJS_WINDOWS_X64_URL:-}" ]]; then
        echo "$QJS_WINDOWS_X64_URL"
        return
      fi
      ;;
    *)
      echo "ERROR: unknown qjs platform: $platform" >&2
      return 1
      ;;
  esac

  local api="https://api.github.com/repos/HuangJian/librime-qjs/releases/tags/${LIBRIME_QJS_TAG}"
  echo "Resolving librime-qjs ${platform} via GitHub API ${LIBRIME_QJS_TAG} ..." >&2
  python3 - "$api" "$platform" <<'PY'
import json, os, sys, urllib.request

api, platform = sys.argv[1], sys.argv[2]
headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "re-gu-trans-packaging",
}
token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
if token:
    headers["Authorization"] = f"Bearer {token}"

req = urllib.request.Request(api, headers=headers)
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.load(resp)

def match(name: str) -> bool:
    n = name.lower()
    if platform == "macos-arm64":
        return "macos-arm64" in n and n.endswith((".tar.bz2", ".tar.gz", ".tgz"))
    if platform == "windows-x64":
        return "windows" in n and ("x64" in n or "amd64" in n)
    return False

for a in data.get("assets") or []:
    name = a.get("name") or ""
    if match(name):
        print(a["browser_download_url"])
        break
else:
    raise SystemExit(f"no {platform} asset found for {api}")
PY
}

# Download URL to dest if missing (curl -fL).
download_file() {
  local url="$1"
  local dest="$2"
  if [[ -f "$dest" && -s "$dest" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  echo "Downloading $url → $dest"
  curl -fL --retry 3 --retry-delay 2 -o "$dest" "$url"
}

# Native path for tools that do not understand MSYS (/d/...) paths (Windows CI).
native_path() {
  local p="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$p"
  else
    echo "$p"
  fi
}

# Zip directory contents into archive_path (.zip). Works on macOS/Linux/Windows Git Bash.
zip_dir_contents() {
  local src_dir="$1"
  local archive_path="$2"
  mkdir -p "$(dirname "$archive_path")"
  rm -f "$archive_path"
  (
    cd "$src_dir"
    if command -v zip >/dev/null 2>&1; then
      zip -r "$archive_path" .
      return
    fi
    # 7-Zip (Windows CI) — needs native Windows paths under Git Bash
    if command -v 7z >/dev/null 2>&1; then
      local out_native
      out_native="$(native_path "$archive_path")"
      7z a -tzip -bd "$out_native" . >/dev/null
      return
    fi
    if command -v powershell.exe >/dev/null 2>&1; then
      local src_win out_win
      src_win="$(native_path "$src_dir")"
      out_win="$(native_path "$archive_path")"
      powershell.exe -NoProfile -Command \
        "Compress-Archive -Path (Join-Path -Path '$src_win' -ChildPath '*') -DestinationPath '$out_win' -Force"
      return
    fi
    python3 - "$src_dir" "$archive_path" <<'PY'
import os, shutil, sys

def to_native(p: str) -> str:
    # Git Bash / MSYS: /d/foo → D:\foo
    if len(p) > 2 and p[0] == "/" and p[2] == "/" and p[1].isalpha():
        return p[1].upper() + ":" + p[2:].replace("/", "\\")
    return p

src, dest = to_native(sys.argv[1]), to_native(sys.argv[2])
base, _ = os.path.splitext(dest)
shutil.make_archive(base, "zip", root_dir=src)
PY
  )
}

require_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing required file: $f" >&2
    exit 1
  fi
}
