#!/usr/bin/env python3
"""Offline, no-ADB acceptance tests for the SM8850 GPU evidence tool."""
import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

TOOL_PATH = Path(__file__).with_name("sm8850-gpu-acceptance.py")
spec = importlib.util.spec_from_file_location("sm8850_gpu_acceptance", TOOL_PATH)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

GOOD_DEVICE = {
    "uid": "0", "model": "SM-S948B", "device": "m3q", "soc": "SM8850",
    "build": "S948BXXS4BZIG", "fingerprint": "samsung/m3qxxx/m3q:17/x/S948BXXS4BZIG:user/release-keys",
    "boot_completed": "1", "zygote": "running", "system_server": "yes",
    "selinux": "Enforcing", "guest_running": "no", "takeover_state": "absent",
    "free_kib": str(tool.MIN_FREE_KIB + 100000), "battery_pct": "65",
    "battery_temp_decic": "320", "timeout": "yes", "map_count": "65530",
}

SUCCESS_GUEST = '''
xnuhost I placed: boot_args "debug=1 vgpu-3d=1 sheng-vsync=60"
guest oneios-gpu: virtio GPU with the DRM native context (features 0x100000059)
guest oneios-vk-init pid=52 Turnip backend=DRM native
guest oneios-vk-init pid=52 Turnip DRM native IOServiceOpen type=0x4149 status=0
guest oneios-vk-init pid=52 vkEnumeratePhysicalDevices result=0 device_count=1
guest oneios-vk-init pid=52 vkCreateDevice device="Adreno 840" result=0
xnuhost I gpu: 10 s host: backboardd fences 4, submit->retired mean 1500 us
'''

SUCCESS_HOST = '''
capset: DRM (6), 160 bytes: wire format 2, msm 1.12, context type 1, chip 0x44050a00, gpu id 6860, GPU addresses 0x4000000000 + 192 GiB
submit: queue 20, 256 bytes of commands at 0x4001000000 run by the GPU, fence retired after 6.14 ms; GPU faults 0, async errors 0
ok
'''


class GPUAcceptanceTests(unittest.TestCase):
    def test_preflight_approved_phone(self):
        checks, failure = tool.validate_preflight(GOOD_DEVICE)
        self.assertFalse(failure)
        self.assertTrue(all(checks.values()))

    def test_preflight_rejects_wrong_firmware_guest_takeover_or_low_space(self):
        for name, value, expected in (
            ("model", "SM-S928B", "target"),
            ("fingerprint", "samsung/other", "firmware"),
            ("guest_running", "yes", "no_guest"),
            ("takeover_state", "running", "no_takeover"),
            ("free_kib", str(tool.MIN_FREE_KIB - 1), "space"),
            ("battery_temp_decic", "460", "temperature"),
            ("selinux", "Permissive", "selinux"),
            ("timeout", "no", "timeout"),
        ):
            with self.subTest(name=name):
                data = {**GOOD_DEVICE, name: value}
                _, failures = tool.validate_preflight(data)
                self.assertIn(expected, failures)

    def test_storage_diagnostics_report_exact_deficit_and_unknown(self):
        actual = tool.storage_summary({**GOOD_DEVICE, "free_kib": str(tool.MIN_FREE_KIB - 1025)})
        self.assertEqual(tool.MIN_FREE_KIB - 1025, actual["free_kib"])
        self.assertEqual(tool.MIN_FREE_KIB, actual["required_kib"])
        self.assertEqual(1025, actual["deficit_kib"])
        self.assertEqual(30 * 1024 * 1024, actual["reserve_kib"])
        self.assertEqual(65536, actual["probe_headroom_kib"])
        self.assertIsNone(tool.storage_summary({})["free_kib"])
        self.assertIsNone(tool.storage_summary({})["deficit_kib"])

    def test_missing_fields_fail_closed(self):
        _, failures = tool.validate_preflight({})
        self.assertGreaterEqual(len(failures), 8)

    def test_host_submit_accepts_only_fault_free_adreno_and_capset(self):
        self.assertTrue(tool.host_submit_pass(SUCCESS_HOST))
        self.assertFalse(tool.host_submit_pass(SUCCESS_HOST.replace("GPU faults 0", "GPU faults 1")))
        self.assertFalse(tool.host_submit_pass(SUCCESS_HOST.replace("gpu id 6860", "gpu id 6850")))
        self.assertFalse(tool.host_submit_pass("submit: queue 20, fence retired\nok\n"))

    def test_guest_requires_every_distinct_gpu_milestone(self):
        complete = tool.analyze_guest(SUCCESS_GUEST)
        self.assertEqual("PASS", complete["IOS_VULKAN"])
        self.assertEqual("NOT_EVALUATED", complete["GUI_STABLE"])
        for omitted in SUCCESS_GUEST.splitlines():
            if not omitted.strip():
                continue
            with self.subTest(omit=omitted[:40]):
                outcome = tool.analyze_guest(SUCCESS_GUEST.replace(omitted, ""))
                self.assertEqual("UNVERIFIED", outcome["IOS_VULKAN"])

    def test_library_load_and_host_submit_are_not_guest_vulkan(self):
        log = "guest oneios-gpu-plugin: backboardd library validation of NativeAdrenoMetal: error 0\n"
        log += "guest oneios-gpu-open: backboardd AGXAccelerator type 0x4149 -> 0\n"
        log += SUCCESS_HOST
        report = tool.analyze_guest(log)
        self.assertEqual("UNVERIFIED", report["IOS_VULKAN"])

    def test_guest_failure_and_abort_are_separate(self):
        report = tool.analyze_guest(SUCCESS_GUEST +
            "guest oneios-gpu-text: backboardd PUB no device: device: Vulkan(VkResultCode(-3))\n" +
            "guest sheng-exit: backboardd[52] status 0x6\n")
        self.assertEqual("UNVERIFIED", report["IOS_VULKAN"])
        self.assertEqual("FAIL", report["GUI_STABLE"])

    def test_selects_usb_only(self):
        with patch.object(tool, "run", return_value=SimpleNamespace(stdout=(
                "List of devices attached\nABC123 device usb:1-2 product:m3q\n"))):
            self.assertEqual(["adb", "-s", "ABC123"], tool.select_usb("adb"))
        with patch.object(tool, "run", return_value=SimpleNamespace(stdout=(
                "List of devices attached\n192.168.1.2:5555 device product:m3q\n"))):
            with self.assertRaises(tool.Blocked):
                tool.select_usb("adb")

    def test_analyze_requires_no_hardware(self):
        with patch.object(tool, "select_usb", side_effect=AssertionError("should not use ADB")):
            self.assertEqual("PASS", tool.analyze_guest(SUCCESS_GUEST)["IOS_VULKAN"])


if __name__ == "__main__":
    unittest.main()
