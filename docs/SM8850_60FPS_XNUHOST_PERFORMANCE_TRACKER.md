# SM8850: 60 FPS performance execution tracker (XNUHost-first)

**Scope:** Galaxy S26 Ultra / SM-S948B / SM8850, OneiOS iOS 27.0.1 guest. **Priority: visible >=60 FPS, low jank and responsive touch.** Created 2026-11-24.

> Performance planning **does not authorize a new live framework takeover**, disable vendor/kernel safety protections, or change the existing OneOS root thermal/reboot-return policy. The operator's preferred fixed-duration X-second experimental profile is an existing configuration, not newly modified here. Root-side safety/evidence tasks remain independently documented and their factual status is unchanged.

## What is measured (not assumed)

- Latest evaluated 180.6-second physical session: OneiOS `f244b5cdfdedd592cc68bcbbb0770762def9e140` and pinned OneOS `f5c1b4a44fc45d78987694a230f7ffabb213e99c`; session `7434ae27f8e84b76806f7a4b506e90c9`.
- Display **57.42 posts/s peak**, **43.91 Hz median estimated active post cadence**. These are **not actual presented FPS**. Nine of sixteen gesture summaries lacked a next guest frame *before summary close*, not proof of dropped touches.
- XNUHost **8,889,193 traps**, **4,897,306 guest faults**, **3,921,008 syscalls**, about **1,895,124 actual host timer calls** during the run; GPU fence max **61.656 ms**. The CPU/VM counts are potential costs; their causal connection to each slow frame remains unknown.
- Guest thermal junction **104.8 C** reported from earlier passive chat telemetry and recovery provenance not fully authenticated. Preserve telemetry and do not hide uncertainty; do not use temperature cutoffs as a tuning proxy.

**Measurement contract:** FPS = distinct frames *presented* during a confirmed animated workload, not guest flush count, renderer policy events or ANativeWindow posts. Aim for >=60 presented FPS sustained where the display workload can deliver 60, frame budget <=16.667 ms, low active-window jank and improving p95/p99 touch-to-present latency. Keep raw interval distributions and classify idle separately. Do not declare success from an unverified presentation timestamp.

## P0 — XNUHost correctness and attribution

- [ ] **PERF-P0-01 — Safe deferred-only task order error diagnostic.** `runtime/xnuhost/src/task.c`: fix `order(t,NULL,0)` log dereference, cover -ETIMEDOUT, >=1000ms, explicit op and empty batch; preserve wait rc and mapping synchronization. **Status: source fix + 11-check diagnostic unit test + Android ARM64 build and complete CachyOS local CI PASS on `7ee2743a` (operator log 2026-11-24). Integrated service-thread timeout injection is still pending; no performance gain claimed.** Existing tracker: ONI-P1-01.
- [ ] **PERF-P0-02 — XNUHost low-overhead profiler.** Add opt-in bounded counters/histograms by vCPU, guest pid/thread and event kind for syscall, VM fault, map/unmap, timer and futex; no per-event default logs, measure instrumentation overhead.
  - **First source slice committed; CachyOS local CI PASS at `f2c24fa` (2026-11-24):** `--set perf-task=1` enables bounded, atomic-relaxed counters in `task.c` for task-process host PID and vCPU: syscall/fault/IRQ/other trap kinds, deferred/ordered maps/unmaps and futex waits/sleeps. Prints top eight *active* host task processes by cumulative activity at each `perf-log` report. Default is OFF; absent opt-in produces no counter writes. Host-only process IDs are **not yet mapped to guest XNU PID/name**, retired processes are not included and guest-thread/timer attribution plus overhead A/B are outstanding. No per-event logs or hardware state changes.
- [ ] **PERF-P0-03 — End-to-end frame critical-path IDs.** Connect guest render/scanout, `virtio_gpu.c`, `xh_display_flush`, display seqpacket, Android lock/copy/post, and actual presentation/VSync where supported; document clock domains and trace loss.
  - **First source slice CI PASS (`fc89dd7`, operator CachyOS log 2026-11-24).** `--set frame-trace=1` (default OFF) makes `xh_display_flush` send a 40-byte XHDF record that preserves the legacy 20-byte rectangle prefix; it appends version 1, monotonically increasing flush ID and CLOCK_MONOTONIC ns at the post-copy host flush. A legacy helper receiving 20 bytes continues to render. Updated `xhd_drain_trace` accepts both, counts sequence gaps/invalid and coalesced flushes, and `liboneios-display.so` reports p95/latest/oldest `flush -> helper` and `flush -> ANativeWindow_unlockAndPost` timing in bounded 5-second windows. The visible frame is NOT proven presented; stages before `xh_display_flush` (including Metal/KGSL/guest process), actual SurfaceFlinger/HWC present fences/VSync and precise touch correlation remain uninstrumented. No hardware/root policy changes and no physical run authorized.
  - **Second source slice verified by operator: CachyOS full local CI PASS at `f0b0042` on 2026-11-24.** Version 2 adds a 64-byte `XHDF` packet while preserving the first 20 bytes (legacy display) and the first 40 bytes (v1 trace). Optional per-scanout samples in `virtio_gpu.c` record `CLOCK_MONOTONIC` CPU shadow framebuffer copy start/end for **2D** and **guest blob** RESOURCE_FLUSH; the packet is issued only after successful scanout copy and includes source kind and resource ID. Display helper accepts 20/40/64-byte packets and reports `scanout-trace:` per-window **copy mean/max**, worst copy per posted batch p95, and earliest scanout-start-to-Android-post p95. No per-frame hot-path logging. **Do not equate RESOURCE_FLUSH with Metal present or a particular KGSL fence; no physical panel-present timestamps, no FPS claim.** Stubbed device tests cover both GPU scanout paths; helper tests cover old reader interoperability, v2 decode, invalid timestamps and copy histograms. Original OneOS commit is unchanged; this CI gate is source-only.

  - **Third source slice committed; fresh CachyOS CI pending.** Reuse existing `gpu3d_kgsl.c` 10-second backend `submit->retired` aggregates; add a *different* opt-in `gpu-fence-trace:` in `virtio_gpu.c`, with `frame-trace=1`. For every actually pending fenced guest command, capture a monotonic timestamp just before the backend `submit_fence` call and record its duration only after a **matching (ctx, ring, fence) backend retire callback**, including mergeable multi-fence retire. Classify `xnu:backboardd` fast context separately from other contexts; exclude refusal, destroy and reset releases from successful completions, report these outcomes separately. Bounded 5-second opportunistic summaries report count, mean, max, p95/p99 **upper bucket bounds** and `mono_ms` timestamps; nothing is logged per fence. The data is **fence wait after `submit_fence`**, not GPU execution duration, not the same as KGSL backend stats, and **not causally tied to any scanout frame**. Host-only sanitizer test covers merged completions, bad clocks and cancellations; fake-VirtIO integration checks real callback/refusal/context-destroy classification. Default OFF; no hardware change.
- [ ] **PERF-P0-04 — VM fault and deferred map attribution.** Histogram queue occupancy, joined operations, ordered unmaps, unmaps by release, stall times; never remove `map-defer` or weaken TLB ordering without concurrency proofs.
- [ ] **PERF-P0-05 — Syscall/trap hotspot and long tails.** Group syscall/fault classes by guest pid and vCPU and time-correlate the 286.6ms syscall / 596.2ms VM-fault outliers with frame IDs before blaming a frame.
- [ ] **PERF-P0-06 — Timer/futex wakeup churn.** Inspect duplicate timer programming, host timer call rate, guest wakeups, service-thread waits, and futex sleep/wake tails; compare no-op instrumentation baseline.
- [ ] **PERF-P0-07 — 4/6/8 vCPU affinity benchmark.** Collect actual affinity masks, migration counts, per-vCPU load, wake latency; benchmark on matched workloads, do not interpret last observed CPU IDs as pinning.
- [ ] **PERF-P0-08 — `host_statistics64` ABI count.** Identify owner of 22 warnings `actual:104 > HOST_VM_INFO64_COUNT:62`; investigate guest interfaces, validate sizes and add tests rather than suppress diagnostics.

## P1 — CPU and VM improvement after attribution

- [ ] **PERF-P1-01** Improve deferred map/unmap batching and queue contention with correctness proofs and measured p95/p99 benefit.
- [ ] **PERF-P1-02** Improve vCPU handoff, service-thread scheduling and affinity where matched experiments show benefit.
- [ ] **PERF-P1-03** Reduce proven redundant host timer re-arms and unnecessary wakeups without missing deadlines.
- [ ] **PERF-P1-04** Reduce expensive fault/address-space translation paths without breaking coherency, mapping semantics or guest isolation.
- [ ] **PERF-P1-05** Attribute and optimize guest background-service interference (Spotlight, iconservicesagent, etc.) during active UI transitions.

## P2 — GPU and display after and alongside profiler

- [ ] **PERF-P2-01** Distinguish 60 FPS *presented* from post cadence; active-animation frame-time p50/p95/p99, jank, refresh/VSync and duplicate/dropped frames.
- [ ] **PERF-P2-02** Attribute 61.656ms KGSL fence maximum to GPU execution, host wait, scheduler, queue or buffer import; preserve GPU reset/error semantics.
- [ ] **PERF-P2-03** Profile Metal-to-VirtIO-to-drm2kgsl/KGSL command submit, wait, retire and queue depth; compare same-session clocks.
- [ ] **PERF-P2-04** Profile `flush_blob` dirty-rect copying, format conversions, `ANativeWindow_lock`, `xhd_copy` and `unlockAndPost` individually; current implementation already supports dirty rectangles.
- [ ] **PERF-P2-05** Evaluate guest/Android VSync pacing, avoiding extra queue depth and producer/consumer phase mismatch.
- [ ] **PERF-P2-06** Correctly pair touch down through guest input receipt, scanout, post and presentation with bounded IDs, late matches and unmatched/idle classifications.

## P3 — Validate optimizations without guessing

- [ ] **PERF-P3-01** One-parameter-at-a-time A/B with identical code provenance, task script, guest state and cooldown; report confidence and thermal drift.
- [ ] **PERF-P3-02** Standard workloads: Home swipes, Settings scrolling, app transition, brightness slider, touch bursts, cold/warm launch.
- [ ] **PERF-P3-03** Plot guest RAM, page tables, KGSL imported memory, memory pressure and resource lifecycle; separate caching from leak.
- [ ] **PERF-P3-04** Evaluate zero-copy or buffer-sharing only if timeline demonstrates framebuffer copying dominates.
- [ ] **PERF-P3-05** Fault-injection and sanitizer regressions for every CPU/GPU/display optimization; preserve input, frame order and guest correctness.

## P4 — Acceptance and CI

- [ ] **PERF-P4-01** Reproducible benchmark fixture: exact OneiOS/OneOS SHAs, image, firmware, session, mode, input script, display mode, workload windows, clock domains.
- [ ] **PERF-P4-02** >=60 FPS actual presented within explicitly active animation windows, <=16.667ms frame budget for 60Hz, report p50/p95/p99 and jank ratio instead of invented results.
- [ ] **PERF-P4-03** Touch-to-visible-frame and missing/late/duplicate frame report with percentiles and classification.
- [ ] **PERF-P4-04** All feasible builds, sanitizers, Python fixtures and CI on local CachyOS x86_64 **first**; GitHub Actions only final PR validation. No implicit ADB or full-framework start.
- [ ] **PERF-P4-05** Versioned code, docs, benchmarks and baseline evidence in both repos; update OneiOS's OneOS submodule only after selecting and validating the corresponding OneOS commit.

## First implementation sprint

1. Fix and test `task.c` deferred-only diagnostic without changing happy-path service order performance. **Operator's CachyOS CI PASSED at commit `7ee2743a` (11 focused checks; full `ci-local.sh all` PASS). Additional integrated timeout fault injection remains open.**
2. Add bounded per-vCPU, per-guest-process VM/map/syscall/timer attribution with measurable profiler overhead.
3. Add frame IDs and common timeline across `virtio_gpu.c`, `display.c` and `runtime/display`; keep actual presentation as a separate, explicitly optional observable.
4. Prioritize the verified critical-path long tail, then A/B at identical workload; do not extrapolate 60 FPS from peak buffer post rate.

## New opt-in profiler: host-side test and expected output

```bash
# On CachyOS; no ADB and no physical framework takeover.
make -C runtime/xnuhost build/host/test_task_profile
ASAN_OPTIONS=detect_leaks=0 runtime/xnuhost/build/host/test_task_profile
make -C runtime/xnuhost test
make -C runtime/display test
JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci
```

`--set perf-task=1` is intended to be passed **explicitly to an already approved XNUHost session**. It adds `perf-task:` cumulative top-active-host-task lines to the normal `perf:` report; `perf-task=0` is the default. It is not a capture of real presented FPS and its current host PIDs are not guest process names. Compare profiler OFF vs ON for overhead before using its tails as an optimization baseline. This branch has not been validated on the actual SM8850 device.

## New opt-in frame trace: compatibility and local regression

The unchanged XHDF first 20 bytes contain `magic + x/y/w/h`. Extra fields are only sent if `--set frame-trace=1` is explicitly requested; the updated helper accepts **20 (legacy), 40 (v1) and 64 (v2 scanout) bytes**. Old 20-byte SOCK_SEQPACKET readers consume only the rectangle prefix; v1 helper clients can still display v2 rectangles but cannot attribute v2 timing without upgrading. The trace is **not a real screen FPS counter** and does not imply a completed performance optimization.

- Clock domain: `CLOCK_MONOTONIC` nanoseconds, from XNUHost through the display helper in the same Linux boot. Trace ID is monotonic within an XNUHost process, not an iOS Quartz/CoreAnimation frame ID.
- Coalescing: multiple XHDF packets may produce one Android post; `traced_flushes - traced_posts` counts coalesced packets only in traced posts. `seq_gaps` shows missing/not received sequence numbers, not necessarily the reason (e.g., socket EAGAIN, invalid records or disconnect).
- Latencies: `flush_to_helper_p95_us` uses the latest flush received for a post; `flush_to_post_latest_p95_us` / `flush_to_post_oldest_p95_us` include helper scheduling, native buffer lock/copy/post and possible initial readiness hold. They end when `ANativeWindow_unlockAndPost` returns, **not at physical panel scanout**.
- Host-side regression: `tests/test_display.c` exercises 40/64-byte packets, an unchanged 20-byte legacy reader, mixed frames, sequence gaps and malformed timestamps. `test_frame_perf.c` checks coalesced packet aggregation, scanout-copy histogram bounds and window reset. `test_xnuhost.c` verifies 2D and blob scanout metadata. v2 has **PASSED** CachyOS full CI at `f0b0042`; the subsequent VirtIO fence instrumentation still needs a separate local gate.

```bash
# CachyOS local-only. No ADB, OneOS switch, guest boot or thermal change.
make -C runtime/display test
make -C runtime/xnuhost test
JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci
```

**Remaining P0.3:** correlate guest GPU submission/ring/fence retirement with scanout using proven resource and generation ownership (avoid guessed fence-to-frame pairs); map to guest process/frame where evidence permits; obtain actual SurfaceFlinger/HWC presentation timestamps if available; correlate touch ID to physical presentation; perform trace OFF/ON overhead A/B only in a separately approved physical test after safety gates.

**Source evidence:** [180s findings](SM8850_180S_UNCAPPED_SESSION_FINDINGS_2026_11_24.md) · [original findings tracker](SM8850_180S_UNCAPPED_ENGINEERING_TRACKER_2026_11_24.md) · [OneOS fixed-duration/root policy](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-no-root-cpu-cap-180s/docs/SM8850_180S_UNCAPPED_ROOT_POLICY_2026_11_24.md).
