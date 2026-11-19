#!/usr/bin/env python3
"""Exercise the passive observer with a scripted ADB transport."""

import importlib.util
import shlex
import subprocess
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "observe_s26_recovery", Path(__file__).with_name("observe-s26-recovery.py")
)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class FakeAdb:
    def __init__(self, model="SM-S948B", denied=False, duplicate=False):
        self.calls = []
        self.denied = denied
        self.inventory = (
            "event1\t0005\tHUAWEI Band 11\n"
            "event4\t0019\tpmic_resin\n"
            "event9\t0019\tgpio-keys\n"
            "event10\t0005\tgpio-keys\n"
            "event16\t0019\tpmic_pwrkey\n"
            "event0;other\t0019\tgpio-keys\n"
        )
        if duplicate:
            self.inventory += "event22\t0019\tgpio-keys\n"
        self.values = dict(zip(observer.IDENTITY, (
            model, "m3q", "SM8850", "17", "S948BXXS4BZIG",
            "fixture/m3q/observer:17/FAKE/0001:user/test-keys",
        )))
        self.values.update({
            "sys.usb.config": "adb", "sys.usb.state": "adb",
            "sys.usb.controller": "a600000.dwc3", "init.svc.adbd": "running",
            "init.svc.zygote": "running", "sys.boot_completed": "1",
        })

    def __call__(self, args, **kwargs):
        self.calls.append((tuple(args[3:]), kwargs.get("input")))
        assert args[:3] == ["adb", "-s", "fixture-serial"], args
        tail = args[3:]
        if len(tail) == 2 and tail[0] == "shell" and tail[1].startswith("su -c "):
            root_command = shlex.split(tail[1])
            assert root_command[:2] == ["su", "-c"] and len(root_command) == 3, tail
            permissions = shlex.split(root_command[2])
            assert permissions in (["sh", "-s"], ["getevent", "-pl", "/dev/input/event4"],
                                   ["getevent", "-pl", "/dev/input/event9"]), tail
            tail = ["shell", *permissions]
        if tail == ["get-state"]:
            response = "device\n"
        elif tail == ["get-devpath"]:
            response = "usb:1-1\n"
        elif tail[:2] == ["shell", "getprop"] and tail[2] in self.values:
            response = self.values[tail[2]] + "\n"
        elif tail == ["shell", "pidof", "system_server"]:
            response = "321\n"
        elif tail == ["shell", "uname", "-r"]:
            response = "6.12.69-fixture\n"
        elif tail == ["shell", "cat", "/sys/class/udc/a600000.dwc3/state"]:
            response = "configured\n"
        elif tail == ["shell", "sh", "-s"] and kwargs["input"] == observer.INPUT_INVENTORY:
            response = self.inventory
        elif tail in (["shell", "getevent", "-pl", "/dev/input/event4"],
                      ["shell", "getevent", "-pl", "/dev/input/event9"]):
            if self.denied:
                return subprocess.CompletedProcess(args, 1, "", "permission denied")
            key = "KEY_VOLUMEDOWN" if tail[-1].endswith("4") else "KEY_VOLUMEUP"
            response = f"    KEY (0001): {key}*\n"
        else:
            raise AssertionError(f"Unexpected ADB command: {tail}")
        return subprocess.CompletedProcess(args, 0, response, "")


class ObserverTest(unittest.TestCase):
    def observe(self, transport):
        return observer.capture("fixture-serial", 0, False, run=transport)

    def test_input_inventory_is_valid_shell(self):
        result = subprocess.run(
            ["/bin/sh", "-n"], input=observer.INPUT_INVENTORY, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_snapshot_queries_only_approved_inputs_and_reports_fingerprint(self):
        fake = FakeAdb()
        report = self.observe(fake)
        self.assertEqual(report["scope"], "physical-passive")
        self.assertEqual(report["firmware"]["fingerprint"], fake.values["ro.build.fingerprint"])
        self.assertEqual(report["inputs"]["up"]["node"], "/dev/input/event9")
        self.assertEqual(report["inputs"]["down"]["node"], "/dev/input/event4")
        self.assertEqual(report["usb"]["transport"], "usb")
        self.assertEqual(report["framework"]["system_server_present"], True)
        self.assertEqual(report["checks"]["gates_abc"]["status"], "BLOCKED")
        self.assertEqual(report["checks"]["chord"]["status"], "BLOCKED")

    def test_wrong_phone_stops_before_input_or_usb_queries(self):
        fake = FakeAdb(model="SM-S928B")
        report = self.observe(fake)
        self.assertEqual(report["checks"]["target"]["status"], "FAIL")
        self.assertFalse(any("getevent" in args or args == ("get-devpath",) for args, _ in fake.calls))

    def test_ambiguous_sources_and_unreadable_keys_block_capture(self):
        for fake in (FakeAdb(duplicate=True), FakeAdb(denied=True)):
            with self.subTest(duplicate=not fake.denied):
                report = self.observe(fake)
                self.assertEqual(report["checks"]["physical_sources"]["status"], "BLOCKED")

    def test_hold_evidence_requires_three_seconds_without_a_sampling_gap(self):
        def sample(at, held=True):
            return {"start_s": at, "end_s": at + 0.05, "up": held, "down": held}

        self.assertEqual(observer.longest_observed_hold([sample(i / 4) for i in range(14)]), 3.2)
        self.assertLess(observer.longest_observed_hold([sample(i / 4) for i in range(12)]), 3)
        self.assertLess(observer.longest_observed_hold([sample(0), sample(4)]), 3)
        self.assertLess(observer.longest_observed_hold([sample(i / 4, i != 7) for i in range(15)]), 3)

    def test_optional_root_is_limited_to_input_reads(self):
        fake = FakeAdb()
        report = observer.capture("fixture-serial", 0, True, run=fake)
        calls = [args[1] for args, _ in fake.calls if len(args) == 2 and args[1].startswith("su -c ")]
        self.assertEqual(set(calls), {"su -c 'sh -s'", "su -c 'getevent -pl /dev/input/event4'",
                                     "su -c 'getevent -pl /dev/input/event9'"})
        self.assertEqual(report["checks"]["physical_sources"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
