# SM8850 bounded iOS GPU-auto bench (One UI remains running)

**OneiOS · Galaxy S26 Ultra / SM8850 · Bounded GPU bench notes**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!NOTE]
> This page is earlier device evidence or an experimental design record. Compare with the [latest physical status](SM8850_LIVE_STATUS_2026-11-20.md); do not infer current safety or performance from a historical PASS.

This is the **first guest hardware attempt after the vgpu-3d=1 source fix**, not a Framework takeover or a stable-GUI acceptance test. It uses the previously SHA-256-verified, independent 8 GiB APFS Data snapshot at a nonce-only path, a newly built Android `xnuhost`, and the **original** GPU addon and trustcache already installed in the benchmark image. The runner does not modify Apple binaries, boot partitions, original APFS Data or watchdog devices. **Exception:** `xnuhost` itself raises global `vm.max_map_count` when below 1,048,576 (`runtime/xnuhost/src/mem.c`). This setting is not restored automatically.

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

Results are intentionally split: `GPU_BOOTARGS_VGPU3D`, `GPU_DRM_NATIVE`, `GPU_FENCES_MAX`, `GPU_FENCES_REPORTED_TOTAL` (sum of non-cumulative accounting intervals), `GUEST_GPU_PATH`, `VK_ERROR_MINUS3` and `QUARTZCORE_ABORT`. `IOS_VULKAN=UNVERIFIED` is expected until a trusted instrumented addon can show successful `vkEnumeratePhysicalDevices` and `vkCreateDevice`. Avoid interpreting a software frame or host `gpuctl` success as proof of iOS GPU acceleration.

**Risks and limitations:** This is a real 4-GiB iOS guest boot and can pressure CPU/GPU/RAM while Android runs. It has a hard deadline but does not yet qualify GUI stability, recovery handback or a complete isolation mechanism against all nonparticipating writers. Do not use it for Framework takeover. Preserve the original off-device recovery backup and the snapshot logs. Do not remove snapshot/rollback data as cleanup.

## Verified S26 Ultra headless guest GPU evidence, 2026-11-19

The bounded device run exited `finished:124` after 240 seconds while Android
`system_server` and zygote stayed alive. The complete phone log had 10,874
lines / 1,324,589 bytes. Line 26 contained `vgpu-3d=1`; line 175 logged
`virtio GPU with the DRM native context`. NativeAdrenoMetal and its
`libvulkan_freedreno.dylib` passed library validation, and AGX user client
0x4149 opened successfully. Thirteen GPU accounting windows reported **236**
backboardd retired fences (maximum 125 in one window). Guest telemetry
reported six drawn IOSurfaces and reads by MercuryPosterExtension.

The provided filtered log had no `VkResultCode(-3)` or old QuartzCore
push_surface assertion, but no direct `vkCreateDevice` trace either.
Therefore `GUEST_GPU_PATH=OBSERVED` is supported and `IOS_VULKAN=UNVERIFIED`
remains the correct strict result. A headless 240-second boot does not
establish visible SpringBoard UI or takeover safety.

The previous runner incorrectly printed `GPU_BOOTARGS_VGPU3D=False` and
`GPU_DRM_NATIVE=False` because it tailed only the last 7,000 lines,
missing initialization near the beginning. The runner now collects the
complete log (up to 64 MiB). Re-analyze the saved log without booting:

```sh
python3 scripts/phone/sm8850-ios-gpu-bench.py analyze-log \
  --log out/sm8850/gpu-acceptance/ios27-gpu-retry-full.log
```

**Global sysctl mutation confirmed:** `MAP_COUNT_BEFORE=65530`,
`MAP_COUNT_AFTER=1048576`, and the last read-only check still showed
1,048,576. `xh_mem_map_limit()` in `runtime/xnuhost/src/mem.c` raised it.
The previous claims of no sysctl changes were incorrect. This global
setting should not be blindly lowered while other processes might rely
on its higher limit; a safe ownership/restore protocol remains open.

**Separate guest warning:** `cameracaptured[50]` repeatedly logged
`host_statistics64() count is larger than expected`
(`actual:104 > HOST_VM_INFO64_COUNT:62`) with a memory-corruption warning.
This needs ABI triage before any Framework takeover.

The snapshot is now consumed by a guest run. Preserve it for evidence;
never run another one-shot guest against it or modify the original Data.
