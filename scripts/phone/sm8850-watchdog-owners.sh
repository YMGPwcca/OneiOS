#!/usr/bin/env bash
# Passive SM8850 watchdog descriptor inventory. No Framework stop or watchdog open.
# Build a small native read-only /proc scanner instead of forking readlink
# separately for every FD (the old implementation timed out after 70 seconds).
set -euo pipefail

serial="${1:?Usage: bash scripts/phone/sm8850-watchdog-owners.sh USB_SERIAL}"
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
adb="${ONEIOS_ADB:-$HOME/Android/Sdk/platform-tools/adb}"
ndk="${ANDROID_NDK_ROOT:-${NDK:-$HOME/Android/Sdk/ndk/28.2.13676358}}"
clang="$ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android30-clang"
[ -x "$adb" ] || { echo "ADB_NOT_FOUND=$adb" >&2; exit 2; }
[ -x "$clang" ] || { echo "ANDROID_NDK_CLANG_NOT_FOUND=$clang" >&2; exit 2; }

echo "===== EXACT DEVICE IDENTITY (READ ONLY) ====="
"$adb" -s "$serial" shell -T "su -c '/system/bin/sh -s'" <<'PHONE'
set -eu
[ "$(id -u)" = 0 ] || { echo "SCAN_REFUSED_NOT_ROOT"; exit 2; }
[ "$(getprop ro.product.model)" = "SM-S948B" ] &&
[ "$(getprop ro.product.device)" = m3q ] &&
[ "$(getprop ro.soc.model)" = SM8850 ] ||
  { echo "SCAN_REFUSED_DEVICE_MISMATCH"; exit 2; }
[ "$(getprop ro.build.version.incremental)" = S948BXXS4BZIG ] ||
  { echo "SCAN_REFUSED_FIRMWARE_MISMATCH"; exit 2; }
echo "boot=$(cat /proc/sys/kernel/random/boot_id)"
echo "boot_completed=$(getprop sys.boot_completed)"
echo "zygote=$(getprop init.svc.zygote)"
echo "system_server=$(pidof system_server 2>/dev/null)"
echo "===== WATCHDOG NODES (STAT ONLY; NO OPEN) ====="
for path in /dev/watchdog /dev/watchdog0 /dev/watchdog1 /dev/softdog; do
    [ -e "$path" ] || [ -L "$path" ] || continue
    echo "node=$path mode=$(stat -c %a "$path" 2>/dev/null) owner=$(stat -c %u:%g "$path" 2>/dev/null) rdev=$(stat -Lc %t:%T "$path" 2>/dev/null)"
done
PHONE

echo "===== COMPILE PASSIVE FD SCANNER LOCALLY ====="
tmp=$(mktemp -d)
remote=""
cleanup() {
    if [ -n "$remote" ]; then
        "$adb" -s "$serial" shell "rm -f '$remote/scan'; rmdir '$remote'" >/dev/null 2>&1 ||
            echo "NOTE: temporary remote scanner may remain at $remote" >&2
    fi
    rm -rf "$tmp"
}
trap cleanup EXIT
"$clang" -std=c11 -Wall -Wextra -Werror -O2 -fPIE -pie \
    "$root/scripts/phone/sm8850-watchdog-owners.c" -o "$tmp/scan"

echo "===== DEPLOY TEMPORARY SCANNER ====="
created=$("$adb" -s "$serial" shell -T \
    'mktemp -d /data/local/tmp/oneios-watchdog-owners.XXXXXXXX' | tr -d '\r\n')
if [[ ! "$created" =~ ^/data/local/tmp/oneios-watchdog-owners\.[A-Za-z0-9]{8}$ ]]; then
    echo "UNSAFE_OR_MISSING_REMOTE_TEMP_DIR=$created" >&2
    exit 2
fi
remote=$created
"$adb" -s "$serial" push "$tmp/scan" "$remote/scan" >/dev/null
"$adb" -s "$serial" shell -T "chmod 700 '$remote/scan'"

echo "===== FAST NATIVE /PROC WATCHDOG FD INVENTORY ====="
# Bound the whole scan. The native scanner makes no external readlink/stat
# subprocess per FD, and prints explicit coverage/incompleteness counters.
set +e
timeout --foreground 45s "$adb" -s "$serial" shell -T \
    "su -c '$remote/scan'"
scan_rc=$?
set -e
if [ "$scan_rc" -ne 0 ]; then
    echo "WATCHDOG_OWNERS_SCAN_EXIT=$scan_rc"
    exit "$scan_rc"
fi
echo "WATCHDOG_OWNERS_SCAN=PASS"
