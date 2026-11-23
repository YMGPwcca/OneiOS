#!/usr/bin/env python3
"""Host-only fixtures for the read-only GPU/respring evidence parser."""
import importlib.util
import io
import tarfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).with_name('sm8850-gpu-respring-forensics.py')
spec = importlib.util.spec_from_file_location('gpu_respring_forensics', SOURCE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class EvidenceTests(unittest.TestCase):
    XNU = '''[ 100.100] xnuhost E drm2kgsl: GPU_COMMAND failed: Protocol error
[ 100.657] guest     sheng-exit: backboardd[52] status 0xf reason ns 2
[ 101.000] guest     sheng-exit: SpringBoard[30] status 0x9: backboardd respawn
[ 101.010] xnuhost I perf: 30.0 s: 988465 task traps (32863/s)
[ 102.000] xnuhost I gpu: 10 s host: backboardd fences 4, submit->retired mean 332715 us max 684274 us;
'''
    DISPLAY = '''oneios-display: perf: mono_ms=102000 window_ms=5000 posts=2 posted_rate=0.40 gap_p95_us=28318753 copy_max_us=8655
'''

    def test_association_measures_time_without_claiming_causality(self):
        r = mod.analyze(self.XNU, self.DISPLAY, 'pct=28 status=APPLIED', 'disabled-180s')
        self.assertEqual(1, len(r['gpu_error_to_backboard_exit']))
        self.assertEqual(0.557, r['gpu_error_to_backboard_exit'][0]['delta_seconds'])
        self.assertIn('ONLY', r['gpu_error_to_backboard_exit'][0]['interpretation'])
        self.assertEqual(32863, r['peak_traps_per_s'])
        self.assertEqual(684.274, r['max_host_submit_to_retire_ms'])
        self.assertEqual(28318.753, r['max_display_gap_p95_ms'])
        self.assertEqual('disabled-180s', r['thermal_profile'])

    def test_distant_exit_is_not_attributed_to_gpu_error(self):
        xnu = self.XNU.replace('[ 100.657]', '[ 142.657]')
        self.assertEqual([], mod.analyze(xnu)['gpu_error_to_backboard_exit'])

    def test_missing_optional_archive_members_do_not_forge_data(self):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            data = self.XNU.encode()
            item = tarfile.TarInfo('session/xnuhost.log')
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
        stream.seek(0)
        with tarfile.open(fileobj=stream) as archive:
            self.assertEqual(self.XNU, mod.read_member(archive, 'session/xnuhost.log'))
            self.assertIsNone(mod.read_member(archive, 'control/display.log'))
        self.assertIsNone(mod.analyze(self.XNU)['max_display_copy_ms'])


if __name__ == '__main__':
    unittest.main()
