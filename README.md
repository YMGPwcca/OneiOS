# OneiOS

**iOS 27 on Galaxy S26 Ultra · hosted XNU · experimental research**

[Documentation](docs/README.md) · [Current evidence](docs/SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](docs/TODO.md) · [Architecture](docs/architecture.md) · [Local build](docs/building.md)

> [!IMPORTANT]
> **Target:** Galaxy S26 Ultra **SM-S948B / m3q / SM8850**, firmware **S948BXXS4BZIG**. This repository is a laboratory prototype, not a consumer iOS installation or an approved OneOS app switch.

## At a glance

| Area | Confirmed observation | Remaining limit |
| :--- | :--- | :--- |
| **Guest boot** | iOS 27.0.1 (24A446), guest-ready and first frame on the phone | Booted does not mean a responsive UI |
| **Framework takeover** | Android Framework stopped under a separate root-only, explicitly risk-acknowledged experiment | **OneOS app switching remains blocked** on SM8850 |
| **Guest lifetime** | ~600.6 s from `xnuhost` telemetry | Precise deadline requester and fully unassisted return not proven |
| **CPU** | Eight host CPUs available (mask `0–7`) | No evidence of eight independent host-core assignments |
| **GPU** | KGSL/drm2kgsl imports and real fence activity | No Vulkan conformance or sustained FPS certification |
| **Memory** | 4 GiB prefaulted/locked, 0 MiB guest swapped in captured sample | Page-table and GPU allocations still require study |
| **Performance** | iOS drew and accepted the experimental guest session | **Severe lag and heat reported**; not accepted |
| **Recovery** | Android boot-complete and OneOS reboot reason observed afterward | Watchdog handoff and unattended normal return remain **unverified** |

> [!CAUTION]
> **Do not repeat the 600-second full takeover just to benchmark performance.** The current full-session path uses `bench/bridges=0`, so OneiOS's standalone thermal bridge is inactive. Kernel/firmware thermal limits still apply, but a separate scoped thermal guard and a stronger recovery-evidence gate are required before another long test.

## How it works

OneiOS runs a source-built **XNU** kernel inside a native Linux host process (`runtime/xnuhost`) on the Android kernel already running the phone. The guest's iOS tasks execute as Linux task processes; system calls and page faults are handled by hosted XNU. Hardware-facing adapters include an Adreno/KGSL GPU path, shared-memory display, and device bridges.

```text
Galaxy S26 Ultra · Android kernel (kept running)
├── Android vendor HALs / SurfaceFlinger / GPU
├── OneOS experimental Framework stop + reboot-return
│   └── Isolated, read-only guest stage with writable Data/session
└── xnuhost · hosted XNU + iOS 27 userland
    ├── up to 8 guest vCPUs + trapped iOS tasks
    ├── drm2kgsl / KGSL → oneios-display
    └── APFS image set + one-shot Data clone
```

This is **not** a native bootloader switch, a secure iPhone environment, or an unrestricted Android-app feature. Apple binaries and locally built image assets are **not** redistributed in this repository.

## Documentation map

| Start here | Purpose |
| :--- | :--- |
| [Documentation hub](docs/README.md) | Browse the complete handbook and experiment logs by topic |
| [Live experiment status](docs/SM8850_LIVE_STATUS_2026-11-20.md) | Physical proof, uncertainties, measured load and immediate blockers |
| [Engineering roadmap](docs/TODO.md) | P0 thermal/recovery first, then CPU, GPU, frame pacing and acceptance |
| [Architecture](docs/architecture.md) | Kernel/host, guest filesystems, graphics and session responsibilities |
| [Build and test](docs/building.md) | CachyOS local CI, runtime build and artifact verification |
| [Full takeover record](docs/SM8850_FULL_IOS_10MIN.md) | Historical runbook, failures, rearm and one-shot rules; **not** an invitation to rerun |

## Working on the project

### Safe local verification

```bash
cd ~/projects/OneiOS
git pull --ff-only origin feat/oneios-sm8850-m3q
git submodule update --init app
python3 scripts/phone/test-sm8850-takeover.py -v
python3 scripts/phone/test-sm8850-full-takeover.py -v
JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci
```

Local CI previously reached **PASS**, including Android NDK ELF dependency checking and SHA-256 verification of the arm64 runtime-only package. That result does **not** mean a new phone session, thermal guard, guest kernel or recovery was tested.

### Engineering rules

- **Safety first:** preserve the exact device/firmware allowlist, SELinux, watchdog supervision and one-shot APFS Data policy.
- **Measure before tuning:** do not force global governors, disable Samsung thermal protections or equate SurfaceFlinger posts with UI animation FPS.
- **Local-first validation:** native/Python regression on CachyOS, then small bounded device trials only after P0 safety gates are ready.
- **Source of truth:** mark each claim **observed**, **inferred** or **not verified**; do not turn rootless boot evidence into a certified return.

## Scope and companion

The Android-side integration lives in [YMGPwcca/OneOS · feat/sm8850-reboot-smoke](https://github.com/YMGPwcca/OneOS/tree/feat/sm8850-reboot-smoke). The **normal OneOS app remains blocked** for OneiOS on SM8850. The root-only experiment requires explicit additional risk acknowledgement and is not a supported alternative for general users.

Last physically exercised pair: **OneiOS `21b88f7` / OneOS `349c029`**. Later documentation and status-reporting changes have not been exercised in another full phone takeover.

---

## Credits

[OneOS](https://github.com/fahadalijaved/OneOS) (fahadalijaved) and
[OneLineage](https://github.com/WeWaffles/OneLineage) (WeWaffles): the container hot-switch.
[MysticGSI](https://github.com/MysticGSI/mysticgsi): the image build model.
[UniXNU](https://github.com/UniXNU/UniXNU) and [Droid-VM](https://github.com/Droid-VM): XNU on non-Apple
ARM64, drm2kgsl, the guest drivers. [iOSPlus10](https://github.com/akshaynexus/iOSPlus10): XNU and iOS userland on
Qualcomm phones, haptics and brightness. [Darling](https://github.com/darlinghq/darling): Mach and XNU on Linux.
