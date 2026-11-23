#!/usr/bin/env bash
# Passive S24 OneiOS switch/return prerequisite audit against an SM8850/m3q phone.
# Runs through adb + KernelSU but does NOT stage, install, vibrate, restart,
# modify settings/sysfs, switch a session, or write anything to the phone.
# Its log is local only. DO NOT upload device reports to a public repository.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ADB=(adb)
if [ -n "${ANDROID_SERIAL:-}" ]; then ADB+=(-s "$ANDROID_SERIAL"); fi
"${ADB[@]}" get-state >/dev/null
model=$("${ADB[@]}" shell getprop ro.product.model | tr -d '\r')
codename=$("${ADB[@]}" shell getprop ro.product.device | tr -d '\r')
if [ "$codename" != m3q ]; then
  echo "audit: target is $model/$codename, not m3q; refusing to use the SM8850-specific audit" >&2
  exit 2
fi

stamp=$(date -u '+%Y%m%dT%H%M%SZ')
OUT="${ONEIOS_AUDIT_OUT:-$HOME/oneios-m3q-ci/audits/$stamp}"
mkdir -p "$OUT"
{
  echo "audit_version=1"
  echo "timestamp_utc=$stamp"
  echo "oneios_commit=$(git -C "$ROOT" rev-parse HEAD)"
  echo "device_model=$model"
  echo "device_codename=$codename"
  echo "scope=passive prerequisites only; no phone changes"
  echo "s24_baseline=YMGPwcca/OneOS feat/oneios-sm8850-m3q b81a6032"
  echo "s24_upstream=akshaynexus/OneOS oneios bdf3db05"
} > "$OUT/metadata.txt"

echo "audit: reading One UI / KernelSU / OneiOS prerequisites from $model ..."
# The only root command is a shell evaluating read-only getprop, cat, stat,
# readlink, getevent -pl, service check and sysfs existence/access checks.
"${ADB[@]}" shell "su -c 'sh -s'" > "$OUT/checks.tsv" <<'PHONE'
PATH=/system/bin:/system/xbin:/vendor/bin:/sbin:$PATH
export PATH
put() { printf 'CHECK|%s|%s|%s|%s\n' "$1" "$2" "$3" "$4"; }
ok()   { put "$1" "$2" PASS "$3"; }
bad()  { put "$1" "$2" FAIL "$3"; }
warn() { put "$1" "$2" WARN "$3"; }
wait() { put "$1" "$2" BLOCKED "$3"; }
info() { put "$1" "$2" INFO "$3"; }
prop() { getprop "$1" 2>/dev/null | tr -d '\r\n'; }
svc() {
  state=$(prop "init.svc.$2")
  if [ "$state" = running ]; then ok "$1" "$2" running
  elif [ -n "$state" ]; then warn "$1" "$2" "$state"
  else info "$1" "$2" not-declared
  fi
}
checkcmd() { command -v "$2" >/dev/null 2>&1 && ok "$1" "$2" present || bad "$1" "$2" missing; }
binder() {
  if command -v timeout >/dev/null 2>&1 &&
     timeout 5 service check "$2" 2>/dev/null | grep -q ': found'; then
    ok "$1" "$2" registered
  else
    warn "$1" "$2" not-registered-or-unavailable
  fi
}

model=$(prop ro.product.model)
dev=$(prop ro.product.device)
soc=$(prop ro.soc.model)
build=$(prop ro.build.version.release)
sdk=$(prop ro.build.version.sdk)
board=$(prop ro.board.platform)
info identity model "$model"
info identity device "$dev"
info identity soc "$soc"
info identity board "$board"
info identity android "$build-sdk$sdk"
info identity kernel "$(uname -r)"
if [ "$dev" = m3q ] && [ "$soc" = SM8850 ]; then ok identity sm8850-profile matched
else bad identity sm8850-profile unexpected-device-or-soc; fi
case "$model:$dev:$soc" in SM-S928*:e3q:SM8650) ok compatibility s24-original-gate matched ;;
 *) wait compatibility s24-original-gate "S24-only: $model/$dev/$soc (must not bypass)";;
esac

if [ "$(id -u)" = 0 ]; then ok root uid root; else bad root uid nonroot; fi
selinux=$(getenforce 2>/dev/null)
if [ "$selinux" = Enforcing ]; then ok root selinux Enforcing; else warn root selinux "${selinux:-unknown}"; fi
info root domain "$(id -Z 2>/dev/null)"
if pm path com.fahadali.oneos >/dev/null 2>&1; then
  ok oneos app installed
  dumpsys package com.fahadali.oneos 2>/dev/null | grep -m 1 -E 'versionCode=' | sed 's/^[[:space:]]*//' | while IFS= read -r ln; do info oneos version "$ln"; done
  dumpsys package com.fahadali.oneos 2>/dev/null | grep -m 1 -E 'versionName=' | sed 's/^[[:space:]]*//' | while IFS= read -r ln; do info oneos version-name "$ln"; done
else bad oneos app not-installed; fi

bb=""
for f in /data/adb/ksu/bin/busybox /data/adb/ap/bin/busybox /data/adb/magisk/busybox; do
  if [ -x "$f" ]; then bb="$f"; break; fi
done
if [ -n "$bb" ]; then
  ok root busybox "$bb"
  applets=" $("$bb" --list 2>/dev/null | tr '\n' ' ') "
  for tool in sh mount umount unshare nsenter setsid awk grep sed; do
    case "$applets" in *" $tool "*) ok root "busybox-$tool" present ;;
      *) bad root "busybox-$tool" missing ;;
    esac
  done
else bad root busybox missing; fi
rp=""
for f in /data/adb/ksu/bin/resetprop /data/adb/ap/bin/resetprop /debug_ramdisk/resetprop /sbin/resetprop; do
  if [ -x "$f" ]; then rp="$f"; break; fi
done
if [ -n "$rp" ]; then ok root resetprop "$rp"; else bad root resetprop missing; fi
checkcmd root sha256sum
checkcmd root getevent
checkcmd root ps
checkcmd root stat
checkcmd root awk
checkcmd root sort
checkcmd root comm
checkcmd root timeout
checkcmd root service
checkcmd root lshal
checkcmd root vdc

self_ns=$(readlink /proc/self/ns/mnt 2>/dev/null)
init_ns=$(readlink /proc/1/ns/mnt 2>/dev/null)
if [ -n "$init_ns" ] && [ "$self_ns" = "$init_ns" ]; then
  ok namespace init "shell-is-in-init-namespace"
else
  warn namespace init "root-shell-not-in-init-namespace; switch re-enters by nsenter"
fi
if [ "$(prop sys.boot_completed)" = 1 ]; then ok oneui boot-completed 1; else bad oneui boot-completed not-1; fi
svc oneui zygote
svc oneui zygote_secondary
svc oneui zygote_next
for app in system_server surfaceflinger; do
  pids=$(pidof "$app" 2>/dev/null)
  if [ -n "$pids" ]; then ok oneui "$app" "pid $pids"; else bad oneui "$app" not-running; fi
done

stage=/data/local/tmp/oneios
if [ -d "$stage" ]; then
  ok stage directory present
  for target in "$stage" "$stage/bin/oneios_root.sh" "$stage/oneios_switch.sh" \
                "$stage/oneios_return.sh" "$stage/runtime/runtime.json" \
                "$stage/image/manifest.json" "$stage/runtime.conf" "$stage/image.conf" \
                "$stage/runtime.sha256" "$stage/image.sha256" \
                "$stage/runtime.ids" "$stage/image.ids"; do
    if [ -L "$target" ]; then bad stage "$(basename "$target")" is-symlink
    elif [ -e "$target" ]; then
      info stage "$(basename "$target")" "$(stat -c '%a:%u:%g:%s' "$target" 2>/dev/null)"
    else wait stage "$(basename "$target")" not-staged
    fi
  done
  for k in runtime image; do
    if [ -r "$stage/$k.sha256" ] && [ -d "$stage/$k" ]; then
      info stage "$k-files" "listed=$(wc -l < "$stage/$k.sha256")"
    fi
  done
else
  wait stage directory "not initialized; OneOS APK alone does not install a stage"
  wait stage runtime "cannot verify ELF/ABI/SHA256 without stage"
  wait stage image "cannot verify kernelcache/manifest/SHA256 without stage"
  wait stage scripts "cannot verify session and return script pinning without stage"
fi

if [ -d "$stage/control" ]; then
  state=$(cat "$stage/control/state" 2>/dev/null)
  case "$state" in starting|running|returning) bad session open "$state" ;;
    *) ok session state "${state:-none}";; esac
  p=$(cat "$stage/control/xnuhost.pid" 2>/dev/null)
  if [ -n "$p" ] && [ -d "/proc/$p" ]; then warn session old-xnuhost "pid $p still exists"; fi
else ok session state no-ios-session-control; fi
if [ -r /sys/fs/cgroup/oneios_session/cgroup.procs ]; then
  p=$(head -n 3 /sys/fs/cgroup/oneios_session/cgroup.procs 2>/dev/null)
  if [ -n "$p" ]; then bad session stale-cgroup "pids $(echo "$p" | tr '\n' ',')"
  else ok session stale-cgroup empty; fi
else ok session stale-cgroup absent; fi
left=$(awk '$5 == "/data/local/tmp/oneios" ||
            index($5, "/data/local/tmp/oneios/") == 1 ||
            index($5, "/data/local/tmp/oneos/") == 1 { print $5 }' /proc/self/mountinfo 2>/dev/null | head -n 3)
if [ -n "$left" ]; then warn session stage-mounts "$(echo "$left" | tr '\n' ',')"
else ok session stage-mounts none-in-current-namespace; fi

if command -v getevent >/dev/null 2>&1; then
  keys=$(getevent -pl 2>/dev/null)
  case "$keys" in *KEY_VOLUMEUP*) ok recovery volume-up detected ;; *) bad recovery volume-up not-detected ;; esac
  case "$keys" in *KEY_VOLUMEDOWN*) ok recovery volume-down detected ;; *) bad recovery volume-down not-detected ;; esac
  kd=$(printf '%s\n' "$keys" | awk '/^add device/ {dev=$NF} /KEY_VOLUME(UP|DOWN)/ {print dev}' | sort -u | tr '\n' ',')
  info recovery volume-key-devices "${kd:-unknown}"
else bad recovery volume-keys getevent-missing; fi
wait recovery volume-chord "physical 3-second chord and reader process not tested passively"
wait recovery in-place-return "Gate A/B/C cannot be proven without a controlled session"

bat=/sys/class/power_supply/battery
cap=$(cat "$bat/capacity" 2>/dev/null)
status=$(cat "$bat/status" 2>/dev/null)
temp=$(cat "$bat/temp" 2>/dev/null)
case "$cap" in ''|*[!0-9]*) bad safety battery-capacity unreadable ;;
  *) if [ "$cap" -ge 30 ] || [ "$status" = Charging ] || [ "$status" = Full ]; then
       ok safety battery-capacity "$cap% ($status)"
     else bad safety battery-capacity "$cap% not charging"; fi;;
esac
case "$temp" in ''|*[!0-9]*) bad safety battery-temperature unreadable ;;
  *) if [ "$temp" -lt 420 ]; then ok safety battery-temperature "$temp tenths-C"
     else bad safety battery-temperature "$temp tenths-C"; fi;;
esac
space=$(stat -f -c '%a %S' /data 2>/dev/null)
if [ -n "$space" ] && echo "$space" | awk '{exit !(NF == 2 && $1 * $2 >= 2147483648)}'; then
  ok safety data-free "at-least-2GiB"
else bad safety data-free "below-2GiB-or-unreadable"; fi
if [ -w /sys/power/wake_lock ]; then ok safety wakelock writable-by-root
else bad safety wakelock inaccessible; fi
if [ -w /sys/fs/cgroup ]; then ok safety cgroup-parent writable-by-root
else warn safety cgroup-parent not-writable; fi
info safety physical-power-reboot "Power + Volume Down fallback must be verified by owner, not triggered"

for s in vold keystore2 servicemanager hwservicemanager logd lmkd installd \
         audioserver cameraserver netd wificond media mediaextractor mediametrics \
         perfmond media.tuner; do
  svc recovery "$s"
done
for n in vold keystore2 servicemanager; do
  p=$(pidof "$n" 2>/dev/null)
  if [ -n "$p" ]; then ok recovery "daemon-$n" "pid $p"
  else bad recovery "daemon-$n" missing; fi
done
for name in SurfaceFlinger media.audio_policy media.audio_flinger installd vold; do
  binder recovery "$name"
done
compositor=""
for name in vendor.qti.hardware.display.composer vendor.hwcomposer-3; do
  st=$(prop "init.svc.$name")
  if [ -n "$st" ]; then compositor="$name"; break; fi
done
if [ -z "$compositor" ]; then
  compositor=$(getprop | sed -n 's/^\[init\.svc\.\([^]]*\)\]: \[running\]$/\1/p' |
    grep -m1 -E 'hwcomposer|display\.composer|graphics\.composer')
fi
if [ -n "$compositor" ]; then
  ok display composer-service "$compositor=$(prop "init.svc.$compositor")"
else bad display composer-service not-found-by-return-lookup; fi
if grep -rqs 'android.hardware.graphics.composer3' /vendor/etc/vintf/ 2>/dev/null; then
  info display interface composer3-AIDL
  binder display android.hardware.graphics.composer3.IComposer/default
else
  info display interface "HIDL-or-vendor"
  if command -v timeout >/dev/null 2>&1 &&
     timeout 6 lshal list -i 2>/dev/null | grep -q 'android.hardware.graphics.composer@.*::IComposer/default'; then
    ok display composer-HIDL registered
  else warn display composer-HIDL unverified; fi
fi
for path in /sys/class/backlight/*/brightness; do
  [ -f "$path" ] || continue
  max=$(cat "$(dirname "$path")/max_brightness" 2>/dev/null)
  now=$(cat "$path" 2>/dev/null)
  info display backlight "$(basename "$(dirname "$path")"):$now/$max"
done

for path in /sys/devices/system/cpu/cpufreq/policy*/scaling_max_freq \
            /sys/devices/system/cpu/cpufreq/policy*/scaling_min_freq \
            /sys/kernel/gpu/gpu_max_clock \
            /sys/class/kgsl/kgsl-3d0/max_gpuclk \
            /sys/devices/system/cpu/cpufreq_limit/cpufreq_max_limit \
            /sys/devices/system/cpu/cpufreq_limit/cpufreq_min_limit; do
  [ -f "$path" ] || continue
  v=$(cat "$path" 2>/dev/null)
  info clocks "$(echo "$path" | sed 's|/sys/||;s|/|_|g')" "$v"
done
cpus=""
for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
  [ -d "$cpu" ] || continue
  num=$(basename "$cpu")
  capacity=$(cat "$cpu/cpu_capacity" 2>/dev/null)
  freq=$(cat "$cpu/cpufreq/cpuinfo_max_freq" 2>/dev/null)
  cpus="$cpus $num:$capacity:$freq"
done
info cpu capacities "$cpus"
if [ -e /dev/kgsl-3d0 ]; then ok gpu kgsl-node present; else bad gpu kgsl-node missing; fi
if [ -e /dev/udmabuf ]; then ok gpu udmabuf-node present; else warn gpu udmabuf-node missing; fi
if [ -e /dev/dma_heap/system ]; then ok gpu system-dma-heap present; else warn gpu system-dma-heap missing; fi
wait gpu guest-metal "not provable from GPU node existence or prior host probes"

shmem=/sys/kernel/mm/transparent_hugepage/shmem_enabled
if [ -r "$shmem" ]; then
  x=$(cat "$shmem" 2>/dev/null)
  selected=$(printf '%s' "$x" | tr ' ' '\n' | grep '^\[.*\]$' | tr -d '[]' | head -n 1)
  normalized=$(printf '%s' "$x" | tr -d '[]')
  case " $normalized " in *" advise "*) ok recovery shmem-advise-capability "supported;current=${selected:-unknown}" ;;
    *) warn recovery shmem-advise-capability "not-advertised;current=${selected:-unknown}" ;;
  esac
  info recovery shmem-current "${selected:-unknown}"
else warn recovery shmem-advise-capability "missing-or-unreadable"; fi

usbconfig=$(prop sys.usb.config)
usbstate=$(prop sys.usb.state)
udc=$(prop sys.usb.controller)
info usb current-config "$usbconfig"
info usb current-state "$usbstate"
info usb controller "$udc"
case "$usbconfig" in *adb*) ok usb adb-config contains-adb ;;
  *) warn usb adb-config not-listed; esac
case "$udc" in ''|.|..|*/*|*[!a-zA-Z0-9._:-]*) warn usb udc-state invalid-or-absent-controller ;;
  *) if [ -r "/sys/class/udc/$udc/state" ]; then
       info usb udc-state "$(cat "/sys/class/udc/$udc/state" 2>/dev/null)"
     else warn usb udc-state missing-or-unreadable; fi ;;
esac
wait usb session-continuity "no switch performed; USB debugging continuity not tested"
# The S24 Ultra's 14 app hardware tests include active tests. Inventory all
# tools, but never trigger audio/vibration/display/controller/camera effects.
for name in bridgectl gpuctl displayctl brightctl camctl oneios-audio; do
  if [ -x "$stage/runtime/bin/$name" ]; then
    info hardware-tool "$name" runtime-staged
  elif [ -x "/data/local/tmp/oneios-m3q-diag/bin/$name" ]; then
    info hardware-tool "$name" standalone-diagnostic
  else
    wait hardware-tool "$name" unavailable-in-staged-runtime
  fi
done
for id in cpu gpu display haptic haptic-pattern audio bt brightness levels als \
          camera-list camera camera-hal-list camera-hal; do
  case "$id" in
    cpu|gpu) info hardware-test "$id" prior-SM8850-test-documented-not-repeated ;;
    brightness|camera-list|camera-hal-list) wait hardware-test "$id" passive-tool-probe-not-run ;;
    *) wait hardware-test "$id" active-or-stateful-device-test-needs-separate-approval ;;
  esac
done
info session staging-impact "No oneios_root.sh, switch, return or install command executed"
PHONE

# ADB shell output can use CRLF; normalize the LOCAL report only.
sed -i 's/\r$//' "$OUT/checks.tsv"
awk -F '|' '
  $1 == "CHECK" { count[$4]++; total++ }
  END {
    printf "audit: %d checks:", total
    for (i = 1; i <= 5; i++) {
      s = (i == 1 ? "PASS" : i == 2 ? "WARN" : i == 3 ? "FAIL" : i == 4 ? "BLOCKED" : "INFO")
      printf " %s=%d", s, count[s]+0
    }
    print ""
  }
' "$OUT/checks.tsv"
echo "audit: $OUT/checks.tsv"
echo "audit: $OUT/metadata.txt"
echo 'audit: BLOCKED means not verified, never approved for a OneiOS switch.'
