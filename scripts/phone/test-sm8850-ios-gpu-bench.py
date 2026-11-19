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
            self.assertNotIn('flock -n 8', script)
            self.assertNotIn('exec 8>', script)
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

if __name__=='__main__':
    unittest.main()
