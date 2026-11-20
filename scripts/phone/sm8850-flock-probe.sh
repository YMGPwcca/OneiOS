#!/usr/bin/env bash
# Test Android mksh/Toybox flock inheritance without stopping Framework.
# Usage: bash scripts/phone/sm8850-flock-probe.sh R5GL64LZ9HA
set -euo pipefail

serial=${1:?Usage: bash sm8850-flock-probe.sh USB_SERIAL}
adb=${ONEIOS_ADB:-"$HOME/Android/Sdk/platform-tools/adb"}
test -x "$adb" || { echo "ERROR: adb missing: $adb" >&2; exit 2; }

"$adb" -s "$serial" shell -T "su -c '/system/bin/sh -s'" <<'PHONE'
set -eu
[ "$(id -u)" = 0 ] || { echo "LOCK_PROBE=FAIL: root required"; exit 2; }
[ "$(getprop ro.product.model):$(getprop ro.product.device):$(getprop ro.soc.model)" = "SM-S948B:m3q:SM8850" ] ||
    { echo "LOCK_PROBE=FAIL: wrong phone"; exit 2; }
[ "$(getprop ro.build.version.incremental)" = "S948BXXS4BZIG" ] ||
    { echo "LOCK_PROBE=FAIL: wrong firmware"; exit 2; }

echo "===== ANDROID FLOCK IMPLEMENTATION ====="
command -v flock || exit 2
echo "===== TEMPORARY LOCK PROBE - FRAMEWORK UNTOUCHED ====="
umask 077
probe=$(mktemp -d /data/local/tmp/oneios-flock-probe.XXXXXXXX) || exit 2
trap 'rm -rf "$probe"' EXIT
lock="$probe/start.lock"

# mksh does NOT pass permanently exec-opened fd8 to external processes.
# Command-scoped fd0 receives a duplicate sharing fd8's open file
# description. The parent shell must retain fd8 and hence the lock.
exec 8>>"$lock"
flock -n 0 0<&8 || { echo "LOCK_PROBE=FAIL: first acquisition"; exit 3; }
echo "FIRST_ACQUISITION=PASS"

# Different open file description must be rejected while fd8 is held.
if ( exec 9>>"$lock"; flock -n 0 0<&9 ); then
    echo "LOCK_PROBE=FAIL: concurrent owner acquired lock"
    exit 4
fi
echo "CONTENDER_REJECTED=PASS"

# Lock must become available after the original shell closes fd8.
exec 8>&-
if ( exec 9>>"$lock"; flock -n 0 0<&9 ); then
    echo "RELEASE_AND_REACQUIRE=PASS"
else
    echo "LOCK_PROBE=FAIL: lock was not released"
    exit 5
fi

echo "LOCK_PROBE=PASS"
PHONE
