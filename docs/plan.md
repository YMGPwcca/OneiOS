# Engineering plan · SM8850

**OneiOS 27.0.1 on Galaxy S26 Ultra · execution plan after first real full guest session**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Task board](TODO.md) · [Architecture](architecture.md)

> [!IMPORTANT]
> **Research stage.** The system has already executed hosted XNU and drawn iOS on the phone. The next milestone is not “first boot”; it is **safe thermal operation, attributable recovery and responsive interaction**. No work on this plan authorizes a new full takeover without a separate safety decision.

## Goal and measurable outcome

The target is a reproducible, bounded, device-specific iOS 27.0.1 experiment on **SM-S948B / SM8850**, running under the current Android kernel with the OneOS Framework switch, while retaining Android data isolation and a demonstrable way back.

| Objective | Current reading | Next acceptance criterion |
| :--- | :--- | :--- |
| Guest boot | Ready + first frame **OBSERVED** | No regression in short bounded tests |
| 3D graphics | KGSL activity **OBSERVED** | Matched GPU/fence/render evidence under UI interaction |
| Responsiveness | Severe lag reported | Repeatable touch-to-frame p95/p99 and cold/warm interaction improvement |
| Thermal | Device hot; OneiOS bridge inactive in `bridges=0` | Independent thermal telemetry and bounded heat-response handling |
| Recovery | New Android boot observed | Root-owned deadline outcome and unassisted return independently demonstrated |
| App integration | Ordinary OneOS iOS switch **BLOCKED** | Keep blocked until safety gates and separate product decision |

## Phase map

```text
Existing boot proof
      │
      ▼
P0  Thermal + recovery provenance + persistent evidence
      │  safety acceptance required
      ▼
P1  CPU, host traps, Spotlight and scheduler isolation
      │  matched short-run A/B data
      ▼
P2  GPU throughput, fences, post timeline and frame pacing
      │  latency + resource-lifecycle evidence
      ▼
P3  Memory, reproducibility, long-duration qualification
      │  local CI + risk-reviewed device acceptance
      ▼
Potential app/product work — separate approval and device gates
```

## P0 · First engineering sprint

**Primary engineering owners:** OneiOS runtime implements sensor integration and temperature handling; OneOS root-side supervisor owns the device-side deadline and mandatory reboot-return. Neither component may assume the other already qualifies the watchdog.

1. Inventory available skin/SoC/battery thermal zones **read-only** on the actual firmware, together with sampling cadence and unit handling.
2. Implement an independent, narrowly scoped thermal guard for the touch-exclusive `bench/bridges=0` session. It may emit only bounded telemetry and a safe return request, not enable other hardware bridges.
3. Test normal, unknown, unavailable, stale and critical sensor readings; verify the recovery path never waits indefinitely on a sensor.
4. Inspect root-owned archived outcome and watcher/feeder logs from the completed session. Preserve boot identity, run token and request reason.
5. Extend host and device logs so an ephemeral DirtyFrag root loss cannot erase guest-ready/first-frame evidence or falsely certify unassisted return.

**Definition of done:** unit tests and local integration pass; no global thermal/governor writes; no hidden extra watchdog opens; honest labels for incomplete evidence.

## P1 · CPU latency attribution

- Profile per-category syscall/page-fault/futex and task handoff overhead before editing scheduling policy.
- Investigate whether a fresh Data clone triggers Spotlight indexing and iconservicesagent cold caches.
- Keep existing 4-vCPU affinity results **as separate bench data**; do not extrapolate the gain to the 8-vCPU full-run.
- If trace evidence supports it, implement opt-in distinct-host-core pairing constrained by the permitted cpuset; reject any failure without a fallback that silently mutates system policy.

**Acceptance:** identical scripted/manual UI actions, bounded duration, thermal sampling and before/after latency distributions. Reject claims based only on a peak posts/s value.

## P2 · Graphics and display

- Correlate guest flush timestamps, KGSL fence submit/retire, render-server resource lifecycle and SurfaceFlinger buffer post windows.
- Explain long zero-post intervals before optimizing them: an unchanged home screen is not a dropped-frame event.
- Quantify copying and memory import cost, then test partial-damage correctness; do not prematurely substitute zero-copy for a safe copying path.
- Validate that `gpu=auto` reports its selected backend per run. Prior KGSL activity does not prove a future selection.

**Acceptance:** no new visual corruption, resource leaks or regressions in touch-to-frame p95/p99; graphics path and limitations logged explicitly.

## P3 · Stability, packaging and shipping boundaries

- Keep a known-good local build flow (`JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci`) with ELF API checks, package integrity and regression tests.
- Audit SHMEM THP, page tables and GPU imported-memory pressure without global kernel tweaks.
- Retain private APFS input provenance: the original source is never mutated, and each used Data clone stays consumed and archived.
- Build a single versioned performance report for every bounded guest trial, including identity/firmware, CPU clock ceiling, real thermal curves, GPU backend, guest RAM and reboot outcome.
- Treat normal OneOS app enablement, longer sessions and other device families as separate future acceptance decisions.

## Change boundaries

> [!CAUTION]
> Do not bypass SELinux, alter vendor watchdog nodes, force high-performance governors, disable firmware thermal trips, reuse a consumed APFS Data clone or claim the previous 600-second run is production-safe. A failed safety gate is a stop condition, not a hint to retry immediately.

## Test path

```bash
cd ~/projects/OneiOS
python3 scripts/phone/test-sm8850-takeover.py -v
python3 scripts/phone/test-sm8850-full-takeover.py -v
make -C runtime/xnuhost test
JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci
```

Device tests remain explicitly bounded and **must follow**, not replace, successful local tests and a review of thermal and recovery risks.

---

**See also:** [Roadmap](TODO.md) · [OneOS experiment status](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-reboot-smoke/docs/SM8850_ONEIOS_FULL_RUN_STATUS.md) · [Evidence ledger](SM8850_LIVE_STATUS_2026-11-20.md)
