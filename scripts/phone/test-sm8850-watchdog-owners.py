#!/usr/bin/env python3
"""Host-side regression for fast read-only SM8850 watchdog FD inventory."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "sm8850-watchdog-owners.c"


class WatchdogOwnerScanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which(os.environ.get("CC", "cc"))
        if not cls.compiler:
            raise unittest.SkipTest("Host C compiler unavailable")
        cls.folder = tempfile.TemporaryDirectory(prefix="oneios-fdscan-test-")
        cls.binary = Path(cls.folder.name) / "fdscan"
        subprocess.run(
            [cls.compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-O2", str(SOURCE), "-o", str(cls.binary)],
            check=True, capture_output=True, text=True,
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "folder"):
            cls.folder.cleanup()

    def test_multiple_named_watchdog_holders_without_device_open(self):
        with tempfile.TemporaryDirectory() as path:
            proc = Path(path) / "proc"
            entries = [
                ("11", "system_server", "121", "/dev/watchdog"),
                ("12", "watchdogd", "4", "/dev/watchdog0"),
                ("13", "init", "5", "/dev/softdog1"),
                ("14", "other", "8", "/dev/null"),
                ("15", "invisible", "99", "/dev/char/10:130"),
            ]
            for pid, comm, fd, target in entries:
                fd_dir = proc / pid / "fd"
                fd_dir.mkdir(parents=True)
                (proc / pid / "comm").write_text(comm + "\n")
                (fd_dir / fd).symlink_to(target)
            (proc / "16").mkdir()  # Raced process without an fd directory.
            command = subprocess.run(
                [str(self.binary), str(proc)],
                capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(0, command.returncode, command.stderr)
            output = command.stdout
            self.assertIn("WATCHDOG_FDS=4\n", output)
            self.assertIn("holder=11 comm=system_server fd=121 target=/dev/watchdog", output)
            self.assertIn("holder=12 comm=watchdogd fd=4 target=/dev/watchdog0", output)
            self.assertIn("holder=13 comm=init fd=5 target=/dev/softdog1", output)
            self.assertIn("holder=15 comm=invisible fd=99 target=/dev/char/10:130", output)
            self.assertNotIn("holder=14", output)
            self.assertIn("PROCESSES_SEEN=6", output)
            self.assertIn("FD_LINKS_SCANNED=5", output)
            self.assertIn("FD_DIR_RACE_ERRORS=1", output)
            self.assertIn("SCAN_COVERAGE=COMPLETE_FOR_VISIBLE_PROCESSES", output)
            self.assertIn("WATCHDOG_DEVICE_OPEN_ATTEMPTED=NO", output)
            self.assertIn("FRAMEWORK_STOP_ATTEMPTED=NO", output)

    def test_empty_proc_is_not_reported_as_busy(self):
        with tempfile.TemporaryDirectory() as path:
            result = subprocess.run(
                [str(self.binary), path], capture_output=True,
                text=True, timeout=5,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("WATCHDOG_FDS=0", result.stdout)
            self.assertIn("FD_LINKS_SCANNED=0", result.stdout)

    def test_invalid_proc_path_fails_instead_of_reporting_no_owners(self):
        with tempfile.TemporaryDirectory() as path:
            result = subprocess.run(
                [str(self.binary), str(Path(path) / "missing")],
                capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(2, result.returncode)
            self.assertIn("opendir proc", result.stderr)


if __name__ == "__main__":
    unittest.main()
