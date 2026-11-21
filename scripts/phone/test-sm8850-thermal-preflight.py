#!/usr/bin/env python3
"""Offline-only thermal preflight regression tests; never contact a phone."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("thermal_preflight", Path(__file__).with_name("sm8850-thermal-preflight.py"))
PREFLIGHT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREFLIGHT)
BOOT = "123e4567-e89b-12d3-a456-426614174000"


class ThermalPreflightTests(unittest.TestCase):
    def test_only_approved_android_service_and_fixed_kernel_reads(self):
        all_commands = [cmd for _, cmd in PREFLIGHT.READS] + [PREFLIGHT.THERMAL, PREFLIGHT.BATTERY]
        self.assertIn(("shell", "dumpsys", "thermalservice"), all_commands)
        for command in all_commands:
            joined = " ".join(command)
            for forbidden in ("su ", "/sys/class/", "/sys/devices/", "/dev/watchdog", "setprop", "reboot", "stop", "kill", "mount", "find "):
                self.assertNotIn(forbidden, joined)

    def test_parse_only_current_hal_temperatures(self):
        raw = "Old event mValue=91, mType=3, mName=SKIN\nCurrent temperatures from HAL:\n  Temperature{mValue=41.2, mType=3, mName=SKIN, mStatus=2}\n  Temperature{mValue=NaN, mType=1, mName=CPU}\nCurrent cooling devices from HAL:\n  CoolingDevice{mValue=75, mType=2, mName=GPU}\n"
        self.assertEqual([{"name": "SKIN", "type": 3, "celsius": 41.2}], PREFLIGHT.parse_current_thermal(raw))
        self.assertEqual([], PREFLIGHT.parse_current_thermal("Current temperatures unavailable"))

    def test_single_device_required(self):
        self.assertEqual(["ABC123"], PREFLIGHT.device_serials("List of devices attached\nABC123\tdevice product:a\nXYZ\toffline\n"))
        self.assertEqual([], PREFLIGHT.device_serials("List of devices attached\nABC\tunauthorized\n"))

    def test_refuses_wrong_firmware_before_dumpsys_and_file_write(self):
        values = {"model": PREFLIGHT.MODEL, "device": PREFLIGHT.DEVICE,
                  "firmware": "WRONG", "boot_completed": "1", "selinux": "Enforcing",
                  "system_server": "234", "boot_id": BOOT, "uptime": "10.0 2.0"}
        def fake(_adb, _serial, command, timeout=12):
            for key, cmd in PREFLIGHT.READS:
                if command == cmd:
                    return values[key]
            raise AssertionError("No dumpsys allowed on invalid device")
        with tempfile.TemporaryDirectory() as tmp, patch.object(PREFLIGHT, "adb_call", side_effect=fake):
            with self.assertRaisesRegex(RuntimeError, "no sensor query was issued"):
                PREFLIGHT.capture("adb", "ABC123", Path(tmp))
            self.assertEqual([], list(Path(tmp).iterdir()))

    def test_normal_collection_cannot_be_called_accepted(self):
        values = {"model": PREFLIGHT.MODEL, "device": PREFLIGHT.DEVICE,
                  "firmware": PREFLIGHT.FIRMWARE, "boot_completed": "1", "selinux": "Enforcing",
                  "system_server": "234", "boot_id": BOOT, "uptime": "10.0 2.0"}
        calls = []
        def fake(_adb, _serial, command, timeout=12):
            calls.append(command)
            for key, cmd in PREFLIGHT.READS:
                if command == cmd:
                    return values[key]
            if command == PREFLIGHT.THERMAL:
                return "Current temperatures from HAL:\n mValue=37.3, mType=3, mName=SKIN\n"
            if command == PREFLIGHT.BATTERY:
                return "temperature: 373\n"
            if command == ("shell", "cat", "/proc/sys/kernel/random/boot_id"):
                return BOOT
            raise AssertionError(command)
        with tempfile.TemporaryDirectory() as tmp, patch.object(PREFLIGHT, "adb_call", side_effect=fake):
            output, data = PREFLIGHT.capture("adb", "ABC123", Path(tmp))
            self.assertEqual("NOT_QUALIFIED", data["acceptance"])
            self.assertEqual("PASSIVE_ONE_UI_HAL_PREFLIGHT_NOT_GUARD_ACCEPTANCE", data["kind"])
            self.assertEqual(1, len(data["temperatures"]))
            self.assertEqual(1, calls.count(PREFLIGHT.THERMAL))
            self.assertTrue((output / "summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
