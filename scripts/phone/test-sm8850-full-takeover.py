#!/usr/bin/env python3
"""Host-only safety/contract tests for the actual SM8850 full iOS takeover.

All tests are static source contract checks and pure host Python. They never
contact ADB, start xnuhost, open watchdog devices, or stop Android Framework.
"""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
TAKEOVER_SOURCE = ROOT / "scripts/phone/sm8850-takeover.py"
STAGER = ROOT / "scripts/phone/framework-stage.sh"
WRAPPER = ROOT / "scripts/phone/sm8850-full-takeover.sh"
ONEOS_SWITCH = ROOT / "app/switcher/assets/oneios_switch.sh"
ONEOS_RETURN = ROOT / "app/switcher/assets/oneios_return.sh"

spec = importlib.util.spec_from_file_location("oneios_full_sm8850", TAKEOVER_SOURCE)
takeover = importlib.util.module_from_spec(spec)
spec.loader.exec_module(takeover)


class FullTakeoverOfflineTest(unittest.TestCase):
    def test_full_runtime_is_real_iOS_8vCPU_GPU3D_touch_and_reboot600(self):
        source = ONEOS_SWITCH.read_text()
        self.assertIn('--cpus 8 --ram 4G', source)
        self.assertIn('--gpu auto --display shm --set touch-exclusive=1', source)
        self.assertIn('host_allowed=$(awk', source)
        self.assertIn('[ "$host_online" = 0-7 ] && [ "$host_allowed" = 0-7 ]', source)
        self.assertIn('fw_seconds=600', source)
        self.assertIn('if [ "$FW_MODE" = run ]; then', source)
        self.assertIn('exec "/data/runtime/$R_XNUHOST" --session-abi 1 --mode bench', source)
        self.assertIn('I_ACCEPT_LEGACY_WATCHDOG_FULL_600S_RISK', source)
        self.assertIn('SM8850_PREVIOUS_REBOOT_SMOKE=VERIFIED_DEADLINE_REQUEST_ONLY', source)
        self.assertIn('the attested 3D, 8-vCPU, 600s guest stage was not finalized', source)
        self.assertIn('reboot-deadline-or-manual*"who=framework-deadline"', source)
        self.assertTrue(
            'isolated APFS Data clone was already consumed' in source,
            'OneOS must reject a previously consumed isolated APFS Data clone',
        )
        self.assertIn('APFS_DATA_CLONE=CONSUMED_ONE_SHOT_BEFORE_FRAMEWORK_STOP', source)
        self.assertTrue(
            "host_allowed=$(awk '/^Cpus_allowed_list:/ {print $2}' /proc/self/status)" in source,
            '8-core guard must inspect the inherited CPU affinity of its own process',
        )
        self.assertNotIn('/proc/$/status)', source)

    def test_reboot_return_is_still_native_oneos_without_inplace_handback(self):
        switch = ONEOS_SWITCH.read_text()
        returner = ONEOS_RETURN.read_text()
        self.assertIn("printf 'reboot\\n' > \"$CTL/framework.return\"", switch)
        self.assertIn('oneios-sm8850-reboot-return', returner)
        self.assertIn('no in-place watchdog handback', returner)
        self.assertIn('OneOS legacy /dev/watchdog magic close', switch)
        self.assertIn('WD_FIRST=10', switch)
        self.assertIn('watchdog_failed "OneOS legacy V write never succeeded within bounded handoff"', switch)
        self.assertNotIn('persist.vendor.softdog=off', switch)

    def test_staging_uses_trusted_native_build_and_fresh_data(self):
        stage = STAGER.read_text()
        host = TAKEOVER_SOURCE.read_text()
        self.assertIn('files["native/" + name] = source', host)
        self.assertIn('files["native.sha256"]', host)
        self.assertIn('sm8850-ios27-3d-8cpu-600s', stage)
        self.assertIn('install -m 700 "$path" "$incoming/runtime/bin/$name"', stage)
        self.assertIn('the GPU-3D artifact list must have exactly four expected files', stage)
        self.assertIn('independent one-shot APFS Data snapshot staged', stage)
        self.assertIn('source changed', stage)
        self.assertIn('clone hash or source identity changed', stage)
        self.assertIn('GUEST_TAKEOVER_LIVE_AUTHORIZED=NO', stage)
        self.assertNotIn('xnuhost=bin/xnuhost-gui-bench', stage)

    def test_wrapper_only_runs_full_takeover_after_explicit_ack(self):
        script = WRAPPER.read_text()
        self.assertIn('mode="$' + '{1:-}"', script)
        self.assertIn('--i-accept-10-minute-legacy-watchdog-risk', script)
        self.assertIn('sm8850-takeover.py', script)
        self.assertIn('--run --confirm --accept-legacy-watchdog-risk', script)
        self.assertIn('--duration 600 --gpu auto', script)
        self.assertIn('--prepare --confirm', script)
        self.assertIn('make -C runtime/xnuhost -j"$jobs"', script)
        self.assertIn('make -C runtime/display -j"$jobs"', script)
        self.assertIn('PHYSICAL_KEYS=DO_NOT_PRESS_BOTH_VOLUME_KEYS', script)
        self.assertIn('git -C app rev-parse HEAD', script)

    def test_shell_syntax_bash_and_available_mksh(self):
        shells = [shutil.which("bash"), shutil.which("sh")]
        for shell in (shutil.which("mksh"),):
            if shell:
                shells.append(shell)
        for shell in filter(None, shells):
            for script in (STAGER, ONEOS_SWITCH, ONEOS_RETURN):
                with self.subTest(shell=shell, script=script.name):
                    result = subprocess.run(
                        [shell, "-n", str(script)], capture_output=True, text=True, timeout=10
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
        shell = shutil.which("bash")
        if shell:
            result = subprocess.run([shell, "-n", str(WRAPPER)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
