#!/usr/bin/env bash
# SM-S948B/m3q iOS 27 FULL Framework takeover, 8 vCPU / GPU 3D / <=600s.
# - prepare: build locally, hash existing phone image, install signed
#   current native artifacts and independent APFS Data clone, NO Framework stop
# - stage-runtime: install pinned OneOS scripts and prebuilt 3D runtime only;
#   preserve the one-shot APFS Data state; NEVER stop Android Framework
# - run: actually stop Android Framework and start the 3D iOS guest.
#          A device-side deadline requests a reboot-return. The legacy
#          watchdog and unassisted return have NOT been qualified.
set -euo pipefail

usage() {
    cat >&2 <<'HELP'
Usage:
  bash scripts/phone/sm8850-full-takeover.sh prepare [SERIAL]
  bash scripts/phone/sm8850-full-takeover.sh rearm [SERIAL]
  bash scripts/phone/sm8850-full-takeover.sh stage-runtime [SERIAL]
  bash scripts/phone/sm8850-full-takeover.sh run [SERIAL] --i-accept-10-minute-legacy-watchdog-risk [--duration SECONDS] [--perf-profile off|frame|task|frame-task] [--cpu-profile default|prime-first]
stage-runtime: root-only stage update, no build/test, no APFS rearm and no
Framework stop; requires previously consumed Data and prebuilt 3D artifacts.
Full-bridges experimental branch: rearm and run are explicitly gated by
ONEIOS_SM8850_FULL_BRIDGES_180S=I_ACCEPT_UNQUALIFIED_180S_LIVE_TEST.
Both rearm and run require --duration 180, selected by the operator.
Re-arming fresh one-shot Data and launching are separate steps; the
180s software deadline is not an independently qualified recovery guarantee.
On feat/sm8850-xnuhost-perf-p0, the existing 180s passive experiment is
selected by the wrapper for rearm/run; callers need no separate export.
On other supported branches, the explicit passive experiment still uses:
ONEIOS_SM8850_SOFT_THERMAL_OFF=I_ACCEPT_SOFT_GUARD_OFF_180S
This disables the OneOS root thermal monitor AND its 28% CPU cap worker.
Kernel/firmware thermal protections remain unchanged; recovery is unqualified.
The floor-aware 28% requested CPU limit may be exceeded by Samsung minimum
frequency votes. All other full-run durations: 60..600 seconds, default 600.
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
duration=600
duration_explicit=0
perf_profile=off
cpu_profile=default
case "$mode" in prepare|rearm|stage-runtime|run) ;; *) usage ;; esac
if [ "$mode" = run ]; then
    [ "$risk" = --i-accept-10-minute-legacy-watchdog-risk ] || usage
    shift 3
    if [ "$#" -gt 0 ] && [ "$1" = --duration ]; then
        [ "$#" -ge 2 ] || usage
        duration=$2
        duration_explicit=1
        shift 2
    fi
    perf_seen=0
    cpu_seen=0
    while [ "$#" -gt 0 ]; do
        [ "$#" -ge 2 ] || usage
        case "$1" in
            --perf-profile)
                [ "$perf_seen" = 0 ] || usage
                perf_seen=1
                perf_profile=$2
                case "$perf_profile" in off|frame|task|frame-task) ;; *) usage ;; esac ;;
            --cpu-profile)
                [ "$cpu_seen" = 0 ] || usage
                cpu_seen=1
                cpu_profile=$2
                case "$cpu_profile" in default|prime-first) ;; *) usage ;; esac ;;
            *) usage ;;
        esac
        shift 2
    done
elif [ "$mode" = rearm ] && [ "$#" -eq 4 ] && [ "$3" = --duration ]; then
    duration=$4
    duration_explicit=1
else
    [ "$#" -le 2 ] || usage
fi
if [ "$mode" = run ] || [ "$mode" = rearm ]; then
    case "$duration" in ''|0*|*[!0-9]*) usage ;; esac
    [ "${#duration}" -le 3 ] && [ "$duration" -ge 60 ] && [ "$duration" -le 600 ] || usage
fi
case "$serial" in
    ''|*[!a-zA-Z0-9_-]*) echo "Invalid ADB serial" >&2; exit 2 ;;
esac
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$ROOT"
git diff --quiet && git diff --cached --quiet || {
    echo "Tracked working tree has local modifications; refusing to operate" >&2
    exit 2
}
FULL_BRIDGES_BRANCH=0
BRANCH=$(git branch --show-current)
case "$BRANCH" in
    feat/sm8850-guarded-duration-tracing)
        [ "$mode" != stage-runtime ] || {
            echo "BLOCKED: stage-runtime is for full-bridges integration only" >&2
            exit 2
        } ;;
    feat/oneios-sm8850-m3q|feat/sm8850-full-bridges-takeover|feat/sm8850-xnuhost-perf-p0)
        FULL_BRIDGES_BRANCH=1
        case "$mode" in
            stage-runtime) ;;
            rearm|run)
                [ "${ONEIOS_SM8850_FULL_BRIDGES_180S:-}" = I_ACCEPT_UNQUALIFIED_180S_LIVE_TEST ] || {
                    echo "BLOCKED: full bridges live trial requires explicit 180s experimental opt-in" >&2
                    exit 2
                }
                [ "$duration_explicit" = 1 ] && [ "$duration" = 180 ] || {
                    echo "BLOCKED: this full bridges trial must explicitly select --duration 180" >&2
                    exit 2
                } ;;
            *)
                echo "BLOCKED: full bridges allows only stage-runtime, rearm or 180s run" >&2
                exit 2 ;;
        esac ;;
    *) echo "Expected an authorized SM8850 feature branch" >&2; exit 2 ;;
esac
# The dedicated performance branch uses one fixed 180s profile throughout
# rearm, preflight and live run. The existing duration/risk gates above remain.
if [ "$BRANCH" = feat/sm8850-xnuhost-perf-p0 ] &&
   { [ "$mode" = rearm ] || [ "$mode" = run ]; }; then
    export ONEIOS_SM8850_SOFT_THERMAL_OFF=I_ACCEPT_SOFT_GUARD_OFF_180S
fi
[ "$(git -C app rev-parse HEAD)" = "$(git rev-parse HEAD:app)" ] || {
    echo "BLOCKED: OneOS submodule commit does not match OneiOS gitlink" >&2
    exit 2
}
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
  elif [ "$mode" = stage-runtime ]; then
    echo "===== VERIFY PREBUILT FULL BRIDGES=1 ARM64 RUNTIME (NO REBUILD) ====="
    XNUHOST=runtime/xnuhost/build/android/xnuhost
    [ -s "$XNUHOST" ] &&
      grep -aFq 'SM8850_FULL_BRIDGES=ACTIVE' "$XNUHOST" || {
        echo "BLOCKED: local ARM64 xnuhost lacks full-bridges marker; no staging attempted" >&2
        exit 2
    }
    grep -aFq 'SM8850_FULL_BRIDGES=ADMITTED_NO_USERSPACE_THERMAL_180S' "$XNUHOST" || {
      echo "BLOCKED: stale ARM64 XNUHost does not recognize the 180s no-thermal-guard stage proof; rebuild native xnuhost before staging" >&2
      exit 2
    }
    echo "STAGED_NO_GUARD_RUNTIME_PROTOCOL=ADMISSION_180S_SUPPORTED"
    for native in oneios-display oneios-display.dex liboneios-display.so; do
      [ -s "runtime/display/build/android/$native" ] || {
        echo "BLOCKED: missing prebuilt runtime/display/build/android/$native" >&2
        exit 2
      }
    done
    sha256sum "$XNUHOST" \
      runtime/display/build/android/oneios-display \
      runtime/display/build/android/oneios-display.dex \
      runtime/display/build/android/liboneios-display.so
    echo "===== STAGE PINNED ONEOS SCRIPTS (ROLLBACK PRESERVED) ====="
    python3 scripts/phone/sm8850-takeover.py \
      --reboot-stage-check --confirm --serial "$serial"
    echo "===== STAGE NATIVE RUNTIME (ROLLBACK PRESERVED; DATA NOT REARMED) ====="
    python3 scripts/phone/sm8850-takeover.py \
      --upgrade-runtime --confirm --serial "$serial"
    echo "FULL_BRIDGES_STAGE_ONLY=PASS"
    echo "APFS_DATA=CONSUMED_NOT_REARMED"
    echo "FRAMEWORK_STOP=NO LIVE_TAKEOVER=NO"
  elif [ "$mode" = rearm ]; then
    if [ "$FULL_BRIDGES_BRANCH" = 1 ]; then
      echo "===== FULL BRIDGES ${duration}S TRIAL: VERIFY PREVIOUSLY STAGED XNUHOST ====="
      XNUHOST=runtime/xnuhost/build/android/xnuhost
      test -s "$XNUHOST"
      grep -aFq 'SM8850_FULL_BRIDGES=ACTIVE' "$XNUHOST"
      EXPECTED_SHA=$(sha256sum "$XNUHOST" | awk '{print $1}')
      INSTALLED_SHA=$("$ADB" -s "$serial" exec-out \
        "su -c 'sha256sum /data/adb/oneios-m3q-framework/runtime/bin/xnuhost'" \
        | tr -d '\r' | awk '{print $1}')
      [ "$EXPECTED_SHA" = "$INSTALLED_SHA" ] || {
        echo "BLOCKED: on-device xnuhost SHA-256 differs from validated local build" >&2
        exit 2
      }
      echo "STAGED_FULL_BRIDGES_XNUHOST_SHA256=$INSTALLED_SHA"
      echo "===== REBIND ONEOS THERMAL SENSOR MANIFEST TO CURRENT BOOT ====="
      python3 scripts/phone/sm8850-takeover.py \
        --reboot-stage-check --confirm --serial "$serial"
      echo "===== FRESH ONE-SHOT APFS DATA CLONE; PRESERVE CONSUMED DATA ====="
      python3 scripts/phone/sm8850-takeover.py \
        --rearm-data --confirm --serial "$serial"
      echo "===== READ-ONLY ${duration}S LIVE ADMISSION PREFLIGHT ====="
      if [ "${ONEIOS_SM8850_SOFT_THERMAL_OFF:-}" = I_ACCEPT_SOFT_GUARD_OFF_180S ]; then
        # Same explicit token and marker checks as the live host launcher.
        python3 scripts/phone/sm8850-600s-thermal-telemetry.py \
          --repo "$ROOT" --adb "$ADB" --serial "$serial" \
          --duration "$duration" --preflight-only
      else
        "$ADB" -s "$serial" shell -T \
          "su -c '/system/bin/sh /data/adb/oneios-m3q-framework/oneios_switch.sh --framework-check run $duration'"
      fi
      echo "FULL_BRIDGES_${duration}S_REARM=PASS_NO_FRAMEWORK_STOP"
      echo "LIVE_FRAMEWORK_STOP=NO"
    else
    echo "===== VERIFY PATCHED GUEST MOUNT SAFETY (LOCAL ONLY) ====="
    python3 scripts/phone/test-sm8850-full-takeover.py -v
    echo "===== UPGRADE ON-DEVICE ONEOS SCRIPTS (NO FRAMEWORK STOP) ====="
    python3 scripts/phone/sm8850-takeover.py \
      --reboot-stage-check --confirm --serial "$serial"
    echo "===== REBUILD LATEST NATIVE 3D/TOUCH RUNTIME ON LOCAL CACHYOS ====="
    jobs=$(nproc)
    make -C runtime/xnuhost -j"$jobs" build/android/xnuhost
    make -C runtime/display -j"$jobs" all
    echo "===== REPLACE NATIVE 3D RUNTIME WITH HASHED ROLLBACK (NO FRAMEWORK STOP) ====="
    python3 scripts/phone/sm8850-takeover.py \
      --upgrade-runtime --confirm --serial "$serial"
    echo "===== FRESH APFS DATA CLONE ONLY; PRESERVE CONSUMED SNAPSHOT ====="
    python3 scripts/phone/sm8850-takeover.py \
      --rearm-data --confirm --serial "$serial"
    echo "===== FULL-RUN ADMISSION PREFLIGHT (READ-ONLY, NO FRAMEWORK STOP) ====="
    "$ADB" -s "$serial" shell -T \
      "su -c '/system/bin/sh /data/adb/oneios-m3q-framework/oneios_switch.sh --framework-check run'"
    echo "FULL_TAKEOVER_ADMISSION=PASS_NO_FRAMEWORK_STOP"
    echo "FULL_TAKEOVER_STAGE=REARMED"
    echo "LIVE_FRAMEWORK_STOP=NO"
    fi
  else
    echo "===== LIVE FULL FRAMEWORK TAKEOVER 8 VCPU + GPU3D ${duration}S ====="
    echo "WARNING=LEGACY_WATCHDOG_NOT_INDEPENDENTLY_QUALIFIED"
    echo "WARNING=UNASSISTED_NORMAL_ONEUI_REBOOT_NOT_VERIFIED"
    echo "WARNING=PRIOR_FULL_RUN_GUEST_READY_AND_KGSL_OBSERVED_BUT_PERFORMANCE_POOR"
    if [ "${ONEIOS_SM8850_SOFT_THERMAL_OFF:-}" = I_ACCEPT_SOFT_GUARD_OFF_180S ]; then
      echo "SM8850_SOFT_THERMAL_GUARD=OFF_NO_ON_DEVICE_PROCESS"
      echo "CPU_UNDERCLOCK=OFF_NO_ROOT_CAP_WORKER"
      echo "WARNING=NO_ONEOS_CPU_CEILING_AND_NO_ROOT_THERMAL_GUARD"
      echo "WARNING=HISTORIC_CPU_PEAK_101C_WITH_SOFTWARE_EARLY_RETURN_DISABLED"
      echo "KERNEL_FIRMWARE_THERMAL_PROTECTION=UNCHANGED"
    else
      echo "THERMAL_SAFETY=ROOT_GUARD_AND_MONOTONIC_THROTTLE_REQUIRED; 80C_THROTTLE; 90C_EMERGENCY_RETURN"
    fi
    if [ "$FULL_BRIDGES_BRANCH" = 1 ]; then
      echo "SM8850_BRIDGES=1 CPU_PIN=1 CPU_AFFINITY_BENCH=0"
      echo "WARNING=HISTORIC_95C_101C_PEAKS; ${duration}S_DEADLINE_AND_WATCHDOG_RETURN_UNQUALIFIED"
    else
      echo "CPU_AFFINITY=BENCH_ONLY_EIGHT_DISTINCT_HOST_CORES_REQUIRED"
    fi
    echo "WARNING=GPU_3D_REQUIRED_NO_2D_FALLBACK; IF_KGSL_INIT_FAILS_GUEST_BOOT_FAILS"
    echo "WARNING=ONE_SHOT_APFS_DATA_MUST_BE_FRESH_FOR_EACH_RUN"
    echo "PHYSICAL_KEYS=DO_NOT_PRESS_BOTH_VOLUME_KEYS"
    echo "RECOVERY=MANDATORY_REBOOT_AT_${duration}_SECONDS_OR_EARLIER_ON_FAILURE"
    extra=()
    [ "$perf_profile" = off ] || extra+=(--perf-profile "$perf_profile")
    [ "$cpu_profile" = default ] || extra+=(--cpu-profile "$cpu_profile")
    if [ "${ONEIOS_SM8850_SOFT_THERMAL_OFF:-}" = I_ACCEPT_SOFT_GUARD_OFF_180S ]; then
      [ "$duration" = 180 ] || { echo "BLOCKED: passive thermal mode requires 180s" >&2; exit 2; }
      extra+=(--no-userspace-thermal-180)
    fi
    python3 scripts/phone/sm8850-takeover.py \
      --run --confirm --accept-legacy-watchdog-risk \
      --duration "$duration" --gpu 3d --serial "$serial" "${extra[@]}"
  fi
} 2>&1 | tee "$LOG"
exit "${PIPESTATUS[0]}"
