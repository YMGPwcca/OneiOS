#!/usr/bin/env python3
"""SM8850 GPU evidence gates: passive preflight, bounded host submit, offline iOS log audit.

Never launches a guest, touches a watchdog, changes sysctls or writes APFS Data.
Host KGSL success is intentionally NOT an iOS Vulkan success.
"""

import argparse
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ("SM-S948B", "m3q", "SM8850")
FIRMWARE = "S948BXXS4BZIG"
MIN_FREE_KIB = 30 * 1024 * 1024 + 65536  # reserve 30 GiB after a modest probe allocation
DEVICE_AUDIT = r'''set -eu
printf 'uid=%s\n' "$(id -u)"
printf 'model=%s\n' "$(getprop ro.product.model)"
printf 'device=%s\n' "$(getprop ro.product.device)"
printf 'soc=%s\n' "$(getprop ro.soc.model)"
printf 'build=%s\n' "$(getprop ro.build.version.incremental)"
printf 'fingerprint=%s\n' "$(getprop ro.build.fingerprint)"
printf 'boot_completed=%s\n' "$(getprop sys.boot_completed)"
printf 'zygote=%s\n' "$(getprop init.svc.zygote)"
printf 'selinux=%s\n' "$(getenforce)"
if pidof system_server >/dev/null 2>&1; then echo system_server=yes; else echo system_server=no; fi
if pidof xnuhost xnuhost-gui-bench xnuhost-tasks oneios-display OneiOSDisplay >/dev/null 2>&1; then
  echo guest_running=yes
else echo guest_running=no; fi
if [ -r /data/adb/oneios-m3q-framework/control/state ]; then
  printf 'takeover_state=%s\n' "$(cat /data/adb/oneios-m3q-framework/control/state)"
else echo takeover_state=absent; fi
printf 'free_kib=%s\n' "$(df -Pk /data/local/tmp | awk 'END {print $4}')"
printf 'battery_pct=%s\n' "$(cat /sys/class/power_supply/battery/capacity)"
printf 'battery_temp_decic=%s\n' "$(cat /sys/class/power_supply/battery/temp)"
printf 'map_count=%s\n' "$(cat /proc/sys/vm/max_map_count)"
if command -v timeout >/dev/null 2>&1; then echo timeout=yes; else echo timeout=no; fi
'''


class Blocked(RuntimeError):
    pass


def run(args, *, script=None, seconds=25, check=True):
    try:
        p = subprocess.run(args, input=script, text=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=seconds, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked(f"command unavailable or timed out: {args[:4]} ({type(exc).__name__})") from exc
    if check and p.returncode:
        raise Blocked(f"command failed ({p.returncode}): {args[:4]}\n{p.stdout[-1500:]}")
    return p


def root(adb, script, *, seconds=25, check=True):
    return run([*adb, "shell", "-T", "su -c 'sh -s'"], script=script + "\n",
               seconds=seconds, check=check)


def select_usb(adb_binary, serial=None):
    out = run([adb_binary, "devices", "-l"], seconds=10).stdout
    matches = [row.split()[0] for row in out.splitlines()
               if re.search(r"\sdevice\s+.*\busb:", row)]
    if not matches or (serial and serial not in matches) or (not serial and len(matches) != 1):
        raise Blocked("select one authorized USB ADB device (use --serial); wireless ADB is not accepted")
    return [adb_binary, "-s", serial or matches[0]]


def decode_kv(text):
    parsed = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        parsed[k] = v.strip()
    return parsed


def validate_preflight(v):
    failures = []
    checks = {
        "target": tuple(v.get(k) for k in ("model", "device", "soc")) == TARGET,
        "firmware": v.get("build", "").startswith(FIRMWARE) and FIRMWARE in v.get("fingerprint", ""),
        "root": v.get("uid") == "0",
        "framework": v.get("boot_completed") == "1" and v.get("zygote") == "running" and v.get("system_server") == "yes",
        "selinux": v.get("selinux") == "Enforcing",
        "no_guest": v.get("guest_running") == "no",
        "no_takeover": v.get("takeover_state") in ("absent", "complete", "returned", "idle"),
        "space": v.get("free_kib", "").isdigit() and int(v["free_kib"]) >= MIN_FREE_KIB,
        "battery": v.get("battery_pct", "").isdigit() and int(v["battery_pct"]) >= 30,
        "temperature": v.get("battery_temp_decic", "").isdigit() and 0 < int(v["battery_temp_decic"]) <= 440,
        "timeout": v.get("timeout") == "yes",
    }
    failures.extend(name for name, ok in checks.items() if not ok)
    return checks, failures


def analyze_guest(text):
    """Never infer iOS Vulkan PASS from plugin load, IOKit open alone or host gpuctl."""
    markers = {
        "drm_renderer": bool(re.search(r"virtio GPU with the DRM native context", text)),
        "bootarg_vgpu3d": bool(re.search(r'boot_args\s+"[^"\n]*\bvgpu-3d=1\b', text)),
        "turnip_drm": bool(re.search(r"oneios-vk-init[^\n]*Turnip backend=DRM native\b", text)),
        "drm_open": bool(re.search(r"oneios-vk-init[^\n]*DRM native IOServiceOpen type=0x4149 status=(?:0|0x0)\b", text)),
        "enumerated": bool(re.search(r"oneios-vk-init[^\n]*vkEnumeratePhysicalDevices result=0 device_count=[1-9][0-9]*\b", text)),
        "created_device": bool(re.search(r"oneios-vk-init[^\n]*vkCreateDevice[^\n]*result=0\b", text)),
        "guest_gpu_fence": any(int(n) > 0 for n in re.findall(r"\bbackboardd fences ([0-9]+)\b", text)),
    }
    errors = {
        "vulkan_initialization_failed": bool(re.search(r"VkResultCode\(-3\)|vkEnumeratePhysicalDevices result=-3|vkCreateDevice[^\n]*result=-3", text)),
        "backboardd_abort": bool(re.search(r"backboardd\[[0-9]+\] status 0x6|ogl-context\.cpp:1309|found != slist->end", text)),
    }
    # A GPU fence alone can be a standalone test; require all guest milestones.
    passed = all(markers.values()) and not errors["vulkan_initialization_failed"]
    return {"markers": markers, "errors": errors, "IOS_VULKAN": "PASS" if passed else "UNVERIFIED",
            "GUI_STABLE": "NOT_EVALUATED" if not errors["backboardd_abort"] else "FAIL"}


def host_submit_pass(logs):
    return (bool(re.search(r"capset: DRM \(6\)[^\n]*chip 0x44050a00, gpu id 6860\b", logs))
            and bool(re.search(r"submit: queue [0-9]+,[^\n]*run by the GPU, fence retired after [0-9.]+ ms; GPU faults 0, async errors 0", logs))
            and "FAILED at:" not in logs and logs.rstrip().endswith("ok"))


def save_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(f"REPORT={path}")


def hardware(adb, gpuctl, report):
    v = decode_kv(root(adb, DEVICE_AUDIT).stdout)
    checks, failures = validate_preflight(v)
    report.update({"preflight": {"values": v, "checks": checks},
                   "PREFLIGHT": "BLOCKED" if failures else "PASS", "failures": failures})
    if failures:
        raise Blocked("preflight failed: " + ", ".join(failures))
    if report["action"] == "preflight":
        return
    if not gpuctl.is_file():
        raise Blocked(f"missing gpuctl: {gpuctl}; build with: make -C runtime/xnuhost build/android/gpuctl")
    local_digest = hashlib.sha256(gpuctl.read_bytes()).hexdigest()
    nonce = secrets.token_hex(8)
    incoming = f"/data/local/tmp/oneios-gpuctl-{nonce}.bin"
    private = f"/data/adb/oneios-gpuctl-{nonce}"
    logs = []
    pushed = False
    staged = False
    try:
        run([*adb, "push", str(gpuctl), incoming], seconds=45)
        pushed = True
        setup = (f"set -eu\numask 077\n[ ! -e '{private}' ]\n"
                 f"[ -f '{incoming}' ] && [ ! -L '{incoming}' ]\n"
                 f"mkdir -m 700 '{private}'\ncp '{incoming}' '{private}/gpuctl'\n"
                 f"chmod 700 '{private}/gpuctl'\nsha256sum '{private}/gpuctl' | cut -d' ' -f1")
        remote_digest = root(adb, setup).stdout.strip().splitlines()[-1]
        staged = True
        if remote_digest != local_digest:
            raise Blocked("root-owned staged gpuctl SHA-256 does not match host")
        for action in ("nodes", "probe", "submit"):
            # Device-side timeout survives host ADB/SSH cancellation.
            command = f"exec timeout -s TERM 20 '{private}/gpuctl' {action} -v"
            outcome = root(adb, command, seconds=30, check=False)
            logs.append(f"===== gpuctl {action} (rc={outcome.returncode}) =====\n{outcome.stdout}")
            if outcome.returncode or not outcome.stdout.rstrip().endswith("ok"):
                raise Blocked(f"gpuctl {action} failed with exit {outcome.returncode}")
        combined = "\n".join(logs)
        if not host_submit_pass(combined.split("===== gpuctl submit")[-1]):
            # capset and submit are both emitted by the submit invocation.
            raise Blocked("cannot prove matching SM8850 DRM capset plus retired, fault-free fence")
        report["HOST_ADRENO"] = "PASS"
    finally:
        report["gpuctl_log"] = "\n".join(logs)
        # Only our unpredictable, path-validated temporary files are removed.
        if pushed:
            cleanup = (f"rm -f '{private}/gpuctl'\nrmdir '{private}' 2>/dev/null || :\n" if staged else "")
            cleanup += f"rm -f '{incoming}'"
            try:
                root(adb, cleanup, seconds=10)
            except Blocked as exc:
                report["cleanup_warning"] = str(exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "host-submit", "analyze"))
    parser.add_argument("--serial", help="authorized USB ADB serial")
    parser.add_argument("--adb", default=shutil.which("adb") or str(Path.home() / "Android/Sdk/platform-tools/adb"))
    parser.add_argument("--gpuctl", type=Path, default=ROOT / "runtime/xnuhost/build/android/gpuctl")
    parser.add_argument("--log", type=Path, help="existing xnuhost log to analyze; no guest launched")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = args.output or ROOT / "out/sm8850/gpu-acceptance" / f"{timestamp}-{args.action}.json"
    report = {"schema_version": 1, "action": args.action,
              "IOS_VULKAN": "UNVERIFIED", "GUI_STABLE": "NOT_EVALUATED", "FRAMEWORK_TAKEOVER": "BLOCKED",
              "scope": "hardware host probe only; no guest boot, watchdog, APFS or sysctl changes"}
    exit_code = 0
    try:
        if args.action == "analyze":
            if not args.log or not args.log.is_file():
                raise Blocked("--analyze requires --log with a readable existing xnuhost log")
            report.update(analyze_guest(args.log.read_text(errors="replace")))
            report["log"] = str(args.log)
            print("IOS_VULKAN=" + report["IOS_VULKAN"])
            print("GUI_STABLE=" + report["GUI_STABLE"])
        else:
            adb = select_usb(args.adb, args.serial)
            report["usb_serial"] = adb[-1]
            hardware(adb, args.gpuctl, report)
            print("PREFLIGHT=" + report["PREFLIGHT"])
            if args.action == "host-submit":
                print("HOST_ADRENO=" + report.get("HOST_ADRENO", "UNVERIFIED"))
            print("IOS_VULKAN=UNVERIFIED (a host GPU submit does NOT verify guest Vulkan)")
    except (Blocked, ValueError) as exc:
        exit_code = 2
        report["error"] = str(exc)
        print("BLOCKED: " + str(exc), file=sys.stderr)
    finally:
        save_report(report_path, report)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
