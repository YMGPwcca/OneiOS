#!/usr/bin/env python3
"""Offline tests for G22 own-pmap opt-in; never invokes ADB."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SWITCH = ROOT / "app/switcher/assets/oneios_switch.sh"
sys.path.insert(0, str(Path(__file__).resolve().parent))


class OwnPresence(unittest.TestCase):
    def test_root_parser_preserves_existing_arguments(self):
        src = SWITCH.read_text()
        parser = src.split("# BEGIN FRAMEWORK_OWN_PRESENCE_ARGS", 1)[1].split(
            "# END FRAMEWORK_OWN_PRESENCE_ARGS", 1)[0]
        script = "FW_OWN_PRESENCE=0\n" + parser + '\nprintf "%s\\n" "$FW_OWN_PRESENCE" "$@"\n'
        cases = [
            ["--framework-check", "run", "180"],
            ["--framework-check", "run", "180", "perf-frame-task", "own-presence-1"],
            ["--framework-session", "run", "ack", "token", "risk", "180",
             "perf-frame-task", "cpu-prime-first", "own-presence-1"],
            ["--framework-session", "run", "ack", "token", "risk", "180",
             "own-presence-1", "cpu-prime-first"],
        ]
        for shell in ("sh", "bash", "mksh"):
            if not shutil.which(shell):
                continue
            for args in cases:
                with self.subTest(shell=shell, args=args):
                    on = args[-1] == "own-presence-1"
                    expected = ["1" if on else "0"] + (args[:-1] if on else args)
                    result = subprocess.check_output([shell, "-c", script, "parser", *args],
                                                     text=True, timeout=10)
                    self.assertEqual(expected, result.splitlines())

    def test_offline_counter_windows(self):
        path = ROOT / "scripts/phone/sm8850-ios-interactive-perf.py"
        spec = importlib.util.spec_from_file_location("own_presence_perf", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertIsNone(mod.own_presence_summary("")["requests"])
        logs = ("oneios-own-presence: enabled=1 history=1 requests=10 skipped=7 issued=3\n"
                "oneios-own-presence: enabled=1 history=1 requests=20 skipped=8 issued=12\n"
                "oneios-own-presence: enabled=1 history=0 requests=100 skipped=0 issued=100\n")
        report = mod.own_presence_summary(logs)
        self.assertEqual((2, 1, 30, 15, 15, 50.0),
                         tuple(report[k] for k in ("valid_windows", "invalid_windows",
                                                   "requests", "skipped", "issued", "skip_percent")))


if __name__ == "__main__":
    unittest.main()
