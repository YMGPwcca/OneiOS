#!/usr/bin/env python3
"""Offline tests of the actual retired Data cleanup, with sparse fake files."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HELPER = Path(__file__).with_name("framework-prune-retired-data.sh")


class RetiredDataPrune(unittest.TestCase):
    def run_case(self, fault=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, bench = root / "stage", root / "bench"
            retired = stage / ".retired-data" / "consumed.ABC123xy"
            for d in (stage, bench, stage / "control", stage / ".retired-data", retired,
                      retired / "data", stage / "data", bench / "data", stage / ".rollback"):
                d.mkdir(mode=0o700)
            def write(path, data):
                path.write_text(data)
                path.chmod(0o600)
            write(stage / "image.ready", "sm8850-ios27-3d-8cpu-600s\n")
            write(stage / ".rollback/keep", "keep rollback\n")
            token = "7502432e-441c-4a05-bc26-251e748f0d48 " + "a" * 32 + "\n"
            write(stage / "data.consumed", token)
            write(retired / "data.consumed", token)
            manifest = "a" * 64 + "  data.img\n" + "b" * 64 + "  unique-chip-id\n"
            for name in ("consumed-data.sha256", "rearm-source.sha256"):
                write(retired / name, manifest)
            for d in (stage / "data", bench / "data", retired / "data"):
                write(d / "unique-chip-id", "12345678")
                write(d / "data.img", "payload")
                with (d / "data.img").open("r+b") as f:
                    f.truncate(8589934592)
            (root / "mountinfo").write_text("")
            (root / "boot").write_text("current\n")
            payload = retired / "data/data.img"
            if fault == "symlink":
                payload.unlink()
                payload.symlink_to(stage / "data/data.img")
            elif fault == "hardlink":
                payload.unlink()
                os.link(stage / "data/data.img", payload)
            elif fault == "receipt":
                (retired / "rearm-source.sha256").write_text("invalid\n")
            elif fault == "pending":
                write(stage / "image.ready.kernel-pending", "pending\n")
            elif fault == "mount":
                (root / "mountinfo").write_text(f"1 1 1:1 / {stage}/.retired-data rw - tmpfs tmpfs rw\n")
            elif fault == "active":
                write(stage / "control/state", "running\n")
                write(stage / "control/boot", "current\n")
            elif fault == "archive_symlink":
                (stage / ".retired-data/consumed.ZZZ123xy").symlink_to(retired)
            body = HELPER.read_text().replace("= 0:600:1", '= "$TEST_UID:600:1"').replace(
                "/proc/1/mountinfo /proc/self/mountinfo", '"$TEST_ROOT/mountinfo"').replace(
                "/proc/sys/kernel/random/boot_id", '"$TEST_ROOT/boot"')
            harness = r'''set -eu
stage="$TEST_ROOT/stage"
bench="$TEST_ROOT/bench"
TEST_UID=$(id -u)
fail() { echo "REFUSED $*" >&2; exit 2; }
root_dir() { [ ! -L "$1" ] && [ "$(stat -c '%u:%a' "$1")" = "$TEST_UID:700" ]; }
getprop() { case "$1" in sys.boot_completed) echo 1 ;; init.svc.zygote) echo running ;; esac; }
getenforce() { echo Enforcing; }
pidof() { [ "$1" = system_server ]; }
sync() { :; }
'''+body+'\nprune_retired_data_locked\n'
            def execute():
                return subprocess.run(["sh", "-c", harness], env={**os.environ, "TEST_ROOT": directory},
                                      capture_output=True, text=True, timeout=10)
            p = execute()
            self.assertEqual(2 if fault else 0, p.returncode, (p.stdout, p.stderr))
            self.assertEqual(bool(fault), payload.exists())
            self.assertEqual(bool(fault), (retired / "data/unique-chip-id").exists())
            for keep in (stage / "data/data.img", bench / "data/data.img", stage / ".rollback/keep",
                         stage / "data.consumed", retired / "data.consumed", retired / "consumed-data.sha256"):
                self.assertTrue(keep.is_file(), keep)
            if not fault:
                self.assertIn("RETIRED_DATA_FILES_PRUNED=2", p.stdout)
                again = execute()
                self.assertEqual(0, again.returncode, (again.stdout, again.stderr))
                self.assertIn("RETIRED_DATA_FILES_PRUNED=0", again.stdout)

    def test_prune_and_idempotence(self):
        self.run_case()

    def test_refuses_unsafe_cases_before_deletion(self):
        for fault in ("symlink", "hardlink", "receipt", "pending", "mount", "active", "archive_symlink"):
            with self.subTest(fault=fault):
                self.run_case(fault)


if __name__ == "__main__":
    unittest.main()
