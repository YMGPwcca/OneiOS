#!/usr/bin/env python3
"""Host-only test of the candidate policy. No device access or sysfs writes."""
from pathlib import Path
import subprocess
import unittest

POLICY = Path(__file__).with_name("sm8850-thermal-hysteresis.sh")


def step(pct, latch, dwell, cpu, gpu=40000, ddr=40000):
    return subprocess.run(
        ["sh", "-c", '. "$1"; shift; sm8850_thermal_hysteresis_step "$@"',
         "test", str(POLICY), *map(str, (pct, latch, dwell, cpu, gpu, ddr))],
        capture_output=True, text=True, timeout=3,
    )


class ThermalHysteresis(unittest.TestCase):
    def check_step(self, expected, *args):
        p = step(*args)
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertEqual(expected, p.stdout.strip())

    def test_soft_and_hard_thresholds(self):
        for temp, expected in ((64999, "COOL:40:0:1"), (65000, "HOLD:40:0:0"),
                               (69999, "HOLD:40:0:0"), (70000, "SOFT:30:0:0"),
                               (75000, "SOFT:20:0:0"), (79999, "SOFT:20:0:0"),
                               (80000, "HARD:10:1:0")):
            self.check_step(expected, 40, 0, 0, temp)

    def test_hard_latched_until_70(self):
        for temp in (80000, 79999, 75000, 70001):
            self.check_step("HARD:10:1:0", 10, 1, 0, temp)
        self.check_step("RECOVERY:10:0:0", 10, 1, 0, 70000)
        self.check_step("RECOVERY:10:0:0", 10, 1, 0, 60000)

    def test_slow_recovery_and_ceiling(self):
        self.check_step("COOL:40:0:4", 40, 0, 3, 44000)
        self.check_step("COOL:50:0:0", 40, 0, 4, 44000)
        self.check_step("COOL:45:0:0", 40, 0, 4, 45000)
        self.check_step("COOL:100:0:0", 95, 0, 4, 44000)
        self.check_step("HOLD:40:0:0", 40, 0, 4, 66000)
        self.check_step("SOFT:10:0:0", 10, 0, 4, 73000)

    def test_hottest_junction_wins(self):
        self.check_step("HARD:10:1:0", 70, 0, 0, 45000, 80000, 40000)
        self.check_step("HARD:10:1:0", 70, 0, 0, 45000, 40000, 80000)
        self.check_step("HARD:10:1:0", 10, 1, 0, 60000, 71000, 60000)

    def test_bad_input_rejected(self):
        for args in ((0, 0, 0, 45000), (101, 0, 0, 45000), (40, 2, 0, 45000),
                     (40, 0, 5, 45000), (40, 0, 0, 0), (40, 0, 0, 200001),
                     (40, 0, 0, "08"), (40, 0, 0, "x"), (40, 0, 0, 45000, 0)):
            self.assertEqual(3, step(*args).returncode, args)


if __name__ == "__main__":
    unittest.main()
