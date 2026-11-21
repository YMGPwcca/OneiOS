#!/usr/bin/env python3
"""Passive SM8850 thermal preflight while stock One UI is running.

No root, sysfs probing, firmware writes, guest launches or watchdog access.
This produces HAL evidence only; it does NOT qualify an independent guard.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

MODEL = "SM-S948B"
DEVICE = "m3q"
FIRMWARE = "S948BXXS4BZIG"
READS = (
    ("model", ("shell", "getprop", "ro.product.model")),
    ("device", ("shell", "getprop", "ro.product.device")),
    ("firmware", ("shell", "getprop", "ro.build.version.incremental")),
    ("boot_completed", ("shell", "getprop", "sys.boot_completed")),
    ("selinux", ("shell", "getenforce")),
    ("system_server", ("shell", "pidof", "system_server")),
    ("boot_id", ("shell", "cat", "/proc/sys/kernel/random/boot_id")),
    ("uptime", ("shell", "cat", "/proc/uptime")),
)
THERMAL = ("shell", "dumpsys", "thermalservice")
BATTERY = ("shell", "dumpsys", "battery")
TEMP = re.compile(r"mValue\s*=\s*(?P<value>[^,}\s]+).*?mType\s*=\s*(?P<type>\d+).*?mName\s*=\s*(?P<name>[^,}]+)")


def device_serials(devices_output):
    """Only explicitly connected and authorised USB/TCP ADB devices count."""
    result = []
    for line in devices_output.splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            result.append(fields[0])
    return result


def parse_current_thermal(text):
    """Parse current HAL readings, not old event/history lines."""
    marker = "Current temperatures from HAL:"
    if marker not in text:
        return []
    current = text.split(marker, 1)[1].split("Current cooling devices from HAL:", 1)[0]
    values = []
    for line in current.splitlines():
        match = TEMP.search(line)
        if not match:
            continue
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        if not math.isfinite(value):
            continue
        values.append({"name": match.group("name").strip(), "type": int(match.group("type")), "celsius": value})
    return values


def adb_call(adb, serial, args, timeout=12):
    command = [adb] + (["-s", serial] if serial else []) + list(args)
    result = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout, check=False)
    if result.returncode:
        message = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"ADB command {args!r} failed (code {result.returncode}): {message[:250]}")
    return result.stdout


def capture(adb, serial, output_base):
    # Refuse to run if Android's stock framework cannot be positively established.
    identity = {}
    for key, args in READS:
        identity[key] = adb_call(adb, serial, args).strip()
    failures = []
    for key, expected in (("model", MODEL), ("device", DEVICE), ("firmware", FIRMWARE),
                          ("boot_completed", "1"), ("selinux", "Enforcing")):
        if identity[key] != expected:
            failures.append(f"{key}: expected {expected!r}, got {identity[key]!r}")
    if not re.fullmatch(r"[0-9]+(?:\s+[0-9]+)*", identity["system_server"]):
        failures.append("Android system_server not positively identified")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", identity["boot_id"]):
        failures.append("No valid boot_id")
    if failures:
        raise RuntimeError("Preflight BLOCKED; no sensor query was issued: " + "; ".join(failures))

    thermal = adb_call(adb, serial, THERMAL, timeout=20)
    battery = adb_call(adb, serial, BATTERY, timeout=12)
    temperatures = parse_current_thermal(thermal)
    # Bind this passive snapshot to one boot without claiming a session token.
    final_boot = adb_call(adb, serial, ("shell", "cat", "/proc/sys/kernel/random/boot_id")).strip()
    if final_boot != identity["boot_id"]:
        raise RuntimeError("Boot ID changed during survey; rejecting mixed-boot evidence")

    destination = output_base / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    files = {"thermalservice.txt": thermal, "battery.txt": battery}
    manifest = {"schema": 1, "kind": "PASSIVE_ONE_UI_HAL_PREFLIGHT_NOT_GUARD_ACCEPTANCE",
                "captured_utc": datetime.now(timezone.utc).isoformat(),
                "adb_serial_sha256_16": hashlib.sha256(serial.encode("utf-8")).hexdigest()[:16],
                "identity": identity, "temperatures": temperatures,
                "has_skin": any("skin" in t["name"].lower() for t in temperatures),
                "raw_sha256": {name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                               for name, content in files.items()},
                "acceptance": "NOT_QUALIFIED", "touches_sysfs": False,
                "opens_watchdog": False, "modifies_device": False}
    for name, content in files.items():
        (destination / name).write_text(content, encoding="utf-8")
        (destination / name).chmod(0o600)
    (destination / "summary.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (destination / "summary.json").chmod(0o600)
    return destination, manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--adb", default=None, help="path to adb executable")
    ap.add_argument("--serial", help="ADB serial; required if multiple devices are connected")
    ap.add_argument("--output", type=Path, default=Path("out/sm8850/thermal-preflight"))
    ap.add_argument("--print-commands", action="store_true", help="show the strictly read-only ADB operations; do not contact any device")
    args = ap.parse_args()
    adb = args.adb or shutil.which("adb") or str(Path.home() / "Android/Sdk/platform-tools/adb")
    if args.print_commands:
        for _, cmd in READS:
            print("adb shell " + " ".join(cmd[1:]))
        for cmd in (THERMAL, BATTERY, ("shell", "cat", "/proc/sys/kernel/random/boot_id")):
            print("adb shell " + " ".join(cmd[1:]))
        return 0
    try:
        serial = args.serial
        if not serial:
            devices = device_serials(adb_call(adb, None, ("devices",)))
            if len(devices) != 1:
                raise RuntimeError(f"Expected exactly one authorised ADB device, got {len(devices)}; use --serial")
            serial = devices[0]
        output, report = capture(adb, serial, args.output)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"THERMAL_PREFLIGHT=BLOCKED: {exc}", file=sys.stderr)
        return 2
    print(f"THERMAL_PREFLIGHT=COLLECTED_NOT_QUALIFIED\nOUTPUT={output}\nREADINGS={len(report['temperatures'])}\nSKIN_OBSERVED={report['has_skin']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
