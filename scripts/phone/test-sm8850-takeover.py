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
        for action in ("--recovery-smoke", "--reboot-stage-check", "--reboot-smoke", "--run", "--storage-probe", "--prepare", "--upgrade-kernel"):
            with self.subTest(action=action), patch.object(TAKEOVER, "Phone") as phone, \
                    patch("sys.argv", ["sm8850-takeover.py", action]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                TAKEOVER.main()
            self.assertEqual(2, error.exception.code)
            phone.assert_not_called()

    def test_passive_soft_thermal_mode_requires_180s_before_phone_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            device = unittest.mock.Mock()
            with self.assertRaisesRegex(ValueError, "exactly 180s"):
                TAKEOVER.launch(device, "run", Path(folder), duration=60,
                                passive_soft_thermal=True)
            device.root.assert_not_called()
        src = Path(TAKEOVER.__file__).read_text()
        self.assertIn('experimental_prefix = (', src)
        self.assertIn('f"{experimental_prefix}{shell} --framework-check', src)
        self.assertIn('{experimental_prefix}{shell} --framework-session', src)
        self.assertIn('--passive-soft-thermal-180', src)  # Backward-compatible alias
        self.assertIn('--no-userspace-thermal-180', src)
        self.assertIn('I_ACCEPT_SOFT_GUARD_OFF_180S', src)

    def test_30s_smoke_duration_is_explicit_and_preflight_checked(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(TAKEOVER, "audit", return_value=0), \
             patch.object(TAKEOVER, "upload", return_value=0):
            device = unittest.mock.Mock()
            callback = unittest.mock.Mock()
            for duration in (0, 31, 180, "30"):
                with self.assertRaises(ValueError):
                    TAKEOVER.launch(device, "smoke", Path(folder), reboot_only=True,
                                    smoke_seconds=duration, on_reboot_smoke_ready=callback)
            with self.assertRaises(ValueError):
                TAKEOVER.launch(device, "smoke", Path(folder), reboot_only=True, smoke_seconds=30)
            device.root.assert_not_called()
            device.root.return_value = subprocess.CompletedProcess([], 0, b"PREFLIGHT OK\n")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = TAKEOVER.launch(device, "smoke", Path(folder), reboot_only=True,
                                     smoke_seconds=30, on_reboot_smoke_ready=callback)
            self.assertEqual(2, rc)
            self.assertIn("--framework-check reboot-smoke 30", device.root.call_args.args[0])
            self.assertEqual(1, device.root.call_count)
            callback.assert_not_called()

    def test_30s_smoke_detached_launch_carries_duration(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(TAKEOVER, "audit", return_value=0), \
             patch.object(TAKEOVER, "upload", return_value=0), \
             patch.object(TAKEOVER, "status", return_value="boot=mock-boot\n"), \
             patch.object(TAKEOVER.time, "monotonic", side_effect=[0.0, 1100.0]):
            device = unittest.mock.Mock()
            device.root.side_effect = [
                subprocess.CompletedProcess([], 0, b"SM8850_FRAMEWORK_SMOKE_SECONDS=30\nPREFLIGHT OK\n"),
                subprocess.CompletedProcess([], 0, b""),
            ]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = TAKEOVER.launch(device, "smoke", Path(folder), reboot_only=True,
                                     smoke_seconds=30, on_reboot_smoke_ready=unittest.mock.Mock())
            self.assertEqual(4, rc)
            cmds = [c.args[0] for c in device.root.call_args_list]
            self.assertIn("--framework-check reboot-smoke 30", cmds[0])
            self.assertRegex(cmds[1], r"--framework-session reboot-smoke I_ACCEPT_SM8850_FRAMEWORK_TAKEOVER [a-f0-9]{32} 30")
            switch = (TAKEOVER.ASSETS / "oneios_switch.sh").read_text()
            self.assertIn("FW_SMOKE_SECONDS=20", switch)
            self.assertIn('case "$FW_SMOKE_SECONDS" in 20|30)', switch)
            self.assertIn("fw_seconds=$FW_SMOKE_SECONDS", switch)

    def test_no_guard_preflight_marker_must_match_before_device_launch(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(TAKEOVER, "audit", return_value=0), \
             patch.object(TAKEOVER, "upload", return_value=0):
            device = unittest.mock.Mock()
            device.root.return_value = subprocess.CompletedProcess([], 0, b"PREFLIGHT OK\n")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = TAKEOVER.launch(device, "run", Path(folder), duration=180,
                                     passive_soft_thermal=True)
            self.assertEqual(2, rc)
            commands = [c.args[0] for c in device.root.call_args_list]
            self.assertEqual(1, len(commands))
            self.assertIn("--framework-check run 180 I_ACCEPT_SOFT_GUARD_OFF_180S", commands[0])
            self.assertFalse(any("--framework-session" in command for command in commands))

    def test_detached_run_carries_explicit_no_guard_profile_token(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(TAKEOVER, "audit", return_value=0), \
             patch.object(TAKEOVER, "upload", return_value=0), \
             patch.object(TAKEOVER, "status", return_value="boot=mock-boot\n"), \
             patch.object(TAKEOVER.time, "monotonic", side_effect=[0.0, 1000.0]):
            device = unittest.mock.Mock()
            device.root.side_effect = [
                subprocess.CompletedProcess([], 0, b"SM8850_SOFT_THERMAL_GUARD=OFF_NOT_SPAWNED\nSM8850_CPU_CAP=DISABLED_NO_ROOT_WORKER\nPREFLIGHT OK\n"),
                subprocess.CompletedProcess([], 0, b""),
            ]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                rc = TAKEOVER.launch(device, "run", Path(folder), duration=180,
                                     passive_soft_thermal=True)
            self.assertEqual(4, rc)  # host-only fake never starts a guest
            commands = [c.args[0] for c in device.root.call_args_list]
            self.assertEqual(2, len(commands))
            self.assertIn("--framework-check run 180 I_ACCEPT_SOFT_GUARD_OFF_180S", commands[0])
            self.assertIn("--framework-session run", commands[1])
            self.assertIn("I_ACCEPT_LEGACY_WATCHDOG_FULL_600S_RISK 180 I_ACCEPT_SOFT_GUARD_OFF_180S", commands[1])

    def test_xnuhost_and_oneos_agree_on_no_thermal_guard_stage_proof(self):
        # The 2026-11-23 failed physical run exposed a cross-repo mismatch:
        # OneOS deliberately removed the required thermal worker markers,
        # while xnuhost still rejected the missing markers unconditionally.
        root = TAKEOVER.REPO
        main = (root / "runtime/xnuhost/src/main.c").read_text()
        policy = (root / "runtime/xnuhost/src/sm8850_stage_admission.h").read_text()
        switch = (root / "app/switcher/assets/oneios_switch.sh").read_text()
        wrapper = (root / "scripts/phone/sm8850-full-takeover.sh").read_text()
        self.assertIn('sm8850_stage_line("/data/control/framework.soft-thermal"', main)
        self.assertIn('sm8850_stage_line("/data/control/framework.duration"', main)
        self.assertIn('sm8850_stage_line("/data/control/framework.takeover-confirmed"', main)
        self.assertIn('sm8850_stage_line("/data/control/framework.deadline"', main)
        self.assertIn('xh_sm8850_classify_stage(', main)
        self.assertIn('XH_SM8850_STAGE_REFUSED', main)
        self.assertIn('XH_SM8850_STAGE_NO_USERSPACE_THERMAL_180S', main)
        self.assertIn('disabled-180s', policy)
        self.assertIn('strcmp(framework_stop_confirmed, generation)', policy)
        self.assertIn('!xh_sm8850_positive_decimal(reboot_deadline)', policy)
        self.assertIn("printf 'disabled-180s\\n'", switch)
        self.assertIn('> "$CTL/framework.takeover-confirmed"', switch)
        self.assertIn('> "$CTL/framework.deadline.tmp"', switch)
        self.assertIn('! sm8850_no_userspace_thermal', switch)
        self.assertIn('THERMAL_GUARD=OFF_NO_PROCESS_NO_HEARTBEAT_NO_SOFT_RETURN', switch)
        self.assertIn('CPU_THROTTLE=OFF_NO_ROOT_CAP_WORKER', switch)
        new_runtime_marker = 'SM8850_FULL_BRIDGES=ADMITTED_NO_USERSPACE_THERMAL_180S'
        self.assertIn(new_runtime_marker, main)
        self.assertIn(new_runtime_marker, switch)
        self.assertIn(new_runtime_marker, wrapper)
        self.assertLess(switch.index(new_runtime_marker),
                        switch.index('APFS_DATA_CLONE=CONSUMED_ONE_SHOT_BEFORE_FRAMEWORK_STOP'))

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

    def test_reboot_stage_check_installs_only_after_passive_audit(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(TAKEOVER, "audit", return_value=0) as audit, \
                patch.object(TAKEOVER, "upload", return_value=0) as upload, \
                contextlib.redirect_stdout(io.StringIO()):
            phone = unittest.mock.Mock()
            phone.root.return_value = subprocess.CompletedProcess([], 0, b"PREFLIGHT OK\n")
            self.assertEqual(0, TAKEOVER.reboot_stage_check(phone, Path(folder)))
            audit.assert_called_once_with(phone, Path(folder) / "preflight.txt", reboot_only=True)
            upload.assert_called_once_with(phone, "upgrade")
            self.assertIn("--framework-check reboot-smoke", phone.root.call_args.args[0])
            self.assertEqual("PREFLIGHT OK\n", (Path(folder) / "stage-check.txt").read_text())

    def test_reboot_stage_check_never_uploads_after_refused_audit(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(TAKEOVER, "audit", return_value=1), \
                patch.object(TAKEOVER, "upload") as upload:
            self.assertEqual(2, TAKEOVER.reboot_stage_check(unittest.mock.Mock(), Path(folder)))
            upload.assert_not_called()

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

    def test_operator_key_prompt_only_after_verified_framework_stop(self):
        token = "a" * 32
        base = ("boot=boot1\ncontrol/framework.launch=" + token
                + "\ncontrol/framework.mode=smoke\ncontrol/framework.return=reboot\n"
                + "control/state=starting\nzygote=running pid=101\nsystem_server=202\n")
        self.assertFalse(TAKEOVER.reboot_smoke_ready(base, "boot1", token))
        live = (base.replace("control/state=starting", "control/state=running")
                .replace("zygote=running pid=101", "zygote=stopped pid=")
                .replace("system_server=202", "system_server=")
                + "control/framework.takeover-confirmed=generation\n")
        self.assertTrue(TAKEOVER.reboot_smoke_ready(live, "boot1", token))
        for original, changed in (
            ("boot=boot1", "boot=boot2"),
            ("control/state=running", "control/state=returning"),
            ("control/framework.return=reboot", "control/framework.return=inplace"),
            ("zygote=stopped pid=", "zygote=running pid=101"),
            ("system_server=", "system_server=202"),
            ("control/framework.takeover-confirmed=generation", ""),
        ):
            with self.subTest(original=original):
                self.assertFalse(TAKEOVER.reboot_smoke_ready(live.replace(original, changed), "boot1", token))
        self.assertFalse(TAKEOVER.reboot_smoke_ready(live + "return_request=keys: early\n", "boot1", token))
        self.assertFalse(TAKEOVER.reboot_smoke_ready(live, "boot1", "b" * 32))
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

    def test_deadline_return_acceptance_is_separate_from_physical_keys(self):
        baseline = "boot=boot-old\n"
        after = (
            "boot=boot-new\nboot_completed=1\nboot_reason=reboot,oneios-sm8850-reboot-return\ncontrol/framework.launch=token-123\n"
            "control/framework.mode=smoke\ncontrol/framework.return=reboot\n"
            "control/framework.takeover-confirmed=verified-gen\n"
            "outcome=reboot-deadline-or-manual 123 who=framework-deadline reason=framework deadline reached\n"
            "return_request=framework deadline reached at 123 (deadline 123)\n"
            "zygote=running pid=12\nzygote_next=running pid=15\n"
            "system_server=25\nSELinux=Enforcing\n"
        )
        self.assertTrue(TAKEOVER.reboot_smoke_deadline_verified(baseline, after, "token-123"))
        self.assertFalse(TAKEOVER.reboot_smoke_verified(baseline, after))
        self.assertFalse(TAKEOVER.reboot_smoke_deadline_verified(baseline, after, "another-token"))
        for old, new in (
            ("boot=boot-new", "boot=boot-old"),
            ("boot_completed=1", "boot_completed=0"),
            ("boot_reason=reboot,oneios-sm8850-reboot-return", "boot_reason=reboot,hard"),
            ("control/framework.takeover-confirmed=verified-gen", "control/framework.takeover-confirmed="),
            ("outcome=reboot-deadline-or-manual", "outcome=reboot-key"),
            ("return_request=framework deadline reached", "return_request=watchdog feeder failed"),
            ("zygote=running pid=12", "zygote=stopped pid="),
            ("system_server=25", "system_server="),
            ("SELinux=Enforcing", "SELinux=Permissive"),
        ):
            with self.subTest(field=old):
                self.assertFalse(TAKEOVER.reboot_smoke_deadline_verified(
                    baseline, after.replace(old, new), "token-123",
                ))

    def test_s26_usb_chord_is_not_requested_after_takeover(self):
        from inspect import getsource
        source = getsource(TAKEOVER.launch)
        self.assertNotIn("PHYSICAL_KEYS=PRESS_NOW", source)
        self.assertNotIn("Hold Volume Up + Volume Down", source)
        self.assertIn("PHYSICAL_KEYS=DO_NOT_PRESS_VOLUME_UP_PLUS_DOWN", source)
        self.assertIn("AUTO_REBOOT=EXPECTED_AFTER_{smoke_seconds}_SECOND_FRAMEWORK_DEADLINE", source)
        self.assertNotIn("REBOOT_SMOKE=PASS_AUTOMATIC_DEADLINE_AND_ONEUI", source)
        self.assertIn("REBOOT_SMOKE=DEADLINE_REQUEST_CONFIRMED_ONEUI_OBSERVED", source)
        self.assertIn("UNASSISTED_RETURN_TO_ONEUI=NOT_VERIFIED", source)
        self.assertIn("PHYSICAL_KEY_REBOOT=NOT_VERIFIED", source)

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

    def test_full_run_requires_3d_legacy_consent_and_bounded_duration(self):
        cases = (
            ["--run", "--confirm", "--duration", "600", "--gpu", "auto"],
            ["--run", "--confirm", "--accept-legacy-watchdog-risk", "--duration", "240", "--gpu", "auto"],
            ["--run", "--confirm", "--accept-legacy-watchdog-risk", "--duration", "600", "--gpu", "2d"],
            ["--run", "--confirm", "--accept-legacy-watchdog-risk", "--duration", "30", "--gpu", "3d"],
            ["--run", "--confirm", "--accept-legacy-watchdog-risk", "--duration", "601", "--gpu", "3d"],
        )
        for extra in cases:
            with self.subTest(extra=extra), patch.object(TAKEOVER, "Phone") as phone, \
                    patch("sys.argv", ["sm8850-takeover.py", *extra]), \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exit_code:
                TAKEOVER.main()
            self.assertEqual(2, exit_code.exception.code)
            phone.assert_not_called()

    def test_run_300s_reaches_launcher_without_phone_activity(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(TAKEOVER, "Phone") as phone, \
             patch.object(TAKEOVER, "launch", return_value=0) as launch, \
             patch("sys.argv", ["sm8850-takeover.py", "--run", "--confirm",
                                "--accept-legacy-watchdog-risk", "--gpu", "3d",
                                "--duration", "300", "--output", str(Path(folder) / "run-300s")]), \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, TAKEOVER.main())
            launch.assert_called_once()
            self.assertEqual(300, launch.call_args.kwargs["duration"])
            self.assertTrue((Path(folder) / "run-300s").is_dir())

    def test_full_run_reuses_oneos_legacy_reboot_audit_and_no_new_smoke(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(TAKEOVER, "audit", return_value=1) as audit, \
                patch.object(TAKEOVER, "upload") as upload, \
                contextlib.redirect_stdout(io.StringIO()):
            phone = unittest.mock.Mock()
            self.assertEqual(2, TAKEOVER.launch(phone, "run", Path(folder)))
            audit.assert_called_once_with(
                phone, Path(folder) / "preflight.txt", reboot_only=True
            )
            upload.assert_not_called()

    def test_rootless_post_reboot_diagnostic_uses_only_adb_shell(self):
        phone = unittest.mock.Mock()
        phone.call.return_value = subprocess.CompletedProcess(
            [], 0,
            b"boot=new-boot\nboot_completed=1\n"
            b"boot_reason=reboot,watchdog\n"
            b"system_boot_reason=reboot,watchdog\nzygote=running\n",
        )
        values, raw = TAKEOVER.post_reboot_without_root(phone)
        self.assertEqual("new-boot", values["boot"])
        self.assertEqual("reboot,watchdog", values["boot_reason"])
        self.assertIn("boot_completed=1", raw)
        self.assertEqual(["shell", "-T"], phone.call.call_args.args[0][:2])
        self.assertNotIn("su ", phone.call.call_args.args[0][2])
        self.assertNotIn("reboot ", phone.call.call_args.args[0][2])
        phone.root.assert_not_called()

    def test_rootless_receipt_preserves_earlier_guest_proof_without_certifying_return(self):
        props = {
            "boot": "another-boot",
            "boot_completed": "1",
            "boot_reason": "reboot,oneios-sm8850-reboot-return",
            "zygote": "running",
            "system_server_pid": "29431",
        }
        values = TAKEOVER.full_run_rootless_receipt(
            props, guest_ready=True, display_first_frame=True, cpu_mask=True
        )
        self.assertIn("IOS_GUEST_START_PRE_REBOOT=OBSERVED", values)
        self.assertIn("IOS_GUEST_READY_PRE_REBOOT=OBSERVED", values)
        self.assertIn("IOS_DISPLAY_FIRST_FRAME_PRE_REBOOT=OBSERVED", values)
        self.assertIn("IOS_HOST_CPU_MASK_PRE_REBOOT=0-7_OBSERVED", values)
        self.assertIn("ANDROID_NEW_BOOT=BOOT_COMPLETED_OBSERVED_VIA_UNPRIVILEGED_ADB", values)
        self.assertIn("ANDROID_SYSTEM_SERVER_AFTER_REBOOT=PID_OBSERVED", values)
        self.assertIn("BOOT_REASON=reboot,oneios-sm8850-reboot-return", values)
        self.assertIn("FULL_TAKEOVER_DEADLINE_RETURN=NOT_VERIFIED_NO_ROOT_OUTCOME", values)
        self.assertIn("UNASSISTED_RETURN_TO_ONEUI=NOT_VERIFIED", values)
        self.assertIn("WATCHDOG_QUALIFICATION=UNVERIFIED_REBOOT_ONLY", values)
        self.assertFalse(any("GUEST_START=NOT_VERIFIED" in v for v in values))
        self.assertFalse(any("DEADLINE_RETURN=PASS" in v for v in values))

    def test_rootless_receipt_does_not_invent_unseen_guest_or_boot_processes(self):
        props = {"boot_reason": "reboot,other", "system_server_pid": ""}
        values = TAKEOVER.full_run_rootless_receipt(
            props, guest_ready=True, display_first_frame=False, cpu_mask=False
        )
        self.assertIn("IOS_GUEST_START_PRE_REBOOT=NOT_VERIFIED", values)
        self.assertIn("IOS_DISPLAY_FIRST_FRAME_PRE_REBOOT=NOT_VERIFIED", values)
        self.assertIn("IOS_HOST_CPU_MASK_PRE_REBOOT=NOT_VERIFIED", values)
        self.assertIn("ANDROID_SYSTEM_SERVER_AFTER_REBOOT=NOT_VERIFIED", values)
        self.assertIn("ANDROID_NEW_BOOT=NOT_VERIFIED", values)
        self.assertIn("FULL_TAKEOVER_DEADLINE_RETURN=NOT_VERIFIED_NO_ROOT_OUTCOME", values)

    def test_full_takeover_deadline_receipt_not_unassisted_boot_proof(self):
        baseline = "boot=old\n"
        after = (
            "boot=new\nboot_completed=1\nboot_reason=reboot,oneios-sm8850-reboot-return\n"
            "control/framework.launch=unique-token\ncontrol/framework.mode=run\n"
            "control/framework.return=reboot\ncontrol/framework.takeover-confirmed=gen\n"
            "outcome=reboot-deadline-or-manual 100 who=framework-deadline reason=framework deadline reached\n"
            "return_request=framework deadline reached at 100 (deadline 100)\n"
            "zygote=running pid=10\nzygote_next=running pid=11\n"
            "system_server=12\nSELinux=Enforcing\n"
        )
        fn = TAKEOVER.full_takeover_deadline_result
        self.assertTrue(fn(baseline, after, "unique-token"))
        for src, dest in (
            ("boot=new", "boot=old"),
            ("boot_reason=reboot,oneios-sm8850-reboot-return", "boot_reason=reboot,hard"),
            ("control/framework.mode=run", "control/framework.mode=smoke"),
            ("control/framework.takeover-confirmed=gen", "control/framework.takeover-confirmed="),
            ("who=framework-deadline", "who=watcher"),
            ("return_request=framework deadline reached", "return_request=volume keys"),
            ("system_server=12", "system_server="),
        ):
            with self.subTest(field=src):
                self.assertFalse(fn(baseline, after.replace(src, dest), "unique-token"))

    def test_manifest_requires_sidecars_and_rejects_conflicting_paths(self):
        names = TAKEOVER.REQUIRED | {"image/kernel.kc.trustcache"}
        base = "".join("1" * 64 + "  " + name + "\n" for name in sorted(names))
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
            with self.assertRaisesRegex(ValueError, "trustcache sidecar"):
                TAKEOVER.manifest_bytes(manifest)
            manifest.write_text(base.replace(
                "image/kernel.kc.trustcache\n", "image/overlay/userland/owner-trust.json\n"
            ) + "1" * 64 + "  image/trust/static.trustcache\n")
            self.assertIn(b"owner-trust.json", TAKEOVER.manifest_bytes(manifest))


if __name__ == "__main__":
    unittest.main()
