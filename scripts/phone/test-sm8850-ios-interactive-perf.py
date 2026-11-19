#!/usr/bin/env python3
"""Offline synthetic regression for the non-mutating iOS interactive perf parser."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('oneios_interactive_perf', HERE / 'sm8850-ios-interactive-perf.py')
perf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(perf)


class InteractivePerfTests(unittest.TestCase):
    def test_measured_metrics_and_manual_icon_latency_remain_distinct(self):
        guest = "\n".join((
            '[1000.1] xnuhost I gpu: 10 s host: backboardd fences 12, submit->retired mean 1700 us max 517141 us',
            '[1001.1] xnuhost I perf: 30.0 s: 123 task traps (40000/s): syscall 100, fault 23',
            '[1002.1] guest oneios-cpu: 10 s: iconservicesagent[111] 216%, SpringBoard[30] 20%',
            '[1003.1] guest oneios-cpu: 10 s: backboardd[52] 40%, SpringBoard[30] 40%',
            '[1004.1] guest oneios-cpu: 10 s: SpringBoard[262] 10%, backboardd[260] 20%',
            '[1005.1] xnuhost I input: touch: 9 frames in 99 ms, 1 contact; the guest\'s next frame 742.2 ms after the touch-down',
            '[1006.1] xnuhost I input: touch: 9 frames in 99 ms, 1 contact; no guest frame after the touch-down',
            '[1007.1] xnuhost I memory: host MemAvailable 1552 MiB of 11084 MiB',
            '[1008.1] guest vm: host_statistics64() count is larger than expected (actual:104 > HOST_VM_INFO64_COUNT:62)',
        ))
        display = "\n".join((
            'oneios-display: perf: mono_ms=1005000 window_ms=5000 posts=80 posted_rate=16.0 active_cadence=56.0 active_gaps=60 gap_p95_us=33000 lock_p95_us=8000 lock_max_us=120000 copy_p95_us=4000 copy_max_us=5000 post_p95_us=16000 post_max_us=30000 full_copies=4 copied_pixels=123456',
            'oneios-display: perf: mono_ms=1010000 window_ms=5000 posts=3 posted_rate=0.6 active_cadence=0.0 active_gaps=1 gap_p95_us=1000000 lock_p95_us=2000 lock_max_us=3000 copy_p95_us=1000 copy_max_us=2000 post_p95_us=2000 post_max_us=4000 full_copies=1 copied_pixels=12345',
        ))
        r = perf.analyze_logs(guest, display)
        self.assertEqual(2, r['display']['windows'])
        self.assertEqual(56.0, r['display']['active_cadence_median'])
        self.assertEqual(120000, r['display']['lock_max_us'])
        self.assertEqual(517141, r['gpu']['max_submit_to_retire_us'])
        self.assertEqual(742.2, r['touch']['max_next_frame_ms'])
        self.assertEqual(1, r['touch']['no_subsequent_guest_frame'])
        self.assertEqual(216, r['cpu']['iconservicesagent_percent_of_one_core_max'])
        self.assertTrue(r['processes']['possible_ui_restart'])
        self.assertEqual([30,262], r['processes']['springboard_pids'])
        self.assertEqual(1552, r['memory']['android_memavailable_mib_min'])
        self.assertEqual('manual observation required', r['settings_icons']['first_vs_second_open_delay'])
        self.assertIn('not iOS animation FPS', r['caveats'][0])

    def test_spotlight_and_gpu_trace_are_measured_not_inferred(self):
        guest = "\n".join((
            '[1] guest oneios-cpu: 10 s: Spotlight[194] 101%, backboardd[52] 13%',
            '[2] guest neios-cpu: 10 s: Spotlight[194] 92%, SpringBoard[30] 3%',
            '[3] guest oneios-cpu-sys: 10 s: Spotlight[194] 14%, kernel_task[0] 8%',
            '[4] guest oneios-cpu: 10 s: backboardd[52] 43%, kernel_task[0] 23%',
            '[5] xnuhost I gpu trace: submit queue_gen=2',
            '[6] xnuhost I gpu trace: complete queue_gen=2',
        ))
        # Six physical lines are required; a literal backslash-n breaks sampling.
        self.assertEqual(6, len(guest.splitlines()))
        result = perf.analyze_logs(guest, '')
        self.assertEqual(101, result['cpu']['spotlight_percent_of_one_core_max'])
        self.assertEqual(2, result['cpu']['spotlight_observed_windows'])
        self.assertEqual(2, result['cpu']['spotlight_ge_80_percent_windows'])
        self.assertEqual(2, result['gpu']['verbose_trace_lines'])
        legacy = perf.analyze_logs('SpringBoard[30]', '')
        self.assertIsNone(legacy['cpu']['spotlight_percent_of_one_core_max'])
        self.assertEqual(0, legacy['cpu']['spotlight_observed_windows'])

    def test_legacy_log_does_not_invent_fps(self):
        r = perf.analyze_logs('SpringBoard[30] boot', 'oneios-display: first frame posted')
        self.assertFalse(r['display']['instrumentation_present'])
        self.assertIsNone(r['display']['active_cadence_median'])
        self.assertIsNone(r['display']['posted_rate_max'])
        self.assertIsNone(r['touch']['max_next_frame_ms'])
        self.assertFalse(r['processes']['possible_ui_restart'])

    def test_cli_paired_logs_json_without_adb(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            host = folder / 'host.log'
            display = folder / 'display.log'
            output = folder / 'result.json'
            host.write_text('SpringBoard[30]')
            display.write_text('oneios-display: first frame posted')
            completed = subprocess.run([sys.executable, str(HERE / 'sm8850-ios-interactive-perf.py'),
                                        '--xnuhost',str(host),'--display',str(display),'--json',str(output)],
                                       text=True,capture_output=True,check=True)
            self.assertIn('DISPLAY_PERF_AVAILABLE=False', completed.stdout)
            self.assertIn('PERF_REPORT=', completed.stdout)
            self.assertFalse(json.loads(output.read_text())['display']['instrumentation_present'])


if __name__ == '__main__':
    unittest.main()
