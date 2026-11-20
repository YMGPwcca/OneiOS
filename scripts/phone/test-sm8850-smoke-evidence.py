#!/usr/bin/env python3
"""Offline-only tests for archived SM8850 reboot smoke inspection."""

import contextlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

FILE = Path(__file__).with_name("inspect-sm8850-smoke.py")
spec = importlib.util.spec_from_file_location("smoke_evidence", FILE)
INSPECTOR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(INSPECTOR)


class EvidenceTest(unittest.TestCase):
    def test_reads_archived_switch_and_return_logs_without_extracting(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "baseline.txt").write_text("boot=first\n")
            (folder / "timeline.txt").write_text(
                "2026-11-20\nboot=first\ncontrol/state=starting\n"
                "boot=first\ncontrol/state=returned\nlaunch_exit=4\n"
            )
            entries = {
                "return.outcome": "inplace return completed\n",
                "control/stopped": "marker\n",
                "launches/token/switch.log": "EARLY PREFLIGHT REFUSAL\n",
                "return.log": "Return to One UI\n",
            }
            with tarfile.open(folder / "device-logs.tar", "w") as archive:
                for name, content in entries.items():
                    data = content.encode()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = INSPECTOR.inspect(folder)
            self.assertEqual(0, rc)
            self.assertIn("TAKEOVER_MARKER=ABSENT", out.getvalue())
            self.assertIn("STOP_MARKER=PRESENT", out.getvalue())
            self.assertIn("EARLY PREFLIGHT REFUSAL", out.getvalue())
            self.assertIn("PHYSICAL_KEY_REBOOT=NOT_VERIFIED", out.getvalue())
            self.assertFalse((folder / "launches").exists(), "must not extract tar contents")

    def test_missing_archive_fails_without_phone(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = INSPECTOR.inspect(Path(tmp))
            self.assertEqual(2, rc)
            self.assertIn("ARCHIVE=NOT_AVAILABLE", out.getvalue())


if __name__ == "__main__":
    unittest.main()
