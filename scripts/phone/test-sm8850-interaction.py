#!/usr/bin/env python3
"""Offline G23.1 parser and receipt fixtures; no ADB."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


class Interaction(unittest.TestCase):
    def test_root_final_token_preserves_existing_suffixes(self):
        src = (ROOT / "app/switcher/assets/oneios_switch.sh").read_text()
        parser = src.split("# BEGIN FRAMEWORK_INTERACTION_ARGS", 1)[1].split(
            "# END FRAMEWORK_INTERACTION_ARGS", 1)[0]
        code = "FW_INTERACTION_PROFILE=off\n" + parser + '\nprintf "%s\\n" "$FW_INTERACTION_PROFILE" "$@"\n'
        for shell in ("sh", "bash", "mksh"):
            if not shutil.which(shell):
                continue
            for args in (["--framework-check", "run", "180", "perf-frame"],
                         ["--framework-check", "run", "180", "perf-frame", "interaction-swipe-60s"],
                         ["--framework-session", "run", "ack", "token", "risk", "180",
                          "perf-frame-task", "cpu-prime-first", "own-presence-1", "interaction-swipe-60s"]):
                with self.subTest(shell=shell, args=args):
                    enabled = args[-1] == "interaction-swipe-60s"
                    expect = ["swipe-60s" if enabled else "off"] + (args[:-1] if enabled else args)
                    self.assertEqual(expect, subprocess.check_output(
                        [shell, "-c", code, "parser", *args], text=True, timeout=10).splitlines())

    def test_receipt_requires_complete_ordered_workload(self):
        spec = importlib.util.spec_from_file_location("stall", HERE / "sm8850-frame-stall-report.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        meta = {"interaction_profile": "swipe-60s"}
        rows = ["status=start profile=swipe-60s mono_ms=100000 boot_ms=100000 deadline_ms=180000 planned=30 ui=unverified"]
        for i in range(30):
            rows += [f"status=gesture_begin index={i+1} mono_ms={100000+i*2000}",
                     f"status=gesture_end index={i+1} mono_ms={100320+i*2000}"]
        rows += ["status=complete completed=30 mono_ms=160100 elapsed_ms=60100"]
        def receipt(lines, metadata=meta):
            return mod.interaction_summary("\n".join("SM8850_INTERACTION_V1 " + r for r in lines), metadata)["status"]
        self.assertEqual("COMPLETE", receipt(rows))
        self.assertEqual("OFF", receipt([], {}))
        for incomplete in (rows[:-1], rows[:4] + rows[5:], rows + [rows[-1]],
                           rows + ["status=aborted completed=30 mono_ms=160101"],
                           rows[:1] + [rows[2], rows[1]] + rows[3:]):
            self.assertEqual("INCOMPLETE_OR_MISMATCH", receipt(incomplete))
        self.assertEqual("INCOMPLETE_OR_MISMATCH", receipt(rows, {"interaction_profile": "off"}))
        completed = mod.interaction_summary("\n".join("SM8850_INTERACTION_V1 " + r for r in rows), meta)
        line = "oneios-display: perf: mono_ms={} window_ms=5000 posts=50 active_gaps=49 active_over_60=10 active_over_120=40"
        display = "\n".join(line.format(t) for t in (101000, 105000, 110000, 160100, 160101))
        report = mod.interaction_display_summary(display, completed)
        self.assertEqual(3, report["whole_windows"])
        self.assertEqual(10, report["peak_post_rate"])
        self.assertEqual(147, report["active_post_summary"]["active_gaps_reported"])


if __name__ == "__main__":
    unittest.main()
