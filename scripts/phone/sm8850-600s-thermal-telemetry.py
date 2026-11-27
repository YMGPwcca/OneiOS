#!/usr/bin/env python3
"""SM-S948B bounded (60..600s) takeover + PASSIVE 15-second telemetry.

Uses the existing OneiOS full-takeover wrapper and its bounded DEVICE-SIDE
framework deadline. Telemetry is read-only. On the dedicated SM8850 performance
branch, guarded 180s uses a hybrid downward-only 40% frequency ceiling and
reversible CFS-v1 CPU budget. Other guarded durations retain the legacy cap. Android
kernel/firmware protection, emergency guard, watchdog and deadline remain.
This is not safety certification.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import signal
import shlex
import subprocess
import threading
import time
import uuid

DEVICE = "SM-S948B"
FIRMWARE = "S948BXXS4BZIG"
WRAPPER = Path("scripts/phone/sm8850-full-takeover.sh")
RISK = "--i-accept-10-minute-legacy-watchdog-risk"


def configure_performance_thermal_profile(branch, duration, env):
    """Guarded performance branch; never inherit the historical passive mode."""
    if branch == "feat/sm8850-xnuhost-perf-p0" and duration == 180:
        env.pop("ONEIOS_SM8850_SOFT_THERMAL_OFF", None)

# A minimal, read-only probe. It runs in Android's init namespace (not inside
# xnuhost's /data bind mount). Both process markers are in current xnuhost.log.
PROBE = r'''
ST=/data/adb/oneios-m3q-framework
meta() { printf 'M\t%s\t%s\n' "$1" "$2"; }
val() { [ ! -r "$1" ] || meta "$2" "$(cat "$1" 2>/dev/null)"; }
val /proc/sys/kernel/random/boot_id boot_id
meta uptime "$(cut -d' ' -f1 /proc/uptime)"
for k in boot state framework.launch framework.mode framework.duration framework.perf-profile framework.cpu-profile framework.own-presence framework.interaction-profile framework.cpu-budget thermal.cap.group framework.deadline framework.takeover-confirmed watchdog.phase thermal.guard.heartbeat thermal.cap.heartbeat thermal.guard.fault thermal.cap.fault; do
    val "$ST/control/$k" "ctl/$k"
done
# The previous session's stage is intentionally retained across a reboot.
# Never advertise an old guest-ready/first-frame as proof on a NEW boot.
ctl_boot=$(cat "$ST/control/boot" 2>/dev/null)
current_boot=$(cat /proc/sys/kernel/random/boot_id)
ctl_state=$(cat "$ST/control/state" 2>/dev/null)
if [ "$ctl_boot" = "$current_boot" ] && [ "$ctl_state" = running ]; then
    [ ! -e "$ST/session/ready" ] || meta guest_ready 1
    # Framework stop must be from this boot's launch token.
    tok=$(cat "$ST/control/framework.launch" 2>/dev/null)
    case "$tok" in
        ''|*[!0-9a-f]*) ;;
        *) if [ "${#tok}" -eq 32 ] && [ -r "$ST/launches/$tok/switch.log" ]; then
               stopline=$(grep -m1 'Framework stopped, app groups drained and Android input absent at uptime' "$ST/launches/$tok/switch.log" 2>/dev/null)
               [ -z "$stopline" ] || meta framework_stop_log "$stopline"
           fi ;;
    esac
    case "$(cat "$ST/control/framework.cpu-budget" 2>/dev/null)" in
        cfs-v1-180s|hybrid-v1-180s)
        case "$tok" in
            ''|*[!0-9a-f]*) ;;
            *)
                group="/dev/cpuctl/oneios_guest.$tok"
                if [ "${#tok}" = 32 ] && [ -d "$group" ] && [ ! -L "$group" ] &&
                   [ "$(realpath "$group")" = "$group" ]; then
                    read -r v b g t i extra < "$ST/control/thermal.cap.group" 2>/dev/null || v=
                    if [ "$v" = v1 ] && [ "$b" = "$current_boot" ] &&
                       [ "$g" = "$(cat "$ST/control/watchdog.generation" 2>/dev/null)" ] &&
                       [ "$t" = "$tok" ] && [ -z "$extra" ] &&
                       [ "$i" = "$(stat -c '%d:%i' "$group" 2>/dev/null)" ]; then
                        val "$group/cpu.cfs_quota_us" cpu_budget/quota_us
                        val "$group/cpu.cfs_period_us" cpu_budget/period_us
                        while read -r key value extra; do
                            case "$key" in nr_periods|nr_throttled|throttled_time|nr_bursts|burst_time)
                                [ -z "$extra" ] && meta "cpu_budget/$key" "$value" ;;
                            esac
                        done < "$group/cpu.stat" 2>/dev/null
                    fi
                fi ;;
        esac
        ;;
    esac
    if [ -f "$ST/control/display.log" ] && grep -qm1 'first frame posted' "$ST/control/display.log" 2>/dev/null; then
        meta first_frame 1
    fi
else
    meta stale_session_markers_ignored 1
fi
'''

MARKERS = r'''
ST=/data/adb/oneios-m3q-framework
if [ "$(cat "$ST/control/boot" 2>/dev/null)" = "$(cat /proc/sys/kernel/random/boot_id)" ] &&
   [ "$(cat "$ST/control/state" 2>/dev/null)" = running ] &&
   [ -f "$ST/session/xnuhost.log" ]; then
    if tail -c 1048576 "$ST/session/xnuhost.log" 2>/dev/null | grep -Eaq 'guest .*backboardd\['; then
        printf 'M\tbackboardd_log\t1\n'
    fi
    if tail -c 1048576 "$ST/session/xnuhost.log" 2>/dev/null | grep -Eaq 'guest .*SpringBoard\['; then
        printf 'M\tspringboard_log\t1\n'
    fi
    if tail -c 1048576 "$ST/session/xnuhost.log" 2>/dev/null | grep -Fq 'gpu: drm2kgsl on /dev/kgsl-3d0'; then
        printf 'M\tkgsl_3d_backend_log\t1\n'
    fi
    if tail -c 1048576 "$ST/session/xnuhost.log" 2>/dev/null | grep -Fq 'SM8850_FULL_BRIDGES=ACTIVE; bridges=1;'; then
        printf 'M\tfull_bridges_runtime_log\t1\n'
    fi
fi
'''

# Only sysfs/proc reads. No "echo > /sys", setprop, writes, kill or reboot.
# Enumerates first-level thermal_zone* and cooling_device* only: no recursion.
METRICS = r'''
data() {
    f="$1"
    [ -r "$f" ] || return 0
    v=""
    IFS= read -r v < "$f" 2>/dev/null || :
    [ -n "$v" ] || return 0
    printf 'D\t%s\t%s\n' "$f" "$v"
}
for z in /sys/class/thermal/thermal_zone*; do
    [ -d "$z" ] || continue
    data "$z/type"
    data "$z/temp"
    data "$z/mode"
done
for c in /sys/class/thermal/cooling_device*; do
    [ -d "$c" ] || continue
    data "$c/type"
    data "$c/cur_state"
    data "$c/max_state"
done
for n in temp lrp temperature capacity status health current_now voltage_now cycle_count; do
    data "/sys/class/power_supply/battery/$n"
done
data /sys/class/sec/sec-ap-thermistor/temperature
for policy in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -d "$policy" ] || continue
    for n in affected_cpus related_cpus scaling_cur_freq cpuinfo_cur_freq scaling_min_freq scaling_max_freq cpuinfo_max_freq scaling_governor; do
        data "$policy/$n"
    done
done
for cpu in /sys/devices/system/cpu/cpu[0-9]*; do
    [ -d "$cpu" ] || continue
    data "$cpu/online"
    data "$cpu/cpufreq/scaling_cur_freq"
done
for n in cpufreq_max_limit cpufreq_min_limit; do
    data "/sys/devices/system/cpu/cpufreq_limit/$n"
done
for n in gpuclk gpu_busy_percentage gpubusy throttling thermal_pwrlevel pwrlevel max_gpuclk min_gpuclk; do
    data "/sys/class/kgsl/kgsl-3d0/$n"
done
for n in cur_freq min_freq max_freq governor; do
    data "/sys/class/kgsl/kgsl-3d0/devfreq/$n"
done
for n in gpu_clock gpu_max_clock gpu_min_clock; do
    data "/sys/kernel/gpu/$n"
done
for f in /sys/class/devfreq/*/cur_freq; do
    [ -r "$f" ] && data "$f"
done
printf 'D\t/proc/meminfo/MemAvailable_kB\t%s\n' "$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo)"
printf 'D\t/proc/meminfo/SwapFree_kB\t%s\n' "$(awk '/^SwapFree:/ {print $2; exit}' /proc/meminfo)"
'''


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_lines(text: str) -> tuple[dict[str, str], dict[str, str]]:
    meta: dict[str, str] = {}
    data: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        kind, key, value = parts
        if kind == "M":
            meta[key] = value
        elif kind == "D" and key.startswith(("/sys/", "/proc/")):
            data[key] = value
    return meta, data


def raw_metric_human(key: str, value: str) -> str:
    if not re.fullmatch(r"-?\d+", value.strip()):
        return value
    n = int(value)
    if key in {
        "/sys/class/power_supply/battery/temp",
        "/sys/class/power_supply/battery/lrp",
        "/sys/class/sec/sec-ap-thermistor/temperature",
    }:
        return f"{n} raw = {n / 10:.1f} C (Samsung deci-C)"
    if re.fullmatch(r"/sys/class/thermal/thermal_zone\d+/temp", key):
        return f"{n} raw (thermal-zone units: verify sensor; usually milli-C)"
    if re.search(r"/(?:policy[0-9]+|cpufreq)/(?:scaling_cur_freq|cpuinfo_cur_freq|scaling_min_freq|scaling_max_freq)$", key):
        return f"{n} kHz = {n / 1000:.1f} MHz"
    if key.endswith("/devfreq/cur_freq") or key.endswith("/gpuclk"):
        return f"{n} raw (typically Hz; verify this kernel path)"
    return value


class Console:
    def __init__(self, path: Path, *, verbose: bool = False):
        self.path = path
        self.verbose = verbose
        self.file = path.open("w", encoding="utf-8", buffering=1)
        self.lock = threading.Lock()

    def say(self, line: str = "", *, visible: bool = True) -> None:
        with self.lock:
            # Keep the complete original transcript regardless of terminal verbosity.
            self.file.write(line + "\n")
            if visible or self.verbose:
                print(line, flush=True)

    def close(self) -> None:
        self.file.close()


def adb_shell(adb: str, serial: str, script: str, *, root: bool, timeout: float) -> str:
    # The entire shell body is a single quoted argument; no user-supplied
    # paths are interpolated into the remote command.
    command = ("su -c " + shlex.quote(script)) if root else script
    result = subprocess.run(
        [adb, "-s", serial, "shell", "-T", command],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        errors="replace", timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(
            f"adb shell rc={result.returncode}: " + (result.stderr or result.stdout).strip()[:180]
        )
    return result.stdout


def remote_probe(adb: str, serial: str, *, full: bool = False,
                 markers: bool = False) -> tuple[dict[str, str], dict[str, str]]:
    body = PROBE + (MARKERS if markers else "") + (METRICS if full else "")
    return parse_lines(adb_shell(adb, serial, body, root=True, timeout=13 if full else 7))


def stock_identity(adb: str, serial: str) -> dict[str, str]:
    body = r'''
printf 'M\tmodel\t%s\n' "$(getprop ro.product.model)"
printf 'M\tdevice\t%s\n' "$(getprop ro.product.device)"
printf 'M\tfirmware\t%s\n' "$(getprop ro.build.version.incremental)"
printf 'M\tboot_completed\t%s\n' "$(getprop sys.boot_completed)"
printf 'M\tboot_id\t%s\n' "$(cat /proc/sys/kernel/random/boot_id)"
printf 'M\tsystem_server\t%s\n' "$(pidof system_server)"
'''
    m, _ = parse_lines(adb_shell(adb, serial, body, root=False, timeout=10))
    if (m.get("model"), m.get("device"), m.get("firmware"), m.get("boot_completed")) != (
        DEVICE, "m3q", FIRMWARE, "1"
    ) or not m.get("system_server") or not m.get("boot_id"):
        raise RuntimeError(f"Not stock/ready target {DEVICE}/{FIRMWARE}: {m}")
    return m


def state_of(meta: dict[str, str]) -> tuple[str, float | None, int | None]:
    boot = meta.get("boot_id", "")
    try:
        uptime = float(meta["uptime"])
        deadline = int(meta["ctl/framework.deadline"])
        if not (uptime >= 0 and deadline > 0):
            raise ValueError("invalid clock/deadline")
    except (KeyError, ValueError, OverflowError):
        return boot, None, None
    return boot, uptime, deadline


def snapshot_summary(record: dict) -> str:
    """Small display-only view; no sensor inference, no change to sampling."""
    meta, metrics = record["meta"], record["metrics"]
    guard = meta.get("ctl/thermal.guard.heartbeat", "").split()
    cap = meta.get("ctl/thermal.cap.heartbeat", "").split()
    current = meta.get("boot_id")
    active = bool(current and meta.get("ctl/boot") == current and meta.get("ctl/state") == "running")
    guard_cpu = guard[8] if active and len(guard) == 14 and guard[:2] == ["v1", current] and guard[7] == "OK" else "NA"
    cap_pct = cap[9] if active and len(cap) == 10 and cap[:2] == ["v1", current] and cap[7] == "OK" else "NA"
    profile = meta.get("ctl/framework.cpu-budget")
    cfs = active and profile in ("cfs-v1-180s", "hybrid-v1-180s") and len(cap) == 10 and cap[8] == "7"
    budget_pct = cap_pct if cfs else "NA"
    hybrid_freq_request = "40" if cfs and profile == "hybrid-v1-180s" and budget_pct != "NA" else "NA"
    if cfs:
        cap_pct = "NA"  # quota is CPU time, not a frequency percentage
    cpu0 = metrics.get("/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq", "NA")
    cpu6 = metrics.get("/sys/devices/system/cpu/cpufreq/policy6/scaling_max_freq", "NA")
    return (f"SNAPSHOT={record['kind']} T={record['elapsed_from_framework_stop_s']}s "
            f"guard_cpu_mC={guard_cpu} cap_pct={cap_pct} cpu_budget_pct={budget_pct} "
            f"nr_throttled={meta.get('cpu_budget/nr_throttled', 'NA') if cfs else 'NA'} "
            f"freq_ceiling_request_pct={hybrid_freq_request} "
            f"policy0_max_kHz={cpu0} policy6_max_kHz={cpu6} "
            f"guest_ready={meta.get('guest_ready', 'unseen')} "
            f"first_frame={meta.get('first_frame', 'unseen')} "
            f"springboard_log={meta.get('springboard_log', 'unseen')} "
            f"backboardd_log={meta.get('backboardd_log', 'unseen')} "
            f"metrics={len(metrics)}")


def guest_milestone_summary(*, ready: bool, first_frame: bool,
                            springboard: bool, backboardd: bool) -> str:
    # A posted buffer is not proof of an Apple logo, Lock Screen or usable UI.
    # Even all four log markers require independent visual observation.
    return ("GUEST_BOOT_MILESTONES=ALL_LOG_MARKERS_OBSERVED_VISUAL_UNVERIFIED"
            if all((ready, first_frame, springboard, backboardd))
            else "GUEST_BOOT_MILESTONES=INCOMPLETE_VISUAL_UNVERIFIED")


def sample(adb: str, serial: str, kind: str, out: Path, console: Console,
           jsonl, expected_boot: str, expected_token: str | None,
           duration: int | None = None) -> dict | None:
    ts = now_utc()
    try:
        meta, metrics = remote_probe(adb, serial, full=True, markers=True)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        error = f"{type(exc).__name__}: {str(exc)[:170]}"
        jsonl.write(json.dumps({"kind": kind, "utc": ts, "error": error}) + "\n")
        jsonl.flush()
        console.say(f"SAMPLE_ERROR kind={kind} utc={ts} error={error}")
        return None
    boot, uptime, deadline = state_of(meta)
    if boot != expected_boot or (expected_token and meta.get("ctl/framework.launch") != expected_token):
        reason = (f"boot changed {boot!r} vs {expected_boot!r}" if boot != expected_boot
                  else "session token changed")
        jsonl.write(json.dumps({"kind": kind, "utc": ts, "rejected": reason}) + "\n")
        jsonl.flush()
        console.say(f"SAMPLE_REJECTED kind={kind}: {reason}")
        return None
    # Defense in depth for old or mocked ADB probes that still surface
    # stale PRE_ONEUI markers. Keep current control metadata for forensics,
    # but never count a previous boot's guest or display as current.
    if meta.get("ctl/boot") != boot:
        for stale in ("guest_ready", "first_frame", "springboard_log",
                      "backboardd_log", "kgsl_3d_backend_log", "framework_stop_log"):
            meta.pop(stale, None)
        meta["stale_session_markers_ignored"] = "1"
    elapsed = (round(duration - (deadline - uptime), 3)
               if deadline is not None and uptime is not None and duration is not None and expected_token else None)
    record = {"kind": kind, "utc": ts, "elapsed_from_framework_stop_s": elapsed,
              "meta": meta, "metrics": metrics}
    jsonl.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    jsonl.flush()
    console.say(snapshot_summary(record))
    console.say(f"\n===== SNAPSHOT {kind} UTC={ts} T={elapsed}S COUNT={len(metrics)} =====", visible=False)
    for k in sorted(meta):
        console.say(f"META {k}={meta[k]}", visible=False)
    for k in sorted(metrics):
        console.say(f"READ {k} = {raw_metric_human(k, metrics[k])}", visible=False)
    console.say(f"===== END SNAPSHOT {kind} =====\n", visible=False)
    if kind in {"BASELINE_SPRINGBOARD_BACKBOARDD", "FINAL_NEAR_DEADLINE"}:
        (out / ("baseline.json" if kind.startswith("BASELINE") else "final.json")).write_text(
            json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
    return record


def numeric(val: str) -> int | None:
    return int(val.strip()) if re.fullmatch(r"-?\d+", val.strip()) else None


def compare(a: dict | None, b: dict | None, console: Console, out: Path) -> None:
    lines = ["===== BASELINE VS FINAL COMPARISON ====="]
    if a is None or b is None:
        lines += ["COMPARISON=INCOMPLETE", "REASON=Baseline or final telemetry unavailable; no fabricated readings"]
    else:
        lines.append(f"BASELINE_T={a['elapsed_from_framework_stop_s']}s")
        lines.append(f"FINAL_T={b['elapsed_from_framework_stop_s']}s")
        before, after = a["metrics"], b["metrics"]
        for key in sorted(set(before) | set(after)):
            old = before.get(key, "MISSING")
            new = after.get(key, "MISSING")
            x, y = numeric(old), numeric(new)
            delta = f" DELTA_RAW={y-x:+d}" if x is not None and y is not None else ""
            if key in {
                "/sys/class/power_supply/battery/temp",
                "/sys/class/power_supply/battery/lrp",
                "/sys/class/sec/sec-ap-thermistor/temperature",
            } and x is not None and y is not None:
                delta += f" DELTA_C={((y-x)/10):+.1f}"
            elif re.fullmatch(r"/sys/class/thermal/thermal_zone\d+/temp", key) and x is not None and y is not None:
                delta += " SENSOR_UNIT=UNVERIFIED"
            elif "scaling_cur_freq" in key and x is not None and y is not None:
                delta += f" DELTA_MHZ={((y-x)/1000):+.1f}"
            lines.append(f"{key}: BEFORE={old} AFTER={new}{delta}")
        lines.append("COMPARISON=MEASURED_NOT_THERMAL_SAFETY_QUALIFIED")
    text = "\n".join(lines) + "\n"
    (out / "comparison.txt").write_text(text, encoding="utf-8")
    for line in lines:
        console.say(line, visible=not (line.startswith(("/sys/", "/proc/"))))


def stream_subprocess(proc: subprocess.Popen, console: Console, logfile: Path, prefix: str) -> None:
    assert proc.stdout is not None
    with logfile.open("w", encoding="utf-8", buffering=1) as f:
        for line in proc.stdout:
            f.write(line)
            message = line.rstrip("\n")
            visible = message.startswith((
                "WARNING=", "BLOCKED", "ERROR", "PREFLIGHT", "FULL_TAKEOVER_",
                "IOS_", "ANDROID_", "BOOT_REASON=", "SM8850_FULL_BRIDGES=",
                "FRAMEWORK_", "RECOVERY=", "PHYSICAL_KEYS=", "LIVE_", "KERNEL_",
                "EVIDENCE=", "LOG=", "EXIT=", "Local evidence:",
            ))
            console.say(prefix + message, visible=visible)


def run_existing(repo: Path, command: list[str], console: Console, outfile: Path,
                 *, async_mode: bool = False):
    proc = subprocess.Popen(command, cwd=repo, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, errors="replace",
                            bufsize=1, start_new_session=async_mode)
    thread = threading.Thread(target=stream_subprocess,
                              args=(proc, console, outfile, "TAKEOVER | " if async_mode else "PREPARE | "),
                              daemon=True)
    thread.start()
    if async_mode:
        return proc, thread
    code = proc.wait()
    thread.join(timeout=10)
    console.say(f"WRAPPER_EXIT={code} FILE={outfile}")
    return code


def finish_local_runner(proc: subprocess.Popen, *, reboot_observed: bool,
                        console: Console) -> int:
    """Bounded host-only cleanup. Never sends a signal or command to the phone.

    When Android has already booted, the old ADB polling subprocess may
    wait for root for minutes. Kill ONLY its separate LOCAL process group,
    not a device-side return or guest process. Always retain session logs.
    """
    if proc.poll() is not None:
        return proc.returncode
    try:
        return proc.wait(timeout=8 if reboot_observed else 15)
    except subprocess.TimeoutExpired:
        console.say("TAKEOVER_HOST_MONITOR=BOUNDED_WAIT_EXPIRED; LOCAL_ONLY_TERMINATION")
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            return proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            console.say("TAKEOVER_HOST_MONITOR=LOCAL_PROCESS_GROUP_FORCE_STOP")
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return proc.wait(timeout=5)


def run_monitor(args, repo: Path, out: Path, console: Console) -> int:
    adb = args.adb
    identity = stock_identity(adb, args.serial)
    console.say(f"DEVICE={identity['model']} FIRMWARE={identity['firmware']} BOOT={identity['boot_id']}")
    console.say("THERMAL_LOGGER=PASSIVE_READ_ONLY; SCRIPT_THERMAL_FORCESHUTDOWN=NONE")
    console.say("KERNEL_FIRMWARE_THERMAL_PROTECTION=UNCHANGED")
    if os.environ.get("ONEIOS_SM8850_SOFT_THERMAL_OFF") == "I_ACCEPT_SOFT_GUARD_OFF_180S":
        console.say("SOFTWARE_THERMAL_GUARD=OFF_NO_ON_DEVICE_PROCESS; WARNING=NO_USERSPACE_TEMP_CUTOFF")
        console.say("CPU_UNDERCLOCK=OFF_NO_ROOT_CAP_WORKER; KERNEL_FIRMWARE_THERMAL_UNCHANGED")
    elif args.duration == 180:
        console.say("SOFTWARE_THERMAL_GUARD=REQUIRED; CPU_BUDGET=HYBRID_FREQ40_CFS_V1; TARGET_45_70C; HARD_80C_RELEASE_70C; 90C_EMERGENCY_RETURN_SEPARATE")
    else:
        console.say("SOFTWARE_THERMAL_GUARD=REQUIRED; CPU_TARGET_30_70C; 75C_THROTTLE_NOT_RETURN; 90C_EMERGENCY_RETURN")
    console.say("GPU_3D=REQUIRED_NO_2D_FALLBACK; BACKEND_PROOF=CHECK_XNUHOST_KGSL_LOG")
    duration = args.duration
    console.say(f"RECOVERY=DEVICE_SIDE_DEADLINE_{duration}S_FROM_FRAMEWORK_STOP_MAX_600S")
    console.say(f"SCHEDULE=15S FROM VERIFIED_FRAMEWORK_STOP; FINAL=ABOUT_T{duration-10}S")
    console.say("WARNING=LEGACY_WATCHDOG_AND_UNASSISTED_RETURN_NOT_FULLY_QUALIFIED")
    before, _ = remote_probe(adb, args.serial)
    old_token = before.get("ctl/framework.launch", "")

    if not args.no_rearm:
        console.say("===== PREPARE: REARM FRESH ONE-SHOT APFS DATA CLONE =====")
        rc = run_existing(repo, ["bash", str(WRAPPER), "rearm", args.serial,
                                 "--duration", str(duration)], console,
                          out / "rearm.log")
        if rc:
            console.say("BLOCKED=REARM_FAILED; NO_LIVE_TAKEOVER_ATTEMPTED")
            return 2
    else:
        console.say("WARNING=REARM_SKIPPED; EXISTING ADMISSION GATE MUST VERIFY FRESH DATA")

    identity = stock_identity(adb, args.serial)
    if identity["boot_id"] != before.get("boot_id"):
        console.say("BLOCKED=BOOT_CHANGED_DURING_REARM")
        return 2

    with (out / "telemetry.jsonl").open("w", encoding="utf-8", buffering=1) as jsonl:
        pre = sample(adb, args.serial, "PRE_ONEUI", out, console, jsonl, identity["boot_id"], None)
        if pre is None or not any(k.endswith("/temp") or
                                  k == "/sys/class/sec/sec-ap-thermistor/temperature"
                                  for k in pre["metrics"]):
            console.say("BLOCKED=NO_PRELAUNCH_TEMPERATURE_READINGS; NO_LIVE_TAKEOVER_ATTEMPTED")
            return 2
        available_zones = sum(k.endswith("/temp") and "thermal_zone" in k
                              for k in pre["metrics"])
        console.say(f"PRELAUNCH_THERMAL_ZONE_COUNT={available_zones}")
        console.say("SENSOR_COVERAGE=VISIBLE_SYSFS_NODES_ONLY; NOT_ALL_INTERNAL_FIRMWARE_SENSORS")
        # This is the existing, risk-acknowledged, state-gated OneiOS runner.
        cmd = ["bash", str(WRAPPER), "run", args.serial, RISK, "--duration", str(duration)]
        if args.perf_profile != "off":
            cmd += ["--perf-profile", args.perf_profile]
        if args.cpu_profile != "default":
            cmd += ["--cpu-profile", args.cpu_profile]
        if args.own_presence == "on":
            cmd += ["--own-presence", "on"]
        if args.interaction_profile != "off":
            cmd += ["--interaction-profile", args.interaction_profile]
        console.say(f"===== LAUNCH GUARDED ONEIOS FULL {duration}S TAKEOVER =====")
        proc, thread = run_existing(repo, cmd, console, out / "takeover.log", async_mode=True)
        deadline = None
        token = None
        stop_verified = False
        incompatible_reported = False
        baseline = None
        final = None
        next_sample = 15
        last_uptime = None
        seen_springboard = False
        seen_backboardd = False
        seen_guest_ready = False
        seen_first_frame = False
        seen_kgsl_3d = False
        seen_full_bridges = False
        last_error_report_at = 0.0
        launched_at = time.monotonic()
        post_reboot = False
        while time.monotonic() - launched_at < duration + 250:
            try:
                meta, _ = remote_probe(adb, args.serial, markers=(baseline is None))
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                if time.monotonic() - last_error_report_at > 15:
                    console.say(f"PROBE_UNAVAILABLE at {now_utc()}: {type(exc).__name__}: {str(exc)[:120]}")
                    last_error_report_at = time.monotonic()
                # Root may disappear after reboot. Read only unprivileged boot status.
                try:
                    check = adb_shell(adb, args.serial,
                                      'printf "BOOT="; cat /proc/sys/kernel/random/boot_id; '
                                      'printf "DONE="; getprop sys.boot_completed',
                                      root=False, timeout=4)
                    remote_boot = re.search(r"^BOOT=([a-fA-F0-9-]{36})$", check, re.M)
                    if (remote_boot and remote_boot.group(1) != identity["boot_id"]
                        and "DONE=1" in check):
                        console.say("POST_REBOOT=ANDROID_BOOT_COMPLETE_OBSERVED_VIA_UNPRIVILEGED_ADB")
                        (out / "post-reboot.txt").write_text(check, encoding="utf-8")
                        post_reboot = True
                        break
                except (OSError, RuntimeError, subprocess.TimeoutExpired):
                    pass
                if proc.poll() is not None and time.monotonic() - launched_at > 15:
                    break
                time.sleep(2)
                continue
            boot, uptime, current_deadline = state_of(meta)
            if token and meta.get("kgsl_3d_backend_log") == "1":
                seen_kgsl_3d = True
            if boot != identity["boot_id"]:
                console.say(f"POST_REBOOT=BOOT_CHANGED boot={boot} prior={identity['boot_id']}")
                post_reboot = True
                break
            observed_token = meta.get("ctl/framework.launch", "")
            if (not token and observed_token and observed_token != old_token
                and meta.get("ctl/framework.mode") == "run"):
                token = observed_token
                console.say(f"SESSION_TOKEN={token} BOOT_ID={boot}")
            if token and observed_token != token:
                console.say("SESSION_MISMATCH=CONTROL_TOKEN_CHANGED; STOPPING_TELEMETRY")
                break
            if token and meta.get("ctl/boot") == boot and meta.get("ctl/state") == "running":
                seen_guest_ready |= meta.get("guest_ready") == "1"
                seen_first_frame |= meta.get("first_frame") == "1"
            if token and meta.get("full_bridges_runtime_log") == "1":
                if not seen_full_bridges:
                    console.say(f"SM8850_FULL_BRIDGES=ACTIVE_RUNTIME_LOG token={token} boot={boot}")
                seen_full_bridges = True
            if (token and current_deadline is not None and deadline is None
                and meta.get("ctl/state") == "running"):
                stop_line = meta.get("framework_stop_log", "")
                matched = re.search(r"uptime (\d+)\. Deadline: (\d+)", stop_line)
                if (matched and int(matched.group(1)) + duration == int(matched.group(2))
                    and int(matched.group(2)) == current_deadline
                    and meta.get("ctl/framework.duration") == str(duration)):
                    deadline = current_deadline
                    stop_verified = True
                    console.say(f"FRAMEWORK_DEADLINE_UPTIME={deadline} FRAMEWORK_STOP_UPTIME={deadline-duration}")
                    console.say(f"FRAMEWORK_{duration}S_TIMEBASE=VERIFIED_FROM_CURRENT_SWITCH_LOG")
                elif not incompatible_reported and stop_line:
                    incompatible_reported = True
                    console.say("FRAMEWORK_TIMEBASE=MISMATCH; WILL_NOT_LABEL_UNVERIFIED_ELAPSED")
            if deadline is not None and uptime is not None and token:
                elapsed = float(duration) - (deadline - uptime)
                last_uptime = uptime
                if meta.get("springboard_log") == "1":
                    seen_springboard = True
                if meta.get("backboardd_log") == "1":
                    seen_backboardd = True
                if seen_springboard and seen_backboardd and baseline is None:
                    baseline = sample(adb, args.serial, "BASELINE_SPRINGBOARD_BACKBOARDD",
                                      out, console, jsonl, identity["boot_id"], token, duration)
                    if baseline:
                        console.say("BASELINE=LOG_MARKERS_OBSERVED_NOT_LIVE_PROCESS_PROOF")
                # Capture 10 seconds before the requested return deadline.
                if elapsed >= duration - 11 and final is None and elapsed < duration - 1:
                    final = sample(adb, args.serial, "FINAL_NEAR_DEADLINE", out, console,
                                   jsonl, identity["boot_id"], token, duration)
                    if final:
                        console.say(f"FINAL_CAPTURE_T={final['elapsed_from_framework_stop_s']}")
                if elapsed >= next_sample and elapsed < duration - 1:
                    actual = next_sample
                    next_sample += 15
                    if elapsed - actual > 12:
                        console.say(f"PERIODIC_MISSED=TARGET_{actual}S ACTUAL_T={elapsed:.1f}S")
                    else:
                        sample(adb, args.serial, f"PERIODIC_TARGET_{actual:03d}S",
                               out, console, jsonl, identity["boot_id"], token, duration)
                if elapsed >= duration + 4 and proc.poll() is not None:
                    break
            if proc.poll() is not None:
                # Successful completion can have exit 4 by design; never infer
                # success from an exit code or from an existing stale marker.
                if deadline is None or (uptime is not None and uptime >= deadline - 2):
                    break
                if meta.get("ctl/state") in {"returned", "failed"}:
                    break
            time.sleep(2.0)

        console.say(f"===== MONITOR FINISHED POST_REBOOT={post_reboot} =====")
        compare(baseline, final, console, out)
        console.say(f"SPRINGBOARD_LOG_SEEN={seen_springboard} BACKBOARDD_LOG_SEEN={seen_backboardd} "
                    f"GUEST_READY_MARKER_SEEN={seen_guest_ready} FIRST_FRAME_MARKER_SEEN={seen_first_frame}")
        console.say(guest_milestone_summary(ready=seen_guest_ready, first_frame=seen_first_frame,
                                           springboard=seen_springboard, backboardd=seen_backboardd))
        console.say("VISUAL_BOOT_ACCEPTANCE=NOT_VERIFIED_OPERATOR_OBSERVATION_REQUIRED")
        if final is None:
            console.say("FINAL_NEAR_DEADLINE=NOT_CAPTURED; CHECK_LOGS_FOR_EARLY_RETURN_OR_USB_LOSS")
        console.say(f"GPU_3D_BACKEND_LOG_SEEN={seen_kgsl_3d}; NO_2D_FALLBACK_ENFORCED_BY_ONEOS")
        console.say(f"SM8850_FULL_BRIDGES_RUNTIME_LOG_SEEN={seen_full_bridges}; "
                    "EXACT_CURRENT_SESSION_CHECK=REQUIRED")
        console.say(f"LAST_BOOT_UPTIME={last_uptime} DEVICE_DEADLINE={deadline} TIMEBASE_VERIFIED={stop_verified}")
        console.say(f"SAMPLES_JSONL={out/'telemetry.jsonl'}")
        console.say(f"TAKEOVER_LOG={out/'takeover.log'}")
        console.say(f"COMPARISON={out/'comparison.txt'}")
        if proc.poll() is None:
            console.say("TAKEOVER_RUNNER_STILL_WAITING=YES; HOST_WAIT_BOUNDED")
        code = finish_local_runner(proc, reboot_observed=post_reboot, console=console)
        thread.join(timeout=10)
        console.say(f"TAKEOVER_RUNNER_EXIT={code} (host process outcome is not recovery proof)")
        if post_reboot:
            console.say("BOUNDED_TAKEOVER_RESULT=POST_REBOOT_OBSERVED_SESSION_CAUSE_NOT_PROVEN")
            return 4
        return code


# Retired policy is retained below only for historical parsing and mocked
# regression coverage. No environment or risk-token override is supported.
LIVE_THERMAL_POLICY_READY = False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=Path.home() / "projects/OneiOS")
    ap.add_argument("--adb", default=str(Path.home() / "Android/Sdk/platform-tools/adb"))
    ap.add_argument("--serial", default="R5GL64LZ9HA")
    ap.add_argument("--i-accept-10-minute-legacy-watchdog-risk", action="store_true")
    ap.add_argument("--duration", type=int, default=600,
                    help="Seconds after verified Framework stop, 60..600 (default 600)")
    ap.add_argument("--perf-profile", choices=("off", "frame", "task", "frame-task"), default="off",
                    help="opt-in bounded runtime instrumentation; does not change admission or thermal policy")
    ap.add_argument("--cpu-profile", choices=("default", "prime-first"), default="default",
                    help="experimental topology-aware placement; no thermal or recovery change")
    ap.add_argument("--own-presence", choices=("off", "on"), default="off",
                    help="opt-in kernel patch 0082; guarded performance branch 180s only")
    ap.add_argument("--interaction-profile", choices=("off", "swipe-60s"), default="off",
                    help="bounded automated gestures, guarded performance branch and frame tracing only")
    ap.add_argument("--no-rearm", action="store_true", help="skip rearm; preflight must still admit a fresh Data clone")
    ap.add_argument("--verbose", action="store_true",
                    help="echo all snapshot and wrapper lines to terminal; full files are always retained")
    ap.add_argument("--self-test", action="store_true", help="parse/unit checks only, never connects to a phone")
    ap.add_argument("--preflight-only", action="store_true",
                    help="read-only exact-duration root admission; never rearm or stop Framework")
    args = ap.parse_args()
    if not 60 <= args.duration <= 600:
        ap.error("--duration must be between 60 and 600 seconds")
    if args.self_test:
        m,d = parse_lines("M\tboot_id\ta\nM\tuptime\t123.50\nM\tctl/framework.deadline\t700\nD\t/sys/x\t451\n")
        assert (m["boot_id"], d["/sys/x"]) == ("a", "451")
        assert state_of(m) == ("a", 123.5, 700)
        assert numeric("-11") == -11 and numeric("not_available") is None
        assert "42.0 C" in raw_metric_human("/sys/class/power_supply/battery/temp", "420")
        for branch, duration in (("feat/sm8850-xnuhost-perf-p0", 180),
                                 ("feat/sm8850-xnuhost-perf-p0", 600),
                                 ("feat/oneios-sm8850-m3q", 180)):
            key = "ONEIOS_SM8850_SOFT_THERMAL_OFF"
            env = {key: "I_ACCEPT_SOFT_GUARD_OFF_180S"}
            configure_performance_thermal_profile(branch, duration, env)
            assert (key not in env) == (branch == "feat/sm8850-xnuhost-perf-p0" and duration == 180)
        import contextlib
        import io
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            for verbose in (False, True):
                transcript = Path(directory) / "console.txt"
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    c = Console(transcript, verbose=verbose)
                    try:
                        c.say("summary")
                        c.say("raw detail", visible=False)
                    finally:
                        c.close()
                assert transcript.read_text() == "summary\nraw detail\n"
                assert stdout.getvalue() == ("summary\nraw detail\n" if verbose else "summary\n")
        assert "INCOMPLETE" in guest_milestone_summary(ready=False, first_frame=True, springboard=False, backboardd=False)
        assert "VISUAL_UNVERIFIED" in guest_milestone_summary(ready=True, first_frame=True, springboard=True, backboardd=True)
        record = {"kind": "FIXTURE", "elapsed_from_framework_stop_s": 30,
                  "meta": {"boot_id": "a", "ctl/boot": "a", "ctl/state": "running",
                           "ctl/thermal.guard.heartbeat": "v1 a g 12 34 5 6 OK 41300 39000 39000 296 321 339",
                           "ctl/thermal.cap.heartbeat": "v1 a g 13 35 5 6 OK 4 18",
                           "first_frame": "1"},
                  "metrics": {"/sys/devices/system/cpu/cpufreq/policy0/scaling_max_freq": "537600"}}
        summary = snapshot_summary(record)
        assert "guard_cpu_mC=41300 cap_pct=18" in summary and "policy0_max_kHz=537600" in summary
        record["meta"]["ctl/framework.cpu-budget"] = "cfs-v1-180s"
        record["meta"]["ctl/thermal.cap.heartbeat"] = "v1 a g 13 35 5 6 OK 7 80"
        record["meta"]["cpu_budget/nr_throttled"] = "12"
        assert "cap_pct=NA cpu_budget_pct=80 nr_throttled=12" in snapshot_summary(record)
        record["meta"]["ctl/framework.cpu-budget"] = "hybrid-v1-180s"
        assert "freq_ceiling_request_pct=40" in snapshot_summary(record)
        record["meta"]["ctl/boot"] = "previous"
        assert "guard_cpu_mC=NA cap_pct=NA" in snapshot_summary(record)
        print("SELF_TEST=PASS NO_DEVICE_ACCESS")
        return 0
    if not args.preflight_only and not args.i_accept_10_minute_legacy_watchdog_risk:
        ap.error("Live run requires --i-accept-10-minute-legacy-watchdog-risk")
    repo = args.repo.expanduser().resolve()
    # On the experimental full-bridges branch the operator explicitly chose
    # 180 seconds. Reject mismatched durations before creating a new Data
    # clone or touching the live Framework.
    branch = subprocess.check_output(
        ["git", "-C", str(repo), "branch", "--show-current"],
        text=True, timeout=10,
    ).strip()
    if (branch in {"feat/oneios-sm8850-m3q", "feat/sm8850-full-bridges-takeover", "feat/sm8850-xnuhost-perf-p0"}
            and args.duration != 180):
        ap.error("SM8850 full bridges live trial requires --duration 180")
    if not LIVE_THERMAL_POLICY_READY:
        ap.error("SM8850_THERMAL_POLICY=BLOCKED_LEGACY_RETIRED; stock-managed thermal runner and non-reboot guest quiesce not integrated/qualified")
    # Apply once before either preflight or the rearm/run subprocesses.
    # Never depend on the caller remembering a separate shell export.
    if args.own_presence == "on" and (branch != "feat/sm8850-xnuhost-perf-p0" or args.duration != 180):
        ap.error("--own-presence on requires the guarded 180s performance branch")
    if args.interaction_profile != "off" and (branch != "feat/sm8850-xnuhost-perf-p0" or
            args.duration != 180 or args.perf_profile not in ("frame", "frame-task") or
            (not args.preflight_only and not args.no_rearm)):
        ap.error("interaction requires guarded 180s performance branch, frame tracing and separately prepared Data (--no-rearm)")
    configure_performance_thermal_profile(branch, args.duration, os.environ)
    if not (repo / WRAPPER).is_file():
        ap.error(f"Missing existing OneiOS wrapper: {repo / WRAPPER}")
    if not Path(args.adb).is_file():
        ap.error(f"ADB not found: {args.adb}")
    if args.preflight_only:
        stock_identity(args.adb, args.serial)
        no_guard = (
            os.environ.get("ONEIOS_SM8850_SOFT_THERMAL_OFF") ==
            "I_ACCEPT_SOFT_GUARD_OFF_180S"
        )
        if no_guard and args.duration != 180:
            ap.error("no-userspace-thermal preflight requires --duration 180")
        prefix = ("ONEIOS_SM8850_EXPERIMENT_NO_SOFT_THERMAL=I_ACCEPT_SOFT_GUARD_OFF_180S "
                  if no_guard else "")
        profile_token = " I_ACCEPT_SOFT_GUARD_OFF_180S" if no_guard else ""
        result = adb_shell(
            args.adb, args.serial,
            prefix + "/system/bin/sh /data/adb/oneios-m3q-framework/oneios_switch.sh --framework-check run " +
            str(args.duration) + profile_token + (" perf-" + args.perf_profile if args.perf_profile != "off" else "") +
            (" cpu-prime-first" if args.cpu_profile == "prime-first" else "") +
            (" own-presence-1" if args.own_presence == "on" else "") +
            (" interaction-swipe-60s" if args.interaction_profile == "swipe-60s" else ""),
            root=True, timeout=120,
        )
        print(result, end="" if result.endswith("\n") else "\n")
        acknowledged_off = "SM8850_SOFT_THERMAL_GUARD=OFF_NOT_SPAWNED" in result
        if no_guard != acknowledged_off:
            raise RuntimeError("root preflight thermal profile mismatch; no Framework stop or data consumption")
        cap_disabled = "SM8850_CPU_CAP=DISABLED_NO_ROOT_WORKER" in result
        if no_guard != cap_disabled:
            raise RuntimeError("root preflight CPU cap profile mismatch; no Framework stop or data consumption")
        thermal_marker = ("SM8850_CPU_THROTTLE_POLICY=HYBRID_FREQ40_CFS_V1_TARGET_45_70_HARD_80_RELEASE_70"
                          if args.duration == 180 else
                          "SM8850_CPU_THROTTLE_POLICY=TARGET_30_70_THROTTLE_BY_75_MONOTONIC")
        if not no_guard and thermal_marker not in result.splitlines():
            raise RuntimeError("guarded thermal policy marker missing; no Framework stop or data consumption")
        profiles = [line.split("=", 1)[1] for line in result.splitlines()
                    if line.startswith("SM8850_PERF_PROFILE=")]
        if (profiles and profiles != [args.perf_profile]) or (args.perf_profile != "off" and not profiles):
            raise RuntimeError("root preflight performance profile mismatch; no Framework stop or data consumption")
        cpu_profiles = [line.split("=", 1)[1] for line in result.splitlines()
                        if line.startswith("SM8850_CPU_PROFILE_REQUESTED=")]
        if (cpu_profiles and cpu_profiles != [args.cpu_profile]) or (args.cpu_profile != "default" and not cpu_profiles):
            raise RuntimeError("root preflight CPU profile mismatch; no Framework stop or data consumption")
        own_profiles = [line for line in result.splitlines()
                        if line.startswith("SM8850_OWN_PRESENCE=")]
        expected_own = "SM8850_OWN_PRESENCE=" + ("1" if args.own_presence == "on" else "0")
        if (own_profiles or args.own_presence == "on") and own_profiles != [expected_own]:
            raise RuntimeError("root preflight own-presence mismatch; no Framework stop or data consumption")
        interaction_profiles = [line for line in result.splitlines()
                                if line.startswith("SM8850_INTERACTION_PROFILE=")]
        if (interaction_profiles or args.interaction_profile != "off") and interaction_profiles != [
                "SM8850_INTERACTION_PROFILE=" + args.interaction_profile]:
            raise RuntimeError("root preflight interaction profile mismatch; no Framework stop or data consumption")
        if no_guard:
            print("NO_USERSPACE_THERMAL_180S_PREFLIGHT=PASS_NO_FRAMEWORK_STOP_NO_DATA_CONSUMPTION")
        else:
            print("GUARDED_PREFLIGHT=PASS_NO_FRAMEWORK_STOP_NO_DATA_CONSUMPTION")
        print("PHYSICAL_THERMAL_WATCHDOG_QUALIFICATION=NOT_VERIFIED")
        return 0
    out = repo / "out/sm8850/thermal-bounded" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    console = Console(out / "console.txt", verbose=args.verbose)
    try:
        console.say(f"ONEIOS_BOUNDED_TELEMETRY=START duration={args.duration}")
        console.say(f"OUTPUT={out}")
        rc = run_monitor(args, repo, out, console)
        console.say(f"ONEIOS_BOUNDED_TELEMETRY=FINISHED EXIT={rc}")
        return rc
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        console.say(f"ONEIOS_BOUNDED_TELEMETRY=ERROR {type(exc).__name__}: {exc}")
        return 2
    finally:
        console.say(f"FULL_CONSOLE_LOG={out/'console.txt'}")
        console.close()


if __name__ == "__main__":
    raise SystemExit(main())
