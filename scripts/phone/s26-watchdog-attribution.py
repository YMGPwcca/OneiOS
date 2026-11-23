#!/usr/bin/env python3
"""Attribute the existing S26 watchdog holder using read-only metadata."""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


PAYLOAD = Path(__file__).with_name("s26-watchdog-metadata.sh")
PROPERTIES = (
    "ro.product.model", "ro.product.device", "ro.soc.model",
    "ro.build.version.release", "ro.build.version.incremental", "ro.build.fingerprint",
)
TARGET = ("SM-S948B", "m3q", "SM8850", "17", "S948BXXS4BZIG")
KERNEL = "6.12.69-android16-6-pb4d3caf-abogkiS948BXXS4BZIG-4k"
ROW_WIDTH = {
    "error": 1, "owner": 2, "fd": 5, "framework": 2, "selinux": 1, "cgroup_kill": 1,
    "boot_id_sha256": 1, "node": 2, "char_link": 3, "class": 3, "class_link": 3,
    "attribute": 3, "config_available": 1, "config": 1, "bootarg": 1, "module": 2,
    "module_note": 2, "module_metadata": 3, "module_parameter": 3, "module_sha256": 3,
    "kernel_notes_sha256": 1, "kernel_notes": 1, "symbol": 2, "log": 2, "log_matches": 2, "complete": 1,
}


def parse_rows(payload):
    rows = defaultdict(list)
    for line in payload.splitlines():
        name, *items = line.split("\t")
        if name in ROW_WIDTH and len(items) == ROW_WIDTH[name]:
            rows[name].append([item.strip() for item in items])
    return dict(rows)


def gnu_build_id(encoded):
    try:
        raw = bytes.fromhex(encoded)
    except ValueError:
        return None
    offset = 0
    while len(raw) - offset >= 12:
        count, size, kind = struct.unpack_from("<III", raw, offset)
        name_start = offset + 12
        value_start = name_start + ((count + 3) & ~3)
        if value_start + size > len(raw):
            return None
        if count == 4 and raw[name_start:name_start + count] == b"GNU\0" and kind == 3 and 1 <= size <= 64:
            return raw[value_start:value_start + size].hex()
        offset = value_start + ((size + 3) & ~3)
    return None


def check(status, confidence, actual):
    return {"status": status, "confidence": confidence, "actual": actual}


def classify(rows):
    owner = rows.get("owner", [])
    fds = rows.get("fd", [])
    nodes = dict(rows.get("node", []))
    classes = {name: (rdev, path) for name, rdev, path in rows.get("class", [])}
    stable = len(owner) == 1 and owner[0][0].isdigit() and owner[0][1] == "stable"
    held = stable and len(fds) == 1 and re.fullmatch(r"[0-9]+:[0-9]+", fds[0][1])
    matched = held and nodes.get(fds[0][2]) == fds[0][1]
    # A runtime module link has weight only when joined through the held rdev,
    # never through a guessed legacy-misc to numbered-watchdog alias.
    direct = sorted({
        path for rdev, part, path in rows.get("char_link", [])
        if matched and rdev == fds[0][1] and part.endswith("/driver/module")
        and re.fullmatch(r"/sys/module/[A-Za-z0-9_]+", path)
    })
    node0 = classes.get("watchdog0", (None, None))[0]
    alias_candidate = bool(matched and fds[0][1] == classes.get("misc", (None, None))[0]
                           and node0 and nodes.get("/dev/watchdog0") == node0
                           and node0 != fds[0][1])
    loaded = {name for name, _ in rows.get("module", [])}
    logs = {kind for kind, _ in rows.get("log", [])}
    collector_checks = {
        "existing_owner": check("PASS" if matched else "BLOCKED", "high" if matched else "unresolved",
                                {"owner": owner, "watchdog_fds": fds, "node_rdev_matches": bool(matched)}),
        "same_endpoint_alias": check("BLOCKED", "unresolved",
                                     {"legacy_and_numbered_candidate": alias_candidate, "classes": classes}),
        "endpoint_driver": check("BLOCKED", "unresolved", {
            "direct_parent_module_links": direct,
            "reason": "Parent links and loaded modules do not identify the registered watchdog operations",
        }),
        "runtime_semantics": check("BLOCKED", "unresolved",
                                   "Exact-build registration, operations, timeout, close and reset behavior require review"),
        "softdog_present": check("PASS" if "softdog" in loaded else "BLOCKED", "high" if "softdog" in loaded else "unresolved",
                                 "Loaded Linux software-watchdog component; holder attribution is independent"),
        "qualcomm_soc_activity": check("PASS" if "soc" in logs else "BLOCKED",
                                       "high" if "soc" in logs else "unresolved",
                                       "Filtered kernel log evidence; pet interval does not identify the held endpoint or its timeout"),
        "max77775_charger_implementation": check(
            "PASS" if ["max77775_chg_set_wdtmr_kick", "[max77775_charger]"] in rows.get("symbol", []) else "BLOCKED",
            "high" if "max77775_charger" in loaded else "unresolved",
            "Charger-module timer kick; no link to the system watchdog character endpoint"),
        "max77775_charger_activity": check("PASS" if "charger" in logs else "BLOCKED",
                                          "high" if "charger" in logs else "unresolved",
                                          "Presence of timer symbols alone does not establish active charger kicks"),
        "source_provenance": check("BLOCKED", "unresolved", "No exact Samsung source archive verified by this collector"),
        "live_acceptance": check("BLOCKED", "unresolved", "Physical handoff and Gates A/B/C are outside passive observation"),
    }
    return collector_checks


def capture(serial, *, run=subprocess.run):
    payload = PAYLOAD.read_text()
    data = {
        "schema_version": 1, "scope": "physical-passive",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "identity": {}, "metadata": {}, "module_build_ids": {},
        "checks": {"live_acceptance": check("BLOCKED", "unresolved", "Passive observation only")},
    }

    def adb(*args, stdin=None, timeout=8):
        response = run(["adb", "-s", serial, *args], input=stdin, text=True, errors="replace",
                       capture_output=True, timeout=timeout)
        if response.returncode:
            raise RuntimeError(f"{' '.join(args[:2])} exited {response.returncode}")
        return response.stdout

    checks = data["checks"]
    try:
        if adb("get-state").strip() != "device" or not adb("get-devpath").strip().startswith("usb:"):
            raise RuntimeError("An already authorized USB ADB connection is required")
        values = [adb("shell", "getprop", prop).strip() for prop in PROPERTIES]
        kernel = adb("shell", "uname", "-r").strip()
        data["identity"] = dict(zip(PROPERTIES, values)) | {"kernel": kernel, "transport": "usb"}
        if tuple(values[:5]) != TARGET or kernel != KERNEL:
            checks["target"] = check("FAIL", "high", "Model, firmware or kernel does not match the acceptance target")
            return data
        checks["target"] = check("PASS", "high", "Exact SM-S948B firmware and kernel on authorized USB")
        raw = adb("shell", "su -c '/system/bin/sh -s'", stdin=payload, timeout=45)
        rows = parse_rows(raw)
        if rows.get("complete") != [["yes"]]:
            raise RuntimeError("Metadata snapshot did not complete")
        data["metadata"] = rows
        data["module_build_ids"] = {name: gnu_build_id(note) for name, note in rows.get("module_note", [])}
        notes = rows.get("kernel_notes", [])
        data["kernel_build_id"] = gnu_build_id(notes[0][0]) if len(notes) == 1 else None
        checks.update(classify(rows))
        checks["metadata_collection"] = check("PASS", "high", "Bounded read-only snapshot completed")
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        checks.setdefault("target", check("BLOCKED", "unresolved", str(error)))
        checks["metadata_collection"] = check("BLOCKED", "unresolved", str(error))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Already authorized USB ADB transport with existing su authorization")
    parser.add_argument("--output", required=True, type=Path, help="New local JSON file")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_.][A-Za-z0-9_.:-]+", args.serial):
        parser.error("invalid ADB serial")
    with args.output.open("x") as report:
        data = capture(args.serial)
        json.dump(data, report, indent=2)
        report.write("\n")
    for name, record in data["checks"].items():
        print(f"{record['status']}\t{name}")
    print(args.output)
    return 0 if data["checks"].get("metadata_collection", {}).get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
