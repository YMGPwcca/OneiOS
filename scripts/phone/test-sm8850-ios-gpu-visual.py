#!/usr/bin/env python3
"""Host-only regression tests. No device, no snapshot, no guest and no ADB."""
import importlib.util
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, alias):
    spec = importlib.util.spec_from_file_location(alias, HERE / name)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


visual = load('sm8850-ios-gpu-visual.py', 'visual')
bench = load('sm8850-ios-gpu-bench.py', 'bench')
STAGE = '/data/adb/oneios-m3q-gpu-snapshot-6e89899ca4039fed'


class VisualBenchTests(unittest.TestCase):
    def test_shm_is_visible_and_never_takes_over(self):
        s = visual.make_visual_script(bench, STAGE, 240, 4096)
        self.assertIn('--gpu auto --display shm --no-input', s)
        self.assertNotIn('--display none', s)
        self.assertIn('--socket "$STAGE/gpu-bench/session/display.sock" --wait 65', s)
        self.assertNotRegex(s, r'(?m)^\s*[^#\n]*--takeover')
        self.assertNotIn('oneios_switch', s)
        self.assertIn('ONEIOS_GPU_TRACE=1 timeout -s TERM -k 15 240', s)
        self.assertIn('timeout -s TERM -k 10 285', s)
        self.assertIn('--data "$STAGE/data"', s)
        self.assertNotIn('--data "$BASE/data"', s)
        self.assertIn('gpu-bench/attempted', s)
        self.assertIn('launch.claim', s)
        self.assertEqual(0, subprocess.run(['sh', '-n'], input=s, text=True, capture_output=True).returncode)

    def test_opt_in_physical_touch_never_leaks_to_android_underlay(self):
        s = visual.make_visual_script(bench, STAGE, 240, 4096, touch=True)
        self.assertIn('--gpu auto --display shm --set touch-exclusive=1', s)
        self.assertNotIn('--no-input', s)
        self.assertNotIn('--display drm', s)
        self.assertIn('--set bridges=0', s)
        self.assertIn('VISUAL_MODE=shm_touch_exclusive', s)
        self.assertIn('gpu-bench/attempted', s)
        self.assertIn('launch.claim', s)
        self.assertIn('timeout -s TERM -k 15 240', s)
        self.assertIn('timeout -s TERM -k 10 285', s)
        self.assertNotRegex(s, r'(?m)^\s*[^#\n]*--takeover')
        self.assertEqual(0, subprocess.run(['sh','-n'], input=s, text=True, capture_output=True).returncode)

    def test_no_touch_remains_default_and_touch_is_cli_opt_in(self):
        s = visual.make_visual_script(bench, STAGE, 240, 4096)
        self.assertIn('--gpu auto --display shm --no-input', s)
        self.assertNotIn('touch-exclusive=1', s)
        source = (HERE / 'sm8850-ios-gpu-visual.py').read_text()
        self.assertIn('p.add_argument("--touch", action="store_true"', source)
        self.assertIn('touch=touch)', source)
        self.assertIn('touch_requested', source)
        self.assertIn('LIVE_TOUCH_GRABBED=YES', source)
        self.assertIn('exclusive sec_touchscreen grab was never confirmed', source)

    def test_native_exclusivity_has_mode_gate_and_failure_closes_fd(self):
        source = (HERE.parent.parent / 'runtime/xnuhost/src/input.c').read_text()
        config = (HERE.parent.parent / 'runtime/xnuhost/src/config.c').read_text()
        main = (HERE.parent.parent / 'runtime/xnuhost/src/main.c').read_text()
        self.assertIn('ioctl(fd, EVIOCGRAB, 1)', source)
        self.assertIn('ioctl(exclusive_touch_fd, EVIOCGRAB, 0)', source)
        self.assertIn('xh_input_exclusive_touch_allowed(name, direct, have_touch)', source)
        self.assertIn('touch_exclusive && !have_touch', source)
        self.assertIn('if (touch_exclusive) keys = false;', source)
        self.assertIn('mode=bench, display=shm, input=1, bridges=0', config)
        self.assertIn('if (config.touch_exclusive)', main)
        self.assertIn('return -1;', main.split('if (config.touch_exclusive)',1)[1].split('}',1)[0])

    def test_sysctl_is_guarded_before_first_guest_attempt(self):
        s = visual.make_visual_script(bench, STAGE, 240, 4096)
        self.assertIn('CURRENT_MAP_COUNT=$(cat /proc/sys/vm/max_map_count)', s)
        self.assertIn('map_count_below_required_for_nonmutating_guest', s)
        self.assertLess(s.index('CURRENT_MAP_COUNT'), s.index('gpu-bench/attempted'))
        self.assertNotRegex(s, r'(?m)^\s*(?:echo|printf|tee|sysctl)\b[^\n]*\s*>\s*/proc/sys')
        self.assertNotIn('sysctl -w', s)

    def test_one_shot_is_preserved_in_input_script(self):
        s = visual.make_visual_script(bench, STAGE, 240, 4096)
        self.assertIn('source-verified.sha256.txt', s)
        self.assertIn('Data_hash:$p', s)
        self.assertIn('guest already running', bench.safe_shell(STAGE, 'a'*64, 'b'*16)[1])
        self.assertIn('launch.claim', s)
        self.assertNotIn('rm -rf', s)
        self.assertNotIn('flock -n 8', '\n'.join(line for line in s.splitlines() if not line.lstrip().startswith('#')))

    def test_private_uploads_and_matching_digests(self):
        digests = {name: 'a'*64 for name in visual.DISPLAY_ARTIFACTS}
        s = visual.prepare_display_shell(STAGE, 'b'*16, digests)
        for name in visual.DISPLAY_ARTIFACTS:
            self.assertIn('oneios-visual-'+'b'*16+'-'+name, s)
            self.assertIn('sha256sum', s)
            self.assertIn('$STAGE/bin/'+name, s)
        self.assertEqual(0, subprocess.run(['sh', '-n'], input=s, text=True, capture_output=True).returncode)
        self.assertIn('chmod 700 "$STAGE/bin/oneios-display"', s)
        self.assertIn('chmod 400 "$STAGE/bin/oneios-display.dex"', s)
        self.assertIn('chmod 400 "$STAGE/bin/liboneios-display.so"', s)
        with self.assertRaises(ValueError):
            visual.prepare_display_shell(STAGE, 'b'*16, {**digests, 'oneios-display':'xyz'})
        with self.assertRaises(ValueError):
            visual.prepare_display_shell(STAGE+';rm -rf /', 'b'*16, digests)

    def test_capture_and_first_frame_are_distinct(self):
        d = visual.preview_summary('oneios-display: first frame posted (format 5)\n'
                                   'oneios-display: the socket closed after 97 frames\n')
        self.assertTrue(d['first_frame_posted'])
        self.assertEqual(97, d['reported_closed_frame_count'])
        self.assertFalse(visual.preview_summary('oneios-display: layer initialized')['first_frame_posted'])
        self.assertIsNone(visual.preview_summary('display exception')['reported_closed_frame_count'])

    def test_build_occurs_before_snapshot_with_no_guest_restart(self):
        source = (HERE / 'sm8850-ios-gpu-visual.py').read_text()
        body = source.split('def run_visible(args, report):',1)[1].split('\ndef main(',1)[0]
        self.assertLess(body.index('checked_build()'), body.index('snapshot_new('))
        self.assertLess(body.index('verified_local_artifacts()'), body.index('snapshot_new('))
        self.assertIn('bench.safe_shell(stage, hashes["xnuhost"], incoming_nonce)', body)
        self.assertIn('make_visual_script(bench, stage', body)
        self.assertIn('finally:', body)
        self.assertNotIn('timeout -s TERM -k 15 240 "$BASE/data', source)
        self.assertNotIn('rmtree(', source)

    def test_runner_rejects_invalid_duration_and_ram_without_work(self):
        for duration, ram in ((30,4096),(301,4096),(240,1024),(240,5130)):
            with self.subTest(duration=duration, ram=ram):
                from contextlib import redirect_stderr
                from io import StringIO
                with patch.object(visual, 'run_visible', side_effect=AssertionError('must not run')), redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit):
                        visual.main(['run','--duration',str(duration),'--ram-mib',str(ram)])


    def test_map_count_gate_runs_before_snapshot(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        harness = SimpleNamespace(
            select_usb=lambda *_: ['adb', '-s', 'testusb'],
            root=lambda *_a, **_kw: SimpleNamespace(stdout='map_count=65530\n'),
            decode_kv=lambda _s: {'map_count':'65530'},
            validate_preflight=lambda _v: ({}, []),
            DEVICE_AUDIT='audit',
        )
        args = SimpleNamespace(adb='adb', serial=None, duration=240, ram_mib=4096)
        report={'tag':'offline'}
        files = {name: Path('/fake') / name for name in ('xnuhost', *visual.DISPLAY_ARTIFACTS)}
        digests={name:'a'*64 for name in files}
        with patch.object(visual, 'load_tool', side_effect=[harness, bench]), \
             patch.object(visual, 'checked_build'), \
             patch.object(visual, 'verified_local_artifacts', return_value=(files,digests)), \
             patch.object(visual, 'snapshot_new', side_effect=AssertionError('must never snapshot')):
            with self.assertRaisesRegex(RuntimeError, 'map_count below 1048576'):
                visual.run_visible(args, report)

    def test_fake_success_orchestrates_one_snapshot_and_display(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        from unittest.mock import Mock
        calls=[]
        def root(_adb, script, **_kw):
            calls.append(script)
            if 'echo PREPARED=PASS' in script:
                return SimpleNamespace(stdout='PREPARED=PASS\n')
            if 'echo VISUAL_ARTIFACTS=PASS' in script:
                return SimpleNamespace(stdout='VISUAL_ARTIFACTS=PASS\n')
            if 'echo VISUAL_RUN_PID' in script:
                return SimpleNamespace(stdout='VISUAL_RUN_PID=1234\n')
            if "gpu-bench/state' 2>/dev/null" in script:
                return SimpleNamespace(stdout='finished:124\n')
            if 'first frame posted' in script:
                return SimpleNamespace(stdout='oneios-display: first frame posted\n')
            if 'backboardd fences' in script:
                return SimpleNamespace(stdout='xnuhost I gpu: backboardd fences 3\n')
            return SimpleNamespace(stdout='map_count=1048576\n')
        harness=SimpleNamespace(
            select_usb=lambda *_: ['adb', '-s', 'testusb'],
            root=root,
            decode_kv=lambda _s: {'map_count':'1048576'},
            validate_preflight=lambda _v: ({}, []),
            DEVICE_AUDIT='audit',
        )
        args=SimpleNamespace(adb='adb',serial=None,duration=240,ram_mib=4096)
        report={'tag':'offline'}
        files={name:Path('/fake') / name for name in ('xnuhost',*visual.DISPLAY_ARTIFACTS)}
        digests={name:'a'*64 for name in files}
        with patch.object(visual,'load_tool',side_effect=[harness,bench]), \
             patch.object(visual,'checked_build'), \
             patch.object(visual,'verified_local_artifacts',return_value=(files,digests)), \
             patch.object(visual,'snapshot_new',return_value=STAGE) as snapshot, \
             patch.object(visual,'push_file') as uploads, \
             patch.object(visual,'acquire_evidence') as evidence, \
             redirect_stdout(StringIO()) as stdout:
            visual.run_visible(args,report)
        snapshot.assert_called_once()
        self.assertEqual(4,uploads.call_count)
        evidence.assert_called_once()
        self.assertIn('LIVE_DISPLAY_FIRST_FRAME=POSTED',stdout.getvalue())
        self.assertIn('LIVE_ADRENO_FENCES=OBSERVED',stdout.getvalue())
        self.assertTrue(any('timeout -s TERM -k 15 240' in x for x in calls))
        self.assertTrue(any('--display shm' in x for x in calls))


if __name__ == '__main__':
    unittest.main()
