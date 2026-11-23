#!/usr/bin/env bash
# One focused local-only check for the experimental SM8850 full bridges=1.
# NEVER talks to adb, does not stage/flash/rearm APFS or start a live guest.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

BRANCH="$(git branch --show-current)"
# OneiOS's configured default integration branch is full-bridges=1.
# Keep the former integration branch accepted for reproducible offline CI.
case "$BRANCH" in
  feat/oneios-sm8850-m3q|feat/sm8850-full-bridges-takeover) ;;
  *)
    echo "BLOCKED: wrong OneiOS branch for full bridges: $BRANCH" >&2
    exit 2 ;;
esac
test "$(git -C app status --porcelain)" = "" || {
  echo "BLOCKED: OneOS submodule has local modifications" >&2
  exit 2
}
echo "===== EXACT SOURCE REVISIONS ====="
git rev-parse HEAD
git -C app rev-parse HEAD
echo "===== VERIFY TRUE BRIDGES=1 IN ONEOS ====="
grep -Fq -- '--set bridges=1 --set sm8850-full-bridges=1' app/switcher/assets/oneios_switch.sh
grep -Fq -- '--set cpu-affinity-bench=0 --set cpu-pin=1' app/switcher/assets/oneios_switch.sh
if grep -Fq -- '--set bridges=0 --set panel-bridge=1' app/switcher/assets/oneios_switch.sh; then
  echo "BLOCKED: stale brightness-only run profile" >&2
  exit 2
fi
echo "===== SYNTAX + OFFLINE TESTS ====="
sh -n app/switcher/assets/oneios_switch.sh
python3 -m py_compile app/tests/test_sm8850_guarded_full.py
python3 app/tests/test_sm8850_guarded_full.py -v
echo "===== HOST TAKEOVER / THERMAL PROFILE HANDOFF REGRESSIONS ====="
python3 scripts/phone/test-sm8850-takeover.py -v
python3 scripts/phone/test-sm8850-full-takeover.py -v
python3 scripts/phone/test-sm8850-guarded-duration.py -v

echo "===== READ-ONLY GPU/RESPRING PARSER REGRESSION ====="
python3 scripts/phone/test-sm8850-gpu-respring-forensics.py -v

echo "===== COMPILE AND RUN XNUHOST PORTABLE UNIT TESTS ====="
make -C runtime/xnuhost -j"${JOBS:-8}" build/host/test_xnuhost
(cd runtime/xnuhost && ASAN_OPTIONS=detect_leaks=0 ./build/host/test_xnuhost)

echo "===== GPU_COMMAND EPROTO FAULT-INJECTION ON PINNED DRM2KGSL ====="
test -f external/virglrenderer/src/drm/drm2kgsl/drm2kgsl_renderer.c || {
  echo "BLOCKED: pinned external/virglrenderer checkout missing" >&2
  exit 2
}
make -C runtime/xnuhost -j"${JOBS:-8}" build/host/test_drm2kgsl
(cd runtime/xnuhost && ASAN_OPTIONS=detect_leaks=0 ./build/host/test_drm2kgsl)

# Opt in to a real arm64 link when NDK/virglrenderer dependencies are installed.
if [ "${SM8850_BUILD_ARM64:-0}" = 1 ]; then
  echo "===== NATIVE ARM64 XNUHOST BUILD ====="
  make -C runtime/xnuhost -j"${JOBS:-8}" build/android/xnuhost
  test -s runtime/xnuhost/build/android/xnuhost
  grep -aFq 'SM8850_FULL_BRIDGES=ACTIVE' runtime/xnuhost/build/android/xnuhost
  file runtime/xnuhost/build/android/xnuhost
  echo "SM8850_NATIVE_ARM64=BUILT_NOT_STAGED"
else
  echo "SM8850_NATIVE_ARM64=NOT_BUILT_SET_SM8850_BUILD_ARM64_1"
fi
echo "SM8850_FULL_BRIDGES_LOCAL_CI=PASS_NO_DEVICE_ACCESS"
echo "BRIDGES=1_TOUCH_EXCLUSIVE=1"
echo "FRAMEWORK_STOP=NO APFS_REARM=NO LIVE_TAKEOVER=NO"
