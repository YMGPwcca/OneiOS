#!/usr/bin/env python3
"""Strict offline tests: bounded takeover timing and noncausal stall reporter."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import signal
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

    def test_preflight_only_never_invokes_takeover_or_rearm(self):
        mod = load("sm8850_tel_preflight_test", TELEMETRY)
        with tempfile.TemporaryDirectory() as td:
            adb = Path(td) / "fake-adb"
            adb.write_text("# no executable needed for isolated mocks")
            argv = ["sm8850-600s-thermal-telemetry.py", "--repo", str(ROOT),
                    "--adb", str(adb), "--preflight-only", "--duration", "300"]
            with patch("sys.argv", argv), \
                 patch.object(mod, "stock_identity", return_value={"boot_id": "test"}), \
                 patch.object(mod, "adb_shell", return_value="PREFLIGHT OK\\n") as root, \
                 patch.object(mod, "run_monitor", side_effect=AssertionError("live call")):
                with contextlib.redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(0, mod.main())
            self.assertIn("NO_FRAMEWORK_STOP", stdout.getvalue())
            self.assertIn("--framework-check run 300", root.call_args.args[2])

    def test_previous_boot_session_markers_are_never_current_boot_proof(self):
        mod = load("sm8850_tel_stale_test", TELEMETRY)
        self.assertIn('[ "$ctl_boot" = "$current_boot" ]', mod.PROBE)
        self.assertIn('meta stale_session_markers_ignored 1', mod.PROBE)
        self.assertIn('[ "$(cat "$ST/control/boot" 2>/dev/null)" = "$(cat /proc/sys/kernel/random/boot_id)" ]',
                      mod.MARKERS)
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            c = mod.Console(directory / "console.txt")
            try:
                old = {"boot_id": "new-boot", "ctl/boot": "old-boot",
                       "ctl/state": "running", "guest_ready": "1",
                       "first_frame": "1", "backboardd_log": "1",
                       "springboard_log": "1", "kgsl_3d_backend_log": "1",
                       "framework_stop_log": "old launch"}
                with (directory / "telemetry.jsonl").open("w") as j:
                    with patch.object(mod, "remote_probe", return_value=(old, {})):
                        result = mod.sample("adb", "fake", "PRE_ONEUI", directory,
                                            c, j, "new-boot", None)
                self.assertIsNotNone(result)
                self.assertEqual("1", result["meta"]["stale_session_markers_ignored"])
                for key in ("guest_ready", "first_frame", "backboardd_log",
                            "springboard_log", "kgsl_3d_backend_log",
                            "framework_stop_log"):
                    self.assertNotIn(key, result["meta"])
            finally:
                c.close()

    def test_post_reboot_host_wait_is_bounded_and_local_only(self):
        mod = load("sm8850_tel_runner_test", TELEMETRY)
        class FakeRunner:
            pid = 123456
            def poll(self):
                return None
            def wait(self, timeout):
                if timeout == 8:
                    raise subprocess.TimeoutExpired("host-side runner", timeout)
                self.assert_timeout = timeout
                return -signal.SIGTERM
        with tempfile.TemporaryDirectory() as temp:
            c = mod.Console(Path(temp) / "console.txt")
            try:
                proc = FakeRunner()
                with patch.object(mod.os, "killpg") as killpg:
                    rc = mod.finish_local_runner(proc, reboot_observed=True,
                                                 console=c)
                    self.assertEqual(-signal.SIGTERM, rc)
                    killpg.assert_called_once_with(proc.pid, signal.SIGTERM)
                    self.assertEqual(5, proc.assert_timeout)
            finally:
                c.close()

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
