#!/usr/bin/env bash
# Passive SM8850 watchdog descriptor ownership inventory.
# Runs on CachyOS, reads proc/sysfs through USB ADB root; never opens watchdog.
set -euo pipefail

serial="${1:?Usage: bash scripts/phone/sm8850-watchdog-owners.sh USB_SERIAL}"
adb="${ONEIOS_ADB:-$HOME/Android/Sdk/platform-tools/adb}"
[ -x "$adb" ] || { echo "ADB_NOT_FOUND=$adb" >&2; exit 2; }

timeout --foreground 70s "$adb" -s "$serial" shell -T "su -c '/system/bin/sh -s'" <<'PHONE'
set -u
[ "$(id -u)" = 0 ] || { echo "WATCHDOG_OWNERS=BLOCKED_NOT_ROOT"; exit 2; }
[ "$(getprop ro.product.model)" = "SM-S948B" ] || { echo "WATCHDOG_OWNERS=BLOCKED_WRONG_MODEL"; exit 2; }
[ "$(getprop ro.build.version.incremental)" = "S948BXXS4BZIG" ] || { echo "WATCHDOG_OWNERS=BLOCKED_WRONG_FIRMWARE"; exit 2; }

echo "=== DEVICE AND BOOT (READ ONLY) ==="
echo "boot=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
echo "boot_completed=$(getprop sys.boot_completed)"
echo "zygote=$(getprop init.svc.zygote)"
echo "system_server=$(pidof system_server 2>/dev/null)"
echo "=== WATCHDOG NODES (NO OPEN) ==="
for path in /dev/watchdog /dev/watchdog0 /dev/watchdog1 /dev/softdog; do
    [ -e "$path" ] || [ -L "$path" ] || continue
    echo "node=$path link=$(readlink "$path" 2>/dev/null) mode=$(stat -c %a "$path" 2>/dev/null) owner=$(stat -c %u:%g "$path" 2>/dev/null) rdev=$(stat -Lc %t:%T "$path" 2>/dev/null)"
done
for path in /sys/class/misc/watchdog/dev /sys/class/watchdog/watchdog0/dev /sys/class/watchdog/watchdog1/dev; do
    [ -r "$path" ] || continue
    echo "sysfs=$path value=$(cat "$path" 2>/dev/null)"
done
echo "=== OPEN FILE DESCRIPTOR REFERENCES ==="
count=0
pids=0
errors=0
for proc in /proc/[0-9]*; do
    [ -d "$proc/fd" ] || continue
    pids=$((pids + 1))
    pid=${proc##*/}
    for fd in "$proc"/fd/*; do
        [ -L "$fd" ] || continue
        target=$(readlink "$fd" 2>/dev/null) || { errors=$((errors + 1)); continue; }
        case "$target" in
            /dev/watchdog*|/dev/softdog*|/dev/char/10:130*|/dev/char/242:0*)
                count=$((count + 1))
                comm=$(cat "$proc/comm" 2>/dev/null || echo unknown)
                rdev=$(stat -Lc %t:%T "$fd" 2>/dev/null || echo unknown)
                echo "holder=$pid comm=$comm fd=${fd##*/} target=$target rdev=$rdev"
                if [ -r "$proc/fdinfo/${fd##*/}" ]; then
                    grep -E "^(flags|mnt_id|ino):" "$proc/fdinfo/${fd##*/}" 2>/dev/null | sed "s/^/  /"
                fi
                ;;
        esac
    done
done
echo "=== INVENTORY SUMMARY ==="
echo "WATCHDOG_FDS=$count"
echo "PROCESSES_SCANNED=$pids"
echo "FD_READLINK_ERRORS=$errors"
echo "PROBE_SCOPE=CURRENT_BOOT_WHILE_ONEUI_IS_RUNNING"
echo "WATCHDOG_DEVICE_OPEN_ATTEMPTED=NO"
echo "FRAMEWORK_STOP_ATTEMPTED=NO"
PHONE
