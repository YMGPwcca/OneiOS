#!/usr/bin/env python3
"""Test the actual stage upgrade function with an isolated, unprivileged tree.

No ADB, /data/adb writes, reboot, root permission, or watchdog I/O.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
STAGER = ROOT / "scripts/phone/framework-stage.sh"
BEGIN = "root_file() {\n"
END = '\ncase "$operation" in\n'

HARNESS = r"""#!/bin/sh
set -eu
stage="$TEST_ROOT/stage"
incoming="$TEST_ROOT/incoming"
operation="$TEST_OPERATION"
TEST_UID=$(id -u)
fail() { echo "STAGING REFUSED: $*" >&2; exit 2; }
root_dir() { [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = "$TEST_UID:700" ]; }
getprop() { [ "$1" = init.svc.zygote ] && printf 'running\n'; }
pidof() {
    case "$1" in
        system_server) printf '12345\n'; return 0 ;;
    esac
    [ ! -e "$TEST_ROOT/active-guest" ] || { printf '9876\n'; return 0; }
    return 1
}
__STAGE_FUNCTION__
install_stage
"""


class StageUpgradeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = STAGER.read_text()
        if source.count(BEGIN) != 1 or source.count(END) != 1:
            raise AssertionError("stage upgrade source boundary changed")
        actual = BEGIN + source.split(BEGIN, 1)[1].split(END, 1)[0]
        cls.function = actual.replace(
            '"$(stat -c \'%u:%a\' "$1")" = 0:700',
            '"$(stat -c \'%u:%a\' "$1")" = "$TEST_UID:700"',
        )
        if cls.function == actual:
            raise AssertionError("fixture did not patch root ownership predicate")
        cls.shells = [shutil.which("bash")]
        mksh = os.environ.get("ONEOS_TEST_MKSH") or shutil.which("mksh")
        if mksh:
            cls.shells.append(mksh)
        cls.shells = [p for p in cls.shells if p]
        cls.test_script = HARNESS.replace("__STAGE_FUNCTION__", cls.function)

    @staticmethod
    def prepare(root):
        stage = root / "stage"
        incoming = root / "incoming"
        for dirpath in (stage, incoming, stage / "control"):
            dirpath.mkdir(parents=True, exist_ok=True, mode=0o700)
            dirpath.chmod(0o700)
        (stage / "control/state").write_text("starting\n")
        (stage / "control/boot").write_text("previous-boot-id\n")
        for name in ("oneios_switch.sh", "oneios_return.sh", "oneios-watchdog"):
            (stage / name).write_text("old " + name + "\n")
            (incoming / name).write_text(
                ("old " if name == "oneios-watchdog" else "new ") + name + "\n"
            )
            (stage / name).chmod(0o700)
            (incoming / name).chmod(0o700)
        return stage, incoming

    def execute(self, shell, root, operation="upgrade"):
        script = root / "harness.sh"
        script.write_text(self.test_script)
        env = dict(os.environ, TEST_ROOT=str(root), TEST_OPERATION=operation)
        return subprocess.run(
            [shell, str(script)], env=env,
            capture_output=True, text=True, timeout=10,
        )

    def test_upgrade_saves_original_and_replaces_scripts_on_prior_boot(self):
        for shell in self.shells:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, incoming = self.prepare(root)
                result = self.execute(shell, root)
                self.assertEqual(0, result.returncode, (result.stdout, result.stderr))
                self.assertIn("ONEOS_STAGE_UPGRADE=PASS_BACKUP_PRESERVED", result.stdout)
                saved = list((stage / ".rollback").glob("oneos-compat.*"))
                self.assertEqual(1, len(saved))
                for name in ("oneios_switch.sh", "oneios_return.sh"):
                    self.assertEqual("new " + name + "\n", (stage / name).read_text())
                    self.assertEqual("old " + name + "\n", (saved[0] / name).read_text())
                self.assertTrue((saved[0] / "old.sha256").exists())
                self.assertTrue((saved[0] / "new.sha256").exists())
                self.assertEqual("old oneios-watchdog\n", (stage / "oneios-watchdog").read_text())
                self.assertEqual("starting\n", (stage / "control/state").read_text())
                self.assertEqual("previous-boot-id\n", (stage / "control/boot").read_text())
                matched = self.execute(shell, root, "install")
                self.assertEqual(0, matched.returncode, matched.stderr)
                self.assertEqual(1, len(list((stage / ".rollback").glob("oneos-compat.*"))))

    def test_upgrade_refuses_live_same_boot_session(self):
        for shell in self.shells:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, incoming = self.prepare(root)
                (stage / "control/boot").write_text(
                    Path("/proc/sys/kernel/random/boot_id").read_text()
                )
                result = self.execute(shell, root)
                self.assertEqual(2, result.returncode)
                self.assertIn("experimental session still open", result.stderr)
                self.assertEqual("old oneios_switch.sh\n", (stage / "oneios_switch.sh").read_text())
                self.assertFalse((stage / ".rollback").exists())

    def test_upgrade_refuses_watchdog_binary_change(self):
        for shell in self.shells:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, incoming = self.prepare(root)
                (incoming / "oneios-watchdog").write_text("unexpected native binary\n")
                result = self.execute(shell, root)
                self.assertEqual(2, result.returncode)
                self.assertIn("native watchdog supervisor changed", result.stderr)
                self.assertEqual("old oneios_switch.sh\n", (stage / "oneios_switch.sh").read_text())

    def test_upgrade_refuses_live_guest(self):
        for shell in self.shells:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, incoming = self.prepare(root)
                (root / "active-guest").touch()
                result = self.execute(shell, root)
                self.assertEqual(2, result.returncode)
                self.assertIn("guest or display helper active", result.stderr)
                self.assertFalse((stage / ".rollback").exists())


if __name__ == "__main__":
    unittest.main()
