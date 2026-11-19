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

if __name__=='__main__':
    unittest.main()
