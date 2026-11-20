#!/usr/bin/env python3
"""Read exactly three previously documented SM8850 Samsung thermal nodes.

One UI must be fully booted and firmware must match. Default is unprivileged;
--allow-root optionally retries only the same three named cat reads as root.
Never scan sysfs, stop Framework, write, reboot or open a watchdog device.

This is correlation evidence, NOT an independent over-temperature guard.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import uuid


PREFLIGHT_FILE = Path(__file__).with_name("sm8850-thermal-preflight.py")
SPEC = importlib.util.spec_from_file_location("sm8850_thermal_preflight", PREFLIGHT_FILE)
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)

# Audited in runtime/bridges/thermal/thermal.c and README.md.
# Units on this Samsung backend: deci-degrees C (value / 10).
NODES = (
    ("battery", "/sys/class/power_supply/battery/temp"),
    ("lrp", "/sys/class/power_supply/battery/lrp"),
    ("board_ap", "/sys/class/sec/sec-ap-thermistor/temperature"),
)


def identity_check(adb, serial):
    identity = {name: PREFLIGHT.adb_call(adb, serial, argv).strip()
                for name, argv in PREFLIGHT.READS}
    required = (
        ("model", PREFLIGHT.MODEL),
        ("device", PREFLIGHT.DEVICE),
        ("firmware", PREFLIGHT.FIRMWARE),
        ("boot_completed", "1"),
        ("selinux", "Enforcing"),
    )
    failures = [f"{key} mismatch" for key, expected in required
                if identity[key] != expected]
    if not re.fullmatch(r"[0-9]+(?:\s+[0-9]+)*", identity["system_server"]):
        failures.append("system_server is not running")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", identity["boot_id"]):
        failures.append("invalid boot ID")
    if failures:
        raise RuntimeError("BLOCKED before thermal/kernel reads: " + ", ".join(failures))
    return identity


def read_named_node(adb, serial, name, path, allow_root=False):
    # No variable paths come from the operator or the device.
    assert (name, path) in NODES
    commands = [("shell", "cat", path)]
    if allow_root:
        commands.append(("shell", "su", "-c", "/system/bin/cat " + path))
    errors = []
    for index, argv in enumerate(commands):
        try:
            text = PREFLIGHT.adb_call(adb, serial, argv, timeout=12).strip()
        except (OSError, RuntimeError) as exc:
            errors.append(str(exc)[:200])
            continue
        if not re.fullmatch(r"[+-]?\d+", text):
            return {"status": "MALFORMED", "raw": text[:80]}
        raw = int(text)
        if not -400 <= raw <= 2000:
            return {"status": "OUT_OF_RANGE", "raw": raw}
        return {"status": "READ", "raw_deci_celsius": raw, "celsius": raw / 10,
                "method": "root_named_cat" if index else "shell_named_cat"}
    return {"status": "UNAVAILABLE", "errors": errors}


def correlate(hal, nodes):
    def hal_value(name, type_id):
        matches = [t["celsius"] for t in hal
                   if t["name"].upper() == name and t["type"] == type_id]
        return matches[0] if len(matches) == 1 else None

    # Android HAL "AP" is TemperatureType.CPU, NOT Samsung's board AP thermistor.
    # A small temperature difference does not prove the paths are equivalent.
    references = {"battery": hal_value("BAT", 2), "lrp": hal_value("SKIN", 3)}
    comparisons = {}
    for name, reference in references.items():
        reading = nodes[name]
        comparisons[name] = {
            "hal_label": "BAT" if name == "battery" else "SKIN",
            "hal_celsius": reference,
            "kernel_celsius": reading.get("celsius"),
            "abs_difference_celsius": (round(abs(reference - reading["celsius"]), 2)
                                       if reference is not None and reading["status"] == "READ" else None),
            "proves_same_physical_sensor": False,
        }
    suspect = [{"name": t["name"], "reason": "zero-valued SUBBAT may be absent/placeholder"}
               for t in hal if t["name"].upper() == "SUBBAT"
               and t["type"] == 2 and t["celsius"] == 0]
    return comparisons, suspect


def capture(adb, serial, destination_base, allow_root=False):
    identity = identity_check(adb, serial)
    thermal = PREFLIGHT.adb_call(adb, serial, PREFLIGHT.THERMAL, timeout=20)
    hal = PREFLIGHT.parse_current_thermal(thermal)
    if not hal:
        raise RuntimeError("No current HAL temperatures; no matching evidence")
    nodes = {name: read_named_node(adb, serial, name, path, allow_root)
             for name, path in NODES}
    final_boot = PREFLIGHT.adb_call(
        adb, serial, ("shell", "cat", "/proc/sys/kernel/random/boot_id")
    ).strip()
    if final_boot != identity["boot_id"]:
        raise RuntimeError("Boot changed during sampling; discarding mixed-boot evidence")
    comparisons, suspect = correlate(hal, nodes)
    report = {
        "schema": 1, "kind": "SM8850_TARGETED_KERNEL_SENSOR_CORRELATION_NOT_GUARD",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "adb_serial_sha256_16": hashlib.sha256(serial.encode()).hexdigest()[:16],
        "identity": identity, "hal_temperatures": hal,
        "kernel_sensor_nodes": nodes, "comparisons": comparisons,
        "suspect_hal_readings": suspect,
        "root_fallback_opted_in": allow_root,
        "kernel_read_scope": [path for _, path in NODES],
        "acceptance": "NOT_QUALIFIED",
        "physical_sensor_equivalence_verified": False,
        "independent_guard_implemented": False,
        "watchdog_opened": False, "device_modified": False,
    }
    output = destination_base / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    (output / "thermalservice.txt").write_text(thermal, encoding="utf-8")
    (output / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for filename in ("thermalservice.txt", "summary.json"):
        (output / filename).chmod(0o600)
    return output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default=None)
    parser.add_argument("--serial")
    parser.add_argument("--output", type=Path, default=Path("out/sm8850/thermal-known-nodes"))
    parser.add_argument("--allow-root", action="store_true",
                        help="explicitly allow root retries of only the three hardcoded named files")
    parser.add_argument("--print-commands", action="store_true")
    options = parser.parse_args()
    adb = options.adb or shutil.which("adb") or str(Path.home() / "Android/Sdk/platform-tools/adb")
    if options.print_commands:
        for _, argv in PREFLIGHT.READS:
            print("adb shell " + " ".join(argv[1:]))
        print("adb shell dumpsys thermalservice")
        for _, path in NODES:
            print("adb shell cat " + path)
            if options.allow_root:
                print("adb shell su -c '/system/bin/cat " + path + "' (retry on failure only)")
        print("adb shell cat /proc/sys/kernel/random/boot_id")
        return 0
    try:
        serial = options.serial
        if not serial:
            connected = PREFLIGHT.device_serials(PREFLIGHT.adb_call(adb, None, ("devices",)))
            if len(connected) != 1:
                raise RuntimeError(f"Need exactly one authorised ADB device, got {len(connected)}; use --serial")
            serial = connected[0]
        output, report = capture(adb, serial, options.output, options.allow_root)
    except (RuntimeError, OSError) as exc:
        print(f"SM8850_KNOWN_NODES=BLOCKED: {exc}", file=sys.stderr)
        return 2
    for name, path in NODES:
        reading = report["kernel_sensor_nodes"][name]
        print(f"{name.upper()}={reading['status']}" +
              (f" {reading['celsius']:.1f}C via {reading['method']}" if reading["status"] == "READ" else ""))
    print(f"SM8850_KNOWN_NODES=EVIDENCE_ONLY_NOT_QUALIFIED\nOUTPUT={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
