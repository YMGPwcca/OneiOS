#!/usr/bin/env bash
# Build only the diagnostic executable and thermalctl from the validated
# source export; never run XNUHost, modify the existing stage, or stop UI.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
R=$PWD
ADB="${ADB:-$HOME/Android/Sdk/platform-tools/adb}"
command -v timeout >/dev/null
D=$(mktemp -d /tmp/oneios-physical-probe.XXXXXX)
echo "EVIDENCE=$D"
if [ -n "${ONEIOS_PROBE_REUSE_DIR:-}" ]; then
    # Reuse the local diagnostics built by this exact probe source.
    # Do not rerun an unrelated native build to debug ADB transport.
    test -s "$ONEIOS_PROBE_REUSE_DIR/actuators"
    test -s "$ONEIOS_PROBE_REUSE_DIR/thermalctl"
    cp "$ONEIOS_PROBE_REUSE_DIR/actuators" "$D/actuators"
    cp "$ONEIOS_PROBE_REUSE_DIR/thermalctl" "$D/thermalctl"
    echo "PROBE_BUILD=REUSED_LOCAL_ARTIFACTS"
else
    NDK="${ANDROID_NDK_ROOT:-${NDK:-$HOME/Android/Sdk/ndk/28.2.13676358}}"
    AC="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"
    test -x "$AC"
    N="$R/app/switcher/native"
    "$AC" -std=gnu11 -O2 -g -Wall -Wextra -Werror -static -I"$N" \
        "$R/runtime/xnuhost/tools/stock-physical-probe.c" \
        "$N/sm8850_owned_groups.c" -o "$D/actuators"
    make -s -C "$R/runtime/bridges/thermal" NDK="$NDK" build/android/thermalctl
    cp "$R/runtime/bridges/thermal/build/android/thermalctl" "$D/thermalctl"
fi
sha256sum "$D/actuators" "$D/thermalctl"
AH=$(sha256sum "$D/actuators" | cut -d' ' -f1)
TH=$(sha256sum "$D/thermalctl" | cut -d' ' -f1)
token=$(tr -d '-' </proc/sys/kernel/random/uuid)
[[ "$token" =~ ^[0-9a-f]{32}$ ]]
remote="/data/local/tmp/oneios-probe.$token"
# New scratch only; no replacement of any existing file.
# A stalled USB/WSL transport must never hold this driver indefinitely.
adb_step() {
    local seconds=$1 label=$2 rc
    shift 2
    echo "===== $label (limit ${seconds}s) =====" >&2
    if timeout -k 2s "${seconds}s" "$ADB" "$@"; then
        return 0
    else
        rc=$?
        echo "ADB_STEP_FAILED=$label RC=$rc" >&2
        return "$rc"
    fi
}
created=0
root_started=0
cleanup_scratch() {
    local rc=$?
    trap - EXIT
    if [ "$created" = 1 ]; then
        if [ "$root_started" = 0 ] ||
            grep -qx 'FRAMEWORK_PRESERVED=YES' "$D/physical.log" 2>/dev/null; then
            timeout -k 2s 8s "$ADB" shell \
                "rm -f '$remote/actuators' '$remote/thermalctl'; rmdir '$remote'" ||
                echo "SCRATCH_CLEANUP_UNCONFIRMED=$remote" >&2
        else
            echo "SCRATCH_RETAINED_FOR_DIAGNOSIS=$remote" >&2
        fi
    fi
    echo "EVIDENCE=$D"
    exit "$rc"
}
trap cleanup_scratch EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
adb_step 12 ADB_DEVICES devices -l
adb_step 12 ADB_GET_STATE get-state | grep -qx device
adb_step 12 ADB_SHELL shell 'echo ADB_SHELL_OK'
adb_step 12 SCRATCH_CREATE shell "mkdir -m 700 '$remote'"
created=1
echo "REMOTE_SCRATCH=$remote"
# Disable sync compression to remove a variable from the retry.
adb_step 25 PUSH_ACTUATORS push -Z "$D/actuators" "$remote/actuators"
adb_step 25 PUSH_THERMALCTL push -Z "$D/thermalctl" "$remote/thermalctl"
echo "ADB_UPLOADS=PASS"
# All writes below concern only the fresh diagnostics and private test
# leaves; the test process moves itself to the root CPU/v2 groups.
# No changes to parent quotas or stock service membership.
echo "===== DEVICE PROBE (bounded) ====="
root_started=1
set +e
timeout -k 3s 80s "$ADB" shell "su -c 'timeout -k 2 60 /system/bin/sh -s $token $AH $TH'" <<'PHONE' | tee "$D/physical.log"
set -eu
token=$1
ah=$2
th=$3
src="/data/local/tmp/oneios-probe.$token"
S=/data/adb/oneios-m3q-framework
test "$(id -u)" = 0
test "$(getprop ro.product.model):$(getprop ro.product.device):$(getprop ro.soc.model)" = SM-S948B:m3q:SM8850
test "$(getprop ro.build.fingerprint)" = samsung/m3qxxx/m3q:17/CP2A.260605.016/S948BXXS4BZIG_OXM4BZIG:user/release-keys
test "$(getenforce)" = Enforcing
test "$(getprop sys.boot_completed)" = 1
test "$(getprop init.svc.zygote)" = running
test "$(getprop init.svc.zygote_next)" = running
before=$(pidof system_server)
test -n "$before"
test -z "$(pidof xnuhost 2>/dev/null || true)"
test -z "$(pidof oneios-stock-session 2>/dev/null || true)"
test "$(readlink /proc/$$/ns/mnt)" = "$(readlink /proc/1/ns/mnt)"
for base in /dev/cpuctl /sys/fs/cgroup; do
    for leaf in "$base"/oneios_guest.*; do
        test ! -e "$leaf" || { echo "REFUSE_EXISTING_GUEST_LEAF=$leaf"; exit 3; }
    done
done
# A stale on-disk state is not sufficient evidence that a session is live.
echo "CURRENT_BOOT=$(cat /proc/sys/kernel/random/boot_id)"
echo "STAGED_BOOT=$(cat "$S/control/boot" 2>/dev/null || true)"
work=$(mktemp -d /data/adb/oneios-stock-probe.XXXXXXXX)
chmod 700 "$work"
trap 'rm -f "$work/actuators" "$work/thermalctl"; rmdir "$work"' EXIT
for f in actuators thermalctl; do
    test -f "$src/$f" && test ! -L "$src/$f"
    cp "$src/$f" "$work/$f"
    chmod 700 "$work/$f"
done
test "$(sha256sum "$work/actuators" | cut -d' ' -f1)" = "$ah"
test "$(sha256sum "$work/thermalctl" | cut -d' ' -f1)" = "$th"
echo "===== RAW DIAGNOSTIC ====="
raw_rc=0
timeout -k 1 5 "$work/thermalctl" native-raw || raw_rc=$?
echo "RAW_RC=$raw_rc"
echo "===== NATIVE HAL ====="
hal_rc=0
timeout -k 1 5 "$work/thermalctl" native-hal || hal_rc=$?
echo "NATIVE_HAL_RC=$hal_rc"
echo "===== PHYSICAL PRIVATE LEAVES ====="
act_rc=0
/system/bin/sh -c '
    set -eu
    # An actual fresh shell (not a subshell with inherited $$) execs the
    # diagnostic, so only that one process joins the root groups.
    echo $$ > /dev/cpuctl/cgroup.procs
    echo $$ > /sys/fs/cgroup/cgroup.procs
    exec "$1" "$2"
' probe "$work/actuators" "$token" || act_rc=$?
echo "ACTUATOR_RC=$act_rc"
echo "===== FINAL ====="
test "$(pidof system_server)" = "$before"
test "$(getprop init.svc.zygote)" = running
test "$(getprop init.svc.zygote_next)" = running
test -z "$(pidof xnuhost 2>/dev/null || true)"
for base in /dev/cpuctl /sys/fs/cgroup; do
    test ! -e "$base/oneios_guest.$token" || {
        echo "PRIVATE_LEAF_REMAINS=$base/oneios_guest.$token"
        exit 4
    }
done
echo "FRAMEWORK_PRESERVED=YES"
echo "GUEST_BOOT=NONE"
echo "LIVE_ADMISSION=NONE"
test "$raw_rc:$hal_rc:$act_rc" = 0:0:0
echo "STOCK_PHYSICAL_PREREQUISITES=PASS"
PHONE
rc=${PIPESTATUS[0]}
set -e
if [ "$rc" != 0 ]; then
    echo "DEVICE_PROBE_RC=$rc" >&2
    echo "Do not automatically rerun the actuator after an incomplete device probe." >&2
fi
echo "PHYSICAL_LOG=$D/physical.log"
exit "$rc"
