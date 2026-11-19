#!/usr/bin/env python3
"""Host-only tests for takeover argument safety and artifact admission."""

import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location("takeover", Path(__file__).with_name("sm8850-takeover.py"))
TAKEOVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TAKEOVER)


class TakeoverTest(unittest.TestCase):
    def test_change_requires_opt_in_before_contacting_a_device(self):
        for action in ("--recovery-smoke", "--run", "--storage-probe", "--prepare"):
            with self.subTest(action=action), patch.object(TAKEOVER, "Phone") as phone, \
                    patch("sys.argv", ["sm8850-takeover.py", action]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                TAKEOVER.main()
            self.assertEqual(2, error.exception.code)
            phone.assert_not_called()

    def test_recovery_audit_refusal_precedes_staging_and_launch(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(TAKEOVER, "upload") as upload, \
                patch.object(TAKEOVER, "Phone") as phone, contextlib.redirect_stdout(io.StringIO()):
            device = phone.return_value
            device.root.return_value = subprocess.CompletedProcess([], 1, b"BLOCKED: watchdog\n")
            self.assertEqual(2, TAKEOVER.launch(device, "smoke", Path(folder)))
            upload.assert_not_called()
            self.assertEqual(1, device.root.call_count)
            self.assertEqual("/system/bin/sh -s -- --framework-audit", device.root.call_args.args[0])
            self.assertEqual("BLOCKED: watchdog\n", (Path(folder) / "preflight.txt").read_text())

    def test_return_checks_boot_pids_map_limit_and_phase_result(self):
        baseline = """boot=42
vm.max_map_count=65530
adbd=running pid=2818
surfaceflinger=running pid=16338
vendor.qti.hardware.display.composer=running pid=2121
system_server=16913
"""
        after = baseline.replace("system_server=16913", "system_server=25363") + """zygote=running pid=25000
zygote_next=running pid=25001
SELinux=Enforcing
outcome=inplace 43 42
control/framework.result=smoke complete
"""
        self.assertTrue(TAKEOVER.restored_on_same_boot(baseline, after, "smoke"))
        for original, replacement in (("boot=42", "boot=70"), ("65530", "1048576"),
                                      ("pid=2121", "pid=2600"), ("25363", "16913"),
                                      ("inplace", "failsafe"), ("smoke complete", "run complete")):
            with self.subTest(original=original):
                self.assertFalse(TAKEOVER.restored_on_same_boot(baseline, after.replace(original, replacement), "smoke"))

    def test_manifest_requires_sidecars_and_rejects_conflicting_paths(self):
        base = "".join("1" * 64 + "  " + name + "\n" for name in sorted(TAKEOVER.REQUIRED))
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / "approved.sha256"
            manifest.write_text(base)
            self.assertEqual(base.encode(), TAKEOVER.manifest_bytes(manifest))
            for path in ("image/../secrets", "runtime/bin", "runtime/bin/xnuhost-gui-bench",
                         "bench/unapproved", "image/kernel.kc"):
                manifest.write_text(base + "2" * 64 + "  " + path + "\n")
                with self.assertRaises(ValueError):
                    TAKEOVER.manifest_bytes(manifest)
            manifest.write_text(base.replace("image/kernel.kc.trustcache\n", "image/different\n"))
            with self.assertRaisesRegex(ValueError, "kernel.kc.trustcache"):
                TAKEOVER.manifest_bytes(manifest)


if __name__ == "__main__":
    unittest.main()
