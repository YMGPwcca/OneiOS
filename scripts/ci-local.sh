#!/usr/bin/env bash
# OneiOS CachyOS local CI. No device access, sudo, Apple firmware or GitHub-hosted build.
# Usage: scripts/ci-local.sh [test|all|recovery] [VERSION]
#   test: validate source and run the full runtime host regression suite.
#   all:  test, then produce and validate the ARM64 runtime artifact.
#   recovery: run the pinned recovery fixture and offline observer tests.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

mode=${1:-all}
version=${2:-0.0.0-ci}
case "$mode" in test|all|recovery) ;; *) echo "usage: $0 [test|all|recovery] [VERSION]" >&2; exit 2 ;; esac

if [ "$mode" = recovery ]; then
  mksh_bin=${ONEOS_TEST_MKSH:-$(command -v mksh || true)}
  test -x "$mksh_bin" || { echo "ci-local: set ONEOS_TEST_MKSH to an executable mksh" >&2; exit 1; }
  report=${ONEIOS_RECOVERY_REPORT:-out/recovery/phase3-$(date -u +%Y%m%dT%H%M%SZ).json}
  bash -n scripts/ci-local.sh
  for script in app/switcher/assets/oneios_switch.sh app/switcher/assets/oneios_return.sh; do
    bash -n "$script"
    "$mksh_bin" -n "$script"
  done
  python3 scripts/phone/test-observe-s26-recovery.py
  bash -n scripts/phone/s26-watchdog-metadata.sh
  "$mksh_bin" -n scripts/phone/s26-watchdog-metadata.sh
  python3 scripts/phone/test-s26-watchdog-attribution.py
  bash -n scripts/phone/sm8850-watchdog-owners.sh
  python3 scripts/phone/test-sm8850-watchdog-owners.py -v
  (
    ndk_for_scan="${ANDROID_NDK_ROOT:-${NDK:-$HOME/Android/Sdk/ndk/28.2.13676358}}"
    cc_for_scan="$ndk_for_scan/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"
    test -x "$cc_for_scan" || {
      echo "ci-local: Android NDK clang missing for SM8850 watchdog scanner" >&2
      exit 1
    }
    scan_build=$(mktemp -d)
    trap 'rm -rf "$scan_build"' EXIT
    "$cc_for_scan" -std=c11 -Wall -Wextra -Werror -O2 -fPIE -pie \
      scripts/phone/sm8850-watchdog-owners.c -o "$scan_build/fdscan"
    test -s "$scan_build/fdscan"
    echo "ci-local: PASS - SM8850 AArch64 passive FD scanner crossbuild"
  )
  awk '
    /<<.*PHONE/ { phone=1; next }
    phone && /^PHONE$/ { closed=1; exit }
    phone { print }
    END { if (!phone || !closed) exit 1 }
  ' scripts/phone/sm8850-watchdog-owners.sh | "$mksh_bin" -n
  python3 scripts/phone/test-sm8850-takeover.py
  python3 scripts/phone/test-sm8850-smoke-evidence.py -v
  ONEOS_TEST_MKSH="$mksh_bin" python3 scripts/phone/test-sm8850-mksh-flock.py -v
  ONEOS_TEST_MKSH="$mksh_bin" python3 scripts/phone/test-sm8850-oneos-legacy-feeder.py -v
  ONEOS_TEST_MKSH="$mksh_bin" python3 scripts/phone/test-sm8850-stage-upgrade.py -v
  observer=()
  if [ -n "${ONEIOS_RECOVERY_OBSERVER_REPORT:-}" ]; then
    observer=(--observer-report "$ONEIOS_RECOVERY_OBSERVER_REPORT")
  fi
  source_flags=()
  if [ "${ONEIOS_RECOVERY_WORKTREE:-0}" = 1 ]; then
    python3 scripts/phone/test-oneios-watchdog.py -v
    source_flags=(--working-tree)
  fi
  python3 scripts/phone/recovery-dry-run.py --mksh "$mksh_bin" --output "$report" "${observer[@]}" "${source_flags[@]}"
  sha256sum "$report"
  exit
fi

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
