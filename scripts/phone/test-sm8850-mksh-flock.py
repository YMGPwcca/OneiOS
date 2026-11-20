#!/usr/bin/env python3
"""Regression for Android mksh's exec-only high FD close-on-exec behavior.

Toybox flock accepts a numeric FD. An mksh "exec 8>file" opens FD 8
inside the shell but does not make it available to external commands.
Pass the same open file description via command-scoped FD 0 instead,
then keep FD 8 open in the parent shell to hold the lock.
"""

import fcntl
import os
from pathlib import Path
import select
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
MKSH = os.environ.get("ONEOS_TEST_MKSH") or shutil.which("mksh")


class MkshFlockTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MKSH or not os.access(MKSH, os.X_OK):
            raise unittest.SkipTest("mksh is not available")
        if not shutil.which("flock"):
            raise unittest.SkipTest("flock is not available")

    def test_stage_and_switch_use_same_mksh_safe_lock_contract(self):
        paths = (
            ROOT / "scripts/phone/framework-stage.sh",
            ROOT / "app/switcher/assets/oneios_switch.sh",
        )
        for path in paths:
            with self.subTest(path=path):
                source = path.read_text()
                self.assertIn("flock -n 0 0<&8", source)
                self.assertNotIn("flock -n 8", source)
                self.assertRegex(source, r'exec 8>>"[^"]*/start\.lock"')

    def test_fd0_dup_keeps_lock_held_by_parent_mksh(self):
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / "start.lock"
            script = (
                'exec 8>>"$1" || exit 80\n'
                'flock -n 0 0<&8 || exit 81\n'
                'printf "LOCK_HELD\\n"\n'
                'IFS= read -r release\n'
            )
            owner = subprocess.Popen(
                [MKSH, "-c", script, "mksh-lock-test", str(lock)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                ready, _, _ = select.select([owner.stdout], [], [], 5)
                self.assertTrue(ready, "mksh never reported a held lock")
                self.assertEqual("LOCK_HELD", owner.stdout.readline().strip())
                self.assertIsNone(owner.poll(), "holder exited before releasing the lock")

                # Independent Python FD observes the lock after the flock
                # subprocess has already exited; parent mksh must still own it.
                with lock.open("a+") as contender_fd:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

                contender = subprocess.run(
                    [MKSH, "-c", 'exec 8>>"$1"; flock -n 0 0<&8',
                     "mksh-lock-contender", str(lock)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self.assertNotEqual(0, contender.returncode, "second mksh acquired a live lock")
            finally:
                if owner.poll() is None:
                    try:
                        owner.communicate(input="\n", timeout=5)
                    except subprocess.TimeoutExpired:
                        owner.kill()
                        owner.communicate(timeout=5)
                else:
                    owner.communicate(timeout=5)

            with lock.open("a+") as released:
                fcntl.flock(released, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(released, fcntl.LOCK_UN)

    def test_plain_exec_fd8_cannot_be_assumed_inherited(self):
        with tempfile.TemporaryDirectory() as folder:
            lock = Path(folder) / "start.lock"
            # This was the failing syntax on the Samsung Android shell.
            bad = subprocess.run(
                [MKSH, "-c", 'exec 8>>"$1"; flock -n 8',
                 "mksh-lock-test", str(lock)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertNotEqual(0, bad.returncode,
                                "the test environment no longer reproduces mksh FD8 CLOEXEC")


if __name__ == "__main__":
    unittest.main()
