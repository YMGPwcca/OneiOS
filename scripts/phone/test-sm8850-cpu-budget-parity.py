#!/usr/bin/env python3
"""Verify that the model and actuator tested in OneiOS are exactly in OneOS."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PHONE = ROOT / "scripts/phone"
CAP = (ROOT / "app/switcher/assets/oneios_sm8850_thermal_cap.sh").read_text()


def block(source, name):
    return source.split("# BEGIN " + name + "\n", 1)[1].split("# END " + name, 1)[0]


class CpuBudgetParity(unittest.TestCase):
    def test_pure_policy_identical(self):
        self.assertEqual((PHONE / "sm8850-thermal-hysteresis.sh").read_text(),
                         block(CAP, "SM8850_HYSTERESIS_MODEL"))

    def test_actuator_identical(self):
        self.assertEqual(block((PHONE / "sm8850-cpu-bandwidth.sh").read_text(), "SM8850_CPU_BANDWIDTH"),
                         block(CAP, "SM8850_CPU_BANDWIDTH"))


if __name__ == "__main__":
    unittest.main()
