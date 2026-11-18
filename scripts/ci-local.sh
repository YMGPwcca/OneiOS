#!/usr/bin/env bash
# OneiOS CachyOS local CI. No device access, sudo, Apple firmware or GitHub-hosted build.
# Usage: scripts/ci-local.sh [test|all] [VERSION]
#   test: validate source and run the full runtime host regression suite.
#   all:  test, then produce and validate the ARM64 runtime artifact.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

mode=${1:-all}
version=${2:-0.0.0-ci}
case "$mode" in test|all) ;; *) echo "usage: $0 [test|all] [VERSION]" >&2; exit 2 ;; esac

JOBS=${JOBS:-$(getconf _NPROCESSORS_ONLN)}
export JOBS
export MAKEFLAGS="${MAKEFLAGS:--j$JOBS}"
export ANDROID_NDK_ROOT="${ANDROID_NDK_ROOT:-${NDK:-$HOME/Android/Sdk/ndk/28.2.13676358}}"
export NDK="$ANDROID_NDK_ROOT"

need() { command -v "$1" >/dev/null 2>&1 || { echo "ci-local: missing $1" >&2; exit 1; }; }
for tool in git make gcc clang python3 zstd tar sha256sum strings shellcheck rustup cargo javac qemu-aarch64; do
  need "$tool"
done
test -x "$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang" || {
  echo "ci-local: Android NDK 28.2.13676358 required at $NDK" >&2
  exit 1
}
grep -q '^Pkg.Revision = 28.2.13676358$' "$NDK/source.properties"
test -n "$(find "${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}/build-tools" -maxdepth 2 -name d8 -type f -print -quit 2>/dev/null)" || {
  echo "ci-local: Android SDK build-tools/d8 is missing" >&2
  exit 1
}
rustup target list --installed | grep -qx 'aarch64-linux-android' || {
  echo "ci-local: rustup target add aarch64-linux-android" >&2
  exit 1
}
echo "ci-local: checkout $(git rev-parse --short HEAD), mode=$mode, jobs=$JOBS"
git diff --check
.github/scripts/check-tracked-files.sh
git ls-files -z '*.sh' | xargs -0 -r -n1 bash -n
git ls-files -z '*.py' | xargs -0 -r python3 -m py_compile
shellcheck -S error $(git ls-files 'kernel/*.sh' 'runtime/*.sh' '.github/*.sh')
bash -n scripts/ci-local.sh
# The passive S24->SM8850 audit is a Bash wrapper containing a POSIX Android
# /system/bin/sh heredoc. Check that phone payload's syntax separately.
for audit in scripts/phone/audit-s24-preflight-m3q.sh scripts/phone/audit-s24-followup-m3q.sh; do
  awk '
    /<<.*PHONE/ { phone=1; next }
    phone && /^PHONE$/ { closed=1; exit }
    phone { print }
    END { if (!phone || !closed) exit 1 }
  ' "$audit" | sh -n
done

# Fetch the pinned 3D renderer before compiling xnuhost. Never build a 2D-only runtime.
scripts/setup/get-references.sh virglrenderer
test -f external/virglrenderer/src/drm/drm2kgsl/drm2kgsl_renderer.c

runtime/host-tests.sh
kernel/tests/host.sh
# Also exercise driver-side PCM haptics, camera and userland host tests.
# The runtime suite already covers runtime/; do not run its tests twice.
while IFS= read -r test_script; do
  case "$test_script" in runtime/*|kernel/*) continue ;; esac
  echo "ci-local: $test_script"
  "$test_script"
done < <(git ls-files '*/tests/host.sh')

if [ "$mode" = all ]; then
  runtime/package.sh "$version"
  archive="out/release/oneios-runtime-$version-arm64.tar.zst"
  ( cd out/release && sha256sum -c "$(basename "$archive").sha256" )
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  zstd -dc "$archive" | tar -xf - -C "$tmp"
  test -x "$tmp/bin/bridgectl"
  for binary in xnuhost gpuctl; do
    if strings "$tmp/bin/$binary" | grep -q 'this build has no drm2kgsl'; then
      echo "ci-local: $binary lacks drm2kgsl" >&2
      exit 1
    fi
  done
  runtime/package/elf-check.sh "$tmp"
  echo "ci-local: PASS - $archive"
else
  echo "ci-local: PASS - host tests"
fi
