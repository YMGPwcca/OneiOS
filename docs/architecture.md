# Architecture

**Hosted XNU on Android · iOS 27.0.1 · Galaxy S26 Ultra / SM8850**

[← Handbook](README.md) · [Live status](SM8850_LIVE_STATUS_2026-11-20.md) · [Build](building.md) · [Safety roadmap](TODO.md)

> [!IMPORTANT]
> This is an **experimental root-only Framework session**. The normal OneOS app still blocks an iOS switch on SM8850. A physical guest boot and first frame were observed; user-facing performance, thermal protection at the OneiOS layer and unattended reboot-return are not accepted.

## System overview

OneiOS executes a source-built **XNU kernel** as a Linux process (`xnuhost`) rather than booting a new kernel or trying to run iOS syscalls directly on Linux. Guest iOS tasks are isolated Linux task processes; their Mach traps, BSD syscalls and faults are directed into hosted XNU. Android's Linux kernel and required vendor services continue running.

```text
Galaxy S26 Ultra · Android 17 / One UI 9 kernel
│
├── Qualcomm/Samsung kernel + vendor services
│   ├── /dev/kgsl-3d0 ← drm2kgsl ← virtio-gpu 3D
│   ├── SurfaceFlinger ← oneios-display (SHM BufferQueue)
│   └── Hardware bridges (only if explicitly enabled)
│
├── OneOS root-only Framework supervisor
│   ├── stop zygote + system_server; preserve vendor services
│   ├── watchdog + device-side 600 s deadline + return watcher
│   └── isolated stage: scripts/runtime/image/control read-only
│       └── Data + session as separate writable bind mounts
│
└── xnuhost (bench profile used by the physical full-run)
    ├── vCPU threads → XNU 12377 + hosted patches
    ├── Linux child tasks → iOS user processes
    ├── image & one-shot APFS Data store
    └── launchd → backboardd → SpringBoard
```

## Components and ownership

| Component | OneiOS implementation | Responsibility |
| :--- | :--- | :--- |
| Hosted XNU | `runtime/xnuhost/`, `kernel/patches/oneios-hosted/` | Boot kernel collection, handle traps, memory and guest tasks |
| Kernel collection | `kernel/prelink/` | Build `kernel.kc` locally with necessary iOS kexts; never redistribute Apple files |
| iOS image | `profiles/`, `scripts/fetch/`, `scripts/image/`, `userland/` | Pin firmware members, trust caches, APFS volumes and profile |
| GPU 3D | `runtime/xnuhost/src/gpu3d*.c`, `drm2kgsl/` | Translate guest GPU resource commands into Qualcomm KGSL operations |
| Display | `runtime/display/` | SurfaceFlinger layer with guest frame buffers and per-window post telemetry |
| CPU | `runtime/xnuhost/src/cpu.c`, `task.c`, `perf.c` | vCPU scheduling, guest-task crossings, trap and handoff statistics |
| Device bridges | `runtime/bridges/`, `drivers/` | Optional audio, thermal, battery, camera, haptics, network and other hardware interfaces |
| OneOS takeover | `app/switcher/assets/oneios_switch.sh` | Root-scoped stage checks, Framework stop, private mount namespace and launch |
| OneOS return | `app/switcher/assets/oneios_return.sh` | Deadline or failure return through mandatory reboot on this profile |

## Physical full-run profile

| Parameter | Current value | Interpretation |
| :--- | :--- | :--- |
| Host | `SM-S948B`, `m3q`, `SM8850`, `S948BXXS4BZIG` | Strict device/firmware admission |
| Guest | iOS `27.0.1` / `24A446` | Locally prepared image, XNU and kext collection |
| CPU | `--cpus 8`; allowed host mask `0–7` | Access to 8 host CPUs, **not** proof of distinct pinned cores |
| Memory | `--ram 4G`, prefault + lock | 0 MiB guest swap in the observed full-run excerpt |
| GPU | `--gpu auto`, `--display shm` | KGSL was active in the observed run; `auto` allows fallback next time |
| Display | 1080 × 2340 / 60 Hz *requested* | Not a measured sustained 60 FPS |
| Input | `touch-exclusive=1` | Bounded, device-specific experimental input isolation |
| Bridges | `--mode bench --set bridges=0` | Avoids other hardware mutations; **OneiOS thermal/CPU bridges inactive** |
| Duration | 600 s after Framework stop | Independent deadline requested; exact recovery cause after last run not verified |
| Return | Mandatory reboot | No in-place One UI handback promise |

> [!CAUTION]
> The `bridges=0` configuration does **not** activate OneiOS's independent thermal bridge. Kernel and vendor thermal protection remain present, but heat was severe in the actual experiment and no synchronized thermistor trace was recorded. Do not enable `bridges=1` just to obtain a thermal sensor: that also enables unrelated hardware paths.

## Lifecycle and trust boundaries

1. **Prepare without takeover.** Verify signed/native runtime, image hashes, sidecars, one-shot Data clone and stage permissions; the real Samsung BusyBox mount probe must pass.
2. **Check risk and recovery.** Confirm exact device/firmware, root privileges, watchdog legacy-risk acknowledgment, prior smoke evidence and a working device-side deadline.
3. **Stop Android Framework.** Preserve kernel/vendor services while zygote and `system_server` stop.
4. **Enter a private mount namespace.** Mount the staged `/data` read-only with explicit BusyBox source/target; carve out only writable Data and session islands. Reject unexpected writes before publishing `xnuhost.pid`.
5. **Run iOS guest.** Hosted XNU boots the APFS image, starts iOS userspace and posts frames through the SHM display helper. Runtime logging distinguishes guest-ready, GPU fences and actual post cadence.
6. **Recover by reboot.** On deadline/failure the OneOS return path requests a named Android reboot; after ephemeral root disappears, rootless ADB boot metadata can prove a new Android boot but cannot authenticate the original root-owned deadline caller.

## Performance model

- **CPU:** iOS instructions can execute natively on ARM64, but every trapped syscall/fault requires crossings to hosted XNU. The captured full-run observed ~21.54 million traps and repeated Spotlight load; optimizing frequency alone does not remove handoff cost.
- **GPU:** KGSL contexts, imports and a retired fence were recorded, but this does not establish Vulkan conformance or stable compositor throughput.
- **Display:** SurfaceFlinger posts are buffer submissions, not animation FPS. Long zero-post intervals may reflect static UI, blocked guest rendering or host pacing and require timestamp correlation.
- **RAM:** 4 GiB guest locking prevented guest swap in the measured excerpt; page tables and GPU blobs still consume substantial host RAM.
- **Thermal:** Qualcomm/Samsung kernel/firmware protections exist independently of the OneiOS bridge, yet a dedicated session-safe monitoring/guard policy is still missing.

## What this architecture is not

- Not a second flashed firmware, kernel/boot-partition modification or hypervisor VM.
- Not Apple's Secure Enclave, passcode security or a trusted device identity.
- Not a supported normal OneOS app switch on this phone.
- Not proof of smooth iOS animations or independently certified unattended return.

---

**Continue:** [Live evidence](SM8850_LIVE_STATUS_2026-11-20.md) · [CPU and GPU analysis](SM8850_IOS_INTERACTIVE_PERF_TRIAGE.md) · [Full-run record](SM8850_FULL_IOS_10MIN.md)
