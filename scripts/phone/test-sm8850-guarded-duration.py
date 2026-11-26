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
PERF_BRANCH = "feat/sm8850-xnuhost-perf-p0"
LEGACY_BRANCH = "feat/oneios-sm8850-m3q"
OFF_TOKEN = "I_ACCEPT_SOFT_GUARD_OFF_180S"
GUARDED_MARKER = "SM8850_CPU_THROTTLE_POLICY=HYBRID_FREQ40_CFS_V1_TARGET_45_70_HARD_80_RELEASE_70"
LEGACY_GUARDED_MARKER = "SM8850_CPU_THROTTLE_POLICY=TARGET_30_70_THROTTLE_BY_75_MONOTONIC"
CFS_ONLY_MARKER = "SM8850_CPU_THROTTLE_POLICY=CFS_V1_TARGET_45_70_HARD_80_RELEASE_70"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BoundedTimingTest(unittest.TestCase):
    def test_retired_policy_refuses_preflight_and_live_before_adb(self):
        for args in (["--preflight-only"],
                     ["--i-accept-10-minute-legacy-watchdog-risk"]):
            mod = load("retired_policy_test", TELEMETRY)
            with patch("sys.argv", [str(TELEMETRY), "--duration", "180", *args]), \
                 patch.object(mod.subprocess, "check_output", return_value=PERF_BRANCH), \
                 patch.object(mod, "stock_identity") as identity, \
                 patch.object(mod, "adb_shell") as adb, \
                 patch.object(mod, "run_monitor") as monitor, \
                 patch.dict(mod.os.environ, {"ONEIOS_SM8850_SOFT_THERMAL_OFF": OFF_TOKEN}), \
                 contextlib.redirect_stderr(io.StringIO()) as stderr, \
                 self.assertRaises(SystemExit) as result:
                mod.main()
            self.assertEqual(2, result.exception.code)
            self.assertIn("SM8850_THERMAL_POLICY=BLOCKED_LEGACY_RETIRED", stderr.getvalue())
            identity.assert_not_called()
            adb.assert_not_called()
            monitor.assert_not_called()

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

    def preflight_fixture(self, branch, env_value, result, error=None, own_presence="off", interaction="off"):
        mod = load("sm8850_tel_preflight_test", TELEMETRY)
        with tempfile.TemporaryDirectory() as td:
            adb = Path(td) / "fake-adb"
            adb.write_text("# no executable needed for isolated mocks")
            argv = ["sm8850-600s-thermal-telemetry.py", "--repo", str(ROOT),
                    "--adb", str(adb), "--preflight-only", "--duration", "180"]
            argv += ["--own-presence", own_presence]
            if interaction != "off":
                argv += ["--perf-profile", "frame", "--interaction-profile", interaction]
            # Historical admission parser coverage, under mocks only.
            with patch("sys.argv", argv), \
                 patch.object(mod, "LIVE_THERMAL_POLICY_READY", True), \
                 patch.dict(mod.os.environ, {"ONEIOS_SM8850_SOFT_THERMAL_OFF": env_value}), \
                 patch.object(mod.subprocess, "check_output", return_value=branch) as git, \
                 patch.object(mod, "stock_identity", return_value={"boot_id": "test"}) as identity, \
                 patch.object(mod, "adb_shell", return_value=result) as root, \
                 patch.object(mod, "run_monitor", side_effect=AssertionError("live call")) as monitor, \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                if error is None:
                    self.assertEqual(0, mod.main())
                    self.assertIn("NO_FRAMEWORK_STOP_NO_DATA_CONSUMPTION", stdout.getvalue())
                    self.assertIn("PHYSICAL_THERMAL_WATCHDOG_QUALIFICATION=NOT_VERIFIED",
                                  stdout.getvalue())
                else:
                    with self.assertRaisesRegex(RuntimeError, error):
                        mod.main()
                git.assert_called_once_with(
                    ["git", "-C", str(ROOT.resolve()), "branch", "--show-current"],
                    text=True, timeout=10)
                identity.assert_called_once()
                root.assert_called_once()
                self.assertTrue(root.call_args.kwargs["root"])
                monitor.assert_not_called()
                return root.call_args.args[2]

    def test_own_presence_preflight_requires_exact_ack(self):
        base = "PREFLIGHT OK\n" + GUARDED_MARKER + "\n"
        cmd = self.preflight_fixture(PERF_BRANCH, "", base + "SM8850_OWN_PRESENCE=1\n",
                                     own_presence="on")
        self.assertTrue(cmd.endswith(" own-presence-1"))
        for reply in (base, base + "SM8850_OWN_PRESENCE=0\n",
                      base + "SM8850_OWN_PRESENCE=1\nSM8850_OWN_PRESENCE=1\n"):
            self.preflight_fixture(PERF_BRANCH, "", reply, "own-presence mismatch",
                                   own_presence="on")
        cmd = self.preflight_fixture(PERF_BRANCH, "", base + "SM8850_OWN_PRESENCE=0\n")
        self.assertNotIn("own-presence-1", cmd)
        self.preflight_fixture(PERF_BRANCH, "", base + "SM8850_OWN_PRESENCE=1\n",
                               "own-presence mismatch")

    def test_interaction_preflight_requires_exact_ack(self):
        base = "PREFLIGHT OK\n" + GUARDED_MARKER + "\nSM8850_PERF_PROFILE=frame\n"
        cmd = self.preflight_fixture(PERF_BRANCH, "", base + "SM8850_INTERACTION_PROFILE=swipe-60s\n",
                                     interaction="swipe-60s")
        self.assertTrue(cmd.endswith(" perf-frame interaction-swipe-60s"))
        for reply in (base, base + "SM8850_INTERACTION_PROFILE=off\n",
                      base + "SM8850_INTERACTION_PROFILE=swipe-60s\nSM8850_INTERACTION_PROFILE=swipe-60s\n"):
            self.preflight_fixture(PERF_BRANCH, "", reply, "interaction profile mismatch",
                                   interaction="swipe-60s")

    def test_preflight_only_never_invokes_takeover_or_rearm(self):
        command = self.preflight_fixture(
            PERF_BRANCH, "", "PREFLIGHT OK\n" + GUARDED_MARKER + "\n")
        self.assertIn("--framework-check run 180", command)
        self.assertNotIn(OFF_TOKEN, command)

    def test_performance_branch_discards_inherited_no_guard_token(self):
        command = self.preflight_fixture(
            PERF_BRANCH, OFF_TOKEN, "PREFLIGHT OK\n" + GUARDED_MARKER + "\n")
        self.assertIn("--framework-check run 180", command)
        self.assertNotIn(OFF_TOKEN, command)

    def test_guarded_preflight_refuses_missing_180s_policy_marker(self):
        command = self.preflight_fixture(
            PERF_BRANCH, "", "PREFLIGHT OK\n", "guarded thermal policy marker missing")
        self.assertIn("--framework-check run 180", command)
        self.assertNotIn(OFF_TOKEN, command)

    def test_guarded_preflight_refuses_stale_monotonic_180s_stage(self):
        self.preflight_fixture(PERF_BRANCH, "", LEGACY_GUARDED_MARKER + "\nPREFLIGHT OK\n",
                               "guarded thermal policy marker missing")

    def test_guarded_preflight_refuses_cfs_only_stage_after_thermal_trip(self):
        self.preflight_fixture(PERF_BRANCH, "", CFS_ONLY_MARKER + "\nPREFLIGHT OK\n",
                               "guarded thermal policy marker missing")

    def test_performance_branch_refuses_unexpected_unguarded_ack(self):
        command = self.preflight_fixture(
            PERF_BRANCH, OFF_TOKEN,
            "SM8850_SOFT_THERMAL_GUARD=OFF_NOT_SPAWNED\n"
            "SM8850_CPU_CAP=DISABLED_NO_ROOT_WORKER\n",
            "thermal profile mismatch")
        self.assertNotIn(OFF_TOKEN, command)

    def test_full_bridges_rejects_300_before_device_access(self):
        mod = load("sm8850_tel_reject_300", TELEMETRY)

        argv = [
            "sm8850-600s-thermal-telemetry.py",
            "--repo", str(ROOT),
            "--preflight-only",
            "--duration", "300",
        ]

        with patch("sys.argv", argv), \
             patch.object(
                 mod.subprocess,
                 "check_output",
                 return_value="feat/oneios-sm8850-m3q",
             ), \
             patch.object(mod, "stock_identity") as identity, \
             patch.object(mod, "adb_shell") as adb, \
             contextlib.redirect_stderr(io.StringIO()) as stderr:

            with self.assertRaises(SystemExit) as exc:
                mod.main()

        self.assertEqual(exc.exception.code, 2)
        self.assertIn(
            "requires --duration 180",
            stderr.getvalue(),
        )
        identity.assert_not_called()
        adb.assert_not_called()

    def test_explicit_off_mode_preflight_rejects_wrong_effective_mode(self):
        # Explicit legacy no-guard admission is NOT the guarded performance branch.
        command = self.preflight_fixture(
            LEGACY_BRANCH, OFF_TOKEN, "PREFLIGHT OK\n", "thermal profile mismatch")
        self.assertIn("--framework-check run 180 " + OFF_TOKEN, command)

    def test_explicit_legacy_off_mode_requires_cpu_cap_ack(self):
        command = self.preflight_fixture(
            LEGACY_BRANCH, OFF_TOKEN, "SM8850_SOFT_THERMAL_GUARD=OFF_NOT_SPAWNED\n",
            "CPU cap profile mismatch")
        self.assertIn("--framework-check run 180 " + OFF_TOKEN, command)

    def test_explicit_legacy_off_mode_accepts_matching_acks(self):
        command = self.preflight_fixture(
            LEGACY_BRANCH, OFF_TOKEN,
            "SM8850_SOFT_THERMAL_GUARD=OFF_NOT_SPAWNED\n"
            "SM8850_CPU_CAP=DISABLED_NO_ROOT_WORKER\n")
        self.assertIn("--framework-check run 180 " + OFF_TOKEN, command)

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

    def test_verified_post_reboot_must_not_claim_root_was_lost(self):
        source = TELEMETRY.read_text()
        self.assertIn("POST_REBOOT=ANDROID_BOOT_COMPLETE_OBSERVED_VIA_UNPRIVILEGED_ADB", source)
        self.assertNotIn("POST_REBOOT=ANDROID_BOOT_COMPLETE_ROOT_UNAVAILABLE", source)
        self.assertIn("BOUNDED_TAKEOVER_RESULT=POST_REBOOT_OBSERVED_SESSION_CAUSE_NOT_PROVEN", source)
        self.assertIn("if post_reboot:\n            console.say(", source)
        self.assertIn("return 4\n        return code", source)

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
        self.assertEqual("all-gap candidate near touch; may include idle; NOT a proven stall",
                         result["candidate_windows"][0]["interpretation"])

    def test_idle_gap_not_labeled_as_proven_stall(self):
        report = load("sm8850_stall_test_idle", REPORT)
        r = report.analyze("", "oneios-display: perf: mono_ms=200000 window_ms=5000 posts=1 "
                              "gap_p95_us=3000000 copy_max_us=800 post_max_us=200")
        self.assertIn("NOT a proven stall", r["candidate_windows"][0]["interpretation"])


if __name__ == "__main__":
    unittest.main()
