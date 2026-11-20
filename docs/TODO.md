# Roadmap & engineering checklist

**OneiOS 27.0.1 · Galaxy S26 Ultra · last evidence review 2026-11-20**

[← Handbook](README.md) · [Physical results](SM8850_LIVE_STATUS_2026-11-20.md) · [Architecture](architecture.md) · [Testing](building.md)

> [!CAUTION]
> **Current release gate: BLOCKED.** Hosted iOS booted, rendered its first frame and ran ~600.6 s, but the phone lagged badly and became very hot. Neither the OneiOS thermal guard nor the exact unattended reboot-return path is qualified. **Do not run another long takeover just to obtain performance metrics.**

## Delivery sequence

| Phase | Goal | Gate to move forward |
| :--- | :--- | :--- |
| **P0 · Safety** | Thermal guard, recovery evidence and durable logs | Safe bounded termination proved, no false return PASS |
| **P1 · CPU** | Locate syscall, page-fault, handoff and guest background work | Measured p95/p99 improvement in matched short sessions |
| **P2 · Graphics** | Fix stalls, GPU resource cost and frame pacing | Touch-to-frame and fence/post timing measurements improve |
| **P3 · Quality** | Memory, automation, reproducibility and final acceptance | Local CI + controlled real-phone evidence without heat/recovery regression |

## P0 · Must fix before another long takeover

- [ ] **P0.1 — Independent thermal telemetry.** Read SoC, battery and skin sensors using an isolated, read-only component available with `bench/bridges=0`. Define trustworthy sensor selection, units, missing-sensor behavior and session-token ownership. Do **not** enable unrelated hardware bridges.
- [ ] **P0.2 — Bounded over-temperature response.** Add thermal thresholds, hysteresis and a fail-safe request to the existing OneOS reboot-return path, with deterministic logging. Keep vendor/kernel throttling intact; never force CPU/GPU clocks or disable thermal trips.
- [ ] **P0.3 — Return provenance.** Read the last run's root-owned `return.log`, `return.outcome`, watcher/feeder evidence and `launches/*/switch.log` without another guest boot. Prove which process requested recovery and when. A reboot reason alone is not enough.
- [ ] **P0.4 — Logs that survive root loss.** Preserve per-session CPU/GPU/thermal/display and final return receipts before reboot; report previously observed guest-ready/frame markers independently of rootless new-boot metadata. Reject stale session tokens.
- [ ] **P0.5 — Unit + simulated physical-safety tests.** Exercise missing or implausible temperatures, stale heartbeat, watchdog errors, timeout ordering, malformed archive data and repeat-run refusal locally.

**Acceptance:** no unsafe escalation on missing sensors; no unbounded heat exposure; return reporting distinguishes **observed new boot** from **verified original requester**. The normal OneOS app device gate remains unchanged.

## P1 · CPU and scheduler bottlenecks

- [ ] **P1.1 — Attribute traps.** Break down syscall, page fault, Mach handoff, futex wake/sleep and task-map/TLB costs by category and guest process. Investigate ~35.9k traps/s and long-tail outliers.
- [ ] **P1.2 — Guest background work.** Establish whether Spotlight and iconservicesagent rebuild caches/indexes every time a fresh one-shot Data clone is used, without permanently disabling guest services.
- [ ] **P1.3 — Safe vCPU pairing experiment.** Design opt-in 8-vCPU host affinity scoped to the guest threads only; keep the inherited cpuset, kernel/firmware caps and thermal behavior. A mask of `0–7` is not sufficient proof.
- [ ] **P1.4 — Controlled A/B.** Repeat short sessions with identical touch paths and trace settings. Compare handoff p50/p99, CPU pressure, frequency policy ceilings and visible UI latency, not just raw trap rate.

**Acceptance:** measurable interactive latency reduction without more heat, increased recovery risk or unverified device-wide scheduler tuning.

## P2 · GPU and frame pacing

- [ ] **P2.1 — GPU provenance.** Correlate active KGSL contexts, imported buffers, guest Vulkan entrypoints and fence retirement; distinguish observed acceleration from comprehensive Vulkan API support.
- [ ] **P2.2 — Frame timeline.** Join guest scanout, backboardd fences, display-helper buffer lock/copy/post and touch timestamps in a single time base. Investigate no-post windows without treating a static frame as a lost FPS sample.
- [ ] **P2.3 — Copy optimization.** Test dirty-rectangle handling and buffer ownership; quantify full-frame copy bandwidth before trying zero-copy.
- [ ] **P2.4 — GPU memory lifecycle.** Audit blob allocation/free/import leaks and thermal impact; retain deterministic fallback and explicit status reporting when GPU auto uses 2D.

**Acceptance:** touch-to-frame p95/p99 and stutter frequency improve; no frame corruption, buffer leak or unsupported FPS claim.

## P3 · Platform readiness

- [ ] **P3.1 — Memory and hugepages.** Explain page-table footprint and SHMEM THP behavior. No global hugepage or sysctl adjustments without isolation and rollback proof.
- [ ] **P3.2 — Repeatable performance suite.** Collect fixed-duration FPS-related, post-cadence, touch latency, host handoff, GPU fence, guest RAM and real thermistor curves in versioned reports.
- [ ] **P3.3 — Driver/HAL audit.** Retain only the hardware bridges actually required by the experimental session. Verify sensor, brightness, haptics, camera and network ownership individually before enabling a bridge.
- [ ] **P3.4 — Build tooling improvements.** Keep the image pipeline local and trusted; optimize optional on-device packaging only after guest stability and recovery are accepted.
- [ ] **P3.5 — Local-first CI.** Run all native/Python tests, ELF/NDK checks, SHA-256 package verification on CachyOS before final remote CI and risk-reviewed phone acceptance.

## Already evidenced (do not repeat as TODO)

| Observation | Scope |
| :--- | :--- |
| On-device isolated BusyBox mount probe | **PASS** in prior rearm; read-only stage and writable Data/session islands |
| APFS Data clone | **PASS** one-shot fresh clone verification; consumed clones must not be reused |
| Guest-ready and first frame | **OBSERVED** in full Framework takeover |
| KGSL 3D activity | **OBSERVED** in captured full-run excerpt; not Vulkan conformance |
| Approx. 600.6 s guest process | **OBSERVED**; not an independently authenticated deadline return |
| Android boot after return | **OBSERVED** with named reboot reason; unassisted path **not verified** |
| Local CI | **PASS** for the reported runtime build/package; not a new phone acceptance |

---

**Next:** [Physical evidence ledger](SM8850_LIVE_STATUS_2026-11-20.md) · [Interactive performance analysis](SM8850_IOS_INTERACTIVE_PERF_TRIAGE.md) · [Documentation policy](STYLE_GUIDE.md)
