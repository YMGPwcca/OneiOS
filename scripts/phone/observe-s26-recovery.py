#!/usr/bin/env python3
"""Opt-in passive observation of S26 inputs, USB and the running framework."""

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


IDENTITY = (
    "ro.product.model", "ro.product.device", "ro.soc.model",
    "ro.build.version.release", "ro.build.version.incremental", "ro.build.fingerprint",
)
KEYS = {"up": ("gpio-keys", "KEY_VOLUMEUP"), "down": ("pmic_resin", "KEY_VOLUMEDOWN")}
INPUT_INVENTORY = """
for evt in /sys/class/input/event*; do
    [ -r "$evt/device/name" ] || continue
    name=$(cat "$evt/device/name") || continue
    case "$name" in gpio-keys|pmic_resin) ;; *) continue ;; esac
    bus=$(cat "$evt/device/id/bustype" 2>/dev/null) || bus=unknown
    printf '%s\t%s\t%s\n' "${evt##*/}" "$bus" "$name"
done
exit 0
"""


class ReadUnavailable(Exception):
    pass


def result(status, expected, actual):
    return {"status": status, "expected": expected, "actual": actual}


def physical_sources(inventory):
    candidates = {role: [] for role in KEYS}
    for line in inventory.splitlines():
        fields = line.split("\t", 2)
        if len(fields) != 3:
            continue
        event, bus, name = fields
        if not re.fullmatch(r"event[0-9]+", event):
            continue
        if not re.fullmatch(r"[0-9a-f]{4}", bus) or bus in {"0003", "0005", "0006"}:
            continue
        for role, (expected, key) in KEYS.items():
            if name == expected:
                candidates[role].append(
                    {"node": f"/dev/input/{event}", "name": name, "bus": bus, "key": key}
                )
    if any(len(matches) != 1 for matches in candidates.values()):
        raise ReadUnavailable("Expected one gpio-keys node and one pmic_resin node with readable non-HID bus metadata")
    selected = {role: matches[0] for role, matches in candidates.items()}
    if selected["up"]["node"] == selected["down"]["node"]:
        raise ReadUnavailable("Both roles resolved to the same input node")
    return selected


def key_state(output, key):
    in_keys = False
    for line in output.splitlines():
        row = re.match(r"\s*([A-Z?]+)\s+\([0-9a-fA-F]+\):\s*(.*)", line)
        if row:
            in_keys = row[1] == "KEY"
            line = row[2]
        elif ":" in line:
            in_keys = False
        if in_keys:
            words = line.split()
            if key + "*" in words:
                return True
            if key in words:
                return False
    raise ReadUnavailable(f"getevent did not report {key} in the selected device's key capabilities")


def longest_observed_hold(samples):
    # Each sample contains two reads. Measure between the end of the first
    # pair and the start of the last pair, and reset when a sample is missing.
    start = None
    previous = None
    longest = 0.0
    for sample in samples:
        if previous is not None and sample["end_s"] - previous["start_s"] > 0.75:
            start = None
        if not (sample["up"] and sample["down"]) or sample["end_s"] - sample["start_s"] > 0.5:
            start = None
        elif start is None:
            start = sample["end_s"]
        else:
            longest = max(longest, sample["start_s"] - start)
        previous = sample
    return round(longest, 3)


def capture(serial, seconds, root_input, *, run=subprocess.run, on_sampling=lambda: None):
    data = {
        "schema_version": 1, "scope": "physical-passive",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "observer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "firmware": None, "inputs": {}, "usb": {}, "framework": {}, "samples": [],
        "checks": {
            "gates_abc": result("BLOCKED", "Independent physical recovery acceptance",
                                "Observer only reads One UI while it is running"),
            "watchdog": result("BLOCKED", "Matched driver and physical watchdog handoff",
                               "Observer does not access watchdog devices"),
            "chord": result("BLOCKED", "At least 3 s of sampled physical chord",
                            "No key-state sampling completed"),
        },
    }
    checks = data["checks"]

    def adb(*args, stdin=None):
        try:
            response = run(["adb", "-s", serial, *args], input=stdin,
                           text=True, capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReadUnavailable(f"{' '.join(args[:2])}: {type(error).__name__}") from error
        if response.returncode:
            raise ReadUnavailable(f"{' '.join(args[:2])} exited {response.returncode}")
        return response.stdout.strip()

    def input_call(*args, stdin=None):
        if root_input:
            command = shlex.join(args)
            return adb("shell", "su -c " + shlex.quote(command), stdin=stdin)
        return adb("shell", *args, stdin=stdin)

    try:
        if adb("get-state") != "device":
            raise ReadUnavailable("ADB did not report an authorized device")
        model, device, soc, android, build, fingerprint = (adb("shell", "getprop", key) for key in IDENTITY)
        data["firmware"] = {
            "model": model, "device": device, "soc": soc, "android": android,
            "build": build, "fingerprint": fingerprint,
        }
    except ReadUnavailable as error:
        checks["target"] = result("BLOCKED", "Authorized SM-S948B/m3q/SM8850 on Android 17", str(error))
        return data
    expected = ("SM-S948B", "m3q", "SM8850", "17")
    actual = (model, device, soc, android)
    checks["target"] = result("PASS" if actual == expected else "FAIL", expected, actual)
    if actual != expected:
        return data
    try:
        data["firmware"]["kernel"] = adb("shell", "uname", "-r")
        checks["fingerprint"] = result("PASS" if fingerprint else "BLOCKED", "Readable build fingerprint", fingerprint)
    except ReadUnavailable as error:
        checks["fingerprint"] = result("BLOCKED", "Readable build fingerprint and kernel", str(error))

    try:
        usb = data["usb"]
        usb["transport"] = "usb" if adb("get-devpath").startswith("usb:") else "unverified"
        for prop in ("sys.usb.config", "sys.usb.state", "sys.usb.controller", "init.svc.adbd"):
            usb[prop] = adb("shell", "getprop", prop)
        controller = usb["sys.usb.controller"]
        if re.fullmatch(r"[A-Za-z0-9_.:-]+", controller) and controller not in {".", ".."}:
            usb["udc_state"] = adb("shell", "cat", f"/sys/class/udc/{controller}/state")
        present = usb["transport"] == "usb" and usb["init.svc.adbd"] == "running"
        checks["usb_adb"] = result("PASS" if present else "BLOCKED", "ADB attached over USB while One UI runs", usb)
    except ReadUnavailable as error:
        checks["usb_adb"] = result("BLOCKED", "Readable USB and ADB status", str(error))

    try:
        framework = data["framework"]
        for prop in ("init.svc.zygote", "sys.boot_completed"):
            framework[prop] = adb("shell", "getprop", prop)
        try:
            framework["system_server_present"] = bool(re.fullmatch(r"[0-9]+(?:\s+[0-9]+)*",
                                                                   adb("shell", "pidof", "system_server")))
        except ReadUnavailable:
            framework["system_server_present"] = None
        ready = (framework["init.svc.zygote"] == "running" and
                 framework["sys.boot_completed"] == "1" and framework["system_server_present"] is True)
        checks["framework"] = result("PASS" if ready else "BLOCKED", "Running One UI framework", framework)
    except ReadUnavailable as error:
        checks["framework"] = result("BLOCKED", "Readable framework status", str(error))

    def read_keys():
        # Node names are generated exclusively from the validated event indices.
        return {role: key_state(input_call("getevent", "-pl", meta["node"]), meta["key"])
                for role, meta in data["inputs"].items()}

    try:
        data["inputs"] = physical_sources(input_call("sh", "-s", stdin=INPUT_INVENTORY))
        read_keys()
        checks["physical_sources"] = result("PASS", "Two physical sources expose their respective keys", data["inputs"])
    except ReadUnavailable as error:
        checks["physical_sources"] = result("BLOCKED", "Readable, unambiguous physical input sources", str(error))
        return data
    if not seconds or checks["framework"]["status"] != "PASS":
        return data

    on_sampling()
    origin = time.monotonic()
    try:
        while time.monotonic() - origin < seconds:
            start = time.monotonic() - origin
            states = read_keys()
            end = time.monotonic() - origin
            data["samples"].append({"start_s": round(start, 4), "end_s": round(end, 4), **states})
            time.sleep(max(0, min(seconds - end, 0.2 - (end - start))))
        held = longest_observed_hold(data["samples"])
        checks["chord"] = result("PASS" if held >= 3 else "BLOCKED",
                                 "At least 3 s of sampled physical chord",
                                 {"hold_s": held, "samples": len(data["samples"])})
    except ReadUnavailable as error:
        checks["chord"] = result("BLOCKED", "Complete bounded sample of both keys", str(error))
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Select one already authorized ADB transport")
    parser.add_argument("--seconds", type=int, default=0, choices=range(0, 21), metavar="0..20",
                        help="Duration of passive sampling. Zero performs a snapshot")
    parser.add_argument("--root-input", action="store_true", help="Use existing su access only for input reads")
    parser.add_argument("--output", required=True, type=Path, help="New local JSON evidence file")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_:.%\[\]-]+", args.serial) or args.serial.startswith("-"):
        parser.error("invalid ADB serial")
    def prompt():
        print("Sampling now. Hold only Volume Up and Volume Down together for 4–5 seconds, then release.",
              flush=True)
    # Exclusive creation prevents overwriting earlier evidence. The output path
    # is local and never appears in a device command.
    with args.output.open("x") as output:
        data = capture(args.serial, args.seconds, args.root_input, on_sampling=prompt)
        json.dump(data, output, indent=2)
        output.write("\n")
    for name, check in data["checks"].items():
        print(f"{name}\t{check['status']}")
    print(args.output)
    return 0 if data["checks"]["target"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
