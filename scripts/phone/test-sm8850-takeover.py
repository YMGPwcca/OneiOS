#!/usr/bin/env python3
"""Host-only tests for takeover argument safety and artifact admission."""

import contextlib
import importlib.util
import io
import json
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
        for action in ("--recovery-smoke", "--reboot-smoke", "--run", "--storage-probe", "--prepare"):
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

    def test_reboot_audit_is_passive_and_selects_dedicated_mode(self):
        with patch.object(TAKEOVER, "Phone") as phone:
            device = phone.return_value
            device.root.return_value = subprocess.CompletedProcess([], 0, b"WATCHDOG_QUALIFICATION=UNVERIFIED_REBOOT_ONLY\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, TAKEOVER.audit(device, reboot_only=True))
            command = device.root.call_args.args[0]
            self.assertEqual("/system/bin/sh -s -- --framework-audit-reboot", command)
            self.assertIn(b"framework_legacy_target", device.root.call_args.kwargs["input"])

    def test_reboot_smoke_rejects_missing_separate_risk_consent(self):
        with patch.object(TAKEOVER, "Phone") as phone, \
                patch("sys.argv", ["sm8850-takeover.py", "--reboot-smoke", "--confirm"]), \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            TAKEOVER.main()
        self.assertEqual(2, error.exception.code)
        phone.assert_not_called()

    def test_reboot_smoke_refusal_precedes_any_staging(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(TAKEOVER, "upload") as upload, \
                patch.object(TAKEOVER, "Phone") as phone, contextlib.redirect_stdout(io.StringIO()):
            device = phone.return_value
            device.root.return_value = subprocess.CompletedProcess([], 1, b"BLOCKED: legacy watchdog\n")
            self.assertEqual(2, TAKEOVER.launch(device, "smoke", Path(folder), reboot_only=True))
            upload.assert_not_called()
            self.assertIn("--framework-audit-reboot", device.root.call_args.args[0])

    def test_reboot_smoke_requires_key_proof_on_healthy_new_boot(self):
        baseline = "boot=old\nzygote=running pid=1\nsystem_server=12\n"
        after = (
            "boot=new\nboot_completed=1\ncontrol/framework.mode=smoke\ncontrol/framework.return=reboot\n"
            "control/framework.takeover-confirmed=gen\n"
            "outcome=reboot-key 123 who=watcher reason=keys: Volume Up + Volume Down\n"
            "zygote=running pid=2\nzygote_next=running pid=3\n"
            "system_server=40\nSELinux=Enforcing\n"
        )
        self.assertTrue(TAKEOVER.reboot_smoke_verified(baseline, after))
        for old, new in (
            ("boot=new", "boot=old"),
            ("boot_completed=1", "boot_completed=0"),
            ("control/framework.return=reboot", "control/framework.return=inplace"),
            ("control/framework.takeover-confirmed=gen", "control/framework.takeover-confirmed="),
            ("outcome=reboot-key", "outcome=reboot-deadline-or-manual"),
            ("system_server=40", "system_server="),
            ("SELinux=Enforcing", "SELinux=Permissive"),
        ):
            with self.subTest(field=old):
                self.assertFalse(TAKEOVER.reboot_smoke_verified(baseline, after.replace(old, new)))

    def test_readiness_reports_blockers_without_phone_modifications(self):
        baseline = ("boot=abc\nzygote=running pid=12\nsystem_server=30\n"
                    "SELinux=Enforcing\nimage_ready=0\nsmoke_current_boot=0\n"
                    "framework_app_cgroup_draining=blocked\n")
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(TAKEOVER, "upload", side_effect=AssertionError("no upload")), \
                 patch.object(TAKEOVER, "launch", side_effect=AssertionError("no launch")), \
                 patch.object(TAKEOVER, "status", return_value=baseline), \
                 patch("builtins.print"):
                phone = unittest.mock.Mock()
                phone.root.return_value = subprocess.CompletedProcess(
                    [], 1, b"BLOCKED: watchdog\n")
                self.assertEqual(0, TAKEOVER.readiness(phone, Path(folder)))
                self.assertEqual(1, phone.root.call_count)
                self.assertEqual("/system/bin/sh -s -- --framework-audit",
                                 phone.root.call_args.args[0])
                report = json.loads((Path(folder) / "readiness.json").read_text())
                self.assertEqual("SM8850_TAKEOVER_GATE0", report["phase"])
                self.assertFalse(report["live_takeover_authorized"])
                self.assertEqual(1, report["audit_exit_code"])
                self.assertIn("BLOCKED: watchdog", report["blockers"])
                self.assertIn("Independent takeover image/Data stage not finalized",
                              report["blockers"])
                self.assertIn("No verified recovery smoke accepted on the current boot",
                              report["blockers"])
                self.assertIn("At least one Android app cgroup cannot be drained by the current script",
                              report["blockers"])

    def test_readiness_pass_does_not_approve_live_takeover(self):
        healthy = ("zygote=running pid=123\nsystem_server=456\nSELinux=Enforcing\n"
                   "image_ready=1\nsmoke_current_boot=1\n")
        report = TAKEOVER.interpret_readiness(0, "framework target: ok\n", healthy)
        self.assertTrue(report["audit_pass"])
        self.assertEqual([], report["blockers"])
        self.assertFalse(report["live_takeover_authorized"])

    def test_readiness_cli_needs_no_confirm_and_never_launches(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(TAKEOVER, "Phone") as phone, \
                 patch.object(TAKEOVER, "readiness", return_value=0) as readiness, \
                 patch.object(TAKEOVER, "launch", side_effect=AssertionError("no launch")), \
                 patch("sys.argv", ["sm8850-takeover.py", "--readiness", "--output", str(Path(folder) / "readiness")]):
                self.assertEqual(0, TAKEOVER.main())
                phone.assert_called_once()
                readiness.assert_called_once_with(phone.return_value, Path(folder) / "readiness")

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
