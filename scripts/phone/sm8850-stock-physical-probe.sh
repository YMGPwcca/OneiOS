#!/usr/bin/env bash
# Build only the diagnostic executable and thermalctl from the validated
# source export; never run XNUHost, modify the existing stage, or stop UI.
set -Eeuo pipefail
cd "$(dirname "$0")/../.."
R=$PWD
ADB="${ADB:-$HOME/Android/Sdk/platform-tools/adb}"
NDK="${ANDROID_NDK_ROOT:-${NDK:-$HOME/Android/Sdk/ndk/28.2.13676358}}"
AC="$NDK/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"
test -x "$AC"
D=$(mktemp -d /tmp/oneios-physical-probe.XXXXXX)
echo "EVIDENCE=$D"
N="$R/app/switcher/native"
"$AC" -std=gnu11 -O2 -g -Wall -Wextra -Werror -static -I"$N" \
    "$R/runtime/xnuhost/tools/stock-physical-probe.c" \
    "$N/sm8850_owned_groups.c" -o "$D/actuators"
make -s -C "$R/runtime/bridges/thermal" NDK="$NDK" build/android/thermalctl
cp "$R/runtime/bridges/thermal/build/android/thermalctl" "$D/thermalctl"
AH=$(sha256sum "$D/actuators" | cut -d' ' -f1)
TH=$(sha256sum "$D/thermalctl" | cut -d' ' -f1)
token=$(tr -d '-' </proc/sys/kernel/random/uuid)
[[ "$token" =~ ^[0-9a-f]{32}$ ]]
remote="/data/local/tmp/oneios-probe.$token"
# New scratch only; no replacement of any existing file.
"$ADB" get-state | grep -qx device
"$ADB" shell "mkdir -m 700 '$remote'"
"$ADB" push "$D/actuators" "$remote/actuators"
"$ADB" push "$D/thermalctl" "$remote/thermalctl"
# All writes below concern only the fresh diagnostics and private test
# leaves; the test process moves itself to the root CPU/v2 groups.
# No changes to parent quotas or stock service membership.
set +e
"$ADB" shell "su -c '/system/bin/sh -s $token $AH $TH'" <<'PHONE' | tee "$D/physical.log"
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
"$ADB" shell "rm -f '$remote/actuators' '$remote/thermalctl'; rmdir '$remote'" || true
echo "EVIDENCE=$D/physical.log"
exit "$rc"
