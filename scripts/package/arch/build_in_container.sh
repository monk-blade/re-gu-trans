#!/usr/bin/env bash
# Build one of the Arch Linux packages (ctc or xlit) inside a fresh
# archlinux:base-devel container, driven by makepkg as required (it refuses
# to run as root). Intended to be run *inside* that container, with the repo
# checkout bind-mounted at /workspace:
#
#   docker run --rm -v "$PWD:/workspace" -w /workspace archlinux:base-devel \
#     bash scripts/package/arch/build_in_container.sh ctc
#
# Verified locally (podman + archlinux:latest): both ctc/xlit variants build
# (makepkg -s --noconfirm --nodeps) and install (pacman -U) cleanly.

set -euo pipefail
VARIANT="${1:?usage: build_in_container.sh <ctc|xlit>}"
case "$VARIANT" in
  ctc) PKGBUILD_SRC="packaging/arch/PKGBUILD.ctc" ;;
  xlit) PKGBUILD_SRC="packaging/arch/PKGBUILD.xlit" ;;
  *) echo "FAIL: variant must be ctc or xlit (got: $VARIANT)" >&2; exit 2 ;;
esac

pacman -Syu --noconfirm --needed \
  base-devel git cmake ninja python python-pip nodejs npm boost \
  gflags google-glog leveldb marisa opencc yaml-cpp unzip curl sudo

useradd -m builder
echo 'builder ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/builder
git config --global --add safe.directory /workspace
chown -R builder:builder /workspace

# The PKGBUILD's build() resolves the repo root via `git rev-parse
# --show-toplevel` from $startdir, which makepkg sets to the PKGBUILD's own
# directory -- so it must be built in place under packaging/arch/, not copied
# elsewhere, for that resolution (and its `cd ../..` fallback) to hold.
BUILD_DIR="/workspace/packaging/arch"
VERSION="$(sudo -u builder bash -c "cd /workspace && source scripts/package/common.sh && resolve_version")"
sed "s/__VERSION__/${VERSION}/g" "$PKGBUILD_SRC" > "$BUILD_DIR/PKGBUILD"

# ONNXRUNTIME_ROOT/TARGET_ARCH are threaded through so the PKGBUILD's build()
# (which shells out to the shared scripts/package/linux/*.sh) can find a
# pre-fetched ONNX Runtime instead of downloading one itself, matching how
# the Nix flake and the release CI jobs already stage it.
sudo -u builder env \
  REQUIRE_BINARY_TRIES=1 \
  ONNXRUNTIME_ROOT="${ONNXRUNTIME_ROOT:-}" \
  TARGET_ARCH="${TARGET_ARCH:-x64}" \
  HOME=/home/builder \
  bash -c "cd '$BUILD_DIR' && makepkg -s --noconfirm --nodeps"

mkdir -p /workspace/dist/packages
cp -f "$BUILD_DIR"/*.pkg.tar.zst /workspace/dist/packages/
rm -f "$BUILD_DIR/PKGBUILD"
echo "Arch package(s):"
ls -la /workspace/dist/packages/*.pkg.tar.zst
