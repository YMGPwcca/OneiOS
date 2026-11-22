#!/usr/bin/env python3
"""Host-only functional fixture for the SM8850 native runtime refresh.

Extract the real stage function, substitute fake source/stage directories,
then exercise it under a normal unprivileged Linux shell. No ADB, phone,
watchdog, Android Framework, or root writes.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
STAGER = ROOT / "scripts/phone/framework-stage.sh"
NAMES = ("xnuhost", "oneios-display", "oneios-display.dex", "liboneios-display.so")

HARNESS = r"""#!/bin/sh
set -eu
umask 077
stage="$TEST_ROOT/stage"
incoming="$TEST_ROOT/incoming"
TEST_UID=$(id -u)
fail() { echo "STAGING REFUSED: $*" >&2; exit 2; }
root_dir() { [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = "$TEST_UID:700" ]; }
hash_of() { sha256sum "$1" | cut -d' ' -f1; }
install_stage() { :; }
__UPGRADE_FUNCTION__
upgrade_native_runtime
"""


class NativeRuntimeUpgradeFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = STAGER.read_text()
        begin = "# BEGIN SM8850_NATIVE_RUNTIME_UPGRADE\n"
        end = "# END SM8850_NATIVE_RUNTIME_UPGRADE"
        if source.count(begin) != 1 or source.count(end) != 1:
            raise AssertionError("native upgrade function boundaries changed")
        actual = source.split(begin, 1)[1].split(end, 1)[0]
        # The phone's stage is root-owned; only the owner UID changes in
        # this isolated fake directory. Keep permission/link checks intact.
        needle = '= 0:600:1 ]'
        if actual.count(needle) != 1:
            raise AssertionError("root ownership fixture predicate changed")
        actual = actual.replace(needle, '= "$TEST_UID:600:1" ]')
        cls.script = HARNESS.replace("__UPGRADE_FUNCTION__", actual)
        cls.shells = [x for x in (shutil.which("bash"), shutil.which("sh")) if x]

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def fixture(self, root):
        stage = root / "stage"
        incoming = root / "incoming"
        for path in (stage, incoming, stage / "runtime", stage / "runtime/bin", incoming / "native"):
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(0o700)
        (stage / "image.ready").write_text("sm8850-ios27-3d-8cpu-600s\n")
        (stage / "runtime.conf").write_text("version=sm8850-ios27-3d-8cpu-600s\nxnuhost=bin/xnuhost\n")
        (stage / "data.consumed").write_text("consumed\n")
        (stage / "data.consumed").chmod(0o600)
        (stage / "data").mkdir(mode=0o700)
        (stage / "data/data.img").write_text("APFS GUEST STATE: MUST NEVER BE MODIFIED")
        old_manifest = []
        new_manifest = []
        for name in NAMES:
            old = stage / "runtime/bin" / name
            new = incoming / "native" / name
            old.write_bytes((name + "-OLD").encode().ljust(300, b"0"))
            new.write_bytes((name + "-NEW").encode().ljust(400, b"1"))
            old.chmod(0o700 if name in ("xnuhost", "oneios-display") else 0o400)
            new.chmod(0o700)
            old_manifest.append(f"{self.digest(old)}  bin/{name}\n")
            new_manifest.append(f"{self.digest(new)}  {name}\n")
        (stage / "runtime.sha256").write_text("".join(old_manifest))
        (incoming / "native.sha256").write_text("".join(new_manifest))
        return stage, incoming

    def execute(self, root, shell):
        path = root / "native-upgrade-fixture.sh"
        path.write_text(self.script)
        return subprocess.run(
            [shell, str(path)], env={**os.environ, "TEST_ROOT": str(root)},
            capture_output=True, text=True, timeout=25
        )

    def test_upgrades_four_native_files_preserves_old_runtime_and_consumed_data(self):
        for shell in self.shells:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, incoming = self.fixture(root)
                old_data = (stage / "data/data.img").read_bytes()
                old_mark = (stage / "data.consumed").read_bytes()
                old_digests = {n: self.digest(stage / "runtime/bin" / n) for n in NAMES}
                new_digests = {n: self.digest(incoming / "native" / n) for n in NAMES}
                result = self.execute(root, shell)
                self.assertEqual(0, result.returncode, (result.stdout, result.stderr))
                self.assertIn("NATIVE_RUNTIME_UPGRADE=PASS_BACKUP_PRESERVED:", result.stdout)
                self.assertIn("APFS_DATA=CONSUMED_STILL_REQUIRES_SEPARATE_REARM", result.stdout)
                self.assertEqual(old_data, (stage / "data/data.img").read_bytes())
                self.assertEqual(old_mark, (stage / "data.consumed").read_bytes())
                self.assertEqual("sm8850-ios27-3d-8cpu-600s\n", (stage / "image.ready").read_text())
                backups = list((stage / ".rollback").glob("runtime.*"))
                self.assertEqual(1, len(backups))
                for name in NAMES:
                    self.assertEqual(new_digests[name], self.digest(stage / "runtime/bin" / name))
                    self.assertEqual(old_digests[name], self.digest(backups[0] / "runtime/bin" / name))
                self.assertEqual(4, len((stage / "runtime.sha256").read_text().splitlines()))

    def test_rejects_tampered_old_native_before_disarming_stage(self):
        for shell in self.shells:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, _ = self.fixture(root)
                (stage / "runtime/bin/xnuhost").write_bytes(b"tampered")
                result = self.execute(root, shell)
                self.assertEqual(2, result.returncode)
                self.assertIn("native source or installed runtime hash mismatch", result.stderr)
                self.assertTrue((stage / "image.ready").exists())
                self.assertFalse((stage / ".rollback").exists())

    def test_rejects_missing_consumed_marker_before_touching_runtime(self):
        for shell in self.shells:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, _ = self.fixture(root)
                (stage / "data.consumed").unlink()
                result = self.execute(root, shell)
                self.assertEqual(2, result.returncode)
                self.assertIn("requires already-consumed one-shot Data", result.stderr)
                self.assertTrue((stage / "image.ready").exists())
                self.assertFalse((stage / ".rollback").exists())

    def test_rejects_wrong_uploaded_native_digest_before_disarming(self):
        for shell in self.shells:
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                stage, incoming = self.fixture(root)
                native = incoming / "native/xnuhost"
                native.write_bytes(b"wrong")
                result = self.execute(root, shell)
                self.assertEqual(2, result.returncode)
                self.assertIn("invalid incoming native artifact", result.stderr)
                self.assertTrue((stage / "image.ready").exists())


if __name__ == "__main__":
    unittest.main()
