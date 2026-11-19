# SM8850 bounded iOS GPU-auto bench (One UI remains running)

This is the **first guest hardware attempt after the vgpu-3d=1 source fix**, not a Framework takeover or a stable-GUI acceptance test. It uses the previously SHA-256-verified, independent 8 GiB APFS Data snapshot at a nonce-only path, a newly built Android `xnuhost`, and the **original** GPU addon and trustcache already installed in the benchmark image. No Apple binary, boot partition, original APFS Data, watchdog device or Android sysctl is modified.

The current signed GPU addon has no Vulkan-API instrumentation. Therefore this run can determine whether the new `xnuhost` supplies `vgpu-3d=1`, whether the DRM-native renderer is offered, whether Vulkan error -3 is still observed, whether any backboardd GPU fences retire, and whether the QuartzCore assertion recurs. **It does not automatically prove `vkCreateDevice` succeeded or that the GUI is stable.** Instrumented addon and matching trustcache would still be a separate, qualified change.

## Run on CachyOS with the USB-attached S26 Ultra

Prerequisite: the phone's `DATA_CLONE_READY=PASS` stage already exists; do **not** create another clone. Android One UI must be running. Only one bench may run at a time.

```sh
cd ~/projects/OneiOS
export PATH="$HOME/Android/Sdk/platform-tools:$PATH"
python3 scripts/phone/test-sm8850-ios-gpu-bench.py -v
make -C runtime/xnuhost -j8 build/android/xnuhost
python3 scripts/phone/sm8850-ios-gpu-bench.py run \
  --stage /data/adb/oneios-m3q-gpu-snapshot-6e89899ca4039fed \
  --duration 240 --ram-mib 4096
```

The runner performs strict USB/firmware/root/Framework/SELinux/storage/temperature checks; stages the new binary with SHA-256; requires an untouched original Data hash and matching separate snapshot; and launches a **single** headless `--mode bench --gpu auto --display none --no-input --set bridges=0` session. The image and original trust artifacts remain at the protected benchmark paths, opened as read-only inputs. Only `--data` points to the new root-owned clone.

The device-side child is launched detached with `nohup`, so losing USB/SSH does not cancel its `timeout -s TERM -k 15 240` deadline. The same snapshot has an `attempted` one-shot marker to prevent silent repetition. The Android Framework remains running and the tool never invokes switch or takeover.

Saved on-device evidence: `<stage>/gpu-bench/run.log`, `xnuhost.log`, `state` and `device-run.log`. Saved on CachyOS: `out/sm8850/gpu-acceptance/*-ios-gpu-bench.json` and `*-ios-gpu-bench.log`. If host USB disappears, the device-side timeout still applies; reconnect later to collect the exact stage files instead of starting another run.

Results are intentionally split: `GPU_BOOTARGS_VGPU3D`, `GPU_DRM_NATIVE`, `GPU_FENCES_MAX`, `VK_ERROR_MINUS3` and `QUARTZCORE_ABORT`. `IOS_VULKAN=UNVERIFIED` is expected until a trusted instrumented addon can show successful `vkEnumeratePhysicalDevices` and `vkCreateDevice`. Avoid interpreting a software frame or host `gpuctl` success as proof of iOS GPU acceleration.

**Risks and limitations:** This is a real 4-GiB iOS guest boot and can pressure CPU/GPU/RAM while Android runs. It has a hard deadline but does not yet qualify GUI stability, recovery handback or a complete isolation mechanism against all nonparticipating writers. Do not use it for Framework takeover. Preserve the original off-device recovery backup and the snapshot logs. Do not remove snapshot/rollback data as cleanup.
