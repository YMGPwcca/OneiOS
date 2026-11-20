# SM8850 iOS 27 performance baseline — observed, not accepted

**OneiOS · Galaxy S26 Ultra SM-S948B / m3q / SM8850 · physical evidence 2026-11-20**

[← Handbook](README.md) · [Physical ledger](SM8850_LIVE_STATUS_2026-11-20.md) · [Performance triage](SM8850_IOS_INTERACTIVE_PERF_TRIAGE.md) · [Roadmap](TODO.md)

> [!CAUTION]
> The numbers below are from **one already completed experiment** and a **filtered** 140-line `oneios-perf.txt` excerpt. They do not establish sustained FPS, sensor temperature, independent deadline behavior or an accepted user experience. **Do not rerun an unsafe 600-second session to refresh this page.**

## Scope and provenance

| Attribute | Historical observation |
| :--- | :--- |
| Device / firmware | SM-S948B / m3q / SM8850, `S948BXXS4BZIG` |
| Guest | iOS 27.0.1, `24A446`, hosted XNU |
| Physically executed commits | OneiOS `21b88f7372cf5a03bd94f9d2a29056f55997655c`; OneOS `349c0293b0083449067f6e849c172277b0c8aabf` |
| Configuration | Root-only Framework takeover, `--mode bench --set bridges=0`, eight **allowed** host CPUs 0–7, 4 GiB prefaulted guest RAM, GPU auto |
| Lifetime | ~**600.6 seconds** `xnuhost` process lifetime, not independent proof that the exact Framework deadline fired |
| Display excerpt coverage | **40 windows / 200.758 seconds**, not the whole 600-second session |
| Safety | Severe observed lag and heat; no synchronized thermistor trace or independently verified unassisted reboot |

## Existing measured values

| Metric | Saved value | Limit of interpretation |
| :--- | :--- | :--- |
| Display helper | **2,135** SurfaceFlinger posts; weighted **10.63 posts/s**, window median **9.82**, peak **40.33** | **Posts are not animation FPS** |
| Zero-post windows | **11/40**, including an approximately 45 s gap | Idle/static images can legitimately yield zero posts |
| Full-frame copying | `full_copies=posts` in sampled windows; most p95 copies ~**1–2 ms** | Does not alone explain multi-second blank post windows |
| Guest host emulation | **21,536,983 traps**, ~**35,862/s** | Not a per-gesture root-cause attribution |
| Syscalls / faults / interrupts | **10,981,111 / 10,171,366 / 384,506** | Lifetime event counters |
| Host handoff up/down | Mean **21.68/20.84 µs**; p99 **114.69/114.69 µs** | No synchronized touch-to-handoff pairing |
| Kernel syscall/fault p99 | **655.36/524.29 µs**; rare max syscall ~3.03 s and interrupt ~11.88 s | Outliers are not yet causally linked to the UI |
| Spotlight load | ~**98–102%** of one guest vCPU across repeated 10 s samples | Fresh Data indexing vs ABI/scheduler cost not isolated |
| Guest memory | **4096/4096 MiB** locked and prefaulted; **0 MiB guest swap** | Linux host swap is a separate metric |
| Page tables | ~**371–378 MiB** in samples, `ShmemPmdMapped=0` | No justification for global hugepage/sysctl changes |
| GPU acceleration | Real KGSL imports/blobs and a retired `backboardd` fence (~988 µs mean in a one-fence 52 s report) | Not Vulkan API conformance or sustained 60 Hz |

## Missing measurements before optimization claims

- [ ] Time-align actual touch gestures, guest scanout/damage, KGSL submit/retire, display buffer lock/copy/post, CPU frequency/pressure and reliable skin/SoC/battery thermal samples.
- [ ] Publish p50/p95/p99 touch-to-frame for **paired** gestures and explicitly count unmatched gestures. Do not substitute posts/s for UI FPS.
- [ ] Separate first-boot one-shot Data indexing (Spotlight, iconservicesagent) from syscall/page-fault/futex/handoff and scheduler overhead.
- [ ] Measure actual per-vCPU affinity/placement; host CPU allowed mask 0–7 is not eight independent host-core pins.
- [ ] Audit GPU memory ownership, context/blobs and fence timing. `gpu=auto` may select 2D in a subsequent run.
- [ ] Satisfy the [independent thermal guard](SM8850_THERMAL_GUARD.md) and [recovery evidence](SM8850_RECOVERY_ACCEPTANCE.md) gates before a new long physical trial.

**Conclusion:** the guest booted and real GPU acceleration was observed; thermal safety, responsive UX and unattended recovery have **not** passed acceptance. Full source context: [physical status](SM8850_LIVE_STATUS_2026-11-20.md).
