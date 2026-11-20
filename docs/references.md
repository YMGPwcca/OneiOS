# Technical references & provenance

**OneiOS on SM8850 · external research index**

[← Handbook](README.md) · [Architecture](architecture.md) · [Hardware](hardware.md) · [GPU](gpu.md)

> [!NOTE]
> Upstream code and public research below are **implementation references**, not evidence that a particular device behavior passed on the S26 Ultra. For physical results use the [2026-11-20 evidence ledger](SM8850_LIVE_STATUS_2026-11-20.md).

## Core projects

| Source | Relevance | Evidence boundary |
| :--- | :--- | :--- |
| [OneOS](https://github.com/YMGPwcca/OneOS) / [OneLineage](https://github.com/WeWaffles/OneLineage) | Framework switch, stage isolation and reboot-return patterns | Root-only SM8850 experimental gate differs from the normal Android app |
| [UniXNU](https://github.com/UniXNU/UniXNU) | Source-built XNU kernel and hosted changes | Source-level compatibility is not device acceptance |
| [Droid-VM](https://github.com/Droid-VM) | Guest drivers, graphics transport, kernel patches and device tooling | Prior board results do not establish this phone's GPU throughput |
| [virglrenderer](https://gitlab.freedesktop.org/virgl/virglrenderer) | Virtio-GPU and renderer infrastructure | Use current pinned sources, not assumptions about system DRM |
| [Mesa](https://gitlab.freedesktop.org/mesa/mesa) | Turnip and Vulkan implementation | Guest Vulkan API compatibility needs its own trace/tests |
| [Darling](https://github.com/darlinghq/darling) | Mach/XNU interaction and user-space compatibility research | Not a substitute for hosted XNU in this architecture |
| [MysticGSI](https://github.com/MysticGSI/mysticgsi) | Image packaging and staging concepts | iOS images remain user-built and never redistributed |

## Authoritative primary sources

- **XNU and Darwin internals:** [Apple open source](https://github.com/apple-oss-distributions), locally pinned kernel and API headers.
- **Linux watchdog semantics:** [watchdog core / userspace API](https://www.kernel.org/doc/html/latest/watchdog/watchdog-api.html). Actual Samsung driver mapping and timeout remain unverified.
- **Linux memory and THP:** [transhuge documentation](https://www.kernel.org/doc/html/latest/admin-guide/mm/transhuge.html). Do not modify host-global policy based on an unverified page-size hypothesis.
- **Android native interfaces:** Android NDK APIs and vendor HIDL/AIDL contracts; inspect actual symbols/permissions on the target firmware.
- **Qualcomm GPU behavior:** source-pinned KGSL/drm2kgsl adapters and on-device imports/fences, with guest API conformance measured separately.

## Pinning and legal boundary

1. Pin upstream revisions before quoting a particular driver ABI or symbol.
2. Keep Apple IPSW data, kexts, cache and signed binaries in ignored local input/build folders; do not add them to Git or releases.
3. Separate **source fact**, **reasonable hypothesis** and **device observation** in every report.
4. Prefer [the repository's concrete build/test notes](building.md) to old machine-local scratchpad paths.

---

**Continue:** [Architecture](architecture.md) · [GPU implementation](gpu.md) · [Current test evidence](SM8850_LIVE_STATUS_2026-11-20.md)
