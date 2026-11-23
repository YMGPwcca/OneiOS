#!/usr/bin/env bash
# Focused follow-up of the original S24 return prerequisites, running READ ONLY
# on m3q. This is not a switch, return, stage or destructive preflight.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
ADB=(adb)
[ -z "${ANDROID_SERIAL:-}" ] || ADB+=(-s "$ANDROID_SERIAL")
"${ADB[@]}" get-state >/dev/null
model=$("${ADB[@]}" shell getprop ro.product.model | tr -d '\r')
device=$("${ADB[@]}" shell getprop ro.product.device | tr -d '\r')
soc=$("${ADB[@]}" shell getprop ro.soc.model | tr -d '\r')
[ "$device" = m3q ] && [ "$soc" = SM8850 ] || {
  echo "Refusing: not an SM8850/m3q device ($model/$device/$soc)" >&2
  exit 2
}
OUT="${ONEIOS_AUDIT_OUT:-$HOME/oneios-m3q-ci/audits/followup-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"
printf 'commit=%s\nscope=read-only; no phone writes, no root service changes\n' \
  "$(git -C "$ROOT" rev-parse HEAD)" > "$OUT/metadata.txt"

"${ADB[@]}" shell "su -c 'sh -s'" > "$OUT/followup.tsv" <<'PHONE'
PATH=/system/bin:/system/xbin:/vendor/bin:/sbin:$PATH
export PATH
say() { printf 'CHECK|%s|%s|%s|%s\n' "$1" "$2" "$3" "$4"; }
info() { say "$1" "$2" INFO "$3"; }
ok() { say "$1" "$2" PASS "$3"; }
warn() { say "$1" "$2" WARN "$3"; }
blocked() { say "$1" "$2" BLOCKED "$3"; }
prop() { getprop "$1" 2>/dev/null | tr -d '\r\n'; }
if [ "$(id -u)" != 0 ]; then say safety root FAIL not-root; exit 3; fi
info identity model "$(prop ro.product.model)"
info identity soc "$(prop ro.soc.model)"
info identity kernel "$(uname -r)"

# Identify whether stopped hwservicemanager is relevant to the services used.
hw=$(prop init.svc.hwservicemanager)
case "$hw" in running) ok hidl hwservicemanager running ;;
  stopped) warn hidl hwservicemanager stopped-on-this-build ;;
  *) info hidl hwservicemanager "${hw:-undeclared}";; esac
for node in /dev/binder /dev/hwbinder /dev/vndbinder; do
  if [ -e "$node" ]; then info binder "$(basename "$node")" "$(ls -l "$node" 2>/dev/null | awk '{print $1, $3, $4}')"
  else warn binder "$(basename "$node")" not-present-at-classic-path; fi
done
for svc in vendor.qti.hardware.display.composer vendor.hwcomposer-3 \
           surfaceflinger audioserver cameraserver wificond netd keystore2 \
           servicemanager hwservicemanager; do
  value=$(prop "init.svc.$svc")
  info services "$svc" "${value:-not-declared}"
done
if timeout 6 service check android.hardware.graphics.composer3.IComposer/default 2>/dev/null | grep -q ': found'; then
  ok display composer3-binder registered
else warn display composer3-binder no-answer; fi
if command -v lshal >/dev/null 2>&1; then
  # Listing is read-only and bounded. Do not start or restart hwbinder.
  names=$(timeout 8 lshal list -i 2>/dev/null | grep -E 'android.hardware.graphics.composer@|android.hardware.camera.provider@|android.hardware.audio@' | head -n 5 | tr '\n' ';')
  info hidl key-interfaces "${names:-none-found-or-lshal-unavailable}"
fi

# Snapshot relevant sysfs without writing brightness or display modes.
for d in /sys/class/backlight/*; do
  [ -d "$d" ] || continue
  name=$(basename "$d")
  for key in brightness actual_brightness max_brightness bl_power type; do
    file="$d/$key"
    [ -r "$file" ] || continue
    value=$(head -c 80 "$file" 2>/dev/null | tr '\n' ' ')
    info backlight "$name.$key" "$value"
  done
  resolved=$(readlink -f "$d" 2>/dev/null)
  info backlight "$name.sysfs" "${resolved:-unresolved}"
done
if command -v dumpsys >/dev/null 2>&1; then
  # Grab bounded non-identifying high-level display state lines only.
  lines=$(timeout 8 dumpsys display 2>/dev/null |
    grep -iE 'mScreenState=|mScreenBrightness=|mBrightnessReason=|state=ON|Display Power:' |
    head -n 5 | tr '\n' ';')
  info display brightness-framework "${lines:-not-readable-or-no-matching-lines}"
fi
blocked display brightness-roundtrip "no brightness writes in passive audit"

# USB continuity cannot be inferred from Wireless ADB.
for key in sys.usb.config sys.usb.state sys.usb.controller init.svc.adbd persist.sys.usb.config; do
  info usb "$key" "$(prop "$key")"
done
udc=$(prop sys.usb.controller)
case "$udc" in ''|.|..|*/*|*[!a-zA-Z0-9._:-]*) warn usb udc invalid-controller ;;
  *)
    if [ -r "/sys/class/udc/$udc/state" ]; then
      info usb udc-state "$(cat "/sys/class/udc/$udc/state" 2>/dev/null)"
    else warn usb udc-state node-not-readable; fi
  ;;
esac
for file in /config/usb_gadget/g1/UDC /config/usb_gadget/g2/UDC /dev/usb-ffs/adb/ep0; do
  if [ -r "$file" ] && [ ! -d "$file" ]; then
    case "$file" in */UDC) info usb "$(echo "$file" | tr '/' '_')" "$(cat "$file" 2>/dev/null)" ;;
      *) info usb ffs-adb-endpoint present;; esac
  else info usb "$(echo "$file" | tr '/' '_')" unavailable; fi
done
blocked usb physical-continuity "requires USB cable, live session and recovery tests"

# Upstream shmem fix requires a bare restore value and a correct early-return.
node=/sys/kernel/mm/transparent_hugepage/shmem_enabled
if [ -r "$node" ]; then
  modes=$(cat "$node" 2>/dev/null)
  active=$(printf '%s' "$modes" | tr ' ' '\n' | grep '^\[.*\]$' | tr -d '[]' | head -n 1)
  info shmem available-modes "$modes"
  info shmem active-mode "${active:-unknown}"
  if [ -w "$node" ]; then ok shmem sysfs-write-permission writable
  else warn shmem sysfs-write-permission not-writable; fi
  case " $(printf '%s' "$modes" | tr -d '[]') " in *" advise "*) ok shmem advise-listed yes ;;
    *) warn shmem advise-listed no;; esac
else warn shmem shmem_enabled missing-or-unreadable; fi
blocked shmem restore-roundtrip "never modify shmem while One UI is operating"

# The original recovery starts a separate reader for EACH eligible device.
if command -v getevent >/dev/null 2>&1; then
  getevent -pl 2>/dev/null | awk '
    /^add device/ { if (up || down) printf "CHECK|keys|%s|INFO|up=%d,down=%d,name=%s\n",dev,up,down,name;
      dev=$NF; up=0; down=0; name="unknown" }
    /name: / { name=$0; sub(/^.*name: /,"",name); gsub(/[^[:alnum:] _.-]/,"",name); }
    /KEY_VOLUMEUP/ { up=1 }
    /KEY_VOLUMEDOWN/ { down=1 }
    END { if (up || down) printf "CHECK|keys|%s|INFO|up=%d,down=%d,name=%s\n",dev,up,down,name }
  '
fi
blocked keys chord "mere capability listing does not test an actual 3-second press"

# Watchdog discovery is strictly stat/readlink, NEVER open() a watchdog.
for dev in /dev/watchdog /dev/watchdog0 /dev/softdog; do
  if [ -c "$dev" ]; then info watchdog "$(basename "$dev")" char-device-present
  else info watchdog "$(basename "$dev")" absent; fi
done
if [ -r /sys/fs/cgroup/cgroup.controllers ]; then
  info cgroup controllers "$(head -c 160 /sys/fs/cgroup/cgroup.controllers 2>/dev/null)"
fi
if [ -e /sys/fs/cgroup/cgroup.kill ]; then info cgroup root-kill-node present
else info cgroup root-kill-node absent; fi
blocked recovery gates-ABC "no session, teardown, service restarts or reboot attempted"
PHONE

sed -i 's/\r$//' "$OUT/followup.tsv"
# Purely LOCAL package inventory: an unstaged phone cannot have all binaries.
STATE="$HOME/oneios-m3q-ci/standalone/last-result.txt"
sha=$(sed -n 's/^commit=//p' "$STATE" 2>/dev/null | head -n 1 || true)
if [ -n "$sha" ] && [ -f "$HOME/oneios-m3q-ci/standalone/runs/$sha/artifacts/oneios-runtime-0.0.0-ci-arm64.tar.zst" ]; then
  archive="$HOME/oneios-m3q-ci/standalone/runs/$sha/artifacts/oneios-runtime-0.0.0-ci-arm64.tar.zst"
  {
    echo "source_commit=$sha"
    ( cd "$(dirname "$archive")" && sha256sum -c "$(basename "$archive").sha256" )
    zstd -dc "$archive" | tar -tf - | grep -E '(^|/)(bin/(camctl|gpuctl|brightctl|bridgectl|displayctl|oneios-audio|oneios-tool)|kernel/|runtime.json)' || true
  } > "$OUT/host-artifact.txt"
else
  printf 'artifact=not found in standalone CI run\n' > "$OUT/host-artifact.txt"
fi
awk -F '|' '$1=="CHECK" { counts[$4]++ } END {
 printf "Follow-up:"
 for(i=1;i<=5;i++){ k=(i==1?"PASS":i==2?"WARN":i==3?"FAIL":i==4?"BLOCKED":"INFO"); printf " %s=%d",k,counts[k]+0 } print ""
}' "$OUT/followup.tsv"
printf 'Follow-up: %s\nPackage: %s\n' "$OUT/followup.tsv" "$OUT/host-artifact.txt"
