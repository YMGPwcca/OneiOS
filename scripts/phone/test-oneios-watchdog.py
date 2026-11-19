#!/usr/bin/env python3
"""Run the native supervisor against a link-time fake watchdog."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "app/switcher/native/oneios_watchdog.c"
FAKE = Path(__file__).with_name("watchdog-fake.c")
GEN = "fixture.42"


class SupervisorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.bin = Path(cls.tmp.name) / "supervisor"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", SOURCE, FAKE,
                        *[f"-Wl,--wrap={name}" for name in
                          ("open", "lstat", "fstat", "ioctl", "write", "close")],
                        "-o", cls.bin], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.session = tempfile.TemporaryDirectory()
        self.addCleanup(self.session.cleanup)
        self.ctrl = Path(self.session.name)
        (self.ctrl / "watchdog.generation").write_text(GEN + "\n")

    def start(self, fault="", nowayout=1):
        arm = int(time.clock_gettime(time.CLOCK_BOOTTIME))
        process = subprocess.Popen([self.bin, self.ctrl, "/dev/watchdog0", "f2:0",
                                    GEN, "101", str(arm), str(nowayout), "120", "20"],
                                   env=dict(os.environ, WD_FAKE_FAULT=fault), start_new_session=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
                process.wait()
        self.addCleanup(cleanup)
        return process

    def read(self, name):
        try:
            return (self.ctrl / name).read_text().strip()
        except FileNotFoundError:
            return ""

    def wait_for(self, name, value):
        until = time.monotonic() + 6
        while time.monotonic() < until:
            if value in self.read(name):
                return
            time.sleep(.02)
        self.fail(f"{name} lacks {value!r}. Actual {self.read(name)!r}")

    def close_request(self):
        (self.ctrl / "feeder.off").touch()

    def test_ebusy_then_delayed_release_and_keep_armed_handback(self):
        process = self.start("busy-three")
        self.wait_for("watchdog.phase", "SUPERVISOR_OWNS")
        self.assertEqual(str(process.pid), self.read("feeder.ready"))
        self.close_request()
        self.assertEqual(0, process.wait(6))
        self.assertIn(f"{GEN} {process.pid} 101 1 ", self.read("feeder.released"))
        self.assertRegex(self.read("fake.trace"), r"^EEEOP{2,}C$")
        self.assertEqual(f"{GEN} RETURN_PENDING", self.read("watchdog.phase"))

    def test_disarmable_branch_uses_magic_once_only_at_close(self):
        process = self.start(nowayout=0)
        self.wait_for("watchdog.phase", "SUPERVISOR_OWNS")
        self.close_request()
        self.assertEqual(0, process.wait(6))
        self.assertRegex(self.read("fake.trace"), r"^OP+VC$")
        self.assertIn(" 101 0 ", self.read("feeder.released"))

    def test_busy_deadline_never_announces_ownership(self):
        self.assertNotEqual(0, self.start("busy").wait(6))
        self.assertEqual("", self.read("feeder.ready"))
        self.assertIn("EBUSY", self.read("feeder.failed"))
        self.assertNotIn("O", self.read("fake.trace"))

    def test_unavailable_node_or_bad_descriptor_metadata_fails_closed(self):
        for fault in ("unavailable", "bad-timeout", "bad-device", "bad-identity", "pretimeout"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                old = self.ctrl
                try:
                    self.ctrl = Path(folder)
                    (self.ctrl / "watchdog.generation").write_text(GEN + "\n")
                    self.assertNotEqual(0, self.start(fault).wait(6))
                    self.assertEqual("", self.read("feeder.ready"))
                    self.assertTrue(self.read("feeder.failed"))
                    self.assertNotIn("P", self.read("fake.trace"))
                finally:
                    self.ctrl = old

    def test_heartbeat_failure_and_process_death_cannot_certify_release(self):
        process = self.start("ping-error")
        self.wait_for("watchdog.phase", "SUPERVISOR_OWNS")
        self.assertNotEqual(0, process.wait(6))
        self.assertIn("heartbeat", self.read("feeder.failed"))
        self.assertEqual("", self.read("feeder.released"))

    def test_supervisor_crash_publishes_no_release_and_uses_no_magic(self):
        process = self.start(nowayout=0)
        self.wait_for("watchdog.phase", "SUPERVISOR_OWNS")
        process.kill()
        self.assertLess(process.wait(6), 0)
        self.assertEqual("", self.read("feeder.released"))
        self.assertNotIn("V", self.read("fake.trace"))

    def test_handback_with_insufficient_time_left_fails_without_magic(self):
        process = self.start("short-handback")
        self.wait_for("watchdog.phase", "SUPERVISOR_OWNS")
        self.close_request()
        self.assertNotEqual(0, process.wait(6))
        self.assertEqual("", self.read("feeder.released"))
        self.assertIn("handback", self.read("feeder.failed"))

    def test_release_receipt_waits_for_descriptor_close(self):
        process = self.start("delay-close")
        self.wait_for("watchdog.phase", "SUPERVISOR_OWNS")
        self.close_request()
        self.wait_for("fake.trace", "B")
        self.assertEqual("", self.read("feeder.released"))
        self.assertEqual(0, process.wait(6))
        self.assertRegex(self.read("fake.trace"), r"^OP{2,}BC$")
        self.assertTrue(self.read("feeder.released"))


if __name__ == "__main__":
    unittest.main()
