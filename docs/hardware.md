# Hardware integration · Galaxy S26 Ultra

**SM-S948B / m3q / SM8850 · verified device facts and outstanding bridge work**

[← Handbook](README.md) · [Physical status](SM8850_LIVE_STATUS_2026-11-20.md) · [Architecture](architecture.md) · [Safety backlog](TODO.md)

> [!IMPORTANT]
> This is the **current SM8850 hardware reference**. Old device-specific electrical descriptions and logs have been retired from the active manual; they remain in Git history. Never reuse another device's sysfs limits, display, thermal, GPIO or watchdog mapping without measuring this firmware.

## Target identity

| Property | Observed or selected value |
| :--- | :--- |
| Model / codename | Samsung **SM-S948B** / **m3q** |
| SoC / build | **SM8850**, **S948BXXS4BZIG** |
| OS / kernel | Android 17 / One UI 9; Linux `6.12.69-android16-6-pb4d3caf-abogkiS948BXXS4BZIG-4k` |
| Root / SELinux | KernelSU / ephemeral DirtyFrag; **Enforcing** |
| Page size | **4096 bytes** |
| CPU topology exposed to host | **8 CPUs**: CPUs 0–5 capacity 741, CPUs 6–7 capacity 1024 (capacity is not a physical-core label) |
| CPU info maxima | 0–5 **3,628,800 kHz**; 6–7 **4,742,400 kHz**; actual operating ceilings can be much lower |
| GPU evidence | KGSL chip `0x44050a00`, GPU ID 6860, successful native probe and observed real guest 3D activity |

## On-device validation matrix

| Subsystem | Result | Meaning and remaining gap |
| :--- | :--- | :--- |
| Framework stop | **OBSERVED** | The full-run OneOS supervisor stopped the Android Framework |
| Hosted iOS | **OBSERVED** | Guest-ready + first frame, ~600.6 s host runtime |
| GPU / KGSL | **OBSERVED** | Command submissions/imported memory/fence; Vulkan conformance **NOT VERIFIED** |
| Display | **OBSERVED** | Guest image presented; ~200 s excerpt includes many no-post windows; not sustained 60 FPS |
| Touch | **OBSERVED** in earlier bounded preview | Interactive gestures reached iOS; full-run latency needs matched timestamps |
| Haptics | **PASS** standalone native HEAVY_CLICK with physically felt pulse | [2026-11-16 HAL + PCM/opt-in evidence](SM8850_HAPTIC_EVIDENCE_2026-11-16.md); complete iOS guest bridge **NOT VERIFIED** |
| Video encoder | **PASS** HEVC/H.264 host keyframe/EOS tests | Not comprehensive iOS VideoToolbox acceptance |
| Guest RAM | **OBSERVED** 4 GiB locked | No guest swap in measured excerpt; page tables/GPU blobs still significant |
| Battery and skin temperature | **NOT VERIFIED** for live full-run | Thermal time series and independent OneiOS thermal guard are missing |
| Watchdog | **UNVERIFIED_REBOOT_ONLY** | Character-node driver/timeout/handoff are not independently attributable |
| Reboot recovery | **PARTIAL** | New Android boot reason observed; unassisted return and exact requester not certified |
| Wi-Fi/Bluetooth/camera/audio/telephony | **NOT VERIFIED** as fully functional iOS guest bridges | Host inventory and individual probes do not prove guest system integration |

## What runs during the Framework experiment

```text
SM8850 kernel + protected vendor services
├── Qualcomm KGSL + memory allocators
│   └── xnuhost virtio-gpu 3D / drm2kgsl
├── SurfaceFlinger + display composer
│   └── oneios-display helper
├── input device event nodes
│   └── touch-exclusive bench reader
└── OneOS device-side watchdog/deadline/reboot-return
    └── isolated iOS/XNU stage and 4 GiB guest RAM
```

While the Framework is stopped, the OneOS script's protected service inventory included `surfaceflinger`, `vendor.qti.hardware.display.composer`, `adbd`, `vold`, `keystore2`, `servicemanager`, `logd`, `lmkd`, `installd`, `audioserver`, `cameraserver`, and `netd`. The existence of a protected daemon is **not** proof all its clients and APIs work during a guest session.

## Bridge policy

- **Samsung backend:** direct device-specific paths used where there is no applicable vendor HAL or where Framework-independent hardware access has actually been qualified.
- **Treble/AIDL/HIDL backend:** prefer stable vendor HAL interfaces when they remain alive during Framework stop and have a tested client/permission model.
- **Touch-exclusive bench:** the observed physical full-run used `--mode bench --set bridges=0`. This avoids unrelated hardware state changes but also **does not initialize OneiOS's thermal and normal CPU placement bridges**.
- **CPU:** `IOS_HOST_CPU_MASK=0-7` confirms permitted CPUs only. It does not establish distinct per-vCPU pinning or prove there is no governor/power-policy throttling.
- **GPU:** `--gpu auto` can choose the software/2D fallback on other runs. Require runtime KGSL/fence evidence to claim acceleration.
- **Display:** buffer-post count is not animation FPS; keep guest flush, helper frame and interaction timing distinct.

## Thermal and power boundary

> [!CAUTION]
> The owner reported severe heat and lag in the ~600-second full Framework session. **No synchronized skin/SoC/battery temperature trace is available.** Qualcomm/Samsung kernel and firmware protections remain active, but the OneiOS thermal bridge is not used in the full-run bench profile. Do not force clocks, override global governors or disable thermal trips to chase FPS.

**P0 work:** inventory thermal sensors and units read-only, implement a narrowly scoped temperature guard available with `bridges=0`, and connect its critical return request to the already-bounded OneOS recovery path. Missing or invalid sensors must fail safely.

## Preserved SM8850 haptic work

The [native-impact evidence note](SM8850_HAPTIC_EVIDENCE_2026-11-16.md) restores S26-specific details from the long original hardware guide: felt standalone HAL click, host fake-vibrator waveform tests, opt-in refusal, and the open guest-to-HAL tactile gate. The [historical engineering index](HISTORICAL_ENGINEERING_EVIDENCE.md) identifies the exact Git revision containing older cross-component debug records without merging unrelated device facts into SM8850.

## Bridge reference map

Some older component READMEs refer to the former hardware guide's numbered bridge subsections. Use these **current owning references** instead; any unverified peripheral behavior remains explicitly unverified for SM8850.

| Previously referenced area | Current owning reference |
| :--- | :--- |
| Panel brightness / ambient light (`7a`) | [Brightness bridge](../runtime/bridges/brightness/README.md), [SM8850 hardware audit](SM8850_PORT.md) |
| Touch and buttons (`7b`) | [Hosted HID implementation](../kernel/patches/oneios-hosted/hid/README.md), [touch preview](SM8850_IOS_TOUCH_PREVIEW.md) |
| Battery (`7c`) | [Battery bridge](../runtime/bridges/battery/README.md) |
| Thermal (`7d`) | [Thermal bridge](../runtime/bridges/thermal/README.md), [P0 safeguards](TODO.md) |
| Samsung/Treble backends (`7e`) | [Runtime bridge architecture](../runtime/bridges/README.md) |
| S Pen (`7f`) | [HID implementation](../kernel/patches/oneios-hosted/hid/README.md) |
| HEVC/MediaCodec (`7g`) | [Encoder bridge](../runtime/bridges/encoder/README.md) |
| Camera (`7`) | [Camera bridge](../runtime/bridges/camera/README.md) |

## Practical evidence sources

| Topic | Where to look |
| :--- | :--- |
| CPU/guest traps and handoff | `runtime/xnuhost/src/perf.c`, saved `session/xnuhost.log` |
| GPU resource path | `runtime/xnuhost/src/gpu3d*.c`, [GPU guide](gpu.md) |
| Display pacing | `runtime/display/`, saved `control/display.log` |
| Thermal sensor backend | `runtime/bridges/thermal/`, [current backlog](TODO.md) |
| Watchdog and return | [OneOS research](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-reboot-smoke/docs/oneios-watchdog-recovery.md) |
| Phone audit and stage provenance | [SM8850 hardware report](SM8850_PORT.md), [physical ledger](SM8850_LIVE_STATUS_2026-11-20.md) |

---

**Next:** [Architecture](architecture.md) · [Thermal and performance roadmap](TODO.md) · [GPU evidence](SM8850_GPU_HARDWARE_ACCEPTANCE.md)
