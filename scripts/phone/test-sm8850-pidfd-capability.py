#!/usr/bin/env python3
"""Offline host tests for benign-only SM8850 pidfd_getfd capability probe."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "sm8850-pidfd-capability.c"
WRAPPER = ROOT / "sm8850-pidfd-capability.sh"


class PidfdCapabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which(os.environ.get("CC", "cc"))
        if not cc:
            raise unittest.SkipTest("host cc unavailable")
        cls.folder = tempfile.TemporaryDirectory(prefix="oneios-pidfd-cap-")
        cls.binary = Path(cls.folder.name) / "probe"
        subprocess.run(
            [cc, "-std=c11", "-Wall", "-Wextra", "-Werror", "-O2",
             str(SOURCE), "-o", str(cls.binary)],
            check=True, capture_output=True, text=True,
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "folder"):
            cls.folder.cleanup()

    def test_only_benign_target_and_no_watchdog_operations(self):
        source = SOURCE.read_text()
        wrapper = WRAPPER.read_text()
        self.assertIn('strcmp(target, "/dev/null")', source)
        self.assertIn("major(st.st_rdev) == 1 && minor(st.st_rdev) == 3", source)
        self.assertNotIn('open("/dev/watchdog', source)
        self.assertNotIn('syscall(SYS_ioctl', source)
        self.assertIn("WATCHDOG_FD_DUPLICATED=NO", wrapper)
        self.assertNotIn("--reboot-smoke", wrapper)
        self.assertNotIn("--framework-session", wrapper)

    def test_selftest_does_not_claim_support_when_blocked(self):
        run = subprocess.run(
            [str(self.binary), "--selftest"], capture_output=True,
            text=True, timeout=5,
        )
        self.assertIn(run.returncode, (0, 3, 4),
                      f"unexpected result code: {run.returncode}\n{run.stdout}\n{run.stderr}")
        self.assertRegex(
            run.stdout, r"PIDFD_PROBE=(SUPPORTED_BENIGN_FD_ONLY|BLOCKED_PIDFD_OPEN|BLOCKED_GETFD|NO_BENIGN_FD)",
        )

    def test_invalid_arguments_refuse_untrusted_target(self):
        for args in (
            [], ["--system-server", "0"], ["--system-server", "-1"],
            ["--system-server", "nan"], ["--system-server", "999999999"],
            ["--watchdog", "121"],
        ):
            with self.subTest(args=args):
                out = subprocess.run(
                    [str(self.binary), *args], capture_output=True,
                    text=True, timeout=5,
                )
                self.assertEqual(2, out.returncode)

    def test_not_system_server_refused_without_syscall(self):
        result = subprocess.run(
            [str(self.binary), "--system-server", str(os.getpid())],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("PIDFD_PROBE=BLOCKED_TARGET_NOT_SYSTEM_SERVER", result.stdout)


if __name__ == "__main__":
    unittest.main()
