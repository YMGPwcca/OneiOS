# SM8850: visually verify iOS GPU on the phone (no takeover)

This is **not** a recovery or Framework-takeover test. The 2026-11-19 full
headless capture already established `vgpu-3d=1`, a DRM-native guest renderer,
AGX type `0x4149`, 236 retired backboardd fences across 13 windows, and six
drawn IOSurfaces. What remained missing was **visually seeing** the iOS screen.

`sm8850-ios-gpu-visual.py run` builds the current `xnuhost` and Android
SurfaceFlinger display helper locally, verifies phone safety, creates **one new
8 GiB isolated APFS Data clone**, and launches a bounded iOS 27 `--mode bench`
with `--gpu auto --display shm --no-input --set bridges=0`. The display helper
connects to the guest's `session/display.sock` via `--socket`, without
`--takeover`, so its layer can show the iOS boot console and eventually
SpringBoard on top of an **otherwise running Android One UI**. Both guest and
layer have on-device timeouts independent of the SSH/ADB connection. The guest
uses the original **trusted** GPU addon/trustcache; there is no unverified
plugin/trustcache replacement.

The original Data remains **read-only**; the new snapshot is the only writable
guest Data store. The previous snapshot (nonce `6e89899ca4039fed`) is already
**consumed** and must NOT be reused or deleted. The script never performs
Framework takeover, operates watchdog devices, remounts partitions, grabs
physical input, edits original APFS, or deletes any snapshot.

## One command on CachyOS via PowerShell

```powershell
Invoke-OneIOS @'
set -euo pipefail
cd ~/projects/OneiOS
export PATH="$HOME/Android/Sdk/platform-tools:$PATH"
git pull --ff-only
python3 scripts/phone/test-sm8850-ios-gpu-visual.py -v
python3 scripts/phone/sm8850-ios-gpu-visual.py run --duration 240 --ram-mib 4096
'@
```

Keep the S26 Ultra **unlocked, display on, and visible**. When the terminal
prints `LIVE_VIEW=CHECK_PHONE_SCREEN_NOW`, look at the **physical phone**.
The temporary full-screen layer may first show a boot console, an Apple logo,
or dark frames while the guest initializes; look for recognizably iOS
SpringBoard/home-screen content or moving UI. It does **not** accept touch
input in this safe bench. The layer automatically disappears when the guest
ends, returning you to One UI. If viewing remotely, you may optionally mirror
the phone with your existing screen mirroring tool; this is not required.

Live telemetry printed while the demo runs:

- `LIVE_DISPLAY_FIRST_FRAME=POSTED`: SurfaceFlinger helper posted at least one
  guest framebuffer. This is **not** by itself proof of 3D GPU.
- `LIVE_ADRENO_FENCES=OBSERVED`: host saw a positive backboardd fence window
  from this same guest. This supports GPU execution, but is not an API-level
  `vkCreateDevice` trace.

After it stops, the tool reports `DISPLAY_FIRST_FRAME`, display frame count,
`GPU_BOOTARGS_VGPU3D`, `GPU_DRM_NATIVE`, backboardd GPU fences, `VK_ERROR_MINUS3`,
`QUARTZCORE_ABORT`, `GUEST_GPU_PATH`, and `IOS_VULKAN`. The latter stays
`UNVERIFIED` without trusted instrumented Vulkan API traces. A screen showing
iOS *plus* positive GPU fences supports the live visual GPU path, not a blanket
claim that every Metal/Vulkan feature passes.

## Non-negotiable gates and recovery boundaries

This visual command first checks the exact SM-S948B/m3q/SM8850 device and
firmware, root, SELinux Enforcing, Android Framework, no other guest, battery,
temperature, and free space. **It also requires the existing global
`/proc/sys/vm/max_map_count >= 1048576` before making the new clone.** The
previous bench raised that value from 65530; `xnuhost` can still write this
global sysctl if the value unexpectedly drops, so the runner checks before
staging and again before guest execution. It never writes the sysctl itself.
If the device rebooted and the limit reset, the visual command blocks *before*
cloning; do not disable that gate just to force a boot.

The guest `timeout -s TERM -k 15 240` (for a 240-second run) and separate
display helper `timeout -s TERM -k 10 285` run on the phone. Closing SSH cannot
extend these limits. Resource pressure is still real: the guest uses 4 GiB
of RAM, host GPU, and CPU. `system_server`/zygote must remain running;
no full takeover is authorized. Only a **fresh** Data clone may be used for
each visual boot. The script retains all snapshots, original backups and
`gpu-bench` logs; an interrupted session is not automatically replayed.

Device logs: `<new-stage>/gpu-bench/{xnuhost.log,display.log,run.log,state}`.
Local logs/reports: `out/sm8850/gpu-acceptance/<timestamp>-visual-*.log` and
`<timestamp>-ios-gpu-visual.json`. Do not assume visually rendering a boot
console means stable iOS GUI: SpringBoard rendering and the
`cameracaptured host_statistics64()` ABI warning remain areas to validate.

If the temporary visual layer remains on the screen after guest termination,
check whether `OneiOSDisplay` is still running; do not stop Android's
surfaceflinger or system_server as a workaround. The helper normally removes
its own layers on socket close or process death and has a separate timeout.
