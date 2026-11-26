#!/usr/bin/env python3
"""Host-only tests: never access a real cgroup or device."""
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("sm8850-cpu-bandwidth.sh")
SOURCE = SCRIPT.read_text()
BODY = SOURCE.split("# BEGIN SM8850_CPU_BANDWIDTH\n", 1)[1].split("# END SM8850_CPU_BANDWIDTH", 1)[0]


class CpuBandwidth(unittest.TestCase):
    def quota(self, pct):
        return subprocess.run(["sh", str(SCRIPT), "--quota-us", str(pct)],
                              capture_output=True, text=True, timeout=3)

    def test_all_budgets(self):
        for pct in range(10, 101):
            with self.subTest(pct=pct):
                p = self.quota(pct)
                self.assertEqual(0, p.returncode, p.stderr)
                self.assertEqual(str(1600 * pct), p.stdout.strip())

    def test_invalid_budget(self):
        for pct in ("", "09", "010", "0", "9", "101", "-1", "1000", "x", "2+8"):
            self.assertNotEqual(0, self.quota(pct).returncode, pct)

    def test_apply_and_verify(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            period = root / "cpu.cfs_period_us"
            quota = root / "cpu.cfs_quota_us"
            period.write_text("20000\n")
            quota.write_text("-1\n")
            def apply(pct, override=""):
                return subprocess.run(["sh", "-c", BODY + "\n" + override +
                                       '\nsm8850_cpu_quota_apply "$@"', "test", td, str(pct)],
                                      capture_output=True, text=True, timeout=3)
            for pct in (40, 10, 40, 100):
                p = apply(pct)
                self.assertEqual(0, p.returncode, (p.stdout, p.stderr))
                self.assertEqual(str(pct * 1600), quota.read_text().strip())
            self.assertNotEqual(0, apply(10, 'sm8850_cpu_quota_write() { :; }').returncode)
            self.assertEqual("160000\n", quota.read_text())
            period.write_text("100000\n")
            self.assertNotEqual(0, apply(10).returncode)
            self.assertEqual("160000\n", quota.read_text())
            period.write_text("20000\n")
            quota.unlink()
            keep = root / "keep"
            keep.write_text("untouched\n")
            quota.symlink_to(keep)
            self.assertNotEqual(0, apply(10).returncode)
            self.assertEqual("untouched\n", keep.read_text())

    def test_probe_has_no_shared_clock_or_parent_quota_writes(self):
        self.assertNotIn("scaling_max_freq", SOURCE)
        self.assertNotIn("scaling_min_freq", SOURCE)
        self.assertNotIn('> "$root/cpu.cfs_', SOURCE)
        self.assertIn('mkdir "$group" || fail create_private_group', SOURCE)
        self.assertIn('flock -n 0 0<&8', SOURCE)
        self.assertIn('rmdir "$group"', SOURCE)


if __name__ == "__main__":
    unittest.main()
