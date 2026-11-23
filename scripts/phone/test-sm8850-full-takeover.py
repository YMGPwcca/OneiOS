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
        self.assertIn('--gpu 3d --display shm --set touch-exclusive=1', source)
        self.assertNotIn('--gpu auto --display shm', source)
        self.assertIn('ONEIOS_GPU_3D_MODE=REQUIRED_FAIL_CLOSED_NO_2D_FALLBACK', source)
        runtime = (ROOT / 'runtime/xnuhost/src/main.c').read_text()
        self.assertIn('if (!gpu3d && !strcmp(config.gpu, "3d"))', runtime)
        self.assertIn('gpu: no 3D:', runtime)
        self.assertIn('host_allowed=$(awk', source)
        self.assertIn('[ "$host_online" = 0-7 ] && [ "$host_allowed" = 0-7 ]', source)
        self.assertIn('fw_seconds=$FW_DURATION', source)
        self.assertIn('FW_DURATION=600', source)
        self.assertIn('FW_DURATION=${6:-600}', source)
        # Full-bridges takeover does not use the older affinity-only benchmark.
        # It must opt in to actual CPU and device bridges, with vCPU pinning.
        self.assertIn('--set cpu-affinity-bench=0 --set cpu-pin=1', source)
        self.assertIn('--set bridges=1 --set sm8850-full-bridges=1', source)
        self.assertIn('ONEIOS_CPU_PLACEMENT_BRIDGE=ACTIVE_BRIDGES_1_CPU_PIN_1', source)
        self.assertNotIn('--set bridges=0', source)
        self.assertIn('root thermal sensor manifest not qualified on current boot', source)
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

    def test_exclusive_interactive_wake_and_power_key_without_volume_leak(self):
        switch = ONEOS_SWITCH.read_text()
        input_source = (ROOT / 'runtime/xnuhost/src/input.c').read_text()
        input_header = (ROOT / 'runtime/xnuhost/src/xnuhost.h').read_text()
        native_test = (ROOT / 'runtime/xnuhost/tests/test_xnuhost.c').read_text()
        # Both guarded and explicitly risk-accepted 180s modes send WAKEUP
        # before stopping Android's input service; the 180s mode additionally
        # uses bounded pre-stop pulses. No Android input after system_server exits.
        before = switch.index('input keyevent KEYCODE_WAKEUP')
        stop = switch.index('if ! stop_android_framework; then')
        self.assertLess(before, stop)
        self.assertIn('FRAMEWORK_PANEL_WAKE=ANDROID_KEYCODE_WAKEUP_PRE_STOP', switch)
        self.assertIn('switch-panel-wake-refused', switch)
        self.assertIn('while [ "$wake_pulses" -lt 4 ]; do', switch)
        self.assertIn('FRAMEWORK_FINAL_WAKE=KEYCODE_WAKEUP_IMMEDIATELY_PRE_STOP', switch)
        self.assertIn('--set bridges=1 --set sm8850-full-bridges=1', switch)
        self.assertIn('bool have_touch = false, have_power = false;', input_source)
        self.assertIn('keys = !have_power && bit(key, KEY_POWER);', input_source)
        self.assertIn('sources[nfds].power_only = true;', input_source)
        self.assertIn('sources[nfds].suppress_volume = touch_exclusive;', input_source)
        self.assertIn('bool       touch, dropping, power_only, suppress_volume;', input_header)
        self.assertIn('(!s->suppress_volume || side_keys[k] == KEY_POWER_)', input_source)
        self.assertIn('bench_keys.power_only = true;', native_test)
        self.assertIn('bench_keys.suppress_volume = true;', native_test)

    def test_integrated_default_branch_requires_explicit_180s_and_full_bridges(self):
        """Post-merge regression: branch name must not weaken live takeover admission."""
        wrapper = WRAPPER.read_text()
        host = TAKEOVER_SOURCE.read_text()
        telemetry = (ROOT / "scripts/phone/sm8850-600s-thermal-telemetry.py").read_text()
        local_ci = (ROOT / "scripts/phone/sm8850-full-bridges-local-ci.sh").read_text()
        self.assertIn('feat/oneios-sm8850-m3q|feat/sm8850-full-bridges-takeover)', wrapper)
        self.assertIn('FULL_BRIDGES_BRANCH=1', wrapper)
        self.assertIn('[ "$FULL_BRIDGES_BRANCH" = 1 ]', wrapper)
        self.assertIn('I_ACCEPT_UNQUALIFIED_180S_LIVE_TEST', wrapper)
        self.assertIn('[ "$duration_explicit" = 1 ] && [ "$duration" = 180 ]', wrapper)
        self.assertIn('full bridges allows only stage-runtime, rearm or 180s run', wrapper)
        self.assertIn('in {"feat/oneios-sm8850-m3q", "feat/sm8850-full-bridges-takeover"}', host)
        self.assertIn('branch in {"feat/oneios-sm8850-m3q", "feat/sm8850-full-bridges-takeover"}', telemetry)
        self.assertIn('feat/oneios-sm8850-m3q|feat/sm8850-full-bridges-takeover)', local_ci)
        self.assertNotIn('feat/oneios-sm8850-m3q|feat/sm8850-guarded-duration-tracing)', wrapper)

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
        self.assertIn('"oneios_sm8850_thermal_cap.sh"', host)
        self.assertIn('"oneios_sm8850_thermal_takeover_guard.sh"', host)
        self.assertIn('thermal_manifest_build()', stage)
        self.assertIn('thermal.guard.manifest', stage)
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
        self.assertIn('--duration "$duration" --gpu 3d', script)
        self.assertIn('[ "$duration" -ge 60 ]', script)
        self.assertIn('[ "$duration" -le 600 ]', script)
        self.assertIn('--prepare --confirm', script)
        self.assertIn('make -C runtime/xnuhost -j"$jobs"', script)
        self.assertIn('make -C runtime/display -j"$jobs"', script)
        self.assertIn('PHYSICAL_KEYS=DO_NOT_PRESS_BOTH_VOLUME_KEYS', script)
        self.assertIn('git -C app rev-parse HEAD', script)

    def test_full_run_safety_warnings_do_not_claim_gpu_fps_or_return_certification(self):
        wrapper = WRAPPER.read_text()
        root_switch = ONEOS_SWITCH.read_text()
        host = TAKEOVER_SOURCE.read_text()
        self.assertIn('THERMAL_SAFETY=ROOT_GUARD_AND_MONOTONIC_THROTTLE_REQUIRED', wrapper)
        self.assertIn('CPU_AFFINITY=BENCH_ONLY_EIGHT_DISTINCT_HOST_CORES_REQUIRED', wrapper)
        self.assertIn('WARNING=GPU_3D_REQUIRED_NO_2D_FALLBACK', wrapper)
        # Sensor/CPU bridges enabled in guest do not certify the independent
        # root-side thermal guard: guarded and exact 180s no-soft-guard modes
        # must remain separately identified, never conflated.
        self.assertIn('SM8850_FULL_RUN_THERMAL_BRIDGE=ACTIVE_BRIDGES_1_ROOT_MONITOR_MANDATORY', root_switch)
        self.assertIn('SM8850_FULL_RUN_THERMAL_BRIDGE=NO_ROOT_THERMAL_GUARD; HOST_READ_ONLY_TELEMETRY_ONLY', root_switch)
        self.assertIn('ONEIOS_BENCH_THERMAL_BRIDGE=ACTIVE_READ_ONLY_ROOT_GUARD_SEPARATE', root_switch)
        self.assertIn('ONEIOS_BENCH_THERMAL_BRIDGE=ACTIVE_WITH_NO_ROOT_THERMAL_MONITOR', root_switch)
        self.assertIn('ONEIOS_CPU_PLACEMENT_BRIDGE=ACTIVE_BRIDGES_1_CPU_PIN_1', root_switch)
        self.assertIn('sm8850_no_userspace_thermal()', root_switch)
        self.assertIn('disabled-180s', root_switch)
        self.assertIn('framework_thermal_guard_healthy()', root_switch)
        self.assertIn('framework_thermal_cap_healthy()', root_switch)
        self.assertIn('SM8850_FULL_RUN_RECOVERY=DEADLINE_AND_UNASSISTED_RETURN_NOT_FULLY_VERIFIED', root_switch)
        self.assertIn('GPU_3D_STATUS=BACKEND_MUST_BE_CONFIRMED_IN_XNUHOST_LOG', host)
        self.assertNotIn('UNASSISTED_RETURN_AND_GUEST_START=NOT_VERIFIED', host)

    def test_inner_guest_mount_protects_scripts_without_busybox_file_remount(self):
        source = ONEOS_SWITCH.read_text()
        begin = source.index('    --inner)')
        end = source.index('    --stop-loop)', begin)
        inner = source[begin:end]
        self.assertIn('for d in data session; do', inner)
        self.assertIn('mount --bind "/data/$d" "/data/$d"', inner)
        self.assertIn('mount -o remount,bind,ro /data /data', inner)
        self.assertIn('the staged /data root is writable', inner)
        self.assertIn('guest writable island is read-only', inner)
        self.assertIn('if true 2>/dev/null > /data/control/.w', inner)
        self.assertNotIn('for d in runtime image control bin oneios_switch.sh oneios_return.sh', inner)
        self.assertNotIn('mount -o remount,bind,ro "/data/$d"', inner)
        self.assertNotIn('mount -o remount,bind,ro /data ||', inner)
        self.assertNotIn('mount -o remount,bind,ro "$dst" ||', STAGER.read_text())
        self.assertIn('probe="$check/.oneios-write-check.' + chr(36) * 2 + '"', inner)
        self.assertLess(
            inner.index('for d in data session; do'),
            inner.index('mount -o remount,bind,ro /data /data'),
            'Data/session write mounts must be isolated before making stage root ro',
        )
        self.assertLess(
            inner.index('mount -o remount,bind,ro /data /data'),
            inner.index('echo ' + chr(36) * 2 + ' > /data/session/xnuhost.pid'),
            'Fail-safe read-only guard must finish before guest pid is published',
        )

    def test_rearm_only_fresh_apfs_clone_and_preserve_old_image_logs(self):
        stage = STAGER.read_text()
        host = TAKEOVER_SOURCE.read_text()
        wrapper = WRAPPER.read_text()
        self.assertIn('probe|prepare|rearm-data|upgrade-runtime)', stage)
        self.assertIn('if [ "$operation" = rearm-data ]; then', stage)
        # A REAL guest may write its one-shot clone; that must not make
        # it impossible to create a NEW isolated clone from the original
        # benchmark seed. Always preserve the old guest Data and marker.
        self.assertIn('APFS_CONSUMED_GUEST_DATA=MODIFIED_PRESERVE_OLD', stage)
        self.assertIn('APFS_REARM_ORIGINAL_SOURCE=EXISTING_BENCHMARK_SEED_NOT_HISTORICALLY_ATTESTED', stage)
        self.assertIn('original seed aliases the already-consumed guest Data', stage)
        self.assertIn('consumed guest Data changed during rearm inspection', stage)
        self.assertIn('source_id=$(file_id "$source")', stage)
        self.assertIn('[ "$(file_id "$source")" = "$source_id" ]', stage)
        self.assertIn('printf \'%s  %s\\n\' "$old_sha" "$name" >> "$incoming/consumed-data.sha256"', stage)
        self.assertIn('mv "$incoming/consumed-data.sha256" "$archive/consumed-data.sha256"', stage)
        self.assertIn('mv "$incoming/rearm-source.sha256" "$archive/rearm-source.sha256"', stage)
        self.assertNotIn('rm -f "$stage/data.consumed"', stage)
        self.assertNotIn('find_pristine_seed_archive()', stage)
        self.assertIn('mv "$stage/data" "$archive/data"', stage)
        self.assertIn('mv "$stage/data.consumed" "$archive/data.consumed"', stage)
        self.assertIn('mv "$stage/image.ready" "$stage/image.ready.rearm-pending"', stage)
        self.assertIn('mv "$incoming/data" "$stage/data"', stage)
        self.assertIn('SM8850_MOUNT_NAMESPACE_PROBE=PASS_NO_FRAMEWORK_STOP', stage)
        self.assertIn('p="$writable/.probe-write.' + chr(36) * 2 + '"', stage)
        self.assertIn('"$bb_probe" unshare -m /system/bin/sh -s --', stage)
        self.assertIn('mount -o remount,bind,ro "$dst" "$dst"', stage)
        self.assertIn('Android BusyBox cannot create read-only guest stage', stage)
        self.assertIn('APFS_DATA_REARMED=YES', stage)
        self.assertIn('"rearm-data"', host)
        self.assertIn('if [ "$mode" = rearm ]; then', wrapper.replace('elif', 'if'))
        self.assertIn('--rearm-data --confirm --serial "$serial"', wrapper)
        self.assertIn('--upgrade-runtime --confirm --serial "$serial"', wrapper)
        self.assertLess(wrapper.index('--upgrade-runtime --confirm'), wrapper.index('--rearm-data --confirm'))
        self.assertIn('NATIVE_RUNTIME_UPGRADE=PASS_BACKUP_PRESERVED', stage)
        self.assertIn('APFS_DATA=CONSUMED_STILL_REQUIRES_SEPARATE_REARM', stage)
        self.assertIn('mv "$stage/runtime" "$archive/runtime"', stage)
        self.assertIn('mv "$stage/runtime.sha256" "$archive/runtime.sha256"', stage)
        self.assertIn('mv "$stage/image.ready" "$stage/image.ready.runtime-pending"', stage)
        self.assertIn('if operation in {"prepare", "upgrade-runtime"}:', host)
        self.assertIn('"upgrade-runtime"', host)
        self.assertIn('--framework-check run', wrapper)
        self.assertIn('FULL_TAKEOVER_ADMISSION=PASS_NO_FRAMEWORK_STOP', wrapper)
        self.assertIn('FULL_TAKEOVER_STAGE=REARMED', wrapper)

    def test_original_reboot_smoke_can_be_read_from_root_owned_archive(self):
        source = ONEOS_SWITCH.read_text()
        self.assertIn('sm8850_old_smoke_valid()', source)
        self.assertIn('"$STAGE"/logs/session.*', source)
        self.assertIn('root_only "$sr_archive"', source)
        self.assertIn('root_only "$sr_outcome_path"', source)
        self.assertIn('SM8850_SMOKE_PROOF_SOURCE=$smoke_proof', source)
        self.assertIn('verified original smoke proof missing from root-owned current or archived session; full run refused', source)
        self.assertIn('smoke_proof=archived', source)

    def test_bounded_duration_telemetry_has_no_hardcoded_600s_timeline(self):
        source = (ROOT / "scripts/phone/sm8850-600s-thermal-telemetry.py").read_text()
        self.assertIn('ap.add_argument("--duration", type=int, default=600', source)
        self.assertIn('FINAL_NEAR_DEADLINE', source)
        self.assertIn('duration-10', source)
        self.assertIn('"--duration", str(duration)', source)
        self.assertIn('FRAMEWORK_TIMEBASE=MISMATCH', source)
        self.assertIn('meta.get("ctl/framework.duration") == str(duration)', source)

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
