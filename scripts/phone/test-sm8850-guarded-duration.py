#!/usr/bin/env python3
"""Strict offline tests: bounded takeover timing and noncausal stall reporter."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY = ROOT / "scripts/phone/sm8850-600s-thermal-telemetry.py"
REPORT = ROOT / "scripts/phone/sm8850-frame-stall-report.py"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BoundedTimingTest(unittest.TestCase):
    def test_no_device_self_tests_at_300_and_600(self):
        for duration in (300, 600):
            with self.subTest(duration=duration):
                p = subprocess.run(["python3", str(TELEMETRY), "--self-test",
                                    "--duration", str(duration)],
                                   capture_output=True, text=True, timeout=10)
                self.assertEqual(0, p.returncode, p.stderr)
                self.assertIn("NO_DEVICE_ACCESS", p.stdout)

    def test_invalid_bounds_fail_before_adb(self):
        for duration in (0, 30, 601, 1200):
            p = subprocess.run(["python3", str(TELEMETRY), "--self-test",
                                "--duration", str(duration)],
                               capture_output=True, text=True, timeout=10)
            self.assertEqual(2, p.returncode)

    def test_sample_300s_clocks_and_pre_oneui_not_stale(self):
        mod = load("sm8850_tel_test", TELEMETRY)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            c = mod.Console(directory / "console.txt")
            try:
                with (directory / "telemetry.jsonl").open("w") as j:
                    meta = {"boot_id": "boot-new", "uptime": "390.0",
                            "ctl/framework.deadline": "400",
                            "ctl/framework.launch": "new-token",
                            "ctl/framework.duration": "300"}
                    with patch.object(mod, "remote_probe", return_value=(meta, {})):
                        pre = mod.sample("adb", "fake", "PRE_ONEUI", directory, c, j,
                                         "boot-new", None)
                        final = mod.sample("adb", "fake", "FINAL_NEAR_DEADLINE", directory, c, j,
                                           "boot-new", "new-token", 300)
                    self.assertIsNone(pre["elapsed_from_framework_stop_s"])
                    self.assertEqual(290.0, final["elapsed_from_framework_stop_s"])
                    self.assertTrue((directory / "final.json").exists())
            finally:
                c.close()


class StallReportTest(unittest.TestCase):
    def test_touch_frame_gap_with_cpu_and_traps(self):
        report = load("sm8850_stall_test", REPORT)
        xnu = "\n".join([
            "[ 1000.00] guest oneios-cpu: 10 s: backboardd[52] 70% (all 700%)",
            "[ 1002.00] xnuhost I perf: 30.0 s: 180000 task traps (6000/s)",
            "[ 1004.00] xnuhost I input: touch: 10 frames in 100 ms; no guest frame after the touch-down",
        ])
        display = ("oneios-display: perf: mono_ms=1005000 window_ms=5000 posts=2 "
                   "gap_p95_us=2100000 copy_max_us=3000 post_max_us=1000")
        result = report.analyze(xnu, display)
        self.assertEqual(1, len(result["candidate_windows"]))
        self.assertEqual(1, result["touch_without_frame_before_summary_end"])
        self.assertEqual(3.0, result["max_display_copy_ms"])
        self.assertEqual(700, result["peak_guest_cpu_pct_window"])
        self.assertEqual(6000, result["peak_traps_per_s_window"])
        self.assertEqual("touch-linked candidate",
                         result["candidate_windows"][0]["interpretation"])

    def test_idle_gap_not_labeled_as_proven_stall(self):
        report = load("sm8850_stall_test_idle", REPORT)
        r = report.analyze("", "oneios-display: perf: mono_ms=200000 window_ms=5000 posts=1 "
                              "gap_p95_us=3000000 copy_max_us=800 post_max_us=200")
        self.assertIn("NOT a proven stall", r["candidate_windows"][0]["interpretation"])


if __name__ == "__main__":
    unittest.main()
