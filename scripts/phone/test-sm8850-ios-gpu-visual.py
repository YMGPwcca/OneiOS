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

    def test_native_harness_does_not_hide_sanitizer_failures(self):
        source = (HERE.parent.parent / 'runtime/xnuhost/tests/test_xnuhost.c').read_text()
        self.assertIn('setvbuf(stdout, NULL, _IONBF, 0)', source)
        self.assertIn('NATIVE_TEST_STAGE=config', source)
        self.assertIn('NATIVE_TEST_STAGE=cleanup', source)
        self.assertNotIn('freopen("/dev/null"', source)

    def test_native_test_documentation_uses_correct_cwd_and_asan_policy(self):
        # Native C tests use paths relative to runtime/xnuhost, not repo root.
        doc = (HERE.parent.parent / 'docs/SM8850_IOS_TOUCH_PREVIEW.md').read_text()
        makefile = (HERE.parent.parent / 'runtime/xnuhost/Makefile').read_text()
        self.assertIn('cd runtime/xnuhost && ASAN_OPTIONS=detect_leaks=0 ./build/host/test_xnuhost', doc)
        self.assertIn('ASAN_OPTIONS=detect_leaks=0 $(H)/test_xnuhost', makefile)
        self.assertNotIn('runtime/xnuhost/build/host/test_xnuhost', doc)

    def test_visual_report_includes_full_log_frame_pacing_and_ui_latency(self):
        source = (HERE / 'sm8850-ios-gpu-visual.py').read_text()
        self.assertIn('sm8850-ios-interactive-perf.py', source)
        self.assertIn('perf.analyze_logs(host_log, display_log)', source)
        self.assertIn('report["performance"]', source)
        self.assertIn('perf._show(report["performance"])', source)
        jni = (HERE.parent.parent / 'runtime/display/src/jni.c').read_text()
        self.assertIn('log_frame_perf(&perf, tick_ns)', jni)
        self.assertIn('ANativeWindow_lock(window, &buffer, &dirty)', jni)
        self.assertIn('xhd_perf_record(&perf, post_done_ns', jni)
        self.assertIn('lock_max_us=', jni)
        self.assertIn('active_cadence=', jni)
        self.assertIn('pending.w ? 0 : 1000', jni)
        self.assertNotIn('system("setprop', jni)

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
        for duration, ram in ((30,4096),(89,4096),(1801,4096),(240,1024),(240,5130)):
            with self.subTest(duration=duration, ram=ram):
                from contextlib import redirect_stderr
                from io import StringIO
                with patch.object(visual, 'run_visible', side_effect=AssertionError('must not run')), redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit):
                        visual.main(['run','--duration',str(duration),'--ram-mib',str(ram)])


    def test_custom_visual_duration_is_bounded_on_phone_and_preserves_one_shot(self):
        # Long sessions need their own explicit device-side TERM/KILL deadline.
        # No unlimited/0 timeout, no reuse of the booted APFS clone.
        for seconds in (301, 600, 900, 1800):
            with self.subTest(seconds=seconds):
                script = visual.make_visual_script(bench, STAGE, seconds, 4096, touch=True)
                self.assertIn(f'ONEIOS_GPU_TRACE=1 timeout -s TERM -k 15 {seconds}', script)
                self.assertIn(f'timeout -s TERM -k 10 {seconds + 45}', script)
                self.assertIn('gpu-bench/attempted', script)
                self.assertIn('launch.claim', script)
                self.assertIn('--set touch-exclusive=1', script)
                self.assertIn('--set bridges=0', script)
                self.assertNotRegex(script, r'(?m)^\s*[^#\n]*--takeover')
                self.assertEqual(0, subprocess.run(['sh', '-n'], input=script, text=True, capture_output=True).returncode)

    def test_opt_in_disable_verbose_gpu_trace_keeps_guest_deadlines_and_evidence(self):
        base = visual.make_visual_script(bench, STAGE, 600, 4096, touch=True)
        quiet = visual.make_visual_script(bench, STAGE, 600, 4096,
                                          touch=True, gpu_trace=False)
        self.assertIn('ONEIOS_GPU_TRACE=1 timeout -s TERM -k 15 600', base)
        self.assertNotIn('ONEIOS_GPU_TRACE=1 timeout', quiet)
        self.assertIn('unset ONEIOS_GPU_TRACE', quiet)
        self.assertIn('timeout -s TERM -k 15 600', quiet)
        self.assertIn('GPU_TRACE_MODE=off_for_ab', quiet)
        self.assertIn('timeout -s TERM -k 10 645', quiet)
        self.assertIn('--set touch-exclusive=1', quiet)
        self.assertIn('--set bridges=0', quiet)
        self.assertIn('--data "$STAGE/data"', quiet)
        self.assertNotIn('--data "$BASE/data"', quiet)
        self.assertNotIn('sysctl -w', quiet)
        self.assertFalse(any('--takeover' in line for line in quiet.splitlines()
                             if not line.lstrip().startswith('#')))
        self.assertEqual(0, subprocess.run(['sh','-n'], input=quiet,
                                          text=True, capture_output=True).returncode)

    def test_no_gpu_trace_collect_is_rejected_before_adb(self):
        from contextlib import redirect_stderr
        from io import StringIO
        with (patch.object(visual, "collect_finished", side_effect=AssertionError('no collect')),
              patch.object(visual, "run_visible", side_effect=AssertionError('no run')),
              redirect_stderr(StringIO())):
            with self.assertRaises(SystemExit):
                visual.main(["collect", "--stage", STAGE, "--no-gpu-trace"])

    def test_visual_extension_does_not_extend_generic_bench_or_retry(self):
        self.assertEqual(300, bench.BENCH_DURATION_MAX_SECONDS)
        self.assertEqual(1800, bench.VISUAL_DURATION_MAX_SECONDS)
        with self.assertRaisesRegex(ValueError, 'bounded test limits exceeded'):
            bench.device_run_script(STAGE, 301, 4096)
        with self.assertRaisesRegex(ValueError, 'bounded test limits exceeded'):
            bench.device_run_script(STAGE, 1801, 4096, max_duration_seconds=1800)
        with self.assertRaisesRegex(ValueError, 'preboot retry'):
            bench.device_run_script(STAGE, 600, 4096, retry_preboot=True, max_duration_seconds=1800)
        with self.assertRaisesRegex(ValueError, 'unsupported guest duration cap'):
            bench.device_run_script(STAGE, 60, 4096, max_duration_seconds=999999)

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



class DetachCollectTests(unittest.TestCase):
    def test_detach_requires_a_running_guest_frame_and_gpu_fence(self):
        f = visual.can_detach
        self.assertTrue(f("running", touch=True, touch_seen=True, frame_seen=True, fence_seen=True))
        self.assertTrue(f("running", touch=False, touch_seen=False, frame_seen=True, fence_seen=True))
        for state in ("pending", "preparing", "blocked:2", "finished:124", ""):
            self.assertFalse(f(state, touch=True, touch_seen=True, frame_seen=True, fence_seen=True))
        for frame, fence, touch_ok in ((False, True, True), (True, False, True), (True, True, False)):
            self.assertFalse(f("running", touch=True, touch_seen=touch_ok, frame_seen=frame, fence_seen=fence))

    def test_detach_after_live_confirmation_does_not_wait_or_collect(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        log = []
        def root(_adb, shell, **_kw):
            log.append(shell)
            if "echo PREPARED=PASS" in shell:
                return SimpleNamespace(stdout="PREPARED=PASS\n")
            if "echo VISUAL_ARTIFACTS=PASS" in shell:
                return SimpleNamespace(stdout="VISUAL_ARTIFACTS=PASS\n")
            if "echo VISUAL_RUN_PID" in shell:
                return SimpleNamespace(stdout="VISUAL_RUN_PID=222\n")
            if "gpu-bench/state' 2>/dev/null" in shell:
                return SimpleNamespace(stdout="running\n")
            if "touch-exclusive: sec_touchscreen grabbed" in shell:
                return SimpleNamespace(stdout="input: touch-exclusive: sec_touchscreen grabbed\n")
            if "first frame posted" in shell:
                return SimpleNamespace(stdout="oneios-display: first frame posted\n")
            if "backboardd fences" in shell:
                return SimpleNamespace(stdout="backboardd fences 3\n")
            return SimpleNamespace(stdout="map_count=1048576\n")
        harness = SimpleNamespace(
            select_usb=lambda *_: ["adb", "-s", "testusb"],
            root=root,
            decode_kv=lambda _: {"map_count": "1048576"},
            validate_preflight=lambda _: ({}, []),
            DEVICE_AUDIT="audit",
        )
        report = {"tag": "testdetach", "action": "run"}
        with tempfile.TemporaryDirectory() as td:
            guest_binary = Path(td) / "xnuhost"
            guest_binary.write_bytes(b"touch-exclusive=1 requires")
            files = {name: Path(td) / name for name in ("xnuhost", *visual.DISPLAY_ARTIFACTS)}
            digests = {name: "a"*64 for name in files}
            args = SimpleNamespace(adb="adb", serial=None, duration=600,
                                   ram_mib=4096, touch=True, detach=True)
            def stage_snapshot(_adb, _harness, new_report):
                new_report["stage"] = STAGE
                return STAGE
            with patch.object(visual, "load_tool", side_effect=[harness, bench]), \
                 patch.object(visual, "checked_build"), \
                 patch.object(visual, "verified_local_artifacts", return_value=(files, digests)), \
                 patch.object(visual, "snapshot_new", side_effect=stage_snapshot) as snap, \
                 patch.object(visual, "push_file"), \
                 patch.object(visual, "acquire_evidence", side_effect=AssertionError("detach must not collect")), \
                 redirect_stdout(StringIO()) as stdout:
                visual.run_visible(args, report)
        snap.assert_called_once()
        self.assertTrue(report["detached"])
        self.assertEqual("DEFERRED_UNTIL_RECONNECT", report["collection_status"])
        self.assertEqual("running", report["polled_state"])
        self.assertIn("DETACH_READY=YES; SAFE_TO_UNPLUG_USB=YES", stdout.getvalue())
        self.assertIn("COLLECT_AFTER_RECONNECT_STAGE=" + STAGE, stdout.getvalue())
        self.assertIn("PHONE_SIDE_TIMEOUT_SECONDS=600", stdout.getvalue())
        self.assertTrue(any("rm -f" in cmd for cmd in log))
        self.assertTrue(any("timeout -s TERM -k 15 600" in cmd for cmd in log))
        self.assertTrue(any("timeout -s TERM -k 10 645" in cmd for cmd in log))
        self.assertFalse(any("pkill" in cmd or "stop system_server" in cmd for cmd in log))

    def test_collect_waits_until_finished_and_does_not_boot(self):
        from types import SimpleNamespace
        states = ["running", "finished:124"]
        calls = []
        def root(_adb, shell, **_kw):
            calls.append(shell)
            if "COLLECT_STAGE=VERIFIED" in shell:
                return SimpleNamespace(stdout="COLLECT_STAGE=VERIFIED\n")
            if "/gpu-bench/state" in shell:
                return SimpleNamespace(stdout=states[0] + "\n")
            raise AssertionError("unexpected root command during read-only collect: " + shell)
        harness = SimpleNamespace(select_usb=lambda *_: ["adb", "-s", "testusb"], root=root)
        args = SimpleNamespace(adb="adb", serial=None, stage=STAGE)
        report = {"tag": "collect", "action": "collect"}
        with patch.object(visual, "load_tool", side_effect=[bench, harness]), \
             patch.object(visual, "acquire_evidence") as evidence:
            with self.assertRaisesRegex(RuntimeError, "not confirmed finished"):
                visual.collect_finished(args, report)
            evidence.assert_not_called()
        states[0] = "finished:124"
        with patch.object(visual, "load_tool", side_effect=[bench, harness]), \
             patch.object(visual, "acquire_evidence") as evidence:
            visual.collect_finished(args, report)
            evidence.assert_called_once_with(harness, ["adb", "-s", "testusb"], STAGE, report, bench)
        self.assertEqual("POST_RUN_READ_ONLY", report["collection_status"])
        self.assertTrue(all("rm -f" not in cmd and "timeout " not in cmd and "nohup" not in cmd for cmd in calls))

    def test_collect_rejects_untrusted_paths_and_detach_flags_without_adb(self):
        from contextlib import redirect_stderr
        from io import StringIO
        with patch.object(visual, "run_visible", side_effect=AssertionError("must not run guest")), \
             patch.object(visual, "collect_finished", side_effect=AssertionError("must not collect")), \
             redirect_stderr(StringIO()):
            for arglist in (
                ["collect"],
                ["collect", "--stage", "/data/local/tmp/a"],
                ["collect", "--stage", STAGE + ";rm -rf /"],
                ["collect", "--stage", STAGE, "--detach"],
                ["collect", "--stage", STAGE, "--touch"],
                ["run", "--stage", STAGE],
            ):
                with self.subTest(args=arglist), self.assertRaises(SystemExit):
                    visual.main(arglist)

    def test_detach_does_not_change_device_timeout_or_original_data(self):
        script = visual.make_visual_script(bench, STAGE, 600, 4096, touch=True)
        self.assertIn("ONEIOS_GPU_TRACE=1 timeout -s TERM -k 15 600", script)
        self.assertIn("timeout -s TERM -k 10 645", script)
        self.assertIn('--data "$STAGE/data"', script)
        self.assertNotIn('--data "$BASE/data"', script)
        self.assertIn("gpu-bench/attempted", script)
        self.assertIn("launch.claim", script)
        self.assertEqual(0, subprocess.run(["sh", "-n"], input=script, text=True, capture_output=True).returncode)


if __name__ == '__main__':
    unittest.main()
