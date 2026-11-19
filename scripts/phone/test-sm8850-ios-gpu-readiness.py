#!/usr/bin/env python3
"""No-ADB tests for the conservative guest image readiness inventory."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("readiness", Path(__file__).with_name("sm8850-ios-gpu-readiness.py"))
readiness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(readiness)


def sample(missing=None):
    lines = []
    for i, name in enumerate(readiness.SOURCE_FILES):
        size = (readiness.DATA_BYTES if name == "data/data.img" else 8 if name == "data/unique-chip-id" else 100)
        lines.append(f"FILE|{name}|" + ("MISSING" if name == missing else f"{size}:1:2000:600:123:{i+1}"))
    for name in ("image/xnuhost.conf", "image/overlay/userland/xnuhost.conf"):
        lines += [f"CONFIG|{name}|BEGIN", "LINE|boot-args=debug=1", f"CONFIG|{name}|END"]
    return "\n".join(lines) + "\n"


class ReadinessTests(unittest.TestCase):
    def test_valid_source_does_not_approve_guest_run(self):
        result = readiness.parse_asset_audit(sample())
        report = readiness.evaluate_inventory({"free_kib": "92000000"}, result)
        self.assertTrue(report["source_complete"])
        self.assertTrue(report["data_pair_sizes"])
        self.assertTrue(report["projected_clone_space"])
        self.assertEqual("BLOCKED", report["GUEST_RUN_READY"])

    def test_missing_data_blocks_source(self):
        result = readiness.evaluate_inventory({"free_kib": "92000000"}, readiness.parse_asset_audit(sample("data/data.img")))
        self.assertFalse(result["source_complete"])
        self.assertFalse(result["data_pair_sizes"])

    def test_low_space_blocks_clone(self):
        result = readiness.evaluate_inventory({"free_kib": "33000000"}, readiness.parse_asset_audit(sample()))
        self.assertFalse(result["projected_clone_space"])

    def test_rejects_untrusted_or_duplicate_inventory(self):
        with self.assertRaises(ValueError):
            readiness.parse_asset_audit(sample() + "FILE|data/data.img|8:1:2000:600:1:9\n")
        with self.assertRaises(ValueError):
            readiness.parse_asset_audit(sample().replace("FILE|image/kernel.kc|100:1:2000:600:123:3", "FILE|image/kernel.kc|BAD"))
        with self.assertRaises(ValueError):
            readiness.parse_asset_audit(sample().replace("CONFIG|image/xnuhost.conf|END", ""))

    def test_observes_asset_config_without_execution(self):
        audit = readiness.parse_asset_audit(sample())
        self.assertEqual(["boot-args=debug=1"], audit["configs"]["image/xnuhost.conf"])
        self.assertIn("data/data.img", audit["files"])


if __name__ == "__main__":
    unittest.main()
