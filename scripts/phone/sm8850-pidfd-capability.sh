#!/usr/bin/env bash
# Benign-only capability probe. Duplicates at most /dev/null in system_server.
# Does NOT duplicate/open/write any watchdog, stop Framework or reboot.
set -euo pipefail

serial="${1:?Usage: bash scripts/phone/sm8850-pidfd-capability.sh USB_SERIAL}"
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
adb="${ONEIOS_ADB:-$HOME/Android/Sdk/platform-tools/adb}"
ndk="${ANDROID_NDK_ROOT:-${NDK:-$HOME/Android/Sdk/ndk/28.2.13676358}}"
clang="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"

[ -x "$adb" ] || { echo "ADB_NOT_FOUND=$adb" >&2; exit 2; }
[ -x "$clang" ] || { echo "NDK_CLANG_NOT_FOUND=$clang" >&2; exit 2; }
echo "===== PASSIVE DEVICE IDENTITY ====="
"$adb" -s "$serial" shell -T "su -c '/system/bin/sh -s'" <<'PHONE'
set -eu
[ "$(id -u)" = 0 ] || exit 2
[ "$(getprop ro.product.model)" = SM-S948B ] &&
[ "$(getprop ro.product.device)" = m3q ] &&
[ "$(getprop ro.soc.model)" = SM8850 ] &&
[ "$(getprop ro.build.version.incremental)" = S948BXXS4BZIG ] &&
[ "$(getprop sys.boot_completed)" = 1 ] ||
    { echo "PIDFD_PROBE=BLOCKED_DEVICE_OR_BOOT"; exit 2; }
echo "boot=$(cat /proc/sys/kernel/random/boot_id)"
echo "system_server=$(pidof system_server)"
PHONE

tmp=$(mktemp -d)
remote=""
cleanup() {
    if [ -n "$remote" ]; then
        "$adb" -s "$serial" shell "rm -f '$remote/probe'; rmdir '$remote'" >/dev/null 2>&1 ||
            echo "NOTE: temporary probe may remain at $remote" >&2
    fi
    rm -rf "$tmp"
}
trap cleanup EXIT

echo "===== COMPILE BENIGN FD PROBE ====="
"$clang" -std=c11 -Wall -Wextra -Werror -O2 -fPIE -pie \
    "$root/scripts/phone/sm8850-pidfd-capability.c" -o "$tmp/probe"

created=$("$adb" -s "$serial" shell -T \
    'mktemp -d /data/local/tmp/oneios-pidfd-capability.XXXXXXXX' | tr -d '\r\n')
if [[ ! "$created" =~ ^/data/local/tmp/oneios-pidfd-capability\.[A-Za-z0-9]{8}$ ]]; then
    echo "UNSAFE_OR_MISSING_REMOTE_TEMP_DIR=$created" >&2
    exit 2
fi
remote=$created
"$adb" -s "$serial" push "$tmp/probe" "$remote/probe" >/dev/null
"$adb" -s "$serial" shell -T "chmod 700 '$remote/probe'"

echo "===== PIDFD GETFD PERMISSION - DEV NULL ONLY ====="
# Command substitution verifies pidof returns exactly one PID and
# never sends a shell-derived path or arbitrary PID into the root command.
pid=$("$adb" -s "$serial" shell -T "pidof system_server" | tr -d '\r\n')
if [[ ! "$pid" =~ ^[1-9][0-9]{1,6}$ ]]; then
    echo "PIDFD_PROBE=BLOCKED_AMBIGUOUS_SYSTEM_SERVER_PID" >&2
    exit 2
fi

set +e
timeout --foreground 15s "$adb" -s "$serial" shell -T \
    "su -c '$remote/probe --system-server $pid'"
rc=$?
set -e
echo "PIDFD_PROBE_EXIT=$rc"
echo "WATCHDOG_FD_DUPLICATED=NO"
echo "LIVE_TAKEOVER_AUTHORIZED=NO"
exit "$rc"
