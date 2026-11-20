#!/usr/bin/env python3
"""Host-only tests for strictly fixed-path, read-only SM8850 sensor correlation."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

FILE = Path(__file__).with_name("sm8850-thermal-known-nodes.py")
SPEC = importlib.util.spec_from_file_location("sm8850_known_nodes", FILE)
APP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APP)

BOOT = "123e4567-e89b-12d3-a456-426614174000"
HAL = ("Current temperatures from HAL:\n"
       "Temperature{mValue=28.7, mType=0, mName=AP, mStatus=0}\n"
       "Temperature{mValue=26.6, mType=2, mName=BAT, mStatus=0}\n"
       "Temperature{mValue=28.9, mType=3, mName=SKIN, mStatus=0}\n"
       "Temperature{mValue=0.0, mType=2, mName=SUBBAT, mStatus=0}\n")


def values(firmware=None):
    p = APP.PREFLIGHT
    return dict(model=p.MODEL, device=p.DEVICE,
                firmware=firmware or p.FIRMWARE, boot_completed="1",
                selinux="Enforcing", system_server="123", boot_id=BOOT,
                uptime="200.1 400.0")


class KnownNodesTests(unittest.TestCase):
    def test_only_three_audited_paths(self):
        self.assertEqual(3, len(APP.NODES))
        self.assertEqual(
            {
                "/sys/class/power_supply/battery/temp",
                "/sys/class/power_supply/battery/lrp",
                "/sys/class/sec/sec-ap-thermistor/temperature",
            },
            {path for _, path in APP.NODES},
        )

    def test_correlate_ignores_subbat_zero_and_does_not_equate_hal_ap_with_board_ap(self):
        hal = APP.PREFLIGHT.parse_current_thermal(HAL)
        nodes = {
            "battery": {"status": "READ", "celsius": 26.5},
            "lrp": {"status": "READ", "celsius": 29.0},
            "board_ap": {"status": "READ", "celsius": 27.5},
        }
        comparisons, suspect = APP.correlate(hal, nodes)
        self.assertAlmostEqual(0.1, comparisons["battery"]["abs_difference_celsius"])
        self.assertAlmostEqual(0.1, comparisons["lrp"]["abs_difference_celsius"])
        self.assertFalse(comparisons["lrp"]["proves_same_physical_sensor"])
        self.assertNotIn("board_ap", comparisons)
        self.assertEqual("SUBBAT", suspect[0]["name"])

    def test_denied_no_root_retry_without_explicit_opt_in(self):
        attempts = []
        def fake(adb, serial, argv, timeout=12):
            attempts.append(argv)
            raise RuntimeError("Permission denied")
        with patch.object(APP.PREFLIGHT, "adb_call", side_effect=fake):
            report = APP.read_named_node("adb", "serial", *APP.NODES[0])
        self.assertEqual("UNAVAILABLE", report["status"])
        self.assertEqual(1, len(attempts))
        self.assertNotIn("su", attempts[0])

    def test_explicit_root_retry_only_same_known_path(self):
        attempts = []
        def fake(adb, serial, argv, timeout=12):
            attempts.append(argv)
            if "su" in argv:
                return "289\n"
            raise RuntimeError("Permission denied")
        with patch.object(APP.PREFLIGHT, "adb_call", side_effect=fake):
            report = APP.read_named_node("adb", "serial", *APP.NODES[1], allow_root=True)
        self.assertEqual("root_named_cat", report["method"])
        self.assertEqual(28.9, report["celsius"])
        self.assertEqual(2, len(attempts))
        self.assertEqual(APP.NODES[1][1], attempts[0][-1])
        self.assertIn(APP.NODES[1][1], attempts[1][-1])

    def test_wrong_firmware_rejects_before_hal_and_sysfs(self):
        identity = values(firmware="WRONG")
        def fake(adb, serial, argv, timeout=12):
            for key, command in APP.PREFLIGHT.READS:
                if command == argv:
                    return identity[key]
            raise AssertionError("No thermal probe on unexpected firmware")
        with tempfile.TemporaryDirectory() as tmp, patch.object(APP.PREFLIGHT, "adb_call", side_effect=fake):
            with self.assertRaisesRegex(RuntimeError, "BLOCKED before thermal/kernel reads"):
                APP.capture("adb", "serial", Path(tmp))
            self.assertEqual([], list(Path(tmp).iterdir()))

    def test_normal_collect_is_explicitly_not_guard_acceptance(self):
        identity = values()
        data = {name: f"{int(c * 10)}\n" for name, c in
                (("battery", 26.6), ("lrp", 28.9), ("board_ap", 28.7))}
        touched = []
        def fake(adb, serial, argv, timeout=12):
            touched.append(argv)
            for key, command in APP.PREFLIGHT.READS:
                if command == argv:
                    return identity[key]
            if argv == APP.PREFLIGHT.THERMAL:
                return HAL
            if argv == ("shell", "cat", "/proc/sys/kernel/random/boot_id"):
                return BOOT
            for name, path in APP.NODES:
                if argv == ("shell", "cat", path):
                    return data[name]
            raise AssertionError(argv)
        with tempfile.TemporaryDirectory() as tmp, patch.object(APP.PREFLIGHT, "adb_call", side_effect=fake):
            output, report = APP.capture("adb", "serial", Path(tmp))
            self.assertEqual("NOT_QUALIFIED", report["acceptance"])
            self.assertFalse(report["independent_guard_implemented"])
            self.assertFalse(report["physical_sensor_equivalence_verified"])
            self.assertEqual("READ", report["kernel_sensor_nodes"]["lrp"]["status"])
            self.assertTrue((output / "summary.json").exists())
            self.assertTrue(all("su" not in argv for argv in touched))

    def test_invalid_kernel_node_does_not_become_valid(self):
        with patch.object(APP.PREFLIGHT, "adb_call", return_value="-273000\n"):
            report = APP.read_named_node("adb", "serial", *APP.NODES[0])
        self.assertEqual("OUT_OF_RANGE", report["status"])


if __name__ == "__main__":
    unittest.main()
