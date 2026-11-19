#!/usr/bin/env python3
"""Offline tests for the passive watchdog collector and evidence classifier."""

import importlib.util
from pathlib import Path
import struct
import subprocess
import unittest


spec = importlib.util.spec_from_file_location(
    "collector", Path(__file__).with_name("s26-watchdog-attribution.py")
)
collector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collector)


class AttributionTests(unittest.TestCase):
    def test_payload_is_valid_shell_and_has_no_device_content_operation(self):
        payload = collector.PAYLOAD.read_text()
        check = subprocess.run(["/bin/sh", "-n"], text=True, input=payload, capture_output=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        for forbidden in ("wdctl", "ioctl ", "setprop ", "ctl.stop", "oneios_switch.sh",
                          "oneios_return.sh", "\nreboot ", "\nkill ", "adb push"):
            self.assertNotIn(forbidden, payload)
        self.assertIn('stat -Lc', payload)
        self.assertIn('"/proc/$pid/fdinfo/', payload)
        self.assertNotRegex(payload, r'(?:cat|head|dd|od|sha256sum) [^\n]*(?:/dev/watchdog|\$fd")')

    def test_alias_candidates_do_not_prove_shared_device_or_driver(self):
        rows = collector.parse_rows(
            "owner\t2031\tstable\n"
            "fd\t28\t10:130\t/dev/watchdog\t42\t0100001\n"
            "class\tmisc\t10:130\t/sys/devices/virtual/misc/watchdog\n"
            "class\twatchdog0\t242:0\t/sys/devices/virtual/watchdog/watchdog0\n"
            "node\t/dev/watchdog\t10:130\n"
            "node\t/dev/watchdog0\t242:0\n"
            "module\tsoftdog\tlisted\n"
            "module\tqcom_soc_wdt\tlisted\n"
            "log\tsoftdog\t[ 2.0] softdog: initialized\n"
            "log\tsoc\t[ 3.0] msm_watchdog_data: pet 9472\n"
            "log\tcharger\t[ 4.0] max77775_chg_set_wdtmr_kick\n"
        )
        checks = collector.classify(rows)
        self.assertEqual(checks["existing_owner"]["status"], "PASS")
        self.assertEqual(checks["endpoint_driver"]["status"], "BLOCKED")
        self.assertEqual(checks["same_endpoint_alias"]["status"], "BLOCKED")
        self.assertEqual(checks["runtime_semantics"]["status"], "BLOCKED")

    def test_owner_race_and_no_fd_are_blocked(self):
        for payload in (
            "owner\t2031\tchanged\nfd\t28\t10:130\t/dev/watchdog\t42\t0100001\n",
            "owner\t2031\tstable\n",
            "owner\t2031\tstable\nfd\t28\t10:130\t/dev/watchdog\t42\t0100001\n"
            "fd\t29\t242:1\t/dev/watchdog1\t43\t0100001\n",
        ):
            with self.subTest(payload=payload):
                self.assertEqual(collector.classify(collector.parse_rows(payload))["existing_owner"]["status"], "BLOCKED")

    def test_gnu_build_id_note_rejects_bad_header_and_truncation(self):
        desc = bytes.fromhex("12" * 20)
        note = struct.pack("<III", 4, len(desc), 3) + b"GNU\x00" + desc
        self.assertEqual(collector.gnu_build_id(note.hex()), desc.hex())
        other = struct.pack("<III", 6, 3, 0) + b"Linux\x00\x00\x00" + b"abc\x00"
        self.assertEqual(collector.gnu_build_id((other + note).hex()), desc.hex())
        for bad in (note[:-1].hex(), (note[:12] + b"BAD\x00" + desc).hex(), "unknown", ""):
            self.assertIsNone(collector.gnu_build_id(bad))

    def test_wrong_firmware_never_runs_privileged_payload(self):
        calls = []

        def fake(args, **kwargs):
            calls.append(args[3:])
            values = ["SM-S948B", "m3q", "SM8850", "17", "other-build", "fingerprint"]
            if args[3:] == ["get-state"]:
                value = "device"
            elif args[3:] == ["get-devpath"]:
                value = "usb:fixture"
            elif args[3:] == ["shell", "uname", "-r"]:
                value = collector.KERNEL
            else:
                value = values[collector.PROPERTIES.index(args[-1])]
            return subprocess.CompletedProcess(args, 0, value + "\n", "")

        result = collector.capture("fixture", run=fake)
        self.assertEqual(result["checks"]["target"]["status"], "FAIL")
        self.assertNotIn(["shell", "su -c '/system/bin/sh -s'"], calls)

    def test_matching_firmware_uses_only_the_fixed_metadata_payload(self):
        calls = []

        def fake(args, **kwargs):
            calls.append((args[3:], kwargs.get("input")))
            tail = args[3:]
            if tail == ["get-state"]:
                value = "device"
            elif tail == ["get-devpath"]:
                value = "usb:fixture"
            elif tail == ["shell", "uname", "-r"]:
                value = collector.KERNEL
            elif tail[:2] == ["shell", "getprop"] and tail[-1] in collector.PROPERTIES:
                value = (*collector.TARGET, "fingerprint")[collector.PROPERTIES.index(tail[-1])]
            else:
                self.assertEqual(tail, ["shell", "su -c '/system/bin/sh -s'"])
                self.assertEqual(kwargs["input"], collector.PAYLOAD.read_text())
                self.assertEqual(kwargs["timeout"], 45)
                value = "owner\t2031\tstable\ncomplete\tyes"
            return subprocess.CompletedProcess(args, 0, value + "\n", "")

        result = collector.capture("fixture", run=fake)
        self.assertEqual(result["checks"]["metadata_collection"]["status"], "PASS")
        self.assertEqual(result["checks"]["live_acceptance"]["status"], "BLOCKED")
        self.assertEqual(sum(payload is not None for _, payload in calls), 1)


if __name__ == "__main__":
    unittest.main()
