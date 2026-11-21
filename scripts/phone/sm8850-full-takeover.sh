#!/usr/bin/env bash
# SM-S948B/m3q iOS 27 FULL Framework takeover, 8 vCPU / GPU 3D / 600s.
# - prepare: build locally, hash existing phone image, install signed
#   current native artifacts and independent APFS Data clone, NO Framework stop
# - run: actually stop Android Framework and start the 3D iOS guest.
#          An independent 600s deadline forces a return REBOOT.
set -euo pipefail

usage() {
    cat >&2 <<'HELP'
Usage:
  bash scripts/phone/sm8850-full-takeover.sh prepare [SERIAL]
  bash scripts/phone/sm8850-full-takeover.sh rearm [SERIAL]
  bash scripts/phone/sm8850-full-takeover.sh run [SERIAL] --i-accept-10-minute-legacy-watchdog-risk
The live run WILL stop Android Framework. Samsung USB + Volume Up+Down can
enter Download Mode. DO NOT press both volume keys during this experiment.
If frozen, Power/Side + Volume Down for >7 seconds forces a restart.
The 600s legacy-watchdog experiment is NOT qualified for unassisted recovery.
HELP
    exit 2
}

mode="${1:-}"
serial="${2:-R5GL64LZ9HA}"
risk="${3:-}"
case "$mode" in prepare|rearm|run) ;; *) usage ;; esac
[ "$mode" != run ] || [ "$risk" = --i-accept-10-minute-legacy-watchdog-risk ] || usage
[ "$mode" = run ] || [ -z "$risk" ] || usage
case "$serial" in
    ''|*[!a-zA-Z0-9_-]*) echo "Invalid ADB serial" >&2; exit 2 ;;
esac
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT"
git diff --quiet && git diff --cached --quiet || {
    echo "Tracked working tree has local modifications; refusing to operate" >&2
    exit 2
}
[ "$(git branch --show-current)" = feat/oneios-sm8850-m3q ] ||
    { echo "Expected feat/oneios-sm8850-m3q branch" >&2; exit 2; }
[ -z "$(git status --porcelain app)" ] || {
    echo "OneOS submodule has uncommitted or unexpected changes" >&2
    exit 2
}
ADB="${ONEIOS_ADB:-$HOME/Android/Sdk/platform-tools/adb}"
[ -x "$ADB" ] || { echo "ADB_NOT_FOUND=$ADB" >&2; exit 2; }
BASE="/data/local/tmp/oneios-m3q-ios27-bench"
OUT="$ROOT/out/sm8850/takeover"
mkdir -p "$OUT"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$OUT/full-$mode-$stamp-$$.log"
manifest="$OUT/full-image-$stamp-$$.sha256"
cleanup() {
    rc=$?
    trap - EXIT
    # A remote SSH/zsh session can have wl-copy installed but no Wayland
    # compositor/socket; never emit irrelevant clipboard connection errors.
    if [ -n "${WAYLAND_DISPLAY:-}" ] && [ -n "${XDG_RUNTIME_DIR:-}" ] &&
       [ -S "${XDG_RUNTIME_DIR}/${WAYLAND_DISPLAY}" ] &&
       command -v wl-copy >/dev/null 2>&1; then
        wl-copy --type text/plain < "$LOG" || :
        if command -v wl-paste >/dev/null 2>&1 &&
           wl-paste --type text/plain | cmp -s "$LOG" -; then
            echo "CLIPBOARD=VERIFIED"
        else
            echo "CLIPBOARD=NOT_VERIFIED"
        fi
    fi
    echo "LOG=$LOG"
    echo "EXIT=$rc"
    exit "$rc"
}
trap cleanup EXIT
{
  echo "===== EXACT REPO REVISION ====="
  git rev-parse HEAD
  git -C app rev-parse HEAD
  echo "===== USB IDENTITY ====="
  "$ADB" -s "$serial" get-state
  "$ADB" -s "$serial" shell getprop ro.product.model
  "$ADB" -s "$serial" shell getprop ro.build.version.incremental
  if [ "$mode" = prepare ]; then
    echo "===== LOCAL REGRESSION (NO PHONE FRAMEWORK STOP) ====="
    python3 scripts/phone/test-sm8850-takeover.py -v
    python3 scripts/phone/test-sm8850-full-takeover.py -v
    python3 scripts/phone/test-sm8850-oneos-legacy-feeder.py -v
    python3 scripts/phone/test-sm8850-stage-upgrade.py -v

    echo "===== BUILD CURRENT 3D XNUHOST AND DISPLAY USING ALL LOCAL CPU CORES ====="
    jobs=$(nproc)
    echo "LOCAL_BUILD_JOBS=$jobs"
    make -C runtime/xnuhost -j"$jobs" build/android/xnuhost
    make -C runtime/display -j"$jobs" all

    echo "===== CREATE COMPLETE IMAGE HASH MANIFEST (READ ONLY) ====="
    "$ADB" -s "$serial" exec-out \
      "su -c 'cd $BASE && find image -type f | sort | xargs sha256sum'" > "$manifest"
    python3 - "$manifest" <<'PY'
import importlib.util
from pathlib import Path
import sys
path = Path("scripts/phone/sm8850-takeover.py")
spec = importlib.util.spec_from_file_location("sm8850_takeover", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
valid = mod.manifest_bytes(Path(sys.argv[1]))
Path(sys.argv[1]).write_bytes(valid)
print(f"IMAGE_MANIFEST=VERIFIED_ENTRIES:{len(valid.splitlines())}")
PY

    echo "===== SAFE STAGE CHECK AND ROLLBACK-BACKED UPGRADE ====="
    python3 scripts/phone/sm8850-takeover.py \
      --reboot-stage-check --confirm --serial "$serial"

    echo "===== PREPARE FULL 8-VCPU 3D IMAGE AND INDEPENDENT DATA ====="
    python3 scripts/phone/sm8850-takeover.py \
      --prepare --confirm --serial "$serial" \
      --bench-manifest "$manifest"
    echo "FULL_TAKEOVER_STAGE=PREPARED"
    echo "LIVE_FRAMEWORK_STOP=NO"
    echo "MANIFEST=$manifest"
  elif [ "$mode" = rearm ]; then
    echo "===== VERIFY PATCHED GUEST MOUNT SAFETY (LOCAL ONLY) ====="
    python3 scripts/phone/test-sm8850-full-takeover.py -v
    echo "===== UPGRADE ON-DEVICE ONEOS SCRIPTS (NO FRAMEWORK STOP) ====="
    python3 scripts/phone/sm8850-takeover.py \
      --reboot-stage-check --confirm --serial "$serial"
    echo "===== FRESH APFS DATA CLONE ONLY; PRESERVE CONSUMED SNAPSHOT ====="
    python3 scripts/phone/sm8850-takeover.py \
      --rearm-data --confirm --serial "$serial"
    echo "===== FULL-RUN ADMISSION PREFLIGHT (READ-ONLY, NO FRAMEWORK STOP) ====="
    "$ADB" -s "$serial" shell -T \
      "su -c '/system/bin/sh /data/adb/oneios-m3q-framework/oneios_switch.sh --framework-check run'"
    echo "FULL_TAKEOVER_ADMISSION=PASS_NO_FRAMEWORK_STOP"
    echo "FULL_TAKEOVER_STAGE=REARMED"
    echo "LIVE_FRAMEWORK_STOP=NO"
  else
    echo "===== LIVE FULL FRAMEWORK TAKEOVER 8 VCPU + GPU3D 600S ====="
    echo "WARNING=LEGACY_WATCHDOG_NOT_INDEPENDENTLY_QUALIFIED"
    echo "WARNING=UNASSISTED_NORMAL_ONEUI_REBOOT_NOT_VERIFIED"
    echo "WARNING=PRIOR_FULL_RUN_GUEST_READY_AND_KGSL_OBSERVED_BUT_PERFORMANCE_POOR"
    echo "WARNING=SEPARATE_ONEIOS_THERMAL_BRIDGE_INACTIVE_WITH_BENCH_BRIDGES_0"
    echo "WARNING=HOST_CPU_MASK_0_7_IS_NOT_8_CORE_AFFINITY_PROOF"
    echo "WARNING=GPU_3D_REQUIRED_NO_2D_FALLBACK; IF_KGSL_INIT_FAILS_GUEST_BOOT_FAILS"
    echo "WARNING=ONE_SHOT_APFS_DATA_MUST_BE_FRESH_FOR_EACH_RUN"
    echo "PHYSICAL_KEYS=DO_NOT_PRESS_BOTH_VOLUME_KEYS"
    echo "RECOVERY=MANDATORY_REBOOT_AT_600_SECONDS_OR_EARLIER_ON_FAILURE"
    python3 scripts/phone/sm8850-takeover.py \
      --run --confirm --accept-legacy-watchdog-risk \
      --duration 600 --gpu 3d --serial "$serial"
  fi
} 2>&1 | tee "$LOG"
exit "${PIPESTATUS[0]}"
