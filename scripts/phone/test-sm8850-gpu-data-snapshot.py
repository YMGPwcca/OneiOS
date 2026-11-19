#!/usr/bin/env python3
"""Pure offline tests; must not use ADB or touch real APFS data."""
import importlib.util
import unittest
from pathlib import Path

p = Path(__file__).with_name('sm8850-gpu-data-snapshot.py')
spec = importlib.util.spec_from_file_location('snap', p)
snap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snap)

D = 'a' * 64
C = 'b' * 64


class SnapshotTests(unittest.TestCase):
    def test_path_is_nonce_only(self):
        self.assertEqual('/data/adb/oneios-m3q-gpu-snapshot-0123456789abcdef', snap.unique_paths('0123456789abcdef')[0])
        for v in ('', '../../data', '0'*15, 'f'*17, 'F'*16, 'f'*15+'z'):
            with self.assertRaises(ValueError):
                snap.unique_paths(v)

    def test_script_has_no_takeover_or_original_writes(self):
        s = snap.device_script('0'*16, D)
        self.assertIn('copy" sparse "$BASE/data.img"', s)
        self.assertIn('30GiB reserve crossed', s)
        self.assertIn('DATA_CLONE_READY=PASS', s)
        self.assertIn('GUEST_RUN_READY=BLOCKED', s)
        self.assertNotIn('oneios_switch.sh', s)
        self.assertNotIn('framework-stage.sh', s)
        self.assertNotIn('rm -rf', s)
        self.assertNotIn('> "$BASE/', s)

    def test_hash_pins_are_validated(self):
        s = snap.device_script('0'*16, D, C, D)
        self.assertIn('source Data differs from supplied independent hash', s)
        with self.assertRaises(ValueError):
            snap.device_script('0'*16, 'missing')
        with self.assertRaises(ValueError):
            snap.device_script('0'*16, D, 'incorrect')

    def test_status_requires_all_equal_hashes_and_reserve(self):
        stage = snap.unique_paths('0'*16)[0]
        lines = f'STAGE_PATH={stage}\nSOURCE_DATA_SHA256={D}\nSNAPSHOT_DATA_SHA256={D}\nSOURCE_CHIP_SHA256={C}\nSNAPSHOT_CHIP_SHA256={C}\nFREE_AFTER_KIB={snap.MIN_AFTER_KIB}\nDATA_CLONE_READY=PASS\nGUEST_RUN_READY=BLOCKED\n'
        self.assertEqual('PASS', snap.parse_success(lines, stage)['DATA_CLONE_READY'])
        with self.assertRaises(ValueError):
            snap.parse_success(lines.replace('SNAPSHOT_DATA_SHA256='+D, 'SNAPSHOT_DATA_SHA256='+C), stage)
        with self.assertRaises(ValueError):
            snap.parse_success(lines.replace('FREE_AFTER_KIB='+str(snap.MIN_AFTER_KIB), 'FREE_AFTER_KIB=100'), stage)
        with self.assertRaises(ValueError):
            snap.parse_success(lines.replace('GUEST_RUN_READY=BLOCKED', 'GUEST_RUN_READY=PASS'), stage)
        with self.assertRaises(ValueError):
            snap.parse_success(lines.replace('DATA_CLONE_READY=PASS', ''), stage)

    def test_full_length_is_8g_and_budget_is_respected(self):
        self.assertEqual(8589934592, snap.EXPECTED_DATA_BYTES)
        self.assertEqual(31522816, snap.MIN_AFTER_KIB)


if __name__ == '__main__':
    unittest.main()
