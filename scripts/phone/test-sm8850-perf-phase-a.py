#!/usr/bin/env python3
"""Offline regressions for Phase A measurement integrity; no device access."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent

def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

stall = load("sm8850-frame-stall-report")
perf = load("sm8850-ios-interactive-perf")
takeover = load("sm8850-takeover")

def window(mono, posts, gaps, over60, over120, p95, maximum, all_gap):
    return (f"oneios-display: perf: mono_ms={mono} window_ms=5000 posts={posts} "
            f"posted_rate=20 active_cadence=34 active_gaps={gaps} "
            f"gap_p95_us={all_gap} active_gap_p95_us={p95} active_gap_p99_us={p95} "
            f"active_gap_max_us={maximum} active_over_60={over60} active_over_120={over120} "
            "lock_p95_us=10 copy_p95_us=20 post_p95_us=30 lock_max_us=9 copy_max_us=19 post_max_us=29")

class PhaseA(unittest.TestCase):
    def test_active_vs_all_and_budget_totals(self):
        # Synthetic partition of handoff's totals, not reconstructed raw windows.
        display = "\n".join((window(5000, 1500, 1500, 900, 1450, 250000, 248218, 7678684),
                             window(10000, 1347, 1347, 742, 1277, 100000, 99000, 100000),
                             window(15000, 0, 0, 0, 0, 0, 0, 0)))
        s = stall.analyze("", display)
        p = perf.analyze_logs("", display)
        self.assertEqual(250.0, s["largest_active_gap_p95_ms"])
        self.assertEqual(7678.684, s["largest_all_gap_p95_bucket_bound_ms"])
        self.assertEqual(s["active_post_summary"], p["active_post_summary"])
        a = s["active_post_summary"]
        self.assertEqual((2847, 1642, 2727, 248218),
                         (a["active_gaps_with_budget_counts"], a["over_60_budget"],
                          a["over_120_budget"], a["max_active_gap_us"]))
        self.assertAlmostEqual(57.6747453, a["over_60_budget_percent"], places=2)
        self.assertTrue(a["budget_coverage_complete"])

    def test_legacy_and_empty_do_not_invent_active_metrics(self):
        legacy = "oneios-display: perf: mono_ms=5000 posts=3 gap_p95_us=8000000"
        r = stall.analyze("", legacy)
        self.assertIsNone(r["largest_active_gap_p95_ms"])
        self.assertIsNone(r["active_post_summary"]["over_60_budget"])
        self.assertEqual(8000, r["largest_all_gap_p95_bucket_bound_ms"])
        empty = window(5000, 0, 0, 0, 0, 0, 0, 0)
        r = perf.analyze_logs("", empty)
        self.assertEqual(0, r["active_post_summary"]["over_60_budget"])
        self.assertIsNone(r["active_post_summary"]["over_60_budget_percent"])
        self.assertIsNone(r["display"]["copy_max_us"])
        self.assertIsNone(stall.analyze("", "")["max_display_copy_ms"])

    def test_partial_or_invalid_budget_not_in_denominator(self):
        valid = window(5000, 4, 3, 1, 2, 33000, 32000, 33000)
        invalid = window(10000, 4, 3, 3, 2, 33000, 32000, 33000)
        legacy = window(15000, 4, 3, 1, 2, 33000, 32000, 33000).replace("active_over_120=2 ", "")
        a = perf.analyze_logs("", "\n".join((valid, invalid, legacy)))["active_post_summary"]
        self.assertEqual(9, a["active_gaps_reported"])
        self.assertEqual(3, a["active_gaps_with_budget_counts"])
        self.assertFalse(a["budget_coverage_complete"])

    def test_cpu_merged_prefix_and_non_10_second_window(self):
        raw = ("[1.0] guestlogoneios-cpu: 7.5 s: Spotlight[248] 12%, iconservicesagent[44] 99% "
               "[1.1] guest oneios-cpu-sys: 7.5 s: Spotlight[248] 999%\n"
               "[2.0] guest neios-cpu: 11 s: Spotlight[248] 34%oneios-cpu: 8 s: SpringBoard[44] 90%\n"
               "[3.0] Spotlight[248] 999%\n")
        r = perf.analyze_logs(raw, "")["cpu"]
        self.assertEqual(34, r["spotlight_percent_of_one_core_max"])
        self.assertEqual(2, r["spotlight_observed_windows"])
        self.assertEqual(99, r["iconservicesagent_percent_of_one_core_max"])
        self.assertIsNone(perf.analyze_logs("Spotlight[248] 12%", "")["cpu"]["spotlight_percent_of_one_core_max"])

    def test_archive_identity_and_legacy_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            archive = Path(d) / "logs.tar"
            launch = "a" * 32
            with tarfile.open(archive, "w") as tf:
                for name, value in {
                    "control/framework.launch": launch,
                    "control/framework.perf-profile": "frame-task",
                    "session/xnuhost.log": "ONEIOS_PERF_PROFILE=frame-task\nperf-task: enabled\n",
                    "control/display.log": window(5000, 4, 3, 1, 2, 33000, 32000, 33000),
                    "logs/session.old/control/framework.launch": "b" * 32,
                    "logs/session.old/session/xnuhost.log": "old",
                    "logs/session.old/control/display.log": "old",
                }.items():
                    raw = value.encode()
                    member = tarfile.TarInfo(name)
                    member.size = len(raw)
                    tf.addfile(member, io.BytesIO(raw))
            metadata = {}
            stall.read_logs(archive, None, expected_launch=launch, metadata=metadata)
            self.assertEqual("frame-task", metadata["perf_profile"])
            with self.assertRaises(stall.MissingTraceInputs):
                stall.read_logs(archive, None, expected_launch="b" * 32)
            self.assertEqual(("old", "old"), stall.read_logs(archive, None, "old", expected_launch="b" * 32))
            report = Path(d) / "perf.json"
            cmd = [sys.executable, str(HERE / "sm8850-ios-interactive-perf.py"),
                   "--archive", str(archive), "--expected-launch", launch, "--json", str(report)]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            self.assertEqual(launch, json.loads(report.read_text())["session_metadata"]["launch_id"])
            cmd[5] = "b" * 32
            failed = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(2, failed.returncode)

    def test_detached_profile_and_refusal_before_launch(self):
        for profile in ("off", "frame", "task", "frame-task"):
            for acknowledged in (profile, "invalid"):
                with self.subTest(profile=profile, acknowledged=acknowledged), tempfile.TemporaryDirectory() as d, \
                        patch.object(takeover, "audit", return_value=0), patch.object(takeover, "upload", return_value=0), \
                        patch.object(takeover, "status", return_value="boot=mock\n"), \
                        patch.object(takeover.time, "monotonic", side_effect=[0.0, 1000.0]):
                    phone = Mock()
                    phone.root.side_effect = [subprocess.CompletedProcess([], 0, f"SM8850_PERF_PROFILE={acknowledged}\n".encode()),
                                              subprocess.CompletedProcess([], 0, b"")]
                    rc = takeover.launch(phone, "run", Path(d), duration=180, perf_profile=profile)
                    calls = [c.args[0] for c in phone.root.call_args_list]
                    if profile != acknowledged:
                        self.assertEqual(2, rc)
                        self.assertEqual(1, len(calls))
                    else:
                        self.assertEqual(4, rc)
                        self.assertEqual(2, len(calls))
                        if profile != "off":
                            self.assertIn("run 180 perf-" + profile, calls[0])
                            self.assertIn("180 perf-" + profile, calls[1])
                        self.assertEqual(profile, json.loads((Path(d) / "performance-profile.json").read_text())["requested_profile"])
        with tempfile.TemporaryDirectory() as d:
            phone = Mock()
            with self.assertRaises(ValueError):
                takeover.launch(phone, "smoke", Path(d), perf_profile="frame")
            phone.root.assert_not_called()

    def test_cpu_profile_detached_and_acknowledged(self):
        for acknowledged in ("prime-first", "default", None):
            with self.subTest(acknowledged=acknowledged), tempfile.TemporaryDirectory() as d, \
                    patch.object(takeover, "audit", return_value=0), patch.object(takeover, "upload", return_value=0), \
                    patch.object(takeover, "status", return_value="boot=mock\n"), \
                    patch.object(takeover.time, "monotonic", side_effect=[0.0, 1000.0]):
                phone = Mock()
                lines = "SM8850_PERF_PROFILE=frame-task\n"
                if acknowledged:
                    lines += f"SM8850_CPU_PROFILE_REQUESTED={acknowledged}\n"
                phone.root.side_effect = [subprocess.CompletedProcess([], 0, lines.encode()),
                                          subprocess.CompletedProcess([], 0, b"")]
                rc = takeover.launch(phone, "run", Path(d), duration=180, perf_profile="frame-task",
                                     cpu_profile="prime-first")
                calls = [c.args[0] for c in phone.root.call_args_list]
                if acknowledged == "prime-first":
                    self.assertEqual(4, rc)
                    self.assertEqual(2, len(calls))
                    self.assertIn("180 perf-frame-task cpu-prime-first", calls[0])
                    self.assertIn("180 perf-frame-task cpu-prime-first", calls[1])
                    self.assertEqual("prime-first", json.loads((Path(d) / "performance-profile.json").read_text())["preflight_cpu_profile"])
                else:
                    self.assertEqual(2, rc)
                    self.assertEqual(1, len(calls))
        with tempfile.TemporaryDirectory() as d:
            phone = Mock()
            with self.assertRaises(ValueError):
                takeover.launch(phone, "smoke", Path(d), cpu_profile="prime-first")
            phone.root.assert_not_called()

    def test_placement_evidence_does_not_pool_cumulative_values(self):
        host = "\n".join((
            "SM8850_CPU_PROFILE=PRIME_FIRST_ACTIVE (experimental)",
            "cpu0: host CPU mask 0x40",
            "cpu: vCPU 0 (E) is described to iOS as host CPU 6: 768000-4742400 kHz, 2 table entries, capacity 1024",
            "perf-affinity: vcpu=0 tid=123 allowed=6 migrations=1 last_cpu=6",
            "perf-affinity: vcpu=1 tid=124 allowed=unknown migrations=unknown last_cpu=-1",
            "perf-placement: vcpu=0 role=guest-thread calls=4 failed=0 readback_samples=3 readback_errors=0 readback_mismatches=1 current_target=0x40",
            "perf-placement: vcpu=0 role=guest-thread calls=8 failed=0 readback_samples=4 readback_errors=0 readback_mismatches=1 current_target=0x3f",
            "perf-placement: vcpu=0 role=service-thread calls=2 failed=0 readback_samples=2 readback_errors=0 readback_mismatches=0 current_target=0x3f",
        ))
        a = perf.analyze_logs(host, "")["cpu_placement"]
        self.assertEqual(["PRIME_FIRST_ACTIVE"], a["runtime_profile_markers"])
        self.assertEqual("0x40", a["initial_target_masks"][0]["target_mask"])
        self.assertEqual(6, a["described_cores"][0]["host_cpu"])
        self.assertEqual("6", a["vcpu_affinity_samples"][0]["allowed"])
        self.assertIsNone(a["vcpu_affinity_samples"][1]["allowed"])
        self.assertEqual([4, 8, 2], [x["calls"] for x in a["placement_cumulative_samples"]])
        self.assertIsNone(a["residency"])
        self.assertEqual(a, stall.analyze(host, "")["cpu_placement"])
        self.assertEqual([], perf.analyze_logs("", "")["cpu_placement"]["runtime_profile_markers"])

if __name__ == "__main__":
    unittest.main()
