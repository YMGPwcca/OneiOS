#!/usr/bin/env python3
"""Offline tests of the bounded SM8850 guest GPU runner (no phone/ADB)."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).with_name('sm8850-ios-gpu-bench.py')
spec = importlib.util.spec_from_file_location('oneios_sm8850_bench', SOURCE)
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
STAGE = '/data/adb/oneios-m3q-gpu-snapshot-6e89899ca4039fed'

class BenchTests(unittest.TestCase):
    def test_stage_requires_exact_private_snapshot_path(self):
        self.assertEqual(STAGE, bench.stage_name(STAGE))
        for p in ('/data/local/tmp/oneios-m3q-ios27-bench/data',
                  STAGE + '/../../data', STAGE + '/data',
                  '/data/adb/oneios-m3q-gpu-snapshot-../../x'):
            with self.subTest(p=p), self.assertRaises(ValueError):
                bench.stage_name(p)

    def test_upload_refuses_bad_hash_or_nonce(self):
        for sha, nonce in [('z'*64, 'a'*16), ('a'*64,'BAD'), ('a'*63,'a'*16)]:
            with self.assertRaises(ValueError):
                bench.safe_shell(STAGE,sha,nonce)

    def test_script_has_bounded_run_and_no_takeover(self):
        run=bench.device_run_script(STAGE,240,4096)
        self.assertIn('timeout -s TERM -k 15 240',run)
        self.assertIn('--data "$STAGE/data"',run)
        self.assertIn('--gpu auto --display none --no-input',run)
        self.assertIn('--mode bench',run)
        self.assertIn('--set bridges=0',run)
        self.assertIn('gpu-bench/attempted',run)
        self.assertNotIn('sm8850-takeover',run)
        self.assertNotIn('watchdog',run.lower())
        self.assertNotIn('> /proc/sys',run)
        self.assertNotIn('--data "$BASE/data"',run)
        self.assertNotIn('rm -rf',run)
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write(run);f.flush()
            self.assertEqual(0, subprocess.run(['sh','-n',f.name],check=False).returncode)

    def test_prepare_excludes_other_guest_and_old_candidate(self):
        _,setup=bench.safe_shell(STAGE,'a'*64,'b'*16)
        self.assertIn('guest already running',setup)
        self.assertIn('snapshot previously used for a bench',setup)
        self.assertIn('missing nohup',setup)
        self.assertIn('sha256sum',setup)
        with tempfile.NamedTemporaryFile(mode='w') as f:
            f.write(setup);f.flush()
            self.assertEqual(0, subprocess.run(['sh','-n',f.name],check=False).returncode)

    def test_limits_rejected(self):
        for s,m in ((301,4096),(29,4096),(240,1024),(240,4355),(240,6144)):
            with self.subTest(s=s,m=m),self.assertRaises(ValueError):
                bench.device_run_script(STAGE,s,m)

    def test_guest_markers_never_claim_vulkan_device_from_host_submit(self):
        self.assertFalse(bench.summarize_log('capset DRM (6)\nGPU fence retired')
                         ['gpu_execution_observed'])
        example=('xnuhost I placed: boot-args "debug=1 vgpu-3d=1"\n'
                 'oneios-gpu: virtio GPU with the DRM native context (features 0x100000059)\n'
                 'xnuhost I gpu: backboardd fences 7, submit->retired mean 1200 us\n')
        marks=bench.summarize_log(example)
        self.assertTrue(marks['gpu_execution_observed'])
        self.assertEqual(7,marks['backboardd_fences_max'])
        self.assertFalse(marks['legacy_vulkan_failure'])
        self.assertTrue(bench.summarize_log(example+'oneios-gpu-text Vulkan(VkResultCode(-3))\n')['legacy_vulkan_failure'])


# Additional source-level regressions for the previously too-strict trustcache gate
# and a strictly pre-boot, exact-error retry. These tests do not access a phone.
class FixedBenchTests(unittest.TestCase):
    def test_trustcache_imageset_fallback_and_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            def put(name):
                path=base/'image'/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('fixture')
            put('kernel.kc.gpuaddon')
            put('trust/static.trustcache')
            put('overlay/userland/owner-trust.json')
            script=bench.device_run_script(STAGE,240,4096)
            start=script.index('[ -f "$BASE/image/kernel.kc.gpuaddon"')
            end=script.index('mkdir -m 700 "$STAGE/',start)
            gate=script[start:end]
            log=base/'run.log'
            state=base/'state'
            pre='set -eu\nBASE="'+str(base)+'"\nFAIL="'+str(log)+'"\nSTATUS="'+str(state)+'"\n'
            p=subprocess.run(['sh'],input=pre+gate,text=True,capture_output=True)
            self.assertEqual(0,p.returncode,p.stderr)
            self.assertIn('TRUST_SOURCE=imageset_static_plus_owner',log.read_text())
            (base/'image/overlay/userland/owner-trust.json').unlink()
            log.unlink()
            p=subprocess.run(['sh'],input=pre+gate,text=True,capture_output=True)
            self.assertEqual(2,p.returncode,p.stderr)
            self.assertIn('ERROR=missing_trustcache_source_or_owner_module',log.read_text())
            put('kernel.kc.trustcache')
            log.unlink()
            p=subprocess.run(['sh'],input=pre+gate,text=True,capture_output=True)
            self.assertEqual(0,p.returncode,p.stderr)
            self.assertIn('TRUST_SOURCE=kernel_sidecar',log.read_text())

    def test_retry_preboot_fails_closed_and_preserves_old_evidence(self):
        _,old=bench.safe_shell(STAGE,'a'*64,'b'*16)
        _,retry=bench.safe_shell(STAGE,'a'*64,'b'*16,retry_preboot=True)
        for critical in ('guest already attempted on this Data clone',
                         'previous bench was not blocked:2',
                         'ERROR=trusted_addon_missing',
                         'previous guest log exists',
                         'retry evidence directory cannot be created'):
            self.assertIn(critical,retry)
        self.assertIn('xnuhost-gpu-retry',retry)
        self.assertNotIn('rm -f',retry)
        self.assertNotIn('rm -rf',retry)
        self.assertNotIn('retry-preboot',old)
        for part in (old,retry):
            p=subprocess.run(['sh','-n'],input=part,text=True,capture_output=True)
            self.assertEqual(0,p.returncode,p.stderr)

    def test_retry_session_is_independent_and_still_one_shot(self):
        orig=bench.device_run_script(STAGE,240,4096)
        retry=bench.device_run_script(STAGE,240,4096,retry_preboot=True)
        self.assertIn('--data "$STAGE/data"',retry)
        self.assertIn('"$STAGE/gpu-bench/attempted"',retry)
        self.assertIn('"$STAGE/bin/xnuhost-gpu-retry"',retry)
        self.assertIn('"$STAGE/gpu-bench/retry-preboot/xnuhost.log"',retry)
        self.assertIn('--mode bench',retry)
        self.assertIn('--set bridges=0',retry)
        self.assertIn('timeout -s TERM -k 15 240',retry)
        self.assertNotIn('gpu-bench/retry-preboot',orig)
        for part in (orig,retry):
            p=subprocess.run(['sh','-n'],input=part,text=True,capture_output=True)
            self.assertEqual(0,p.returncode,p.stderr)

    def test_readonly_inspection_only_calls_root_for_read(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        harness=SimpleNamespace(root=Mock(return_value=SimpleNamespace(stdout='BENCH_ATTEMPTED=NO\n')))
        report={}
        bench.inspect_stage(STAGE,harness,['adb','-s','phone'],report)
        self.assertIn('BENCH_ATTEMPTED=NO',report['inspection'])
        self.assertIn('tail -n 80',harness.root.call_args[0][1])
        self.assertNotIn('rm -',harness.root.call_args[0][1])
        self.assertNotIn('cp ',harness.root.call_args[0][1])


    def test_android_lock_replaced_with_atomic_one_shot_claim(self):
        # Android returned "flock: Bad file descriptor" before the guest boot.
        for retry in (False, True):
            script = bench.device_run_script(STAGE, 240, 4096, retry_preboot=retry)
            active_script = "\n".join(
                line for line in script.splitlines()
                if not line.lstrip().startswith("#")
            )
            self.assertNotRegex(active_script, r'(?m)^\s*(?:if\s+!\s*)?flock(?:\s|$)')
            self.assertNotIn('exec 8>', active_script)
            self.assertIn('launch.claim', script)
            self.assertIn('mkdir -m 700 "$STAGE/', script)
            self.assertNotIn('rmdir "$STAGE/', script)
            p = subprocess.run(['sh','-n'],input=script,text=True,capture_output=True)
            self.assertEqual(0,p.returncode,p.stderr)

        # A mkdir is atomic and permanent: a second launcher fails closed.
        script = bench.device_run_script(STAGE, 240, 4096)
        begin = script.index('# An atomic, permanent one-shot claim')
        end = script.index("printf 'preparing", begin)
        claim = script[begin:end]
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / 'gpu-bench'
            d.mkdir()
            prefix = 'set -u\nSTAGE="' + td + '"\nFAIL="' + str(d / 'run.log') + '"\n'
            p = subprocess.run(['sh'],input=prefix+claim,text=True,capture_output=True)
            self.assertEqual(0,p.returncode,p.stderr)
            self.assertTrue((d / 'launch.claim').is_dir())
            p = subprocess.run(['sh'],input=prefix+claim,text=True,capture_output=True)
            self.assertEqual(2,p.returncode,p.stderr)
            self.assertIn('ERROR=launch_already_claimed', (d/'run.log').read_text())

    def test_exact_fd_error_retry_only_without_any_guest_evidence(self):
        _, retry_shell = bench.safe_shell(STAGE,'a'*64,'b'*16,retry_preboot=True)
        self.assertIn('ERROR=locked', retry_shell)
        self.assertIn('flock: flock: Bad file descriptor', retry_shell)
        self.assertIn('previous guest session tree exists', retry_shell)
        begin = retry_shell.index("previous_error=$(grep")
        end = retry_shell.index('[ ! -e "$STAGE/gpu-bench/session" ]', begin)
        gate = retry_shell[begin:end]
        with tempfile.TemporaryDirectory() as td:
            d = Path(td) / 'gpu-bench'
            d.mkdir()
            (d/'run.log').write_text('ERROR=locked\n')
            (d/'device-run.log').write_text('flock: flock: Bad file descriptor\n')
            prefix = 'STAGE="' + td + '"\nfail() { exit 2; }\n'
            def check():
                return subprocess.run(['sh'],input=prefix+gate,text=True,capture_output=True)
            self.assertEqual(0,check().returncode)
            (d/'device-run.log').write_text('other: Failure\n')
            self.assertEqual(2,check().returncode)
            (d/'device-run.log').write_text('flock: flock: Bad file descriptor\n')
            (d/'run.log').write_text('ERROR=locked\nERROR=other\n')
            self.assertEqual(2,check().returncode)
            (d/'run.log').write_text('ERROR=unexpected\n')
            self.assertEqual(2,check().returncode)
            (d/'run.log').write_text('ERROR=trusted_addon_missing\n')
            self.assertEqual(0,check().returncode)


class GuestFullLogAnalysisTests(unittest.TestCase):
    def test_old_head_and_real_fence_windows_avoid_tail_false_negative(self):
        # The actual 2026-11-19 guest log was 10,874 lines; old collection
        # truncated its boot args and renderer-negotiation lines.
        log = ('xnuhost I placed: boot-args "debug=1 vgpu-3d=1"\n'
               'guest oneios-gpu: virtio GPU with the DRM native context\n'
               + 'guest idle\n' * 8000
               + 'xnuhost I gpu: 10 s host: backboardd fences 125, submit->retired mean 2424 us\n'
               + 'xnuhost I gpu: 10 s host: backboardd fences 84, submit->retired mean 2107 us\n'
               + 'xnuhost I gpu: 10 s host: backboardd fences 27, submit->retired mean 3071 us\n')
        full = bench.summarize_log(log)
        self.assertTrue(full['bootargs_vgpu_3d'])
        self.assertTrue(full['gpu_drm_native'])
        self.assertTrue(full['gpu_execution_observed'])
        self.assertEqual(125, full['backboardd_fences_max'])
        self.assertEqual(236, full['backboardd_fences_reported_total'])
        self.assertEqual(3, full['backboardd_fence_windows'])
        # Regression evidence: the former tail-only summarizer was wrong.
        tail_only = bench.summarize_log('\n'.join(log.splitlines()[-7000:]))
        self.assertFalse(tail_only['bootargs_vgpu_3d'])
        self.assertFalse(tail_only['gpu_execution_observed'])

    def test_analyze_log_without_phone_never_calls_adb(self):
        import json
        from unittest.mock import patch
        log = ('xnuhost I placed: boot-args "debug vgpu-3d=1"\n'
               'guest oneios-gpu: virtio GPU with the DRM native context\n'
               'xnuhost I gpu: backboardd fences 12, submit->retired mean 1000 us\n')
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / 'full.log'
            report_file = Path(td) / 'report.json'
            file.write_text(log)
            with patch.object(bench, 'load_harness', side_effect=AssertionError('ADB is forbidden for analyze-log')):
                rc = bench.main(['analyze-log', '--log', str(file), '--output', str(report_file)])
            self.assertEqual(0, rc)
            result = json.loads(report_file.read_text())
            self.assertEqual('OBSERVED', result['GUEST_GPU_PATH'])
            self.assertEqual('UNVERIFIED', result['IOS_VULKAN'])
            self.assertEqual(12, result['markers']['backboardd_fences_reported_total'])
            self.assertEqual(str(file), result['source_log'])

    def test_vk_error_prevents_gpu_path_pass(self):
        sample = ('xnuhost I placed: boot-args "debug=1 vgpu-3d=1"\n'
                  'oneios-gpu: virtio GPU with the DRM native context\n'
                  'xnuhost I gpu: backboardd fences 8\n'
                  'oneios-gpu-text Vulkan(VkResultCode(-3))\n')
        marks = bench.summarize_log(sample)
        self.assertTrue(marks['legacy_vulkan_failure'])
        self.assertFalse(marks['gpu_execution_observed'])


    def test_missing_guest_log_preserves_preboot_device_error(self):
        source = SOURCE.read_text()
        begin = source.index('        log_name = stage + "/" + log_dir + "/xnuhost.log"')
        until_runlog = source.index('        device_log = harness.root', begin)
        collection = source[begin:until_runlog]
        self.assertIn('2>/dev/null || echo 0', collection)
        self.assertIn('host_log = ""', collection)
        self.assertIn('log_collection_warning', collection)
        self.assertNotIn('raise RuntimeError', collection)
        self.assertIn('device_log', source[until_runlog:])

if __name__=='__main__':
    unittest.main()
