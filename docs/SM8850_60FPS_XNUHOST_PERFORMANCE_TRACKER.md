# SM8850: 60 FPS performance execution tracker (XNUHost-first)

> **CURRENT THERMAL POLICY STATUS (2026-11-26; supersedes all older admission receipts):** the operator explicitly rejects fixed 40% frequency ceilings and OneOS/OneiOS temperature-triggered return or forced reboot. Target 45–70 C, soft throttle at 70 C, hard throttle at 80 C latched until <=70 C, gradual recovery. Preserve stock thermal safeguards; no Android kernel/module work or shared QoS relaxation. See [AGENTS.md](../AGENTS.md) and [OneOS adaptive policy](../app/docs/SM8850_ADAPTIVE_THERMAL.md). The pinned OneOS root switcher, direct host launcher, telemetry CLI and wrapper now refuse new full-run admission; historical code/logs are retained, NOT current launch instructions. The adaptive policy is an offline reference, NOT a qualified live actuator. Reversible independent ownership and non-reboot guest quiesce remain implementation blockers, not permission to run old policy. G23.1 runtime and three display artifacts staged; Data fresh and guarded preflight passed **under the now-retired policy** only. No further stage, rearm or live run requested by this commit. Existing rollback and evidence remain valid. Local-first offline validation only.

**Scope:** Galaxy S26 Ultra / SM-S948B / SM8850, OneiOS iOS 27.0.1 guest. **Priority: visible >=60 FPS, low jank and responsive touch.** Created 2026-11-24.

> Performance planning **does not authorize a new live framework takeover**, disable vendor/kernel safety protections, or change the existing OneOS root thermal/reboot-return policy. The operator's preferred fixed-duration X-second experimental profile is an existing configuration, not newly modified here. Root-side safety/evidence tasks remain independently documented and their factual status is unchanged.

**Operator priority clarification (2026-11-24):** The active performance branch is exclusively focused on XNUHost CPU/VM, GPU submission, display and measured iOS responsiveness. Watchdog qualification, watchdog attribution and recovery certification are separate workstreams; the operator explicitly does not want them repeatedly reopened or requested as routine performance tasks. Do not insert additional readiness/attribution rounds into local CI, synthetic CPU benchmarks, or GPU source work. Existing independently documented physical-device safety/release boundaries are unchanged; this is a prioritization decision, not an assertion that an unqualified recovery path has passed or permission to disable thermal protections.

**Active scope correction (2026-11-27):** return to the original PERF-P0–P4 / Phase G CPU, VM, GPU and display performance roadmap. The G24–G25 audio, microphone, camera, encoder, network and whole-session park workstream is deferred, not an automatic prerequisite for offline optimization. Preserve completed receipts and the current live-admission block. Do not invent further provider milestones or reopen recovery qualification as routine performance work. The independent adaptive frequency actuator remains blocked; no policy or physical launch is authorized by resuming source optimization.

**Requested final CPU experiment — Framework ON/OFF:** Reuse the lifecycle and bounded telemetry architecture of the previously executed 180-second experiment rather than restart a watchdog investigation. Historical run: OneiOS `f244b5cdfdedd592cc68bcbbb0770762def9e140`, OneOS `f5c1b4a44fc45d78987694a230f7ffabb213e99c`, runner `scripts/phone/sm8850-600s-thermal-telemetry.py`, duration 180 seconds, `--no-rearm`, with full-bridge experimental profile. That runner boots full iOS and is not a drop-in runner for the current synthetic test kernel. The requested comparison is a separate bounded, headless synthetic workload: identical runtime/fixture hashes, launch UID/environment and CPU placement, 3-vCPU latency on 0-2/0-5 and parallel 6-vCPU pinned/8-vCPU shared, with Framework state as the intended variable. Keep thermal protections unchanged in both arms, capture the actual effective masks and state; do not attribute any difference to Framework alone if UID, CPU policy or other conditions differ. No live launch or safety-policy change is included in this documentation update. The prior 180-second physical receipt is historical evidence, not a new authorization. Do not repeat watchdog audit for this performance question.

## What is measured (not assumed)

**Latest F1 evidence (2026-11-25):** both exact-session analyses PASS at runtime `88ab6ca` / OneOS `49e6f51`; default retained, prime-first opt-in only, stable 60 FPS not reached. See the [F1 receipt](#phase-f1-operator-ab-receipt-and-next-priority-2026-11-25). Controlled old/new runtime comparison deferred; proceed with offline Phase G.

- Prior 180.6-second physical reference session (latest F1 A/B receipt below): OneiOS `f244b5cdfdedd592cc68bcbbb0770762def9e140` and pinned OneOS `f5c1b4a44fc45d78987694a230f7ffabb213e99c`; session `7434ae27f8e84b76806f7a4b506e90c9`.
- Display **57.42 posts/s peak**, **43.91 Hz median estimated active post cadence**. These are **not actual presented FPS**. Nine of sixteen gesture summaries lacked a next guest frame *before summary close*, not proof of dropped touches.
- XNUHost **8,889,193 traps**, **4,897,306 guest faults**, **3,921,008 syscalls**, about **1,895,124 actual host timer calls** during the run; GPU fence max **61.656 ms**. The CPU/VM counts are potential costs; their causal connection to each slow frame remains unknown.
- Guest thermal junction **104.8 C** reported from earlier passive chat telemetry and recovery provenance not fully authenticated. Preserve telemetry and do not hide uncertainty; do not use temperature cutoffs as a tuning proxy.

**Measurement contract:** FPS = distinct frames *presented* during a confirmed animated workload, not guest flush count, renderer policy events or ANativeWindow posts. Aim for >=60 presented FPS sustained where the display workload can deliver 60, frame budget <=16.667 ms, low active-window jank and improving p95/p99 touch-to-present latency. Keep raw interval distributions and classify idle separately. Do not declare success from an unverified presentation timestamp.

## 2026-11-25: handoff execution order (Phase A and B)

**Source batch, not accepted hardware/CI evidence.** Companion OneOS pinned to `49e6f51ba0cd52eba4049b39120186efff422076` on `feat/sm8850-xnuhost-perf-p0`, descended from `51a05e9`; previous CPU benchmark branch is unchanged. This section records the new handoff IDs (distinct from the historical PERF-P0/P1 items and the safety TODO).

| Handoff item | Source | Regression / CI / physical acceptance | Dependency and acceptance |
|---|---|---|---|
| A / P0.1 full takeover instrumentation | Implemented | Test source added; CachyOS and physical pending | `--perf-profile off\|frame\|task\|frame-task`; same launch preflight, detached root metadata and runtime flags; observed matching frame/queue/fence/task traces on a later admitted run. |
| A / P0.2 offline analyzer corrections | Implemented | Synthetic handoff-value fixtures added; archive reanalysis and CachyOS tests pending | Same-session archive, correct active/all-gap split, budget coverage, bucket bounds vs max, valid CPU sampler parsing. No inferred FPS. |
| B / P1.1 topology-aware placement | Candidate implemented | Fixture/CLI regression source added; native build, effective readbacks, representative iOS A/B pending | Qualified Oryon 6+2 topology, distinct initial masks, safe thermal narrowing, fallback; never production-default selection on one run. |

**Latest handoff evidence (operator-provided summary, not a new raw-log reanalysis):** full-bridges Framework OFF 8-vCPU session `0f803f5ac4564942a641b0dcee8bb4d5`, 180.2s, peak posted-buffer rate 46.28, median active cadence 34.44, max recorded touch-to-next-guest-frame 214.1ms, render fence max 55.354ms. Active post totals 2,847 gaps; 1,642 above nominal 60-Hz budget and 2,727 above 120-Hz budget; max 248.218ms. The old 7,678.684ms field came from all-gap p95, not active stall. The previous Framework-on comparison had a different vCPU/bridge/pin configuration, so no isolated Framework effect or physical presentation claim. `Spotlight[248] 12%` is one observed value, not necessarily the peak.

### Phase A implementation

- Full takeover runners and OneOS root shell carry independent optional performance tokens across detach. Profile tokens and native capabilities are checked before one-shot consumption. The existing claim precedes archiving the old session and creating fresh root-owned control metadata. `framework.perf-profile` and `framework.cpu-profile` are then written before Framework stop/inner launch and verified against native flags. Failed setup leaves the one-shot claim consumed. Missing legacy default-only metadata is distinguished from explicit profiles. Opt-in frame/task instrumentation leaves per-command GPU verbosity off. Default invocation has no new trace flags.
- Collector keeps the original archive. A launch-aware collection refuses to analyze a mismatched current launch; explicit historical selection remains available. Reports describe actual observed trace markers separately from requested metadata. `sm8850_perf_metrics.py` aggregates only reported valid budget counters, exposes partial coverage, preserves zero versus unknown and distinguishes histogram upper bucket bounds from measured maxima. All-gap candidate windows remain possible idle.
- CPU process sampler accepts merged prefixes and positive non-10-second intervals, excludes the -sys sampler, and does not infer unlisted processes as zero. Existing `host_statistics64` ABI warning remains open; no suppressions or guessed fix.
- The exact raw archive is on the operator's CachyOS host, not available in this development environment. The regression fixture uses the handoff totals synthetically, not fabricated raw windows.

### Phase B implementation

`--cpu-profile prime-first` / native `--set sm8850-prime-first=1` is restricted to the admitted full-bridges 8-vCPU bench with no cluster override. On the captured SM8850 topology the baseline target derives from the generic Oryon rule (lend the slowest two physical P cores to guest E): 0/1 -> 4/5, 2..7 -> 0/1/2/3/6/7. The candidate maps 0/1 -> 6/7, 2..7 -> 0/1/2/3/4/5. The two highest-capacity cores must be a distinct higher-frequency policy with Qualcomm MIDR, all eight present and inherited allowed, and all existing hot steps must exclude the Prime pair. IDs are derived, not assumed. Incompatible/missing topology logs DEFAULT_FALLBACK without applying the candidate.

Guest cluster labels/order remain 2E/6P; each descriptor uses the mapped host core's actual capacity, frequency table and caches. This is experimental: XNU AMP may respond differently to fast E descriptors. At cap 0 the candidate uses singleton masks; at nonzero thermal steps all eight vCPUs share the existing restricted slower-core mask instead of forcing stacked pairs. The thermal thresholds, root cap/guard, firmware/kernel controls and reboot/deadline policy are not changed. Advertised descriptors remain the cold plan, as in the existing thermal bridge; effective masks can narrow.

vCPU, guest user thread and task service thread follow placement independently. With perf-task enabled (or active candidate), `perf-placement:` reports cumulative attempts, failures, logarithmically sampled readback and mismatches, without per-event logs. Existing `perf-affinity:` provides sampled kernel-reported masks/migration counts/last CPU. A successful set call does not prove residency; GPU/display workers are not pinned by this patch. True per-core residency, GPU/display contention, profile overhead and actual frame benefit need representative evidence. Do not interpret a fallback session as the candidate arm or change default policy.

**Offline gate:** `python3 scripts/phone/test-sm8850-perf-phase-a.py -v`, `python3 app/tests/test_sm8850_perf_profile.py -v`, existing interactive analyzer and bridge/XNUHost tests. Integrated in `scripts/ci-local.sh all`; no ADB, APFS stage/rearm, watchdog audit or live takeover. Run on CachyOS before progressing to physical validation. Continue Phase C (GPU fence/buffer) and D (display pipeline) as evidence permits; E full batch CI, F representative matched A/B, G runtime critical path and H HakiOS review. No repeat of the completed synthetic CPU/GPU campaign.

## P0 — XNUHost correctness and attribution

- [ ] **PERF-P0-01 — Safe deferred-only task order error diagnostic.** `runtime/xnuhost/src/task.c`: fix `order(t,NULL,0)` log dereference, cover -ETIMEDOUT, >=1000ms, explicit op and empty batch; preserve wait rc and mapping synchronization. **Status: source fix + 11-check diagnostic unit test + Android ARM64 build and complete CachyOS local CI PASS on `7ee2743a` (operator log 2026-11-24). Integrated service-thread timeout injection is still pending; no performance gain claimed.** Existing tracker: ONI-P1-01.
- [ ] **PERF-P0-02 — XNUHost low-overhead profiler.** Add opt-in bounded counters/histograms by vCPU, guest pid/thread and event kind for syscall, VM fault, map/unmap, timer and futex; no per-event default logs, measure instrumentation overhead.
  - **First source slice committed; CachyOS local CI PASS at `f2c24fa` (2026-11-24):** `--set perf-task=1` enables bounded, atomic-relaxed counters in `task.c` for task-process host PID and vCPU: syscall/fault/IRQ/other trap kinds, deferred/ordered maps/unmaps and futex waits/sleeps. Prints top eight *active* host task processes by cumulative activity at each `perf-log` report. Default is OFF; absent opt-in produces no counter writes. Host-only process IDs are **not yet mapped to guest XNU PID/name**, retired processes are not included and guest-thread/timer attribution plus overhead A/B are outstanding. No per-event logs or hardware state changes.
- [ ] **PERF-P0-03 — End-to-end frame critical-path IDs.** Connect guest render/scanout, `virtio_gpu.c`, `xh_display_flush`, display seqpacket, Android lock/copy/post, and actual presentation/VSync where supported; document clock domains and trace loss.
  - **First source slice CI PASS (`fc89dd7`, operator CachyOS log 2026-11-24).** `--set frame-trace=1` (default OFF) makes `xh_display_flush` send a 40-byte XHDF record that preserves the legacy 20-byte rectangle prefix; it appends version 1, monotonically increasing flush ID and CLOCK_MONOTONIC ns at the post-copy host flush. A legacy helper receiving 20 bytes continues to render. Updated `xhd_drain_trace` accepts both, counts sequence gaps/invalid and coalesced flushes, and `liboneios-display.so` reports p95/latest/oldest `flush -> helper` and `flush -> ANativeWindow_unlockAndPost` timing in bounded 5-second windows. The visible frame is NOT proven presented; stages before `xh_display_flush` (including Metal/KGSL/guest process), actual SurfaceFlinger/HWC present fences/VSync and precise touch correlation remain uninstrumented. No hardware/root policy changes and no physical run authorized.
  - **Second source slice verified by operator: CachyOS full local CI PASS at `f0b0042` on 2026-11-24.** Version 2 adds a 64-byte `XHDF` packet while preserving the first 20 bytes (legacy display) and the first 40 bytes (v1 trace). Optional per-scanout samples in `virtio_gpu.c` record `CLOCK_MONOTONIC` CPU shadow framebuffer copy start/end for **2D** and **guest blob** RESOURCE_FLUSH; the packet is issued only after successful scanout copy and includes source kind and resource ID. Display helper accepts 20/40/64-byte packets and reports `scanout-trace:` per-window **copy mean/max**, worst copy per posted batch p95, and earliest scanout-start-to-Android-post p95. No per-frame hot-path logging. **Do not equate RESOURCE_FLUSH with Metal present or a particular KGSL fence; no physical panel-present timestamps, no FPS claim.** Stubbed device tests cover both GPU scanout paths; helper tests cover old reader interoperability, v2 decode, invalid timestamps and copy histograms. Original OneOS commit is unchanged; this CI gate is source-only.

  - **Third source slice verified by operator: CachyOS full local CI PASS at `2067def` on 2026-11-24 (18/18 fence unit checks, 14,346/14,346 XNUHost native checks, 956/956 GPU leak checks).** Reuse existing `gpu3d_kgsl.c` 10-second backend `submit->retired` aggregates; add a *different* opt-in `gpu-fence-trace:` in `virtio_gpu.c`, with `frame-trace=1`. For every actually pending fenced guest command, capture a monotonic timestamp just before the backend `submit_fence` call and record its duration only after a **matching (ctx, ring, fence) backend retire callback**, including mergeable multi-fence retire. Classify `xnu:backboardd` fast context separately from other contexts; exclude refusal, destroy and reset releases from successful completions, report these outcomes separately. Bounded 5-second opportunistic summaries report count, mean, max, p95/p99 **upper bucket bounds** and `mono_ms` timestamps; nothing is logged per fence. The data is **fence wait after `submit_fence`**, not GPU execution duration, not the same as KGSL backend stats, and **not causally tied to any scanout frame**. Host-only sanitizer test covers merged completions, bad clocks and cancellations; fake-VirtIO integration checks real callback/refusal/context-destroy classification. Default OFF; no hardware change.
  - **Fourth source slice verified by operator: CachyOS `make -C runtime/display test`, `make -C runtime/xnuhost test`, and full `ci-local.sh all` PASS at `bc6d30d` on 2026-11-24.** new `XHDF v3` extends the existing 20/40/64-byte prefix to **88 bytes** with a VirtIO-GPU `queue_generation`, monotonically allocated `resource_generation`, `resource_id` and `creator/owner context`. The 64-byte scanout portion and 20-byte rectangle prefix remain unchanged; old readers keep displaying the rectangle. Resource serials are allocated on CREATE_2D/CREATE_BLOB when `frame-trace=1` (or legacy `ONEIOS_GPU_TRACE`) and are distinct across ID reuse and queue resets **within one XNUHost process**. Initial queue generation zero is valid; identifiers are **not globally unique across process restarts**, so compare with the exact session/executable provenance.
  - Updated helper accepts **20/40/64/88 bytes** and attributes an Android post to one source **only if every received flush contributing to it has valid v3 metadata for the same queue/resource serial/id/owner**, with no invalid or legacy packets. Otherwise it reports mixed or unknown, never guesses. In bounded 5-second reports, `frame-source:` prints up to eight distinct provenance keys (counting overflow explicitly); `frame-trace:` reports source-single/mixed/unknown and overflow. This is **source scanout allocation identity, not a proof that a Metal submission/fence rendered its pixels**, not physical present timing, and not evidence of 60 FPS. The parser/regression covers v1/v2/v3 compatibility, invalid generation, queue reuse, resource ID reuse, different-sourced coalescing and eight-slot overflow; default frame trace OFF.
- [ ] **PERF-P0-04 — VM fault and deferred map attribution.** Histogram queue occupancy, joined operations, ordered unmaps, unmaps by release, stall times; never remove `map-defer` or weaken TLB ordering without concurrency proofs.
  - **First P0.4 source slice verified by operator: full CachyOS local CI PASS at `ea30eee` on 2026-11-24 (35/35 task-profiler checks, 14,354 native XNUHost checks, 956 GPU leak checks, 39 frame-profiler checks).** Extended `perf-task=1` with bounded atomic `perf-task-queue:` counters for each of the top eight *active Linux host task processes*: deferred queue **batch count**, **actual queued `xs_op` entries**, **logical unmap requests** (distinct from coalesced entries), and queue depth histogram separately for batches drained by **thread release** versus **service order**. Also classify immediate ordered fallbacks into map queue full, unmap queue full, and unmap of a task with running user threads. Log only during the existing `perf-task` report; all new atomic writes are skipped when `perf-task=0`. Pure-host ASAN/UBSAN tests cover depth bins (including 256), empty batch, concurrent counter updates, logical unmap coalescing, invalid reasons and null inputs. **No VM ordering or execution semantics changed.** This first slice does *not* measure the cost of instrumentation, host `mmap`/futex latency per task, guest PID attribution, or a real FPS improvement.
  - **Second P0.4 source slice verified by operator: full CachyOS local CI PASS at `cae22a2` on 2026-11-24 (50/50 task-profiler checks, 14,354 native checks, 956 GPU leak checks, 39 frame-profiler checks, both ARM64 profiler OFF/ON integration runs PASS).** With `perf-task=1`, `perf-task-wait:` records elapsed host counter time for five stages: acquisition of both order mutexes, service-thread acknowledgment with/without deferred ops, acquisition of both release mutexes (only when checking pending operations/unmaps_out), and release-to-observed-ops_done. Acknowledged waits feed 16 fixed latency bins, sum and max; failed acknowledgment/invalid time is counted separately. Report count/mean/p95/p99 bucket ceilings/max for each stage at existing reporting cadence, both for active top-eight tasks and process-lifetime totals including destroyed tasks. These are approximate concurrent snapshots, not isolated mmap CPU time, not queue-residence time, not per-frame attribution. Default OFF; no new clock reads or atomic updates on unprofiled paths; VM ordering unchanged. Profiling incurs additional atomic histogram writes including process totals, so OFF/ON overhead still requires measurement.
  - **Integrated regression:** `make -C runtime/xnuhost check-task-profiler-arm64` uses the repo's freestanding test kernel and temporary Data stores on native ARM64 or QEMU. Runs with profiler OFF/ON, requires both guest test runs to PASS, no timing logs when OFF, and nonzero process totals for order lock/direct ack and release lock/ack when ON. Included in `make test`; unavailable ARM64 runner explicitly skips. Test validates instrumentation, not actual device timing or a performance gain.
  - **Initial integration receipt:** Two synthetic QEMU test-kernel runs with profiling ON reported deferred-order ACK mean 251.05/314.00 us (max 1329/1205 us), direct-order ACK mean 48.72/46.71 us, release-lock mean 83.82/90.06 us and release ACK mean 85.88/97.99 us, with no aborted/invalid samples. Their deferred/direct mix differed (94/18 versus 77/35), so these two ON runs do not establish instrumentation overhead or real-device behavior.
  - **Paired benchmark harness parser CI PASS at `08a5b85`; native synthetic OFF/ON operator receipt PASS (see below):** `make -C runtime/xnuhost bench-profiler-arm64 PROFILER_PAIRS=6 PROFILER_SCALE=2` runs the same freestanding test kernel with `perf-task=0/1`, one discarded warmup pair, alternating OFF/ON order, fresh temporary Data directories, 3 vCPU, 256 MiB RAM, and no ADB or physical device. It rejects incomplete/failed benchmark logs, checks expected sample counts, saves per-run raw logs and `runs.json` with binary/kernel hashes, and emits `summary.json` containing median per-run mean and percentile values, paired percentage changes in mean latency, sample-count ranges, and whole-process wall times. Parser self-test is included in `make test`; benchmark itself is not a CI timing gate. Existing guest benchmark histogram saturates around 170 us under QEMU (quantile values are not exact tails or pooled percentiles). The native Android run subsequently measured +0.28% paired median syscall-round-trip change; no universal overhead or performance gain is established.
  - **P0.4 remaining:** quantify queue residence and individual host syscall costs; extend the now-passed synthetic native profiler overhead measurement to representative full workloads, separating QEMU from physical evidence. Use results to choose the next optimization. Do not change map-defer or TLB ordering without concurrency proofs.

- [ ] **PERF-P0-05 — Syscall/trap hotspot and long tails.** Group syscall/fault classes by guest pid and vCPU and time-correlate the 286.6ms syscall / 596.2ms VM-fault outliers with frame IDs before blaming a frame.
  - **Consolidated P0 source batch: full local CI PASS at `08a5b85`.** Guest patches 0041/0075 already report top BSD/Mach syscall numbers, VM fills/refills and per-vCPU guest counters. Host perf-task=1 adds actual trap-class hits per top host task (perf-task-class), plus per-vCPU next-run-minus-idle interval counts and >=16.667 ms counts by BSD direct/indirect, Mach, platform and fault access (perf-detail). These intervals include other kernel work/scheduling; they do not prove isolated syscall CPU time, guest PID, or frame causality. Guest identity and presentation correlation remain pending.
- [ ] **PERF-P0-06 — Timer/futex wakeup churn.** Inspect duplicate timer programming, host timer call rate, guest wakeups, service-thread waits, and futex sleep/wake tails; compare no-op instrumentation baseline.
  - **Source batch: full local CI PASS at `08a5b85`.** cpu.c already skips same-future-deadline re-arms. Opt-in perf-timer separates skipped duplicates, armed/disarmed cancel, already-due, future arm and host failures. perf-futex separates wait return, EAGAIN, EINTR, timeout and other outcomes for thread_run and idle. No timer/wakeup policy change; native workload/overhead is required before optimization.
- [ ] **PERF-P0-07 — 4/6/8 vCPU affinity benchmark.** Collect actual affinity masks, migration counts, per-vCPU load, wake latency; benchmark on matched workloads, do not interpret last observed CPU IDs as pinning.
  - **Operator-requested native CPU matrix: 40/40 runs PASS at `cbab66a`, after local CI receipt at `72a54f6`:** `scripts/phone/bench-sm8850-cpu-scaling.py`. Reuse CI-built artifacts; 3-vCPU handoff latency on 0-2/0-5/0-7, two active vCPUs on equal-sized 0-1 vs 6-7 masks, six active vCPUs on 0-5 shared/pinned individually and 0-7 shared, eight active vCPUs on 0-7 shared/pinned individually. Use the existing parallel test kernel for 2/6/8 active threads (ordinary latency test hardcodes 3 vCPUs). Deep Doze and screen off checked per run, no root or hardware bridges. Compare within fixed vCPU counts; cross-count throughput is synthetic scaling, not latency equivalence. Group restriction applies to the whole runtime; distinct 6+2 per-vCPU group assignment in one eight-vCPU guest is not implemented by this existing headless benchmark. Results: 3-vCPU syscall means 5.632/11.704/11.987 us for masks 0-2/0-5/0-7. For all-active parallel work, six vCPUs pinned individually to 0-5 gave 23 ms and 130,435 rounds/s, versus 35 ms and 85,714 rounds/s with the same shared mask (paired wall-time delta -34.29%). Eight vCPUs unrestricted gave 39 ms and 102,564 rounds/s, versus 51 ms and 78,431 rounds/s pinned (paired +8.33%). Two Prime cores beat two regular cores, 18 vs 28 ms (paired -35.71%). Distinct per-condition medians and paired deltas must not be conflated. Candidate 6-vCPU pinned for parallel synthetic workloads; 8-vCPU shared and topology-aware 6+2 remain candidates, not production defaults or proven iOS improvements. Only vCPU masks verified; no task-thread residency or frequency evidence. 4-vCPU scaling and representative iOS measurements remain open. No additional CPU microbenchmark needed before the GPU/display source work.
  - **Source batch: full local CI PASS at `08a5b85`.** perf-affinity reads Cpus_allowed_list and se.nr_migrations from each known vCPU thread's proc status/sched at report time, with explicit unknown for unavailable fields. Observed mask and migrations, not a pinning change. Existing parallel-arm64 covers synthetic CPU scaling; SM8850 4/6/8 workload comparison remains pending.
- [ ] **PERF-P0-08 — `host_statistics64` ABI count.** Identify owner of 22 warnings `actual:104 > HOST_VM_INFO64_COUNT:62`; investigate guest interfaces, validate sizes and add tests rather than suppress diagnostics.
  - **Source audit completed; caller evidence pending.** Upstream [xnu-12377.121.6/osfmk/kern/host.c](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.121.6/osfmk/kern/host.c) vm_stats() emits this warning and includes task_best_name(current_task()) and task_pid(current_task()). [host_info.h](https://github.com/apple-oss-distributions/xnu/blob/xnu-12377.121.6/osfmk/mach/host_info.h) defines the count as sizeof(vm_statistics64_data_t)/sizeof(integer_t), with revision offsets. Observed 62 is 248 bytes in 32-bit integer units; caller-supplied 104 claims 416 bytes of capacity, not proof of the allocation. Recover the complete warning from existing guest logs. Do not alter reply size, count units, layout or warning before caller buffer/schema and exact build are established.

## Consolidated validation policy (2026-11-24)

Operator receipt, 2026-11-24: complete CachyOS local CI PASS at `08a5b8576e8da8c10c3a2ac3d989bf75240cba3f`, pinned OneOS `f5c1b4a44fc45d78987694a230f7ffabb213e99c`. Task profile 67/67, XNUHost host tests 14,354/14,354, GPU leak 956/956, frame profiler 39/39, profiler benchmark parser and ARM64 OFF/ON integration PASS; runtime package verified by ci-local. Receipt log: `/tmp/oneios-p0-batch-ci.lJcmW4.log`. QEMU is correctness evidence only.

**Native synthetic benchmark: PASS.** [Exact operator receipt and P1 decision](SM8850_NATIVE_P0_BENCHMARK_2026_11_24.md). Native syscall round trip 81.711/81.874 us OFF/ON (+0.28% paired median), fault 33.556/31.863 us, deferred service ACK 505.55 us mean (107 samples), release ACK 34.75 us mean (10,310 samples). Frequent handoff and release paths take priority over isolated large batch averages. No physical iOS frame performance established. Placement A/B PASS at `a56a49e`: with common inherited CPUs 0-2, unpaired/paired syscall round trip 6.199/8.302 us (+33.92% median paired regression), fault 15.320/19.936 us (+30.13%), timer kick 12.883/17.991 us (+39.56%). Reject this same-core candidate for the tested workload. Earlier 0-7 timing is cross-session, not a matched mask comparison. Next: a consolidated P1 code/measurement batch, described below; no QEMU performance gate or production policy/default change.

- Batch source-only P0 changes and tests, then run one `JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci` on CachyOS. QEMU ARM64 integration is correctness evidence only, never a hardware latency threshold.
- Paired bench-profiler-arm64 defaults to native ARM64 Linux. Explicit PROFILER_ALLOW_EMULATED=1 permits diagnostic QEMU timing only; manifest and summary label it emulated_diagnostic_only. No QEMU benchmark required for P0.
- Guest PID/TID mapping, render-fence dependency, panel presentation, queue residence, native overhead, actual SM8850 affinity comparison and host_statistics64 caller ABI remain unresolved. CI PASS is not full P0 acceptance or 60 FPS.

## P1 — CPU and VM improvement after attribution

**P1 CI correction:** first attempt at `f56964b` stopped before compilation because `scripts/ci-local.sh` lost its executable bit in the Git tree edit. Restore mode 100755 (same blob); all other existing tracked modes match `a56a49e`. Baseline binary hash verified and archived. Corrected full local CI PASS at `f9893c7`. Native matrix now records read-only Android CPU topology and advertised maximum clocks; both prior placement conditions used only CPUs 0-2, never 6/7. No change to the matrix conditions or production policies.

- [ ] **PERF-P1-01** Improve deferred map/unmap batching and queue contention with correctness proofs and measured p95/p99 benefit.
  - **Consolidated source batch; local CI receipt PASS at `72a54f6` (validated by native scaling harness):** extend existing adjacent map join to descending VA and RAM-file ranges with matching protection. No queue ordering, locking, unmap or TLB changes; host join tests and guest backing-page/unmap regression. No measured speedup or descending-map occurrence rate yet.
- [ ] **PERF-P1-02** Improve vCPU handoff, service-thread scheduling and affinity where matched experiments show benefit.
  - **Native placement A/B receipt:** 3 vCPUs on CPUs 0-2; unpaired beats requested same-core pairing (see native receipt). Do not extrapolate to full bridges or alter default pinning without actual topology/workload evidence.
  - **First P1 code batch: full local CI and native Deep Doze matrix PASS at `f9893c7`; retain provisionally.** replace per-byte signal-state copy in the freestanding stub with aligned alias-safe volatile 64/32-bit scalar copies, preserving byte fallback, ABI and isolation. Add host offset/length/guard-page regression, expanded guest register-state regression and a native old/new 0-2/0-7 matched matrix (archive exact baseline binary before CI). No memory ordering, seccomp, futex, timer, spin or VM policy change. Full local CI PASS (11,051 copy checks; 14,354 XNUHost host tests). Native matched Doze matrix reports syscall paired delta -7.39% on 0-2 and -2.94% on 0-7; mixed secondary metrics, only three measured blocks. No claim of full iOS speedup. Equal-size mask study PASS at `fabab2d`: median syscall means 5.673/5.641/14.011 us on 0-2/3-5/5-7; paired 5-7 vs 0-2 +144.21%, timer kick +913.81%. No proof of Prime-only latency or cause. Close this synthetic experiment; no additional CPU microbenchmark required for the next source batch. CPU topology confirms 0-5 capacity 741/max 3.6288 GHz, 6-7 capacity 1024/max 4.7424 GHz. Widening mask 0-2 to 0-7 regressed candidate syscall paired latency +104.82%; not proof Prime cores are slower. See native receipt. No production default change.
- [ ] **PERF-P1-03** Reduce proven redundant host timer re-arms and unnecessary wakeups without missing deadlines.
- [ ] **PERF-P1-04** Reduce expensive fault/address-space translation paths without breaking coherency, mapping semantics or guest isolation.
- [ ] **PERF-P1-05** Attribute and optimize guest background-service interference (Spotlight, iconservicesagent, etc.) during active UI transitions.

## P2 — GPU and display after and alongside profiler

- [ ] **PERF-P2-01** Distinguish 60 FPS *presented* from post cadence; active-animation frame-time p50/p95/p99, jank, refresh/VSync and duplicate/dropped frames.
  - **Consolidated source batch; local CI receipt PASS at `72a54f6` (validated by native scaling harness):** count valid-content successful posts only, track unlockAndPost and copy failures separately; stop helper on invalid copy/post error, preserve unposted metadata. XHDF actual packet length validation and conservative unknown-source on missing/invalid/legacy/gap batches. Existing legacy rectangle retained for unknown extensions. No physical present evidence.
- [ ] **PERF-P2-02** Attribute 61.656ms KGSL fence maximum to GPU execution, host wait, scheduler, queue or buffer import; preserve GPU reset/error semantics.
- [ ] **PERF-P2-03** Profile Metal-to-VirtIO-to-drm2kgsl/KGSL command submit, wait, retire and queue depth; compare same-session clocks.
- [ ] **PERF-P2-04** Profile `flush_blob` dirty-rect copying, format conversions, `ANativeWindow_lock`, `xhd_copy` and `unlockAndPost` individually; current implementation already supports dirty rectangles.
  - **Consolidated source batch; local CI receipt PASS at `72a54f6` (validated by native scaling harness):** one exact contiguous memcpy for same-layout full-width unpadded rows, including nonzero y; preserve row copies and color conversion otherwise. Test padding, both layouts and untouched surrounding bytes. No GPU or hardware FPS gain claimed.
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

The unchanged XHDF first 20 bytes contain `magic + x/y/w/h`. Extra fields are only sent if `--set frame-trace=1` is explicitly requested; the updated helper accepts **20 (legacy), 40 (v1), 64 (v2 scanout) and 88 (v3 source provenance) bytes**. Old 20-byte SOCK_SEQPACKET readers consume only the rectangle prefix; older helpers can still display v2/v3 rectangles but cannot interpret unknown trace versions without upgrading. The trace is **not a real screen FPS counter** and does not imply a completed performance optimization.

- Clock domain: `CLOCK_MONOTONIC` nanoseconds, from XNUHost through the display helper in the same Linux boot. Trace ID is monotonic within an XNUHost process, not an iOS Quartz/CoreAnimation frame ID.
- Coalescing: multiple XHDF packets may produce one Android post; `traced_flushes - traced_posts` counts coalesced packets only in traced posts. `seq_gaps` shows missing/not received sequence numbers, not necessarily the reason (e.g., socket EAGAIN, invalid records or disconnect).
- Latencies: `flush_to_helper_p95_us` uses the latest flush received for a post; `flush_to_post_latest_p95_us` / `flush_to_post_oldest_p95_us` include helper scheduling, native buffer lock/copy/post and possible initial readiness hold. They end when `ANativeWindow_unlockAndPost` returns, **not at physical panel scanout**.
- Host-side regression: `tests/test_display.c` exercises 40/64-byte packets, an unchanged 20-byte legacy reader, mixed frames, sequence gaps and malformed timestamps. `test_frame_perf.c` checks coalesced packet aggregation, scanout-copy histogram bounds and window reset. `test_xnuhost.c` verifies 2D and blob scanout metadata. v2 has **PASSED** CachyOS full CI at `f0b0042`; the subsequent VirtIO fence instrumentation still needs a separate local gate.

```bash
# CachyOS local-only. No ADB, OneOS switch, guest boot or thermal change.
make -C runtime/xnuhost build/host/test_task_profile
ASAN_OPTIONS=detect_leaks=0 runtime/xnuhost/build/host/test_task_profile
make -C runtime/display test
make -C runtime/xnuhost test
JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci
```

**Remaining P0.3:** add a proven guest render-to-scanout dependency link (resource provenance alone does not establish one) and correlate GPU command/fence ownership only when the actual rendering producer/consumer relation is demonstrated; map to guest process/frame where evidence permits; obtain actual SurfaceFlinger/HWC presentation timestamps if available; correlate touch ID to physical presentation; perform trace OFF/ON overhead A/B only in a separately approved physical test after safety gates.

**Source evidence:** [180s findings](SM8850_180S_UNCAPPED_SESSION_FINDINGS_2026_11_24.md) · [original findings tracker](SM8850_180S_UNCAPPED_ENGINEERING_TRACKER_2026_11_24.md) · [OneOS fixed-duration/root policy](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-no-root-cpu-cap-180s/docs/SM8850_180S_UNCAPPED_ROOT_POLICY_2026_11_24.md).


### Framework-state exploratory benchmark (operator receipt: 4/4 matched PASS at `e038985`)

`scripts/phone/bench-sm8850-framework-state.py` prepares the same CI-built test kernel and runtime before any Framework stop, captures a fresh four-case Deep Doze baseline, and attaches a bounded unprivileged synthetic workload to the existing 20-second Framework-only reboot-smoke lifecycle after its verified stop marker. The former 180-second full iOS runner cannot be reused unchanged because it launches 8 vCPUs, 4 GiB and GPU3D. No new stop/return implementation, no thermal-policy switch, no APFS rearm, and no OneOS/runtime change. The existing lifecycle's admissions still apply; this is not a workaround if it refuses. Explicit consent is the existing reboot-smoke consent. The four cases have individual 3-second limits and a reserved return margin; report partial results rather than extend the device deadline. Screen/idle state and runtime scheduling context may differ after stop; record the same UID and effective masks, do not infer full iOS FPS or certify recovery. Parser/plan self-tests and all four matched ON/OFF cases passed. New Android boot observed. Syscall 0-2 7.912 -> 7.986 us; 0-5 12.220 -> 11.353 us. Six pinned throughput 166667 -> 96774 rounds/s; eight shared 93023 -> 125000 rounds/s. The ranking reverses, but one block and unmeasured OFF residency/clock/thermal/idle context do not establish causality. At the time of this historical receipt, two of seven parallel conditions and two of three latency masks had OFF data; see the subsequent complete 30s matrix below. See the native receipt. No production affinity change or requirement to repeat the four cases.


### Requested full Framework-state matrix — 30-second window, 10/10 matched PASS at `c2934ae`

The operator requests all ten existing scaling cases (three latency masks and seven parallel configurations), one fresh matched ON/OFF block, within a 30-second device-side Framework-only deadline. OneOS `51a05e95c2a14ecc1d0ca981229d8481ec882c29` adds an explicitly selected 20/30-second smoke option; the ordinary smoke default remains 20 seconds, and the full-iOS profile, initial cutoff, existing admission/return path and thermal policy are unchanged. Host verifies the duration in preflight and live metadata. The runtime and fixture source remains `72a54f6`, so reuse the prior full CI artifacts; run the targeted host-only tests and shell syntax check before the live command. No full iOS boot, GPU3D, APFS rearm or additional standalone audit. All ten cases are attempted with per-workload limits and a return reserve; partial results are preserved and reported as incomplete rather than extending the deadline. Operator receipt: 29/29 offline tests and all 20 physical synthetic workloads passed, 10/10 matched cases; 30s preflight/live duration and expected vCPU masks verified, new Android boot observed. Syscall ON -> OFF: 0-2 8.076 -> 7.239 us, 0-5 11.815 -> 11.428 us, 0-7 11.859 -> 11.218 us. OFF all-active throughput: 6 pinned 176471, 8 pinned 173913, 6 shared 0-5 120000, 6 shared 0-7 93750, 2 Prime 71429, 8 shared 60606, 2 regular 50000 rounds/s. Eight pinned beats eight shared by 2.87x in this block; six pinned and eight pinned are essentially tied at this measurement resolution. The earlier 20s run had opposite changes for six pinned and eight shared, so no stable Framework causal effect is established. Keep both receipts, do not replace production CPU policy. Existing full-bridge placement differs from synthetic identity pinning. All requested conditions measured; end the synthetic CPU campaign for now and proceed with GPU/display source work. See native receipt.


## GPU/display consolidated source batch (local CI PASS; physical acceptance pending)

Baseline `4653d119a8f0dd3c2c2aeaffb3c2466081831410`; OneOS gitlink unchanged. Do not change production CPU affinity, GPU clock constraints, governor, thermal or recovery policy. This is a source/host-regression batch, not a measured FPS improvement.

Operator full CachyOS local CI PASS at `9034d35e3931b5dbaf0e5ac3ab51af0aff524cb6`, OneOS `51a05e95c2a14ecc1d0ca981229d8481ec882c29`: log `/tmp/oneios-gpu-display-ci.h5xD68.log`, XNUHost 14372/14372, fence profiler 24/24, frame profiler 50/50, loader 160/160, SM8850 admission 22/22, display mode checks and synthetic ARM64 guest PASS. Package `out/release/oneios-runtime-0.0.0-ci-arm64.tar.zst` (5.6 MiB as printed by operator), SHA256 `348fc09c7c9e507b8d23ebf3c917a585d4f7e32fbc65d09fac3f30c6432d936d`. The supplied summary does not enumerate individual DRM2KGSL/leak test counts; no separate counts inferred. Source/packaging verified, physical GPU and actual FPS still pending.

- GPU submission: small aligned private request and fixed-size reply buffers avoid the normal per-command allocations; capset replies alone may allocate up to 1 MiB. Larger requests still use the existing 1 MiB bound; scatter/gather, copy isolation and alignment are retained. Reserve a potential pending fence before command execution; unfenced replies are allocation-free. Slow-job allocation failure drains preceding slow work and serves the chain synchronously, retaining ordering.
- Fence retirement: a refused fence releases only its own chain (existing reply compatibility retained), not earlier accepted fences; real merged callbacks continue to retire earlier fences on that ring. Publish batches of current-generation used entries in existing order with one interrupt per <=16 entries. Backend bookkeeping removes refused samples and decrements foreground-pending; untracked capacity/rings are explicitly counted. No change to waittimestamp, reset or KGSL submission error policy.
- GPU scheduling: retain backboardd fast lane, context ordering, QoS and dependency retry. A class promotion clears stale background-lowest state. Opt-in frame-trace=1 adds monotonic fast/slow host dequeue-to-service, service, submit/blob/flush and dependency-wait histograms. These measure host stages, including copy/renderer call, not GPU execution and not causal frame IDs. Five-second windows; no per-command logging; no new clocks on unprofiled path.
- GPU memory: avoid redundant dup/close for HOST3D_GUEST import; keep actual fd ownership, coherence checks, and unref/reset lifecycle.
- Scanout: same-layout full-width tightly packed 2D and GUEST blob rectangles use contiguous-span copy (per guest segment for scatter-backed blobs); preserve conversion, stride padding and partial damage paths. No zero-copy or GPU-coherence claim. SHM send failure retains full repair damage for the next successful flush (or new helper); repair downgrades to v1 timing rather than claiming a single v3 source. No guarantee of retry if the guest never flushes again.
- Frame pacing: report active-only post-gap p95/p99/max, idle gaps and counts over 16.666667/8.333334 ms. Keep legacy all-gap statistics. ANativeWindow post intervals are not physical presentation or actual jank; idle classification is a heuristic.
- Touch: arm next-flush candidate before SYN_REPORT and do not count helper reconnect as a guest flush. Guest input consumption and exact input-to-present attribution remain open.
- Regression: fake renderer accepted-then-refused same-ring sequence, large capset writable descriptor, tight nonzero-y scanout, histogram invalid clocks, post-budget and idle accounting, display helper reconnect. Existing local suite also tests 2D/3D, reset overlap, fd ownership/leaks, policies and ARM64 correctness.

### HakiOS reference and remaining real-device work

HakiOS upstream guide (https://hackios-web.vercel.app/en/guide/metal) reports direct Adreno command/shader path vs Metal-on-Vulkan on POCO X5 Pro (Adreno 642L), including reduced-resolution and full-resolution results. The direct path uses its own XNU GPU transport and Metal plug-in; it is not a drop-in replacement for OneiOS's hosted iOS 27 VirtIO/DRM2KGSL and SM8850. No upstream implementation copied or port claimed. Prefer measuring current submission/fence/scanout path before a separate architecture/ABI/licensing/ISA port. Need native SM8850 backend proof, GPU/host fence-to-render correlation, exact layer/HWC presentation timestamps, real touch/animation and cold vs warm workload A/B. No 60/120 FPS claim until that evidence exists.


### Next native GPU measurement (no runtime rebuild)

Use the packaged `bin/gpuctl` from the exact verified CI artifact, the existing `scripts/phone/sm8850-gpu-acceptance.py host-submit` hardware gate and the ordinary booted Android Framework. Each invocation opens a fresh renderer/context and retires one 32-CP_NOP command buffer (256 bytes). Save per-invocation JSON, hash and observed battery temperature, run one discarded initial sample and five measured samples, report min/median/max. This is fresh-context backend submit-to-retire latency, not steady-state GPU execution, not a VirtIO A/B, not iOS FPS. Existing USB, device, firmware, root, no-active-guest, storage, battery, temperature and device-side timeout gates remain mandatory. No takeover, CPU pinning, governor, thermal change or APFS Data access. Use the later real guest/scanout evidence to assess the changes outside gpuctl; do not interpret this microprobe as validation of the whole GPU/display optimization.


### Native GPU preflight follow-up — boot-scoped state

First warm-up was BLOCKED before any GPU command: `/tmp/oneios-native-gpu.Tvgu3u/run-0.json` reported persisted `takeover_state=running`, while root, healthy Android Framework, no guest, temperature (29.7 C), battery (79%), firmware, SELinux and storage checks passed. Package SHA256 verified; packaged gpuctl SHA256 `cc998a4daf5dd1a1690d7bef2ae6134fd6284a6f1a5a4685f4b19539a9f5b51d`. Prior 30s Framework-only session observed new Android boot; a stale marker is plausible, not proven until the two boot IDs are read. Match OneOS's boot-scoped active-session semantics: retain raw state, require valid distinct current and recorded boot IDs plus healthy Framework/no-guest evidence before classifying an active marker as STALE_PREVIOUS_BOOT; same-boot, missing/malformed boot evidence and unknown state remain blocked. No control file mutation, no runtime/OneOS/thermal/watchdog change; add regression cases and rerun the existing exact CI artifact after offline tests. Hardware measurement still pending.


### Native KGSL probe receipt and timing decomposition

Operator receipt at `a2f13161bd4277b6ce4adbfaf3f3b9c1f0a23b36`: 11/11 offline acceptance tests PASS; artifact gpuctl SHA256 `cc998a4daf5dd1a1690d7bef2ae6134fd6284a6f1a5a4685f4b19539a9f5b51d`. Six fresh-process/context 32-CP_NOP submits passed, all preflights STALE_PREVIOUS_BOOT, evidence `/tmp/oneios-native-gpu.Bx7www/run-{0..5}.json`. Initial sample 41.88 ms, measured 79.35, 39.33, 45.19, 40.18, 44.20 ms (min 39.33, median 44.20, mean 49.65, max 79.35); battery 29.0-29.6 C. Legacy probe reported zero faults/async errors; its fault readback fallback can print zero even when the counter is not readable. No VirtIO/display, no actual FPS and no old/new runtime A/B claim.

Next: `gpuctl bench` fixed 69 commands in one new context/queue/BO, one outstanding fence, phases first(1), warmup(4), hot(32), pace60(16), pace120(16), minimum start-to-start pacing without catch-up bursts. Measure ccmd submission, fence registration (includes validation overhead), callback since submit, nonnegative wait after registration, wake-to-caller, total, actual spacing; callbacks can overlap registration. Log after the workload, GET_PARAM fault counters before/after (unreadable explicitly UNVERIFIED), verify exact context/ring/fence. Existing host GPU acceptance adds host-timing action, 20s device limit and root/private binary digest verification; strict parser validates order/counts/spacing/clocks. Three fresh sessions recommended; no forced clock, thermal changes, no NCTX_NO_WAITTS override (prior device crash recorded in patch 0007), no guest/takeover. Build only gpuctl and run Python regression; prior packaged runtime remains immutable. No performance change or native timing result claimed until operator runs it. The callback is host notification, not hardware execution time; timing budgets are comparisons only, not frame drop counts. First submission in a fresh context is not proof the GPU was powered off.


### Native same-context timing receipt — complete PASS at `65a4f78900567c7db0f530ebf6b836565d573d9a`

Operator 13/13 offline tests, NDK targeted gpuctl build PASS (SHA256 `e12eda4b7d575e5173e2cb49a03227b66f5d1a42299e51cc9ca07b3f4041bf2c`), three native sessions 207/207, evidence `/tmp/oneios-gpu-timing.MQZiAc/run-{1..3}.json`. First totals 43.718/38.348/42.996 ms; after-register callback waits 43.680/38.303/42.912 ms. Hot medians 0.111/0.117/0.117 ms (worst 0.129), pace60 0.824/0.751/0.754 (worst 1.089), pace120 0.765/0.743/0.786 (worst 0.890). All 204 after-first samples below both budgets, readable fault counters unchanged, async errors zero. Host submit and registration not the observed first-fence bottleneck. Cause of first wait unproven; no new GPU wake/power override or waittimestamp policy change. No FPS inference. Conclude synthetic GPU microprobe; next representative iOS UI workload.

Add opt-in visual runner --frame-trace to require GPU3D and enable bounded frame/fence/queue telemetry, with --no-gpu-trace to avoid verbose command logging. Existing 4 vCPU, 1080x2340, 60 Hz, 4 GiB, fresh isolated Data clone, Android Framework-on preview and bounded timeout remain unchanged. The offline analyzer keeps render/other fence classes separate despite repeated metric names, reports individual active post windows and queue stages, not pooled percentile or physical presentation. Existing storage reserve and non-mutating max_map_count admission remain mandatory. Last available free storage 38164868 KiB vs required 42008576 KiB (deficit 3843708 KiB); earlier map_count=65530 vs required 1048576. Both must be rechecked before attempting an iOS clone/run; no automatic deletion or sysctl writes. No runtime rebuild/full CI required by these host-only script changes; targeted offline tests pending operator. Physical presentation and representative animation remain unverified.


### Low-storage visual preview follow-up

Operator at `10de7ef03cf5700bc22915b8fae2adbc2a7d7284`: interactive analyzer 5/5 PASS, visual 29/30; stale source-string assertion expected pre-Power-key `keys=false` (and obsolete config diagnostic). Source already allows one ungrabbed Power device and suppresses Volume, native touch-only EVIOCGRAB and failure closure remain. Correct regression assertion, do not alter runtime input policy. Operator cannot free additional user storage. Add explicit `--compact-clone` for new verified snapshot: existing 64 KiB sparse copy and default logical 8 GiB+2 GiB budget remain; optional helper scans exact nonzero 4 KiB payload (not compressed st_blocks), checks actual filesystem allocation-unit compatibility and reserve + 2 GiB margin + planned bytes before writing any Data payload, checks free space every 64 MiB, refuses unexpected write growth and checks post-fsync reserve. Original/clone full logical SHA256 and independent inode checks unchanged. Partial stage preserved on error, no automatic deletion/reuse of consumed Data, no reserve reduction or promise that source fits. If pre-scan reports insufficient space, stop without a large allocation. Existing map-count admission and all guest gates unchanged. Targeted local host compiler and Python offline tests pending operator; no XNUHost runtime or OneOS changes.


### Framework-on visual receipt and next guarded full-bridges comparison

Operator at `ecaf3236071405b7f3db90571c95cf7b976a893a`: offline analyzer 5/5, visual 31/31, snapshot 6/6, helper syntax and native build PASS. Compact clone nonzero/written 2235387904 bytes; independent hash checks PASS; pre-run free 38173400 KiB, reserve unchanged. 240s Framework-on 4-vCPU, bridges=0, no affinity pairing, 1080x2340/60Hz, 4GiB, GPU3D, frame trace, verbose GPU trace off: 968 valid posts, peak window post rate 30.6, median active cadence estimate 16.92, lock max 132.097 ms, display copy max 4.98 ms, render fence max 26.16 ms, touch candidate max 825.3 ms; no direct vkCreateDevice proof. Return finished:124, touch released, Android healthy, map_count restored 65530. Evidence `/tmp/oneios-ios-compact.KM5NLI/visual.json`; host/display/CPU logs under `out/sm8850/gpu-acceptance/20261124T111318Z-visual-*`. CPU allowed 0-7 but not per-thread pinning; GPU backend still requests transient uclamp 1024/0 (not full CPU bridge). Both policy ceilings reached 2112000 kHz, PSI some avg10 peak 19.23, MemAvailable near 849 MiB. CPU probe uptime and host CLOCK_MONOTONIC differ, so do not align raw timestamps as identical; no isolated thermal/Framework/bridge causal attribution. Host summary handoff up/down means 13.92/14.54 us, max down 124.277 ms; cumulative syscall-class max 3.649 s is not proof of a particular render stall. User requests guarded full-bridges comparison; recognize exact performance branch in existing explicit 180-second wrapper, native marker gate and telemetry duration gate. Stage CI-built runtime with rollback, rearm separate one-shot Data; low-space rearm uses existing measured compact helper with unchanged reserve + 64MiB and 2GiB margin, rechecks reserve before ready-marker transaction; stop on inadequate capacity. Keep all preflight, root thermal guard/cap, deadline, watchdog/recovery risk acknowledgement and existing OneOS revision unchanged. Existing full-bridges profile does not explicitly request new frame trace; compare existing GPU/display/perf summaries and thermal telemetry, not claim controlled A/B. No actual live test or CI result claimed until operator receipt.


### Phase A/B focused regression receipt (2026-11-25)

Operator CachyOS receipt at OneiOS `0c5300f447ad906953c7f143ea26ea6ae98fbbdb`, OneOS `6d283b1c949fb50425728f179a86aa186646b2a6`: exact gitlink verified, shell syntax passed, Phase A/B Python 8/8, interactive perf 5/5, takeover 29/29, full-takeover 14/14. OneOS profile tests 4/5: `test_metadata_and_exec_are_wired` incorrectly asserted that new control metadata precedes the historical one-shot Data claim. Actual source claims Data, archives previous session, creates fresh control, records metadata, then stops Framework and starts the inner runtime. Correct the regression and documentation without moving the claim or changing switcher behavior. New OneOS test checks capability/token validation before claim and metadata before stop/inner. Native bridge/XNUHost tests and archive reanalysis were not reached because the command stopped on failure. Corrected regression and remaining local checks pending; no live validation, recovery certification or thermal change. Log `/tmp/oneios-phase-ab.Ourcul.log`.

### Phase A/B focused local receipt and corrected historical evidence (2026-11-25)

CachyOS operator receipt at OneiOS `fe01153eb4901a6b021224d3f2ce5d9c0462df6b`, OneOS `49e6f51ba0cd52eba4049b39120186efff422076`: corrected OneOS regression 5/5; preceding unchanged Python suites 8+5+29+14/56 PASS. Native bridges 439/439 (plus Wi-Fi, HAL, battery, brightness, thermal and audio suites); XNUHost 14391/14391; stage admission 22/22; task profile 67/67; fence profiler 24/24; GPU leak scenarios 956/956 with LeakSanitizer clean after context destruction; GPU policy 166/166. ARM64 compile/link, QEMU test kernel (documented process_vm skips), task-profiler OFF/ON checks PASS. `PHASE_AB_REGRESSION=PASS`, `PHASE_AB_CHECK=COMPLETE`; log `/tmp/oneios-phase-ab-resume.9wu5VL.log`. Not full ci-local packaging and not physical validation of the new CPU profile.

Offline reanalysis PASS for the original launch `0f803f5ac4564942a641b0dcee8bb4d5`, output `/tmp/oneios-phase-ab-reanalysis.CWJ6Gn`. The previous handoff summed 29 displayed active windows (threshold >=3 gaps): 2847. Aggregate covers all 34 reported windows including sparse ones: **2848 gaps**, 1642 >60Hz budget (57.6545%), 2727 >120Hz budget (95.7514%); all 34 report valid counts, max active gap 248218us, maximum window p95/p99 bucket bounds 250000us. The 7678.684ms all-gap candidate may be idle, not active-stall p95. Peak post rate 46.28/s; median active cadence 34.44/s; ANativeWindow lock/copy/post maxima 11.37/14.87/11.13ms; touch to next guest frame max 214.1ms, 11/25 touch summaries ended without a recorded subsequent guest frame. Spotlight: one observed CPU sample, 12%, not proof of peak outside sampled windows. Backend fence max 55.35ms and 21 ABI warnings. Queue/fence/transport/scanout opt-in trace windows all zero in this historical run. Default descriptors and target masks confirm vCPU0/1 -> CPU4/5; no new profile marker, affinity readback, role counters or residency evidence. No claim of physical FPS or of improvement from Phase A/B.

### Phase C first source slices (P1.2 / P1.3, 2026-11-25)

**P1.2 — fence completion/attribution:** Source audit found backend `fence_retired()` calls `stat_report()` under its statistics lock before forwarding completion to VirtIO. Move that periodic report after the callback, with context ID captured before forwarding and no later context dereference. Preserve the policy's retirement bookkeeping before forwarding and use a fresh report clock under the statistics lock; protect against stale timestamps. VirtIO publishes matching current-generation used-ring chains before optional histogram accounting and log formatting. The backend is not given new waits, priorities, timeout/keepalive policy or synchronization semantics. The A830 WAITTIMESTAMP path is unchanged. Other reporting can still contend on the statistics lock and the backend callback thread can still be busy after this publication; this is a source-level removal from the immediate completion path, not proof of a reduced 55.354ms tail.

With frame-trace enabled, existing submit_fence -> VirtIO callback wait uses callback-entry time. Separately record per-callback-batch time through successful host used-index publication and IRQ request; count actual published chains and matched-but-unpublished chains (stale generation or invalid queue), and invalid clocks. No guest interrupt handling, thread wakeup, frame causality or display-present claim. Merged callbacks count once for publication and once per completed fence for wait, refusals and destroy cancellations are excluded from the publication histogram. Legacy logs lack the new fields and remain unknown. Regression source covers merged and synchronous callbacks, refusal, cancel, invalid clock, legacy parser and modern publication counts.

**P1.3 — blob/udmabuf churn:** Allocate the udmabuf create-list for min(input entries, kernel run limit), preserving run/byte splitting. Single-chunk GUEST transfers the original CLOEXEC fd to the resource; single-chunk HOST3D_GUEST transfers it to the renderer's documented take-ownership-on-failure contract. Mark the source entry transferred before cleanup; retain original multi-chunk copies/ownership, imports, coherence, bindings and reset. Avoid one redundant dup/close per single-chunk blob and avoid oversized list allocation. No persistent guest-page/dma-buf/BO cache or reuse pool: old guest backing must not survive a resource lifetime. Existing KGSL stand-in leak/bind-failure scenarios plus new same-ID/different-backing cycles cover both guest/context blobs and foreign-context import. Real workload allocation/import/fence cost reduction not yet measured.

**Remaining Phase C:** audit indicates a shared command mutex and dependency retry that can wait for the preceding slow-lane batch; no evidence yet that changing lane ordering is safe or beneficial. Full-bridges historical session lacked the required trace. Keep ordering, retry semantics, context class/clock policy, VA/coherence and reset unchanged until attributable evidence. No synthetic campaign rerun; validate targeted native/host tests first, then continue Phase D. More aggressive allocation reuse, priority and head-of-line improvements remain pending measurement. Phase C sources committed, CachyOS test execution and physical acceptance pending. OneOS gitlink remains `49e6f51`. No live launch authorization.

### Phase C focused local receipt (2026-11-25)

Operator CachyOS at OneiOS `cd8b68b261631a8ac539e830339846797bd0a895`, OneOS `49e6f51ba0cd52eba4049b39120186efff422076`: interactive analyzer 6/6, Phase A/B 8/8, native XNUHost 14395/14395, fence profiler 29/29, DRM2KGSL stand-in 77/77, leak scenarios 998/998, GPU policy 166/166, task profile 67/67, stage admission 22/22, stub copy 11051/11051, imageset 37/37. ARM64 test kernel and task profiler OFF/ON PASS. Both same-resource-ID/different-backing single-chunk tests returned zero FD and KGSL-object delta. LeakSanitizer clean (mapping counts printed separately; not a physical GPU test). `PHASE_C_REGRESSION=PASS`, `PHASE_C_CHECK=COMPLETE`, log `/tmp/oneios-phase-c.dt05tw.log`. P1.2/P1.3 first slices locally validated; head-of-line and policy decisions remain pending real trace; no measured physical speedup.

### Phase D / P1.4 display path audit and initial source slices (2026-11-25)

**Actual path:** KGSL imports guest pages through udmabuf; a blob scanout flush copies from those pages in XNUHost's RAM mapping into the shared display memfd. 2D transfer resources can also have a host-private intermediate resource. SHM hello passes a memfd, not a gralloc allocation. The separate Android display helper maps it read-only; XHDF damage (v1/v2/v3 optional trace) is drained and coalesced; ANativeWindow_lock supplies a buffer and actual dirty rectangle (the first four posts request full frame). The helper copies that rectangle from SHM, preserving stride, format and fallback, then unlockAndPost. BufferQueue may do additional copyback for partial damage; compositor/HWC/panel timing not measured. Earlier physical baseline at 1080x2340/60Hz had lock/copy/post maxima 11.37/14.87/11.13ms (different observations, not additive). At full-frame 8-bit 1080x2340, the two explicit copies move about 20.2 MB per update (about 1.21 GB/s at 60Hz or 2.43 GB/s at 120Hz, not measured DRAM traffic). Existing raw tight-row fast paths are kept.

**D1 — compact scanout view:** Once a validated SET_SCANOUT_BLOB actually selects a blob, compact its CPU-only segment list in-place by joining physically adjacent entries in their original logical order, only when the combined length fits uint32 and the whole span passes RAM translation. Backend create_blob receives the original list, never retains a borrowed pointer, and its imports/coherence/ownership remain unchanged. No sort, copy of guest memory, buffer pool, or cached host pointers. Preserve disjoint runs, original size, scanout offsets, stride, format conversion, partial damage and reset. This reduces repeated segment walks/copy calls where pages are adjacent; all-scattered pages may see no benefit. New native fixture exercises adjacent/disjoint boundaries, nonzero scanout offset, reselect, partial damage and unref.

**D2 — bounded late coalescing after lock:** While ANativeWindow_lock waits, additional XHDF notifications can arrive. The old helper drains only before lock, so a full-frame copy can already include newer shadow damage that is processed again next iteration. Once a validated full-frame lock is obtained, drain at most 32 additional nonblocking records before copying. Clip/union damage and update the existing pending trace/sequence state; partial locks consume none because Android's granted dirty rectangle must not be enlarged. Preserve first-frame ready wait, first four full copies, invalid-content failure handling, format fallback, legacy protocol, reconnect/damage repair, and release the already locked buffer if the socket closes. No frame pacing policy or deliberately delayed wait. Extra drain has a small syscall/processing cost and may not help if no late notifications arrive. It does not prove a coherent snapshot: the existing SHM protocol still allows concurrent writes/tearing. Receipt of damage is not unique frames, saved posts, GPU fence attribution or physical presentation. New counters distinguish attempts, accepted damage records, valid timing samples, invalid clocks, maximum and window p95 bounds; separate from copy timing. Legacy/partial analyzer coverage remains unknown or explicit. Portable socketpair tests cover partial non-consumption, clipping, trace merging, 32-record cap, empty drain and disconnect; frame profiler and analyzer fixtures cover counts, timing, reset and missing fields.

**Direct sharing / zero-copy: not implemented.** Current guest-backed udmabuf and shadow memfd are not established as importable Android gralloc/AHardwareBuffer allocations. A correct future design needs a supported buffer allocator/import contract with validated stride/format/modifier, producer acquire/release synchronization, cache/coherence, stable per-buffer resource identity and reset/reconnect/FD ownership, and a proven fallback. No direct import of arbitrary guest RAM and no promise that removing the shadow is safe on this firmware. No change to XHDF wire format, GPU waits, OneOS/thermal/recovery, or guest data. Phase D source committed; Phase D focused tests are included in Phase E full local CI/package to avoid duplicated builds. Both pending operator receipt; physical matched comparison requires separate explicit admission/approval.

### Phase D/E full local CI receipt and Phase F preparation (2026-11-25)

Operator CachyOS at OneiOS `88ab6cace4d56b68ef5ce9056c47c0043096a16c`, OneOS `49e6f51ba0cd52eba4049b39120186efff422076`: `PHASE_DE_CI=PASS`, `PHASE_DE_CHECK=COMPLETE`, log `/tmp/oneios-phase-de.VAUgMw.log`. Loader 160/160, XNUHost 14404/14404, fence profiler 29/29, task profiler 67/67, admission 22/22, DRM2KGSL stand-in 77/77, GPU leak scenarios 998/998 and LeakSanitizer clean, display core 261/261, frame profiler 55/55, display modes 10/10, bridges 439/439 plus component suites; ARM64 test kernel and task-profiler OFF/ON PASS, Python interactive analyzer 7/7, A/B fixtures 8/8, OneOS profile 5/5. Full local build, links, package and ELF checks passed. Runtime-only package (no kernel at out/kernel/current): `out/release/oneios-runtime-0.0.0-ci-arm64.tar.zst`, 5858986 bytes, SHA256 `c93e55ae6e4e39cb02f35547b661765ccfc174697521fc88be1b09b9bbcfc0a9`; independently checked by operator. Artifact provenance remains the tested source commit, not this subsequent documentation-only receipt. D1/D2 and E locally validated; actual Android buffer behavior, throughput and physical FPS remain unverified. No new phone stage or live launch in this receipt.

**F0 — readiness before any device mutation.** Verify the tested package and exact source/gitlink; inspect normal Android boot, root/SELinux, current stage and one-shot Data marker, storage and thermal state read-only. The existing stage-runtime wrapper uses unstripped native build outputs, whereas runtime/build.sh strips the packaged ELFs; compare packaged members with freshly stripped copies of the exact build outputs (DEX compared directly) before staging. Stage-runtime requires consumed Data and preserves rollback; do not silently reuse a consumed clone or rearm during readiness. The compact-rearm path requires at least 30 GiB reserve + 64 MiB headroom + 2 GiB margin before its measured allocation checks. No reserve reduction or deletion. The readiness diagnostic is not the exact-profile live admission and may report smoke-current-boot missing even when archived proof can pass the latter; never treat either as independent recovery certification.

**F1 — proposed controlled experiment, not launch authorization.** First isolate CPU placement with the same current runtime and guest image/seed, full bridges, 8 vCPU/4 GiB, 1080x2340/60 Hz, GPU3D, explicit 180-second limit and frame-task instrumentation for both default and prime-first. Hold guard/cap policy, initial temperatures, charging, workload, warmup and observation intervals constant; verify actual effective masks/residency and guard/cap behavior, not merely requested profile. Use independent fresh Data clones, collect and hash each session's logs, verify normal Android return before considering another run. Existing historical full-bridges session lacked matching trace, and Framework-on comparison changed CPU/bridge settings; neither is a controlled old-vs-new runtime A/B. A separate matched old/new runtime comparison is needed to quantify combined A-D speedup. If the guarded profile cannot be admitted or safely exercised, stop; do not disable safeguards to obtain benchmark results. The legacy watchdog and unassisted return remain unqualified, and historical >100 C readings remain safety blockers for uncapped testing. No automatic risk token, thermal change, recovery run, stage or takeover authorized here. Physical panel timestamps remain a P2.3 dependency.

### Phase F0/F0.1/F0.2 operator receipts (2026-11-25)

At validated runtime source `88ab6cace4d56b68ef5ce9056c47c0043096a16c`, OneOS `49e6f51ba0cd52eba4049b39120186efff422076`, the operator matched the package hash and all four native artifacts. F0 log `/tmp/oneios-phase-f0.YBykI7.log`: normal Android on SM-S948B/m3q/SM8850 S948BXXS4BZIG, SELinux Enforcing, boot ID `2cb5d726-5b7c-46ca-bace-072f2e7a5e2d`, no XNUHost process. Strict independent-watchdog readiness BLOCKED; archived reboot-only smoke remains deadline-request evidence, not proof of unassisted recovery. F0.1 `PHASE_F_STAGE=PASS` at `/tmp/oneios-phase-f-stage.2Sl1Hd.log`: reboot-only passive audit, boot-pinned 28-sensor thermal manifest, rollback-backed OneOS and native upgrade; all four staged hashes match, no Framework stop. Rollback directories retained `.rollback/oneos-compat.RHw0zWJy` and `.rollback/runtime.axL4W4Ko`.

F0.2 `PHASE_F_REARM=PASS`, `APFS_DATA=FRESH_UNCONSUMED`, `DEFAULT_PREFLIGHT=PASS`, `PRIME_FIRST_PREFLIGHT=PASS`, `FRAMEWORK_STOP=NO`, `LIVE_TAKEOVER=NO`: `/tmp/oneios-phase-f-admission.wnGGcb/rearm-admission.log` (separate profile receipts in the same directory). F2FS reflink unsupported; sparse fallback and isolated mount namespace probe passed. Both replacement files verified against existing benchmark seed, not historically attested; modified prior guest Data preserved in `.retired-data/consumed.hTFvYsdH`, with rearm-source digest manifest available for a matched future clone. Free space changed from 63666544 to 61454036 KiB; 30 GiB reserve unchanged. Both 180s/frame-task preflights acknowledged the requested CPU profile and guarded default; root guard/cap checks explicitly ready/not certified, legacy watchdog `UNVERIFIED_REBOOT_ONLY`, unassisted return unverified. No claim of runtime affinity, live safety, physical FPS or new recovery validation. F1-A remains pending separate operator risk decision; do not rearm again before the first trial. If an explicitly approved guarded run is undertaken, use the existing bounded telemetry runner with `--no-rearm`, compare seed digest manifests for A and B, collect exact new session logs, and verify normal Android return before a second run. No automatic second launch, no thermal-policy changes.

### Phase F1 operator A/B receipt and next priority (2026-11-25)

Operator on CachyOS collected both launch-matched pairs from `/tmp/oneios-phase-f1-ab.naVZFn/collect/device-logs.tar`: `AB_COMPLETE=YES`, both analyzers PASS, four JSON reports in the parent directory. Runtime revision `88ab6cace4d56b68ef5ce9056c47c0043096a16c`, OneOS `49e6f51ba0cd52eba4049b39120186efff422076` (not this docs commit). A/default launch `77e4076633f84ad0880e5b6536c8fd8f`, archived suffix `lGy4jk`; B/prime-first `eebb6cbae59b43dc96b7f1fd9e7a51a7`, current. Both 180s full bridges, 8 vCPU, 4GiB, 1080x2340/60Hz, GPU3D, frame-task; root software thermal guard and CPU cap OFF in the actual sessions. Both reached guest-ready/first frame and normal Android boot was observed. B previously exited with postboot root status unavailable, not guest boot failure; later collection succeeded. Independent recovery qualification is still open, but no additional recovery investigation is required for offline performance work.

| Metric (descriptive, not causal) | A / default | B / prime-first |
|---|---:|---:|
| Display windows / peak posts per second | 36 / 50.80 | 35 / 50.82 |
| Median estimated active post cadence | 33.32 | 36.34 |
| Active gaps / complete budget-count coverage | 2814 / 36 of 36 windows | 3773 / 35 of 35 windows |
| Above 60Hz budget | 1612 (57.285%) | 2269 (60.138%) |
| Above 120Hz budget | 2545 (90.441%) | 3480 (92.234%) |
| Max active gap (ms) | 243.616 | 245.529 |
| Max window p95/p99 active gap bucket bounds (ms) | 250/250 | 250/250 |
| ANativeWindow lock/copy/post maxima (ms) | 12.31/15.97/5.10 | 11.43/5.91/3.67 |
| Max touch-to-next-guest-frame (ms); no frame before summary close | 739.1; 3/11 | 622.4; 4/14 |
| Render fence max (ms) | 24.854 | 32.656 |
| Other fence max (ms) | 33.669 | 46.151 |
| Flush service max (ms) | 7.871 | 20.114 |
| Fast wait max / slow wait max (ms) | 0.374/11.581 | 0.924/6.453 |
| Used-publish chains / unmatched publication count; max (ms) | 3942/0; 1.731 | 4489/0; 2.125 |
| Late full-frame drain attempts / accepted damage / invalid clocks; max (us) | 2859/1/0; 17 | 3838/1/0; 15 |
| Peak traps/s | 91022 | 115702 |
| Spotlight peak % of one core; observed / >=80% windows | 28; 1/0 | 103; 8/7 |
| host_statistics64 warning lines | 20 | 23 |
| SpringBoard / backboardd observed PID | 30 / 52 | 30 / 52 |
| Runtime CPU marker; affinity / role samples | DEFAULT; 56/168 | PRIME_FIRST_ACTIVE; 56/168 |

Prior passive thermal summaries: A/B CPU peaks 104/106.3 C, GPU 78.4/86.1 C, battery pre 28.1/32.2 C and final 39.1/44.8 C. These are sampled values, not maximum possible junction temperatures; unequal initial thermal states and background activity prevent causal CPU-profile or power comparisons. No root thermal guard/cap is newly authorized or changed.

**Decision:** preserve the default profile; keep prime-first explicitly opt-in. Its median cadence was ~9.1% higher but the proportion of over-60Hz gaps was ~2.85 percentage points worse, peak post rate essentially unchanged, and observed render/flush tails and temperatures worse. Neither reaches stable 60 FPS. Effective-mask samples and role counters exist but counts alone cannot establish readback success or residency. Different workloads, sparse top-process observations, and thermal starting states mean this is an exploratory same-runtime comparison, not a fully matched controlled A/B or old/new runtime speedup. No physical present timestamps, pooled p95/p99, or proof of touch loss. Late-drain measured at most 17 us, with only one accepted damage notification per arm; no evidence it removed a meaningful number of posts. All recorded matched used chains published, but no proof of guest IRQ wakeup latency. Queue wait measurements do not establish a general head-of-line causal mechanism. Retain the current queue ordering, resource lifetime, scanout and fence fixes provisionally.

**Next:** Phase F1 collection complete, controlled F2 deferred. No further hot takeovers or repeat of completed native synthetic campaigns for this decision. Phase G starts with existing task-profile/affinity/CPU samples and exact log pairs: attribute trap classes, cumulative counters and map/unmap ACK tails; inspect timer/futex outcomes, guest process identities and the host_statistics64 ABI warning before changing semantics. Examine fresh-Data Spotlight/index/icon work as a workload confound, without disabling guest services. Add bounded PID/TID attribution only if current data lacks it. Audit actual compositor/layer/present telemetry and monotonic clock domains; physical FPS acceptance remains outstanding. Phase H Metal feasibility stays separate. Local-first regression for future source changes; no new runtime/OneOS, firmware, thermal or recovery policy changes in this receipt.

### G1 — shared-region kernel artifact refresh (2026-11-25)

Operator F1-B retest found broad DYLD 32 MiB unnest warnings, missing `oneios-top`/`oneios-srprot`, and staged kernel SHA-256 `6eb601e46e06bb178a9a38825e7ba61c09dfaa9a3ca37e0729739b4ed1b2d0d6` without patch 0080 markers. The source patch initially failed to apply; `e40a5bf` fixed the hunk context only. CachyOS hosted XNU/prelink PASS (266 s hosted build, 2,711 paired, 0 binding-audit failures, 135 fileset entries, four markers present); candidate `6e8196bf48f242911bd58f4ea6d987505a8aeb21a6b26c4e05559ed5b593531f`, 96,288,768 bytes. This is not guest boot or speedup evidence. The kernel-only stage operation requires explicit old/new and sidecar pins, exact kernel chunk list/build record, consumed Data, image manifest/hash/inode inventory, stage lock, storage reserve and idle healthy Android. It updates only kernel.kc, its hashes, manifest.json, image.sha256 and image.ids, preserving prior inodes in .rollback/kernel.*. Interrupted publication stays disarmed; no automatic rollback or live authorization. Existing GPU addon/trustcache are byte-preserved, not ABI-qualified with the new kernel. No OneOS/runtime/APFS changes. Local tests and physical stage receipt pending.

**G1.4 physical stage receipt (2026-11-25):** At `ef6df45`, CachyOS regression 57/57 PASS (5 kernel upgrade, 29 takeover, 4 stage, 4 native runtime, 15 full takeover). Kernel-only transaction PASS; independent device SHA-256 readback `6e8196bf48f242911bd58f4ea6d987505a8aeb21a6b26c4e05559ed5b593531f`; old inodes and metadata preserved under `/data/adb/oneios-m3q-framework/.rollback/kernel.ZOxS9Sco`. GPU addon/trustcache preserved, runtime unchanged, Data remains consumed, no Framework stop. Local receipt `out/g1-0080.aW751x/kernel-upgrade-retry.log`.

**G1.5 host compatibility and bounded QEMU execution (2026-11-25):** `out/g1-0080.aW751x/host-boot.JC0fG7`: local artifact compatibility PASS (24A446/iPhone18,2, format 1/session ABI 1, 21 files, 17,862,827,289 bytes; MH_FILESET arm64e); candidate kernel SHA matches above; Linux runtime xnuhost SHA `340941e6d1e15d4ee2f0d303ed9a017d6202f522430ca162806aed1981e6f43a`, not the staged Android runtime. QEMU 8 vCPU/4 GiB, display none/no input; outer timeout 124, xnuhost reported 899.9 s and exit 0, RAM returned. iOS daemon execution and 0080 reporting verified. Subsequent targeted read of the same boot log confirmed backboardd PID 54 HID touch/buttons clients at monotonic 1154/1155 s, IOMobileFramebuffer open status 0 at 1157.073 s, first black guest frame at 1192.683 s, and `guest ready: first frame with content` at 1193.102 s (0.4 s, one frame after black). Hosted first-content milestone PASS; this is not physical panel/touch, SpringBoard identity, GPU3D or native performance evidence. No repeat QEMU required. Fifteen complete 30-second 0080 summary windows in the supplied excerpt (not entire boot) total 6,106 shared-region vm_protect calls, 604 unnests, 0 no-op nested avoids, 17,629 PTEs flushed and 43,309 kept (71.07% of these counted PTEs). This is measured preservation of unchanged PTEs, not a percentage improvement in total unmaps or FPS. Final host cumulative 6,902,862 traps (7,670/s), 2,630,042 faults, 3,311,656 release-map operations; QEMU/runtime/workload differ from native F1-B, so do not compare as speedup. The host_statistics64 count mismatch remains a separate ABI investigation; unsigned-looking attrlistbulk time anomaly requires source verification. Native GPU addon compatibility, native first-frame and performance still pending; preserve existing safety controls and rollback evidence. Do not use old benchmark image as proof of the newly staged kernel.

**G1.6 native boot and preliminary performance receipt (2026-11-25):** The staged candidate booted in the 180 s SM8850 prime-first/frame-task full-bridges trial on OneiOS `3ed8b15` with the unchanged OneOS gitlink and previously pinned Android runtime. The operator's telemetry reports guest ready, display first frame, host mask 0-7, KGSL 3D and full-bridges runtime markers before an observed subsequent Android boot. Host exit 4: post-reboot root unavailable; recovery cause/qualification not proven. Exact current launch `225a83e62acf48e8823245356789bafe` matched the host console and collected device metadata. Evidence: `out/sm8850/thermal-bounded/20261125T021306Z-cc3cd4f6/` and `out/g1-0080.aW751x/native-g1.soK3H3/analysis.kYaRD1/` (collector archive, raw xnuhost log, perf.json, shared-region/handoff traces, telemetry). These are operator-local paths, not repository artifacts. Native first-frame and KGSL functional evidence PASS for this trial; full performance acceptance FAIL.

Relative to F1-B retest (old kernel), peak display posts/s 53.66 -> 47.28; median estimated active cadence 39.30 -> 34.02; over-16.667-ms active gaps 1,899/3,328 (57.06%) -> 2,242/3,742 (59.91%); over-8.333-ms 85.67% -> 90.83%; max active gap 246.320 -> 248.072 ms. Max touch-to-next-observed-frame proxy 515.7 -> 635.2 ms, missing 5 -> 4 (not end-to-end touch latency). Frame copy max 12.534 -> 7.25 ms; render fence max 44.421 -> 30.505 ms; blob service max 24.107 -> 38.073 ms and worst window p95 bucket bound 8 -> 16 ms. New trial: 35 display windows, complete budget-count coverage; GPU callback-to-used-ring/IRQ request 4,587 published chains, zero unpublished, max 2.574 ms (not guest wake-up); Spotlight 105% peak, 7 of 8 observed windows >=80%, iconservices 68%, 22 ABI warnings. At T+35.59/T+171.71 s the hottest observed CPU sensor reads 104600/105000 (approx 104.6/105 C if millidegree units; runner flags units unverified); battery 32.4 -> 41.9 C; prime policy scaling_max_freq 4262400 -> 3974400 kHz. These are two snapshots, not full-session maxima. Native thermal constraint and uncontrolled background/index/interactive workload confound the comparison. Do not claim causal regression or speedup from the kernel alone; do not confuse display posts/cadence with physical FPS. Keep candidate and rollback available without promoting to default. No additional hot trial, recovery smoke, QEMU run, rearm or native rebuild for analysis. Raw native shared-region and handoff traces have been generated but not yet inspected in the current review; determine whether fanout persists, whether PTE retention/no-op counters are active and whether map/ACK contention, guest daemon load or fence/queue tails explain the result before selecting the next code change. No production or policy changes in this receipt.

**G1.6 raw attribution / G2 admission (2026-11-25, same matched launch):** Inspect operator-local `g1-shared-region.txt` and `g1-handoff-trace.txt` from analysis.kYaRD1. Five guest 30 s reports, ending at 22097.156, 22127.160, 22157.235, 22187.236, 22217.238: shared-region protect calls [29364,23247,13095,6408,1428] = 73542; no-op successes zero; internal unnest count 7046; 89 textual DYLD unnest notices, all 0x1e5200000->0x1e7200000 (not the same counter). PTE protect counters 99559 changed/flush candidates and 229734 unchanged (69.77% counted entries; 0080 flushes the span from first to last changed PTE, so an unchanged PTE inside that span need not actually survive). First 24 srprot lines all launchd: prot 0x13 (READ|WRITE|COPY) 9, 0x3 (RW) 6, 0x1 (R) 9; not proof of redundant requests. No relaxation of COPY, TPRO/JIT or real permission/refmod changes.

Guest shared-region/commpage flushes [1017,1227,218,8958,30191] = 41611; fanned unmap orders [1158,25720,26803,1301779,6084442] = 7439902 (3.49x F1-B's 2134505 in five reports, unmatched workload). Last window 201.53 unmaps/flush and 90.08% of classified unmap orders; own 669747. Total own 4407170; last two windows 99.28% of fanout. Per-user TLB aggregate wait 11.276 s over five reports (not elapsed stall or CPU time), last window 2.643 s; global wait last 69.945 ms. Guest free RAM 24-28 MiB after first minute, wired 2061 MiB and compressor 201 MiB holding 712 MiB at 22221.058, memorystatus available 735 MiB. Memory pressure/reclaim is a plausible confound/cause, not proven attribution. Six host reports (~180.2 s): 13657379 traps, 7048617 syscall, 6485033 fault, 123729 interrupt; 18509058 deferred unmap orders, 773354 ordered unmaps, 7278122 release-map timing samples. Weighted means (window counts) up/down 3.313/3.721 us, release-map 14.203 us, ordered unmap 28.056 us; worst window p99 12.29/20.48/131.07/1572.86 us respectively; running maxima up/down/release/unmap 19.596/14.124/24.283/86.925 ms, not per-frame timings. Do not pool window quantiles. Prime guest vCPU0/1 0% idle in middle two host windows, 65/69% idle in fifth while vCPU2/3 ~36/40% idle; placement and workload may be uneven, no evidence that all eight cores are saturated.

Per-process approximate 0080 top slots (not full census; mixed/truncated print lines): backboardd PID52 four reports sum 1471342 traps, 27.197 s trap time, 740024 vm_fault counter, 1268210 current-context target-pmap unmaps; Spotlight PID211 two reports 1219420 traps, 9.577 s trap time, 353887 vm_fault, 281420 such unmaps, late window 421174 BSD466 calls. Pinned XNU syscalls.master identifies 466=faccessat, 75=madvise, 368=workq_kernreturn, 375=kevent_id, 478=bsdthread_ctl. Backboardd and Spotlight are significant workloads, not attribution of the 6.08M broadcast orders. 0080's per-process 'own unmaps' hook runs inside hosted_task_unmap_locked, including a broadcast to current task, so it is not the aggregate 0045 own-only counter. The trace also includes 0 HID drops and one sample up to 3162 us scan-to-HID driver, distinct from touch-to-next-frame; not a full input-latency acceptance.

**Source audit and next change:** 0045 `hosted_tlb_flush_region` iterates map_pmap_list under pmaps_lock and each target's TLB word; only PMAP_TYPE_NESTED checks `hosted_nested_seen` (32 MiB history bitmap, sticky except full address-space flush, overflow bucket); commpage is broadcast to every eligible hosted task. 0080's protect optimization addresses one call path, not all pmap invalidations. Pinned upstream XNU also has pmap_unnest NG transitions, pmap_page_protect and phys_attribute_clear/arm_force_fast_fault paths. Existing logs aggregate nested/commpage and do not identify flush caller, range size or whether targets really held mappings. G2.1 is fanout elimination with a conservative address-presence proof at the guest pmap boundary: audit all normal/refill/fault-around task_map paths, address-space creation/destruction/nest/unnest/role transitions, pending map/unmap ordering and lock lifetime; first add source-type/range/target counters and a bounded no-false-negative presence filter candidate with conservative fallback on unknown/overflow, host-side model/race tests before kernel integration. Never skip a real invalidation, coalesce across an intervening map/protect, drop acknowledged work or bypass the existing order protocol. Pair source-type and before/after counters with the candidate in the next justified validation rather than a separate hot diagnostic run. G2.2 host queue/ACK tails after controlling fanout; G2.3 memory-pressure/guest background and host_statistics64 ABI investigate in parallel; GPU/physical FPS acceptance still outstanding. Keep current staged kernel and rollback, no promotion or automatic rollback, no further hot takeover/QEMU/rearm/rebuild just for these logs. The observed >100 C readings and unqualified recovery make repeated unguarded trials inappropriate. No production code in this evidence commit; filter design requires implementation and tests, not yet qualified.

**G2.1 implementation candidate and thermal profile (2026-11-25):** 0081 adds an address-space-local, fixed 128-set tag/64-page presence table (2 KiB per pmap) under the existing user TLB word. Both normal and fault-around fill mark every attempted map before submission; all history is sticky until pmap creation, collisions are sticky unknown and large ranges fall back to the original behavior. Review of task.c showed that deferred unmap success is queue acceptance, and log_map_failure merely logs an eventual failed munmap. Consequently 0081 never clears history on any unmap (including full ranges). This intentionally sacrifices some filtering power rather than assuming an ACK that the guest does not receive. Existing coarse 0045 filter remains; no changes to ordering, permissions, pmap list lifetime, PMAP refmod or host ACK protocol. Nested/commpage only: skip a legacy fanout candidate when the new table proves no possible mapping. `oneios-fanout-presence=0` restores legacy decisions. New `oneios-fanout:` reports flushes, pages, targets, legacy skips, new skips, issued orders separately for nested/commpage/other. The legacy aggregate skipped counter now also includes page-level never-attempted-map decisions. Stats are relaxed nontransactional snapshots. No real kernel build, phone stage, physical qualification or measured savings yet; local `python3 kernel/tests/test-fanout-presence.py` compiles the exact patch header and exercises a deterministic reference model; use `--xnu-dir` on the actual patched XNU before staging to audit both map publication sites. Maintain previous kernel rollback. G2.2 ACK optimization remains pending.

OneOS gitlink `147b0aa3f858c142abc41450c36883684bc782a5` changes the guarded CPU-only escalation to 65C/28%, 70C/18%, 75C/12%, 80C/8% of hardware max, retaining the existing 40% initial cap, independent other-sensor thresholds and 90C emergency guard. 30–70C is a target, not guaranteed. Ordinary 75C escalation does not request reboot; cap failure, invalid sensor, emergency recovery and deadline still use the old fail-closed behavior. No automatic reboost/shared-QoS relaxation. The dedicated 180s performance wrapper and telemetry default to guarded mode, discard stale historical no-guard environment, and require the 75C policy preflight marker. Do not compare the next thermally capped run as a kernel-only A/B against unguarded G1.6. Local CI before any staging, no new live trial authorized in this commit.

**G2.1 review:** The C model copied from the final 0081 helper and exact fanout-presence.c blob 9e803b378871ca8203317c29eaecf2dec900c78f compiled on a local x86_64 review container with C11, -Wall -Wextra -Werror and UBSan and passed 200,000 deterministic operations. Extracted OneOS 147b0aa policy function passed CPU threshold boundaries, no reboost and CPU/GPU/battery emergency cases. These are isolated tests, not full repo regression, actual XNU patch apply, kernel link, Android sysfs qualification or measured performance. Full CI cannot run in the review container because direct GitHub DNS/checkout is unavailable. Local CI now invokes the actual header model and OneOS thermal policy test; operator must validate full patched source, kernel build and both map publication sites before any stage update. No device changes, recovery smoke or live run.


**G2.1 physical early-return / boot regression (2026-11-25).** Exact kernel-only deployment succeeded for G2 KC SHA-256 701a16323ac8e6b668827995c59e8978b6b458ba0b26c4317b3f8f7aff849ff9, G1 rollback /data/adb/oneios-m3q-framework/.rollback/kernel.iNxzyvvE; GPU addon, trustcache, four native artifacts and consumed Data identity preserved. OneOS 147b0aa stage passed; fresh Data rearmed. Guarded 180s default CPU placement/frame-task trial b425135c9e5a4c2babc97a5a781fe694 on boot b67c7148-0e86-41c7-8cd4-6cc94d785820 returned at approximately T+82s, not the 180s deadline. Operator reported no Apple logo or Lock Screen; SpringBoard/BackBoardd and guest-ready not observed, first-frame and KGSL log markers observed but not proof of UI. Logs report CPU cap 18%, later junction samples about 40–41 C, and stale_guard_sample return; dyld hashing remained unfinished. G2 fanout effectiveness and performance not qualified; do not classify this as native boot PASS or compare it with G1.6. Preserve device evidence and kernel rollback. Host exit 4 after observed reboot is not independent recovery qualification.

**G2.1 recovery of the guarded boot experiment.** Pin OneOS 98c2acd1fd68a08600f0f8ca25efa1477327fd51: shell builtin single-value thermal and cpufreq reads replace per-attribute cat forks, sample-age diagnostics added, all existing thresholds/strict caps/monotonic policy/3s freshness/watchdog retained. Operator CachyOS exact-commit archive local regression PASS (thermal75 8, guarded_full 26, perf_profile 5; 39 total tests, no device access). This commit adds compact-by-default telemetry console with all detailed snapshots, JSONL, comparison and subprocess logs still retained; --verbose restores the full stream. Separate log-milestone result and explicitly unverified physical UI acceptance. No change to XNU, GPU addon, signature validation, kernel build or watchdog. Host telemetry self-test and regression pending on CachyOS; physical thermal sampler timing, boot and UI acceptance remain pending. Do not change dyld signing/hash validation based on this confounded trial; first isolate the sampler fix and collect boot timings before considering a separately qualified hash optimization. No new live test in this commit.


**G2.1 guarded default retest and QoS handoff blocker (2026-11-25).** The fork-reduction fix at OneOS 98c2acd and OneiOS 44c9d6f passed local telemetry self-test, takeover/full-takeover regression and staged guarded admission. In the default/frame-task session 4fe58297aab945319f6ddb70328a3bbe, the operator confirmed visible iOS UI; SpringBoard, BackBoardd, guest-ready and first-frame markers were recorded. The root return record attributed return to the 180 s framework deadline. Root loss after reboot and the unqualified legacy watchdog still preclude independent recovery certification. This is a successful individual guarded guest boot, not stable 60 FPS or a controlled affinity comparison.

Prime-first session 24d822d167a14c2992743ef2078ad9d7 was refused before Framework stop by panel-wake admission. Session 27d2e9a5ea7a48e6812efb1c6b47c8d8 on boot ca407baa-81fd-4c75-aadf-4c7f3181f317 failed at the CPU cap handoff, before guest boot: effective policy0 MIN 3628800 kHz versus requested 1451520 kHz, unachievable_cpu_cap_floor. The watcher requested reboot; boot cf0fa677-fc16-4e50-b1c2-8aa73bfb0455 reported boot_completed=1, healthy zygotes/system_server and no active OneOS processes, with the old control/state=starting preserved. This is a stale session on a different boot, not an active takeover. There is no evidence that prime affinity itself caused either refusal.

Operator-local QoS trace qos-20261125-111139.txt confirmed UFS full-frequency MIN requests and SCMI MAX limit updates; this does not identify the owner of the failed session's exact MIN vote. Diagnostic MAX requests used store_scaling_max_freq. v2 established effective 1440000/1862400 kHz ceilings, but direct IO failed; v3 stopped before cap writes on unsupported direct IO. v4 buffered read accounted 8396800 storage bytes, no UFS boost under cap. v5 panel-wake trace 26/26 events, peak 43600 mC, MIN 1228800/883200 kHz below cap, no observed ceiling violation, initial effective ceilings restored. Both v4/v5 arbitration results remain INCONCLUSIVE: no above-cap MIN vote observed while cap held. No further repetitive diagnostics or unguarded run justified.

**P0 MAX-first source integration, not hardware acceptance.** Pin the exact locally tested OneOS candidate 88dc7335337371bb9fa0efc6d0783f4de6e6720b from fix/sm8850-qos-max-first-candidate into feat/sm8850-xnuhost-perf-p0. Operator CachyOS log /tmp/oneos-qos-ci.65zEyr.log: shell syntax PASS, guarded_full 32/32, thermal75 8/8, perf_profile 5/5 (45/45), exact commit diff check PASS, DEVICE_DEPLOYMENT=NO and LIVE_TAKEOVER=NO. The candidate now attempts a lowering MAX write after verified Framework stop, revalidates both clusters' effective MIN/MAX, permits at most three 50 ms settlement sleeps and rechecks original thermal-sample freshness. Unresolved conflict/invalid readback still faults; no optimistic OK, no raising to the MIN floor, no threshold/firmware/vendor/legacy recovery or deadline change. It is a shared sysfs MAX request, not independently owned or continuously enforced QoS; offline fixtures model arbitration rather than proving it on the Samsung kernel. Do not declare P0 complete. This receipt authorizes source integration only. Local integrated host regression and rollback-backed script staging/check before separately considering a guarded physical trial; no new native runtime, XNU/kernelcache, APK or GPU build, no automatic Data rearm, no live trial in this commit. G2.2 XNUHost handoff/map/ACK work remains separate.


**P0 MAX-first guarded default regression on Arch WSL2 (2026-11-25).** OneiOS a1467026671a86ea2068826862bb3ebcf14eb412, OneOS 88dc7335337371bb9fa0efc6d0783f4de6e6720b. Operator WSL local regression: 121 unit tests (32+30+15+4+4+4+16+3+8+5) and two telemetry self-tests passed. Rollback-backed script upgrade retained unchanged watchdog, .rollback/oneos-compat.vyPbgnFA; staged cap SHA-256 b942cf414fca534f6a6dda6eca8f8d5084e81f54e935a5618e77459e4122a9c6. G2 kernel and XNUHost hashes remained 701a16323ac8e6b668827995c59e8978b6b458ba0b26c4317b3f8f7aff849ff9 and 7c6f4d468c19d2c1d69808881920a3fbb1c6ec0f6136366c04e842bd5e745b20. Restored pinned staged ARM64 runtime into WSL, not a new local build. Fresh compact clone wrote 2235387904 bytes, preserved consumed Data at .retired-data/consumed.qeisip1X, guarded preflight passed. No thermal threshold, kernel or runtime change.

Session 2cf82d5516dd4988941246fc90f9fcdd, boot cf0fa677-fc16-4e50-b1c2-8aa73bfb0455, default CPU placement/frame-task/180 seconds, evidence out/sm8850/thermal-bounded/20261125T144722Z-70bdaece; post-reboot-20261125-215533 collection exit 0. Verified Framework stop uptime 38708, deadline 38888. First-frame, SpringBoard/BackBoardd at T43.37, guest-ready at T61.85 (observed samples, not exact event times), KGSL and full-bridges log markers. Snapshot CPU maximum 50.5 C, effective MAX 1440000/1862400 kHz at all live periodic snapshots; last T176.5. Current generation cf0fa677-fc16-4e50-b1c2-8aa73bfb0455.5311.3865248 strict cap armed; final cap heartbeat OK seq164 uptime38888 level2 pct40, guard heartbeat OK seq192 uptime38890. Historical failures in appended cap log must not be assigned to this session. No MAX_FIRST_MIN_CONFLICT or MAX_FIRST_CONFLICT_READBACK_OK reported for this generation in the provided excerpt; actual conflicting-MIN arbitration still unqualified. Physical UI observation not yet supplied for this session.

Return outcome and log record watcher/framework deadline request at uptime38889; new boot 7502432e-441c-4a05-bc26-251e748f0d48, reboot reason oneios-sm8850-reboot-return, boot_completed=1, zygotes/system_server healthy, SELinux Enforcing, root uid0 available and ADB USB transport reattached. Host bounded wait terminated runner locally (-15), telemetry exit4 is not guest boot failure. Observed return/deadline record is not proof of unassisted return, independent watchdog qualification or continuous cap enforcement. Keep MAX-first baseline, no repetitive live run or storage-consuming rearm for this receipt.

Same-session frame report: 34 display windows, 1215 active adjacent Android post gaps, 1134 >60-Hz budget (93.33%), 1187 >120-Hz budget (97.70%), max active gap 244674 us, max copy 11.314 ms, 12 touch summaries (3 no frame before summary end), max recorded touch-to-guest-frame 713.9 ms, peak guest CPU window 425%, peak traps 43556/s. Not physical FPS or causal stall proof; idle/all-gap metrics excluded from active budget. Latest cumulative placement per vCPU/role: guest 147223, service 102891, vCPU 8 attempts (250122 total), zero reported failures/mismatches in sampled records. Source main.c place() calls sched_setaffinity; task.c already caches placement by vCPU/epoch. High count does not establish redundancy or contention. Next G2.2: extract exact current-session raw perf histograms, process-total perf-task-wait, queue/ACK/futex detail and fanout counters from preserved archive; choose a targeted offline candidate without weakening ordering, affinity, thermal or recovery invariants. No additional device mutation or runtime change in this documentation receipt.

**G2.2 baseline and first host ACK candidate (2026-11-25).** Token-verified same-session g22-baseline.txt from the archived G2 default/frame-task MAX-first run. Final runtime summary 181.5 s: 6248576 traps (34427/s), 3534655 faults (56.57%), 2648949 syscall, 64972 IRQ; 6246522 handoffs each direction, 7203641 host futex waits, 2766101 guest sleeps, 3534514 deferred maps/0 ordered, 1707198 queued unmaps/355255 ordered, 1208080 joined operations. Process-total release ACK n3896343 mean28.52 us p99 bucket128 us max22025.21 us; release lock n3955682 mean6.18 us p99 bucket128 us max31424.69 us; direct order ACK n340790 mean28.32 us p99 bucket128 us max15386.51 us; deferred order ACK n19315 mean134.36 us p99 bucket4000 us max62983.44 us. Final handoff up/down mean8.06/9.22 us, p99 20.48/28.67 us. Kernel fault next-run interval max1123567.7 us, not isolated fault CPU time. These intervals overlap and are not wall-time attribution. All eight final thread_run futex timeout counters zero, no ACK timeout diagnosed from these logs. 250122 placement attempts, not evidence of redundant affinity calls. Fanout log interleaving lost three nested summary lines: only two complete nested windows available, one with 837 presence skips out of 27262 post-legacy candidates; do not extrapolate to whole session. Host map counts and own-task unmaps dominate the measured volume, but GPU/physical frame pacing cause remains unproven.

G2.2a changes only the embedded stub/host event handshake. Previously ops_done was published on a different word from to_host; a FUTEX_WAKE between the host's ACK check and FUTEX_WAIT(to_host,0) could be lost while the thread continues running, retaining task order lock until trap or the 200 ms poll. This is a source-level race, not an observed timeout or proven frame-stall cause. The new event values PENDING=0, TRAPPED=1, MAP_ACK=2 use the actual futex word; acquire observation of TRAPPED also acknowledges all queued ops, because the non-nesting stub finishes them before returning to guest code. Host uses the original event snapshot as wait expectation, so either event arriving before enqueue changes that word and returns EAGAIN. ACK alone never completes thread_run. Slot layout retained with former ops_done reserved; no change to guest hostcall ABI, map/unmap order, queue bounds, locks, timeouts, interrupt/kick, seccomp, thermal policy or recovery. Both host and stub must be rebuilt together (embedded stub.bin); no mixing binaries. Source review container x86_64 C11/Werror/UBSan helper test passed 20000 process-shared futex release rounds plus deterministic stale expected-value ACK/trap tests; exact blob verification required. This is not an AArch64 memory-model proof or full runtime integration test. Run local make test (including the new test and ARM64 synthetic kernel suite) on WSL/CachyOS before considering deployment. No physical trial, kernel rebuild, Data rearm or device changes. G2.2b remains evidence-driven map/ACK volume and placement work; do not promise FPS gain from G2.2a alone.

**G2.2a operator-local CI, partial-lock assertion correction (2026-11-25).** Exact OneiOS 9e5a9933e26a385686c62f8ade1b5409bd6ab3ce, OneOS 88dc7335337371bb9fa0efc6d0783f4de6e6720b, Arch WSL2 isolated build out/sm8850/g22a-ci.lCA5g5/ci.log. Synthetic ARM64 guest all passed including 200-round unmap race, timer preemption and JIT aliases; profiler OFF/ON passed. ram=auto selected 1024 MiB, held fixed, prefaulted/locked 64 MiB and guest reported all passed, but old Makefile completion regex recognized only full or zero lock; make test failed before its host-test recipes (including new stub_event) ran. Do not mark integrated CI PASS yet. ramfix.c already intentionally supports partial mlock, preserving locked pages and stopping further prefault. Correct only the synthetic test oracle: require exact matching auto/fixed size, completed full/partial/zero mlock semantics, consistent final held/locked amount, guest PASS, clean host exit and actual zero command status. No runtime, memory policy, memlock limit, thermal, GPU, kernel or OneOS changes. Isolated review-container parser self-test PASS 16 fixtures (3 valid, 13 negative), exact tested blob 954b139edd29edf1f3d226852a23842e00d4d989. Replay the existing ramauto.log first, then rerun integrated synthetic CI locally; neither is physical performance or recovery qualification. No staging/rearm/device access.

**G2.2a integrated synthetic CI PASS (2026-11-25).** Operator-local Arch WSL2 at OneiOS 623394a7eefe9cfd8dd83e882d3330d14c6720aa and OneOS 88dc7335337371bb9fa0efc6d0783f4de6e6720b: previous partial mlock receipt replay passed; all make test recipes passed (including 16 RAM log fixtures, synthetic ARM64, profiler OFF/ON, and 20000 cross-process futex rounds). Isolated 2D-only candidate out/sm8850/g22a-ci-fixed.Arik54/runtime/xnuhost/build/android/xnuhost SHA-256 d7e4baacc01f5a7999f56c3edccb373371a1bf1053609242f501f1a4c2d44d62; ci.log adjacent. Existing full-bridges runtime preserved; not a production candidate or physical FPS result.

**G2.2b1 own-pmap presence candidate.** Baseline own-pmap flush volume motivates reusing 0081's conservative history for own-task unmaps, not suppressing previously attempted mappings. New 0082 is opt-in (oneios-own-presence=0 by default; =1 for controlled candidate); requires 0081 history enabled, page alignment, nonoverflowing and bounded range, and proof of no attempted map. Unknown/collision/large ranges retain old path. No history reset added, no change to fanout, map/ACK ordering, pmap lock, mapcheck, fault-around invalidation, logical flush attribution, thermal or recovery. Actual user_unmaps counts issued hostcalls; own logical count unchanged. Relaxed oneios-own-presence windows count candidate requests, skipped, issued only while enabled (requests excludes pmaps without hosted_task). No claim of skip fraction from live baseline. Review-container C11/Werror/UBSan test using equivalent 0081 helper passed 200000 deterministic operations (69319 skips in synthetic model, not physical expectation); operator test extracts actual 0081 and 0082 headers. Require pre-0082 exact patched source audit (all map sites plus apply check and actual post-apply helper inspection) before kernel build; no kernel compilation, stage, rearm or device mutation performed. Keep 0082 disabled until source/build review, then paired guarded comparison at unchanged cap with full bridge candidate. G2.2b2 fault/map volume remains separate work.

**G2.2b1 WSL source receipt and patch-context repair (2026-11-25).** Operator-local c1d573611e8f1ed2e9464a74dbe7fbdd2655e745, app 88dc7335337371bb9fa0efc6d0783f4de6e6720b: both 200000-operation presence models passed (own skip count 69319 synthetic only); host 5/5 passed, then pinned external fetch, oneios-tool release --locked, series/profile and build-record self-test all passed. Full 94 base patches and hosted series through 0081 applied in out/sm8850/g22b-source.UJUNOE/base/series/xnu, PRE0082 345bfe181f42133dd0428339c40772ebd59f77d3, both map publication sites audited PASS. 0082 git apply --check failed at hosted_pmap.h:124. The authored second hunk ended on an added line, with zero trailing context, so git apply treats it as an end-of-file match; reconstructed 0081 excerpt reproduces exact failure with git apply, then passes after adding the three following unchanged lines. Correct patch context and counts only, identical added/deleted source lines (no runtime semantics change). Resume source audit against the preserved exact pre-0082 tree; no need to refetch or rebuild oneios-tool. Full actual-tree application, kernel compilation and phone validation remain pending. Source receipt out/sm8850/g22b-source.UJUNOE/source-validation.log.

**G2.2b1 actual source validation PASS (2026-11-25).** OneiOS 900dcfecc25f85b4298bcc0bb6b93976557f0e5c, OneOS 88dc7335337371bb9fa0efc6d0783f4de6e6720b; preserved pre-0082 tree 345bfe181f42133dd0428339c40772ebd59f77d3, corrected patch context, both presence models, normal/fault-around map sites and actual patched source audit passed. 0082 applied and committed as 764e4554c5a58a382c385493aae2f4263a4da14c in out/sm8850/g22b-source.UJUNOE/base/series/xnu; source-validation-resume.log. No kernel compile, prelink, runtime build or phone access. Opt-in still off by default.

**G2.2b2 decision and G2.2 profiling-overhead candidate.** Re-read same-session g22-baseline.txt: all five complete guest 30-second reports show fault-around maps 0. The own-pmap counts were 21349, 282127, 499506, 394448, 415461; these are logical flush windows, not unique pages or acknowledged host syscalls. Avoid a speculative fault-around batching patch for an inactive path; do not enable wider prefetch on the basis of these data. Existing queue already coalesces adjacent compatible ranges. Affinity source cache by vCPU/epoch is present and default bench uses distinct host cores; high attempt count alone is not redundant work, so placement policy unchanged. G2.2b2 remains open after 0082 hardware measurement. Instead reduce optional profiling perturbation: the baseline process-total release_locks and release_ack alone record about 7.85 million timing observations; every sample also touches a shared process-total histogram across vCPU writers. Shard that total into eight logical vCPU buckets plus host bucket with 128-byte separation (6912 bytes for this configuration instead of 760); still relaxed atomic writes, per-task timing unchanged, merge counts/sums/aborted by addition and maxima by max at report time, lifetime totals survive task exit, existing log schema and approximate concurrent snapshot semantics retained. No change when perf-task is off except static storage; no change to affinity, thermal, guest mapping, stub/ACK, kernel or recovery. Review-container C11/Werror/UBSan isolated helper test against copied unchanged timing primitives passed 200000 samples from ten concurrent workers (two share host bucket); verified header/test blobs 102a983f573006deb7b20bc8ff60cf81f84744a5 and 963cf15ee8f870e166c26319573cce6f8adb3983. Full repo integration/ARM64 synthetic CI and physical effect remain unverified; do not present synthetic helper equality as measured performance improvement. Next: integrated local CI, then prepare combined guarded full-bridges candidate with 0082 off/on admission and controlled measurements before additional map/affinity changes.

**G2.2 profiling sharding integrated WSL CI PASS (2026-11-25).** Operator-local OneiOS aca9e6ca88ad4a41589c6873b9e56ddd87ccc06a, OneOS 88dc7335337371bb9fa0efc6d0783f4de6e6720b. Preserved clean actual post-0082 XNU tree at 764e4554c5a58a382c385493aae2f4263a4da14c. Isolated full synthetic make test passed: RAM_AUTO_LOG_SELF_TEST 16 cases, partial lock 64 of 1024 MiB, TESTKERNEL all passed, profiler OFF/ON and process totals retained, STUB_HOST_EVENT 20000 cross-process releases, TASK_TIMING_TOTALS workers=10 samples=200000 shards=9 bytes=6912. Evidence out/sm8850/g22-profile-ci.OIf4Zg/ci.log; 2D-only binary SHA-256 d59535bb487993e1ec5522eb1552cf5fd9bef6471c06f22af03a5dd2308692a5. Not a KGSL/full-bridges production binary or physical performance result. No kernel rebuild or device access. Next admission is host-only combined build of the 0082 kernel, full KGSL XNUHost with ACK and profiling changes, existing OneOS MAX-first and unchanged guard policy. Reproduce prior G2 prelink flags (RELEASE reference, X18=1); pin Apple kernelcache to 24A446, retain complete prelink audit and chunk hashes. Separate output roots, preserve staged G2 and rollback. 0082 remains opt-in; defer stage/boot-argument changes, APFS rearm and live trials until candidate artifacts and prerequisites are validated. WSL udmabuf-dependent tests may explicitly skip; do not interpret them as passing physical memory/leak acceptance. No source/runtime change in this receipt.

**G2.2 combined native CachyOS build PASS (2026-11-26).** Operator OneiOS c1a36f93e2caa9d403cf67d7539af9b10d6d2798, OneOS 88dc7335337371bb9fa0efc6d0783f4de6e6720b, Linux 7.3.6-1-cachyos x86_64, NDK 28.2.13676358. Oneios-tool release, pinned virglrenderer/XnuPrelink/cache, complete hosted series through 0082 compiled; initial bootstrap link missing archive symbols was followed by successful final link. Hosted kernel 216 s, RELEASE reference 16866656 bytes, prelink X18=1; collection 96305152 bytes, 135 fileset entries, 2711 paired, 93 functions on stub, 9 data unpaired, 0 binding audit failures; 26 unresolved closure references/183 stubbed functions reported at emit, runtime qualification pending. Candidate validation PASS, kernel SHA-256 fd213c272f7053cd54146351dd617b2e1707e2a0efa4dda0aaa096b091c579f5, chunk list 26b545443eef4589774678ac8980fccf679a60199ac685d572e63b8daa75c58c, record 889e3a966a66d2c359b0725754bf09343e5d1121b98d51aff92631bfd4d4b6a9, binds d40eaa78e67daf016ebd8ae2254b01f6107cfff4098e0a2e4a774b5e83e6c942. Full KGSL ARM64 XNUHost SHA-256 8ada56b0e0396d19d7e167082c13247cb90888a18d67db224c7f45a5521af13f. Work out/sm8850/g22-combined-native.i4dbbI; prelink/ and runtime-source/runtime/xnuhost/build/android/xnuhost; SHA256SUMS plus step logs. Synthetic kernel and profiler OFF/ON PASS, RAM auto full lock 1280 MiB, ACK 20000 process-shared rounds, shards 200000 samples, XNUHost 14404 checks zero failed, stage admission 22 checks zero failed, actual Linux udmabuf exercised with stand-in KGSL (six scenarios 77 checks zero failed), leak scenarios 998 checks zero failed and LeakSanitizer no leaks (parked dma-bufs released on reset), GPU policy 166 checks zero failed. QEMU-user process_vm read/write unavailable/skipped and cache maintenance emulation limits remain. This is local build/test evidence, not physical Adreno, guest boot or FPS acceptance. 0082 default off; no boot-arg change yet. Existing device runtime and kernel preserved, no ADB, stage, Data rearm or live run. Next: read-only device admission with exact old pins, verify storage and consumed Data, preserve display helpers unchanged and use rollback-backed independent kernel/native transactions only; keep no-live/rearm boundary. No change to thermal policy or independent recovery qualification.

**G2.2 rollback-backed device staging PASS (2026-11-26).** Operator OneiOS 9767bf1592e7ac1766d2788d8e7f1de75a8b00e1, app 88dc7335337371bb9fa0efc6d0783f4de6e6720b, SM-S948B/m3q/SM8850 S948BXXS4BZIG, USB/root and Android healthy. Admission verified consumed Data token 2cf82d5516dd4988941246fc90f9fcdd from boot cf0fa677-fc16-4e50-b1c2-8aa73bfb0455, current Android boot 7502432e-441c-4a05-bc26-251e748f0d48 unchanged through staging. Evidence out/sm8850/g22-combined-native.i4dbbI/deploy.pDdLJo/receipt.txt plus per-step logs; previous read-only admission stage-admission-fixed.txt. Recovery stage-check refreshed boot-pinned 28-sensor manifest (16 CPU, 11 GPU, 1 DDR), .rollback/oneos-compat.pUqGx82g, no framework stop. Kernel installed fd213c272f7053cd54146351dd617b2e1707e2a0efa4dda0aaa096b091c579f5, previous kernel hash verified in .rollback/kernel.aV61fOPv; KGSL runtime installed 8ada56b0e0396d19d7e167082c13247cb90888a18d67db224c7f45a5521af13f, all four previous native artifact hashes verified in .rollback/runtime.Q3CBFPR7. GPU addon, trustcache, three display helper hashes and MAX-first cap worker hash unchanged. Local canonical runtime populated from exact built candidate and copied verified display helpers, previous local artifacts preserved in deploy.pDdLJo/local-runtime-backup. Data consumption marker unchanged, stage image.ready present, free storage 36979224 KiB after stage, Android protected services running, SELinux Enforcing, MemAvailable 3854416 KiB, SwapFree 5047052 KiB. Old running/ready markers belong to prior boot, not fresh guest acceptance. No rebuild, APFS rearm, Framework stop, live takeover or independent watchdog qualification. Transactions separately rollback-backed, not jointly atomic; rollback boot and candidate addon compatibility still unverified. Next: G2.2 A guarded default CPU/frame-task 180s with 0082 default OFF, fresh compact Data clone subject to unchanged reserve and exact-profile preflight; compare with G2 session while treating kernel/prelink differences and workload as confounders. Add controlled own-presence ON profile only for subsequent B after reviewing A; no safety gate relaxation.

**G2.2 A aborted pre-stop, no guest performance receipt (2026-11-26).** At OneiOS d742743bc79fb80bafea2a9bcd27e1bacadd0688, OneOS 88dc7335337371bb9fa0efc6d0783f4de6e6720b: installed pins, sparse mount namespace probe, measured compact clone (2235387904 nonzero/written bytes, required free 36662235136 bytes), fresh clone hashes and exact guarded 180s/default CPU/frame-task preflight passed. Prior consumed clone archived in .retired-data/consumed.t2lU5ZVL. Trial ce97ab23a0d843b7913d71694beaddfa, boot 7502432e-441c-4a05-bc26-251e748f0d48, root guard and read-only prearmed cap started. Wake gate refused after 6s with CPU0_MIN=2112000 CPU6_MIN=2112000 CPU_MC=75300. Exact switch log reports One UI never stopped, outcome inplace 1795659604 One UI was never stopped, control state returned, no framework takeover-confirmed, no guest processes, same Android boot and system_server PID 9749. No proof of exact cause of early loop break (guard health, return request, etc.); elevated floor and temperature demonstrably fail gate. Host exit 4 is not kernel/ACK/KGSL failure; no guest performance comparison, do not count as completed A. Log out/sm8850/thermal-bounded/20261126T021827Z-3681de0b/diagnosis-A.txt, takeover/run-4o6u2_tb, trial-A rearm/preflight receipts. Existing early one-shot claim consumed the clone even though guest never ran. Post-abort free 34827456 KiB is below last measured compact requirement 35802964 KiB (~953 MiB short, before other activity). Do not clear consumed marker or automatically delete retired Data or rollback; free additional storage by operator-approved means and use normal measured clone.

**Pre-stop Data claim lifecycle correction (candidate).** Integrate OneOS 8d9614bef9ac0e27993d008e7ac208a5b8d2caac: early existing-marker rejection remains under start.lock; move only fresh claim to after wake admission, deadline guard, stop.lock and final recovery readiness, before watchdog transfer and stop_android_framework. Noclobber plus private umask, chmod, fail-closed cleanup on error, cancellation recheck after claim. No change to thermal thresholds, cap worker, wake loop, watchdog, runtime/kernel, or post-claim one-shot semantics. No reclamation of previously consumed clones; only future failures before claim can retain fresh clone. Review environment actual claim fragment mock shell seven cases PASS (fresh/used/symlink/directory/cancel/chmod/smoke); committed source ordering audit PASS. Full operator-local OneOS/OneiOS tests and stage-check pending, no device mutation by this change yet. Next: local safety tests, rollback-backed stage-only script refresh, storage headroom and cool/awake One UI before rearm. No automatic retry or weakened admission. The 6s early refusal's exact guard-break cause remains unclassified; independent watchdog/physical recovery and G2.2 guest boot not qualified.

**Late-claim local receipt and explicit retired Data retention correction (2026-11-26).** Operator OneiOS 703e072ee1040a35d5672f776b5d2553f8a7bcd3, OneOS 8d9614bef9ac0e27993d008e7ac208a5b8d2caac. 34 guarded-full and 8 thermal tests passed, four of five perf-profile tests passed; metadata order test errored on old claim-before-archive assumption. Stage not reached. OneOS 5a8a2ebd4d45cc1eefc87b7f917f75d00bf2d32f fixes only that test, retains early rejection and metadata-before-claim, claim-before-stop and inner order checks; source order audited. Operator explicitly objects to freeing unrelated phone data for accumulated project-created retired snapshots. Add --prune-retired-data --confirm, independent locked cleanup, and opt-in --rearm-data --confirm --discard-retired-data to prune old archived payloads before copy and the newly retired payload after successful publish. No default implicit deletion; keep original bench seed, active/consumed current Data, all kernel/runtime rollback, logs, consumption tokens and both archived hash receipts. Only regular single-link root-private expected-size data.img/unique-chip-id in validated consumed.XXXXXXXX directories with complete receipt metadata are removed. Refuse active sessions, mounts, pending stage transactions, symlinks/aliases or malformed receipts; two-pass validation; idempotent, report actual df delta and estimated allocated bytes. No off-device copy of retired payloads; explicit prune is irreversible for old iOS guest contents. Helper and test isolated on Linux, sparse files only, two tests PASS (valid/idempotence plus seven unsafe cases). Blob pins 0e2d51e5739bce4199163bb7d9922d7154c478d5 and 2a57c550a00162b1d2e97bb0c456e6946a84ce87. Integrated local CI and device prune pending. No thermal relaxation, kernel/runtime rebuild, rearm or live run in this change.

**Actual retired Data prune PASS; follow-up test/receipt corrections (2026-11-26).** Operator OneiOS 5cac488067fef33a218487b085666b95aa0716a0, OneOS 5a8a2ebd4d45cc1eefc87b7f917f75d00bf2d32f. Both cleanup safety tests passed; on-device explicit prune removed 26 payloads in 13 retired consumed archives, retained receipts, no Framework stop. Actual df free before 34740048 KiB, after 63734100 KiB, delta 28994052 KiB (27.65 GiB); prior estimate -374956032 is consistent with signed 32-bit mksh arithmetic overflow, not negative recovered storage. Use awk decimal accumulation for the allocation estimate and add a mock >32-bit byte regression. Restore original executable modes 100755 on framework-stage.sh and sm8850-takeover.py, unchanged content blobs. OneOS 34+8+5 tests passed, OneiOS full takeover 14/15 passed; the obsolete exact staging case-list assertion missed the newly admitted prune operation. Update contract to require explicit discard opt-in, prune-before-copy and prune-after-ready ordering while preserving existing rearm checks. Full integrated CI and late-claim stage refresh still pending; no rearm, kernel/runtime rebuild, physical guest boot or safety policy change. No need to re-prune the 13 removed snapshots. Subsequent explicitly requested rearm uses --discard-retired-data to avoid accumulation.

**G2.2 A retry admission PASS; retired payload retention verified on-device (2026-11-26).** Operator OneiOS 8bc9c9912a19e307eb49fb1b8ebcfc12de419120, OneOS 5a8a2ebd4d45cc1eefc87b7f917f75d00bf2d32f; out/sm8850/g22-retry-A.nXLzF2/receipt.txt, ci.log, stage.log, rearm.log, preflight.log. All nine local safety suites passed: 34 guarded full, 8 thermal75, 5 perf profile, 2 retired prune, 15 full takeover, 4 stage upgrade, 4 native runtime upgrade, 5 kernel upgrade, 16 guarded duration (93 tests total). Executable modes restored. G2.2 kernel and XNUHost installed hashes reverified. Late-claim switch stage hash matched local OneOS; recovery stage-check passed without Framework stop, compatibility rollback .rollback/oneos-compat.CutY2OvE; thermal sensor manifest boot pinned (28 sensors, CPU 16/GPU 11/DDR 1). Explicit rearm --discard-retired-data: pre-copy prune zero files, FICLONE unsupported with verified sparse fallback; consumed guest data.img and unique-chip-id both matched source, freshly cloned and hash-verified. Old consumed pair archived .retired-data/consumed.8RxHV3OF, exactly two payloads subsequently pruned after ready publication, receipts retained. Allocated bytes estimate 2237681664 (nonnegative on Android), df free delta +2185236 KiB during post-copy prune. Overall free before rearm 63726008 KiB, after preflight 63654448 KiB (net -71560 KiB including concurrent device activity; no retained multi-GiB old clone). Guarded 180s/default CPU/frame-task preflight PASS_NO_FRAMEWORK_STOP_NO_DATA_CONSUMPTION; OWN_PRESENCE default off, no rebuild, stop, or live trial. G22_A_RETRY_READY=PASS. Do not rearm again before A; first read-only cool/settled CPU-floor observations on One UI, then only operator-initiated guarded run with --no-rearm, unchanged protections. Prelaunch cool observations are not proof of post-KEYCODE_WAKEUP stability. Independent watchdog, unassisted return, guest boot and physical performance remain unqualified. If pre-claim admission refuses, retain the fresh clone and inspect exact switch/guard evidence instead of rearming; if post-claim failure, continue one-shot lifecycle with explicit discard policy, never clear consumption marker manually.

**G2.2 A boot and deadline observation (2026-11-26).** OneiOS 6e2a727acccc86a6f9c3dd6176bc9ad551870f42, OneOS 5a8a2ebd4d45cc1eefc87b7f917f75d00bf2d32f, token be6099ecedbb466eaab5f402b982c200, boot 7502432e-441c-4a05-bc26-251e748f0d48, out/sm8850/thermal-bounded/20261126T030113Z-36f3d46d and takeover/run-2qyykcpt. Cool gate CPU 34.2/32.7/32.3 C, both MIN floors settled; no rearm. Framework stop uptime 43840, deadline 44020, first frame observed, eight-core mask 0-7 and current-session full bridge marker; SpringBoard/BackBoardd log markers at T44.19, guest ready observed T60.85, KGSL backend observed. Periodic guard CPU samples 44.0–49.4 C, cap 40% throughout, policy0 MAX 1440000 and policy6 MAX 1862400 kHz; T175.17 final sample 49.4 C. These are sampled temperatures, not a proven continuous peak or FPS measurement. Android boot completed after USB loss, last sampled uptime 44025.59, host bounded wait terminated (-15) despite child printed EXIT=0, outer exit 4; exact return cause and unassisted recovery not yet proven. Visual operator acceptance and frame/task archive analysis pending. Do not repeat the run just to recover evidence.

**Requested revised thermal policy / offline candidate.** Operator requests soft cap at 70 C, target 45–70 C, hard throttle at 80 C latched until 70 C, and no routine thermal-triggered return/reboot. Keep emergency/sensor/actuator failure safeguards, Samsung kernel/firmware limits and existing independent timed recovery deadline; absolute no-reboot guarantee and hard physical temperature ceiling cannot be established by a CPU throttle. Current live policy remains the existing 40% boot ceiling, monotonic MAX reductions and independent emergency guard; no live change in this commit. Add pure POSIX shell hysteresis candidate and five passing host-only test groups (tested blobs below). Candidate takes max CPU/GPU/DDR junction sample, normal soft reductions at 70 and 75 C, hard 10% guest CPU duty budget at >=80 C until <=70 C; hold 65–70 C, increase budget slowly after five new cool samples; no minimum heat target or heating workload. 40% initial candidate budget, 5/10 percentage-point upward steps, 10/20 downward steps, hard 10% are provisional tuning choices, not calibrated CPU frequency percentages. Controller must consume only new validated heartbeat samples; battery/skin/emergency validation remains separate. Do not raise shared scaling_max_freq: no independent ownership or safe restore against concurrent vendor QoS demonstrated. Need read-only capability audit of cgroup v2 CPU bandwidth or isolated v1 cpu controller before actuator integration; no enabling controllers, moving tasks or changing clocks during audit. Candidate model is NOT wired into OneOS runtime and not authorization to run another live test. Exact host-tested policy blob 3bc4ed56953a47f4f55683beff49bd1ccd025550 and test blob 1accb3e168b8b8fcf522178602412ed85208925e. No rearm or device mutation.

**Thermal actuator discovery and isolated bandwidth probe candidate (2026-11-26).** Operator-local pure hysteresis 5/5 PASS, checkout 6e2a727acccc86a6f9c3dd6176bc9ad551870f42 with archived exact 8d0da82910d4676f5c33d2efb56026e409060dcf (out/sm8850/thermal-hysteresis.8vqfgR). Physical audit: Android hybrid cgroups, v2 controllers only memory; v1 /dev/cpuctl cpu controller mounted rw; root cpu.cfs_quota_us=-1, cpu.cfs_period_us=100000, v2 oneios_session/cpu.max absent. SCMI/WALT policies 0/6 restored to hardware min/max 384000/3628800 and 768000/4742400 kHz after return. Exact outcome identifies framework-deadline at uptime 44021 (deadline 44020); no reported thermal guard/cap fault in read-only output. G2.2 A ended by timed return, not a demonstrated thermal emergency; frame/task archive analysis and recovery qualification still pending. Choose isolated v1 CPU CFS budget rather than raising shared cpufreq MAX. New sm8850-cpu-bandwidth.sh candidate defines budget=1600*pct us per 20000 us period over eight host CPUs, from 10 to 100 percent of aggregate capacity. Probe creates one private temporary group under the existing CPU mount with stage start lock, validates readback 40/10/40/100, moves only a short probe child and verifies descendant inheritance, unchanged parent membership and quota, removes group. No guest or heat-generating workload, no controller mount changes, no cpufreq writes, no live integration. Host shell syntax and four actual helper test groups PASS (91 valid budgets, invalid input, mock quota/readback transitions, ignored-write and symlink rejection, source audit); exact blobs 1bd9d4efcafe186be9bc9310bb16a6c92cde760c and 1d2766b0cace081df22bf95abc4243532d8bf2bc. Physical mkdir/write/join permission probe pending; actual bandwidth enforcement, task membership throughout guest lifecycle, frame pacing and thermal response remain unverified. CFS duty budget is not frequency or power cap; RT classes are not qualified and 20 ms period is provisional. Keep independent emergency and fault protection and timed recovery. No kernel/runtime rebuild, rearm or live launch.

**Physical CFS-v1 permission/readback and integration candidate (2026-11-26).** Operator OneiOS 44a13b6eecab82257190b6878c75dbf1b2fcb4bb, OneOS 5a8a2ebd4d45cc1eefc87b7f917f75d00bf2d32f, out/sm8850/cpu-bandwidth.H8TTND/probe.log. Model 5/5 and actuator 4/4 local tests passed; phone successfully created private v1 CPU group, applied 40/10/40/100% quotas at 20ms, verified child/descendant membership, removed temporary group and left parent limits unchanged. nr_periods=8 nr_throttled=0, no actual guest load or throttling qualification. Integrate OneOS b6da06f5c5d723166a099b2a66af668185482855 candidate for guarded exact 180s only. Existing thermal guard and cap-worker generation admission retained; separate guard and worker in root CPU group, guest joins private launch-token CFS group before publishing inner PID, readback and guest leader/namespace/thread checks, dynamic budget on each new validated heartbeat, 40% initial aggregate duty budget, 10% hard latch at >=80 C until <=70 C, cool recovery and unchanged auxiliary battery/skin early throttle thresholds mapped to duty budget. No shared MAX or MIN writes in this profile, no modification of native vendor protection; old modes for other durations retained. The display helper stays outside guest CPU budget for frame delivery; GPU heating, RT tasks, full descendant membership, CFS pacing and transient junction peaks remain unqualified. Group exists only post-stop; reboot destroys it, no foreign group deletion. Host requires exact CFS marker for guarded 180s and labels quota separately from cpufreq; telemetry records generation-pinned cpu.stat and quotas. Independent emergency/fault recovery and deadline unchanged, no absolute no-reboot guarantee. No kernel/XNUHost rebuild needed based on existing native stage admission generation markers, but live compatibility still untested. Added offline source/transition/parity contracts, operator-local integrated CI pending. Explicit optional one-second single-task cool-device quota enforcement probe only, never a guest/stress trial. Do not launch live or rearm until CI, stage and bounded enforcement validation reviewed.

**G2.2 CFS controller local CI, stage and physical enforcement PASS (2026-11-26).** Operator OneiOS 739699e86e4410d545b2e5f3d541d3c6676b307c, OneOS b6da06f5c5d723166a099b2a66af668185482855, evidence out/sm8850/g22-cfs.b3DXZW. All 129 tests in 11 suites PASS (34 guarded-full, 8 thermal75, 5 perf profile, 4 live budget integration, 5 pure hysteresis, 4 CPU bandwidth, 2 parity, 15 full takeover, 17 guarded duration, 31 takeover CLI, 4 stage upgrade); shell syntax PASS. Root/SELinux Enforcing, SM-S948B S948BXXS4BZIG, system_server 9915, protected services present. Boot-pinned 28-sensor manifest (CPU16/GPU11/DDR1), script-only recovery stage upgrade PASS with .rollback/oneos-compat.ZW4J7qkW; all three cap/guard/switch hashes matched local, no Framework stop. Physical private CFS probe: 40/10/40/100% quota readback at 20ms; child membership and inherited membership PASS; cool-start gate accepted; bounded single task at 10% aggregate duty, nr_throttled 0 -> 48, nr_periods 60, throttled_time 188686822 ns, no bursts. Cleanup PASS, parent quota and membership unchanged. G22_CFS_LOCAL_CI=PASS, G22_CFS_STAGE=PASS, G22_CFS_ENFORCEMENT=PASS. No APFS rearm, kernel/runtime rebuild or live guest launch. Physical single-task CPU bandwidth enforcement verified, NOT full guest workload/RT enforcement, thermal stability, GPU heating or frame pacing qualification. Next collect/verify original G2.2 A trace (token be6099ecedbb466eaab5f402b982c200) before any new session; compare A-prime with identical G2.2 native hashes, 0082 OFF, default CPU/frame-task, same workload, new CFS thermal controller as sole intended policy change. Only normal one-shot Data rearm with explicit retired-payload discard, fresh exact policy preflight and separate operator acceptance of 180s deadline/recovery risk. No routine thermal-triggered return at 70/80 C; independent emergency/fault recovery and timed deadline remain. No unbounded live session or hard physical thermal ceiling claim. B with 0082 ON follows a valid A-prime; do not conflate thermal controller effect with own-pmap optimization.

**G2.2 A-prime CFS-only physical startup failed thermal protection (2026-11-26).** Preparation receipt G22_CFS_A_PRIME_READY=PASS at out/sm8850/g22-cfs-A-prime.hrBfow, fresh Data verified and retired payload retention discard, original A archive/report prepared; no rebuild or native artifact change. Actual run out/sm8850/thermal-bounded/20261126T035540Z-f9ae52eb, token d49e472ae7ca443f962e52f6ef82ba5a, boot 63bc38b8-c8ac-4c8f-9452-c739a448f152, generation 63bc38b8-c8ac-4c8f-9452-c739a448f152.3140.300657. Stop uptime 3063 deadline 3243, post-stop MemAvailable 8997060 KiB SwapFree 11995076 KiB, CFS activated, xnuhost PID18972 namespace mnt:[4026536367], display PID19185, Framework takeover and first frame observed, no guest-ready proof or periodic active host snapshots. Cap worker initialized 40% quota; logged sample23 CPU58800 GPU40900 DDR40500 mC, state COOL hard_latch=0, auxiliary_limit=100. No cap fault file; guard recorded soft_temperature_abort crossed=cpu cpu_mC=95700 cpu_zone=cpu-1-1-1@27 GPU46300 DDR48200 mC, battery296 LRP323 boardAP362 dC. Exact return receipt who=framework-deadline reason=independent thermal monitor/cap missing, stale, or exceeded emergency threshold, epoch1795665454; guard fault establishes emergency-temperature recovery rather than successful 180s completion. Outer host exit4; healthy unassisted recovery not certified. One-shot Data consumed with exact boot/token. Do not clear or reuse consumed marker; do not rearm or rerun yet. Last logged 58.8 C is a transition sample, not proof of the immediately preceding temperature/time. Actual CFS quota enforcement in a one-second single-task probe did not establish control of peak power or short high-frequency guest bursts. Thermal policy FAIL; no new FPS result.

**Hybrid protective controller candidate following A-prime fault.** Pin OneOS f22a21908c291697678db00e56c3fa5b5fce21ab. Guarded 180s now requires a distinct hybrid-v1-180s marker (HYBRID_FREQ40_CFS_V1_TARGET_45_70_HARD_80_RELEASE_70), refusing prior CFS-only stages before launch. Reuse strict MAX-first 40% hardware frequency ceiling, applied only after verified Framework down and before guest CPU-group creation and OK cap heartbeat; never raise an observed tighter maximum; revalidate throughout. This is a shared sysfs request, not independent freq_qos ownership. Prior A at 40% frequency sampled CPU 44–49.4 C; this motivates conservative cap, not a guarantee. Keep guest CFS 40% initial, reversible 10–100% budget, 70/80 latch and auxiliary limits, separate unchanged 90 C emergency and other fault/deadline safeguards. Both root loops request 250ms sleep (actual sensor scan, validation and scheduling add latency); every hybrid thermal scan logged with fractional uptime, existing heartbeat structure retained. Cool budget increase gated by five whole-second monotonic tick advances after previous increase/hot/limit transition; faster samples cannot accelerate recovery. New offline fixture for fast/repeated/backward samples, cap failure and initial protective ceiling order; host preflight rejects obsolete CFS-only markers and reports frequency request separately. Full integrated CI and physical behavior NOT yet verified; no launch, stage, rearm or further kernel/runtime build authorized by this source-only change. The fixed frequency ceiling may limit performance; independent native QoS or calibrated power controls are needed before allowing safe frequency recovery. Preserve A and failed A-prime evidence; next validation is offline plus read-only failure collection, not a live stress run.

**G2.2 Hybrid local CI and script-only stage receipt (2026-11-26).** Exact OneiOS 01b879a5da90c42b4ed3bfa1ee3e0dc882345639, OneOS f22a21908c291697678db00e56c3fa5b5fce21ab. Operator local CI out/sm8850/g22-hybrid-ci.YNXqjv: all eleven named suites PASS (guarded full, thermal75, perf profile, CPU budget integration, hysteresis, CPU bandwidth, parity, full takeover, guarded duration, takeover, stage upgrade). Device receipt out/sm8850/g22-hybrid-stage.jbwWoF: Android/root/boot/SELinux admission PASS; failed CFS-only session archive preserved at failed-A-prime/device-logs.tar with exact token d49e472ae7ca443f962e52f6ef82ba5a and 95.7 C CPU guard fault from boot 63bc38b8-c8ac-4c8f-9452-c739a448f152. Hybrid stage PASS, local/device SHA-256 equality for switch, cap and guard scripts, no Framework stop. Read-only markers SM8850_CPU_THROTTLE_POLICY=HYBRID_FREQ40_CFS_V1_TARGET_45_70_HARD_80_RELEASE_70, P0_CPU_CAP=READ_ONLY_HYBRID_AVAILABLE_NOT_CERTIFIED and P0_THERMAL_GUARD=READ_ONLY_CURRENT_BOOT_READY_NOT_CERTIFIED. No APFS rearm, kernel/runtime rebuild or live takeover in this step. Preserve the archived failure; prepare a fresh one-shot clone only under normal explicit discard-retired-data retention consent, confirm exact native pins and Hybrid read-only admission, and keep 0082 OFF. A future bounded Hybrid validation is separate from preparation and requires operator acceptance of its recovery/deadline behavior. No safety qualification or claim that Hybrid prevents an 80 C excursion; previous CFS-only thermal failure means performance optimization and any unbounded launch remain blocked pending controlled validation.

**G2.2 hybrid A′ physical baseline (2026-11-26).** OneiOS 9db14f6, OneOS f22a219, session fbe958081c064a169bcf3dc12e4c601d. Operator evidence: out/sm8850/g22-hybrid-A-prime-analysis.EEzYen and thermal-bounded/20261126T055318Z-27aa5c39. Guarded 180s, default CPU placement, frame-task, 0082 default OFF. First frame/guest-ready/SpringBoard/backboardd and KGSL log markers observed. Return record: framework-deadline reached at uptime 7220 (deadline 7219), boot changed, no thermal fault record. Peak sampled guard CPU 53.6 C, final 49.8 C at 176.82s, fixed frequency ceiling 40%, CFS budget recovered to 100%. Peak post rate 22.04, median estimated active cadence 19.29, 1022/1116 active gaps over 60 Hz budget, max touch-to-frame 495.4ms; no 60 FPS or thermal safety certification. B′ is a guarded 180s opt-in `--own-presence on` using positional root-session token and session-local metadata; preserve all other parameters and compare same-session 0082 delta windows. Kernel marker found on device; no kernel or native runtime rebuild requested. Local regression and B′ physical acceptance pending. Reboot-return is sufficient for this benchmark; independent watchdog qualification/in-place handback are outside its scope. Do not change thermal or recovery policy in this comparison.

**G2.2b1 hybrid B′ and A′/B′ decision (2026-11-26).** Operator OneiOS 53b08dcfbb659e82bc9e653972d1f238a87135ea, OneOS 1a54c95a321f2bfac06e9b8696950822a134836b; 76 offline regression tests and telemetry self-test passed on WSL. Rollback-backed switcher upgrade, fresh APFS clone and explicit retired-payload discard passed; pre/post kernel, GPU addon, trustcache, native runtime, thermal-worker and return-script hashes matched. Guarded 180s/default CPU/frame-task/fixed 40% MAX plus reversible CFS; own-presence ON requested, root preflight and session-local metadata matched. Session ffd8c850916146bbaa28866b7496d533, boot cd060d11-edb4-45f9-8430-0fe10f5af0b5, exact-session evidence out/sm8850/g22-hybrid-ab-analysis.LsSqnL (archive SHA-256 verified). Five valid 0082 delta windows: 1,697,677 requests, 21 skipped, 1,697,656 issued; skip rate 0.001237%, not whole-session or correctness proof. A′ default OFF emitted no 0082 counters, not zero requests. A′ vs B′: peak post rate 22.04 vs 25.63, median estimated active cadence 19.29 vs 13.60, active gaps exceeding 60Hz budget 91.58% vs 89.42%, peak traps/s 48,264 vs 49,635, frame-copy max 40.80 vs 17.55ms, touch-to-frame max 495.4 vs 175.3ms, no subsequent frame in 5/9 vs 10/16 touch summaries. Workloads differ; no causal speedup or physical FPS claim. Both reached guest markers/KGSL and deadline-triggered reboot (B′ at 2451 vs deadline 2450); no thermal fault record. Periodic guard CPU samples peaked at 53.6 C in both, but B′ initial cap log recorded 59.6 C; obtain full same-boot guard traces for true observed sample extrema. CFS reached 100%, no claim of exhaustive thermal safety qualification. **Decision: 0082 opt-in runtime exercised, useful performance improvement not demonstrated; retain default OFF and close this candidate investigation, not all G2.2/P0.** Existing F1 comparison does not justify repeating prime-first by default. Next priority: audit ownership of frequency control and full guard sampling before any performance-ceiling redesign. Current shared scaling_max_freq actuator is deliberately downward-only; do not restore or raise another actor's limit on temperature alone. Preserve thermal and emergency protections, and distinguish any future independently owned frequency QoS request from shared sysfs writes. No device operation or thermal policy change in this evidence update.

**G23 stock frequency actuator audit and operator safety scope (2026-11-26).** Same-session full guard traces: A′ 630 samples, CPU median 46.7 C, peak 68.9 C at scan uptime 7014.81–7014.84 (framework stop 7039); B′ 615 samples, CPU median 46.3 C, peak 79.5 C at 2251.25–2251.27 (stop 2270). Both maxima precede verified framework stop; these are not post-stop guest peaks. No sampled CPU >=80 C in either trace. Segmented archive analysis deferred because operator switched from WSL back to CachyOS native and original local archives were not copied. Stock SM-S948B/S948BXXS4BZIG Android release 6.12.69-android16-6-pb4d3caf-abogkiS948BXXS4BZIG-4k, SCMI/WALT policy0 CPUs0–5 max3628800 kHz and policy6 CPUs6–7 max4742400 kHz. Read-only stock module imports and five CRCs confirmed against GKI build 16411491 vmlinux.symvers (5/5, 339 overlapping import observations across six modules with no mismatch); does not qualify an external module ABI or signing. Operator explicitly rejected the custom kernel-module direction: no custom Android kernel module, kernel flash, force-load, signature bypass, SELinux relaxation or thermal protection bypass. No such device operation was performed. Root read-only stock audit confirmed /sys/kernel/msm_performance/parameters/cpu_max_freq, eight values 2147483647 at observation, and cpu_min_freq all zero; vendor perf2 AIDL service and Qualcomm/Samsung thermal/power services present. commonresourceconfigs.xml cpufreq minor 0x1 names /sys/module/msm_performance/parameters/cpu_max_freq (firmware also exposes /sys/kernel path); not proof of isolated per-client MAX vote or arbitration/expiry correctness. Do not write shared msm_performance or Samsung cpufreq_limit nodes, invent PerfLock opcodes, or stop vendor protections. Close custom-module path and defer PerfLock without more device probes. Retain fixed 40% strict downward-only ceiling plus existing reversible CFS and emergency/return policy. Alternative without Android kernel changes: a future explicitly selected bounded per-session ceiling, only downward writes, separate validation of startup/thermal response before raising admitted ceiling; no policy change now. Prioritize userspace overhead: compare existing frame-only instrumentation against matched frame-task A′ baseline with 0082 OFF, default placement, identical staged artifacts and guard policy; assess frame cadence, traps and input response before further map/GPU changes. This is a proposed benchmark, not authorization to run it. Native local CI first, no new Android kernel build or device mutation in this docs update.

**G23 frame-only idle physical receipt (2026-11-26).** Operator-local CachyOS preparation passed 87 regression tests plus telemetry self-test at OneiOS d374a9120d7560fed762d68f1da1e46b2ca0a001 / OneOS 1a54c95a321f2bfac06e9b8696950822a134836b; resumed on WSL, verified both G22 A′/B′ archives and all four staged script hashes. Exact guest KC fd213c272f7053cd54146351dd617b2e1707e2a0efa4dda0aaa096b091c579f5 and XNUHost 8ada56b0e0396d19d7e167082c13247cb90888a18d67db224c7f45a5521af13f unchanged before rearm. Fresh Data and unique-chip-id clone verified, retired payloads pruned with receipts preserved (2 files, 2294865920 allocated-byte estimate); guarded frame-only preflight PASS. Initial host launch lacked ONEIOS_SM8850_FULL_BRIDGES_180S opt-in and was blocked before Framework stop/Data consumption; corrected explicit opt-in, no second rearm. Live token 422f1c974069428fbadb81ba4a23a22a, boot fffcd476-358d-4511-b775-1a0a1207fd25, stop 20716/deadline 20896, first-frame/guest-ready/SpringBoard/backboardd/KGSL/full-bridges log markers observed. Fixed 40% ceiling 1440000/1862400 kHz, CFS 65% at T16.91 then 100% by T33.61, sampled nr_throttled 1 thereafter, periodic sampled CPU max 47.1 C and final 44.4 C at T176.5 (not full guard extrema). Return record who=framework-deadline at 20897; new boot 7a5674ec-6569-431e-afa8-ba724fbd29e9, postboot system_server 9751, SELinux Enforcing. Outer host exit4 with bounded local wait termination; not a guest crash or independent recovery qualification. WSL evidence thermal-bounded/20261126T122317Z-1727e702, takeover/run-y_wcn9kt, out/sm8850/g23-frame-analysis.vmukCn/device-logs.tar (SHA-256 verified), G23-perf.json and G23-frame-stall.json. Runtime ONEIOS_PERF_PROFILE=frame, zero perf-task lines, own-presence OFF. Operator explicitly confirms no interaction throughout the trial: zero touch summaries, touch latency unavailable. Peak post 21.84, median estimated active cadence 6.75, 493/513 active gaps over 60Hz budget (96.10%), 503/513 over 120Hz budget (98.05%), max gap 239.864 ms; 35/35 transport windows, display lock max 38.04 ms, copy max 10.20 ms, unlock/post max 10.72 ms, GPU fence max 15.94 ms, peak task traps/s 42123, 3 host_statistics64 ABI warnings. Five frame-stall candidates possibly idle, not proven stalls; no physical FPS result. A′ and B′ had 9/16 touch summaries; G23 is a valid idle boot/trace observation, not a matched interactive A/B. Lower sampled temperature and several lower maxima cannot be attributed causally to disabling task profiling. **Decision:** retain G23 idle reference and frame-only as a lower-instrumentation option for future interactive tests, do not claim a speedup/regression or change global defaults based on G23. No repeat idle trial needed. Continue offline analysis of XNUHost hot paths from existing trace evidence; future causal profiler comparison would require identical scripted or operator-repeated interaction schedules, fresh equivalent guest clones and comparable starting conditions. Keep current 40% hybrid ceiling, independent thermal/emergency protections, timed recovery and 0082 default OFF. No Android kernel/module changes, new live launch or rearm in this receipt; full thermal segmentation, interactive and physical FPS acceptance remain open.


**G23.1 automated interaction candidate (2026-11-26).** Add explicit `--interaction-profile swipe-60s` (default off) through telemetry, full wrapper, host launch and OneOS root-owned session metadata; guarded 180s performance branch and frame/frame-task only. Staged binary capability required before launch; exact requested/preflight acknowledgement and detached positional token, no arbitrary device file input. XNUHost built-in input script waits for current in-memory guest readiness (content or kernel ready call, not black timeout) and VirtIO driver, then 10s warm-up; 30 deterministic center-region left/right/up/down gestures, 320ms movement plus 1680ms rest, real advertised native touchscreen axes. Bounded 65s actual execution, minimum 10s deadline reserve, skips late readiness and aborts incomplete sequence, no key injection or app/icon coordinates; drains native touch in automation mode to avoid competing touch slots, separate side-key and recovery readers unchanged. Records start/begin/end/complete/skip/abort, monotonic timestamps and root deadline; offline analyzer requires complete ordered 30-gesture receipt, does NOT prove screen unlock, app scrolling or physical FPS. Keep 40% hybrid CFS, guard, emergency return, exact 180s deadline, GPU3D and 0082 default OFF. Source candidate only; WSL offline regression and full KGSL Android runtime build/rollback-backed stage upgrade pending. No Android kernel/module/guest kernel rebuild, phone mutation, rearm or live launch in this commit. App launch/mixed profile deferred until reliable guest UI state evidence exists.


### G23.1 prime-first physical receipt and first-frame input gate fix (2026-11-26)

Historical **retired** hybrid frequency-40/CFS policy, not a new admission.
Operator confirms zero physical interaction. Exact launch
`ee7c626acb814d92901a8672dc8169ef`, boot
`51ca8a7b-7fe0-4075-be5f-6a9029b8d392`; archive SHA verified locally at
`out/sm8850/g231-prime-first-analysis.DEJJHg`. Runtime PRIME_FIRST_ACTIVE,
axes 0..4095, ready markers/full bridges/KGSL observed. Stop 2309, deadline
2489, actual return record framework-deadline at 2490, new Android boot
59c28c61-a29a-4bc6-bdbb-4f1315976212, system_server 9737. This is the
historical timer return, not thermal-return authorization or independent
recovery qualification. Periodic CPU snapshots peak 54.4 C, final 44.8 C;
not whole-session extrema. CFS 100% by T43.89, nr_throttled 1. No new
thermal policy validation.

Automation **FAIL**: prepared, started at mono/boot 2365801, deadline
2489000, immediately aborted completed=0 backlog=1. Receipt incomplete,
0 begins/ends; no touch latency measurement or evidence of UI response.
Treat as idle reference, not interactive prime-first vs default A/B.
35 display windows, peak posts/s 20.38, median estimated active cadence
6.58, 500/522 gaps over 60Hz budget (95.785%), 511/522 over 120Hz (97.893%),
max 244.346 ms. Lock/copy/unlock maxima 35.8/31.72/4.02 ms; render-fence
max 13.285 ms, other-fence max 45.538 ms; peak host traps 63286/s, 15 ABI
warnings. No task-affinity sample, 156 role samples; profile marker does
not prove physical core residency. No causal performance or physical FPS
claim.

Source root cause: reserved swipe expands first to ABS_MT_SLOT, then
ABS_MT_TRACKING_ID; VirtIO queues the slot until SYN_REPORT. Old gate
tested zero backlog at the second event and rejected its own prefix.
Move empty-queue check before the slot event; preserve <=128 bound,
release on partial abort, existing timing and completion contracts.
Add native mock VirtIO replay of all 30 gestures, including observed
backlog=1 after slot and refusal of actual pending data at next start.
Local native CI completed on WSL (operator log, 2026-11-26) at
OneiOS `143361dbc1c3f3e332df92d57cadc798e2080377`, pinned OneOS
`42478a784a0e26df88951066a1f36d3ab0ae1502`.
`make -C runtime/xnuhost -j8 test` completed in 26.160s, XNUHost
19,742 checks / 0 failed, SM8850 native admission 22 / 0, GPU policy
166 / 0, task profile 67 / 0, GPU fence 29 / 0, stub copy 11,051 / 0,
display mode and image-set suites passed. Android ARM64 runtime built;
QEMU synthetic test kernel reported all passed, including task profiler.
Real udmabuf imports/leak scenarios and unsupported QEMU process_vm cases
skipped, not certified. The new mock VirtIO gesture replay is in the
passing XNUHost suite; no physical gesture replay has been performed.
The new Python admission/model regressions passed in the operator's WSL
at OneiOS `174fc79f31cd461f223877faee98ba82bda3a23c` and pinned OneOS
`42478a784a0e26df88951066a1f36d3ab0ae1502`: 9 adaptive model + 35 takeover + 16 full takeover +
21 guarded duration + 2 interaction = 83/83, DEVICE_ACCESS=NONE.
No repeat needed for documentation-only changes. The actual adaptive
frequency actuator and bounded non-reboot quiesce remain unimplemented.
Existing per-session CFS and v2 guest cgroup are reuse candidates;
XNUHost per-task/vCPU utilization clamps are not independent hardware
frequency votes. See [OneOS adaptive thermal design](../app/docs/SM8850_ADAPTIVE_THERMAL.md).
No new device test or recovery audit is requested.
No stage, rearm or live device operation is authorized by this receipt.
Thermal redesign admission block remains intact.


### G24.1 native owned-group actuator (source candidate; 2026-11-26)

OneOS `7fa70488c1681679386d80c6cc6359fd6d5b5f6a` implements native private v1 CPU quota
and v2 freezer primitives (`switcher/native/sm8850_owned_groups.{c,h}`).
Use creator-pinned token/group identities and FD-scoped I/O; no shared
frequency writes. Bounded frozen-event polling, fault latch, explicit
verified thaw, no automatic thaw on close; fixture regressions cover
quota 10–100%, drift/replaced groups, nested group refusal, freeze and
thaw ACK/timeout. The production code is not a fixture-only model, but
is not integrated into the phone lifecycle and cannot prove GPU/IO drain.
Local compile and new fixture tests pending; no device access or
existing CI repeat. See [adaptive design](../app/docs/SM8850_ADAPTIVE_THERMAL.md).
Independent reversible frequency provider, session ownership/membership,
sensor supervisor and GPU quiescence integration remain blockers.
The existing legacy admission block remains intact. No kernel/module,
watchdog qualification or physical benchmark is requested.


### G24.1 local receipt and G24.2 native controller (2026-11-26)

G24.1 local WSL CI at OneiOS `e4db1508b0534c8af2db92a9c8dcba675011b291`, OneOS
`7fa70488c1681679386d80c6cc6359fd6d5b5f6a`: production host compile
PASS, owned-group fixture 284 checks PASS, Android ARM64 object compile
PASS, DEVICE_ACCESS=NONE; evidence `/tmp/oneios-g241.SIUBOr`.

G24.2 pins OneOS `25ae4473711265d13a5bbde5df1f271ddf7708ae`: native policy and controller
using the existing owned-group actuator. Exact session and sample freshness
checks; reductions before increases; severe heat requests GPU gate/drain
before CPU freeze; resume at minimum budgets after verified thaw with GPU
gate still closed; persistent fault latch, no thermal-triggered reboot.
Read-only group verification was added, with a new fixture. Native
controller fixture mocks the required providers; deterministic C/Python
parity exercises 8,640 samples. Both new suites, updated owned-group
fixture, host and Android compilation are pending local validation.

This is not a deployable phone controller. Independently owned frequency
provider, GPU/IO gate and drain provider, session creator/membership and
independent thermal reader/runner integration remain unimplemented or
unqualified. Legacy admission remains blocked. No stage, rearm, live run,
watchdog/recovery audit or kernel modification is authorized.


### G24.2 local receipt and G24.3 GPU ingress gate (2026-11-26)

G24.2 local WSL at OneiOS `122c88728c2cd0bc07c5bef06422750b13a25a6b`, OneOS
`25ae4473711265d13a5bbde5df1f271ddf7708ae`: host and Android ARM64
production object compiles PASS, owned-group actuator 330 checks PASS,
native thermal controller 239 checks PASS, C/Python policy parity
8,640 samples PASS; DEVICE_ACCESS=NONE; evidence
`/tmp/oneios-g242.ijjF7A`. OneOS receipt pinned at `2967fda7d727babbb52b8b8675543cc326e97890`.

G24.3 implements the actual XNUHost VirtIO GPU ingress gate in
`virtio_gpu.c`/`gpu3d.h`. Close returns a unique ticket, stops taking new
avail chains at the next chain boundary, and lets already dequeued slow
work finish. Status distinguishes host lanes idle, pending VirtIO fences,
retiring callbacks and reset invalidation. A reset during a closed gate
invalidates its ticket; stale tickets and unconfirmed host drain refuse
resume. Commands are not discarded or given synthetic replies. This is a
nonblocking try-lock API for a later independent deadline owner.
Regression uses the existing fake backend, pending fence, queued
submission, exact-once resume, stale ticket and reset invalidation.
Local native regression and Android compile pending.

Do NOT call host_drained a hardware idle proof. The pinned Droid-VM
virglrenderer has KGSL work without guest VirtIO fences, fence callbacks
which may retire on errors, and an autonomous GPU clock-hold keepalive
thread (patches 0005/0006/0008). A complete backend provider must stop
autonomous submissions, account for each owned KGSL draw context and its
last accepted timestamp (including destruction/fault cases), verify
retirement independently, and handle IO/lifecycle and resume. No new
vendor/kernel writes or raw frequency vote guessed. No live caller has
been added; the thermal admission block stays intact. No phone access,
stage, rearm, watchdog audit or recovery test follows from this commit.


### G24.3 receipt / G24.4 KGSL accepted timestamp ledger (2026-11-26)

Local G24.3 OneiOS `cce950cd256db9cf7e49c3e3680a4301e6983719`, pinned OneOS
`2967fda7d727babbb52b8b8675543cc326e97890`: native regression
19,759 checks / zero failures, Android ARM64 static build PASS,
SHA256 `bb4766aded8aafe520f7894618ee106a9d470c2fe342389e315c896de6b0c68d`,
evidence `/tmp/oneios-g243-resume.j9Fh8z`. DEVICE_ACCESS=NONE.
Earlier two failures were relative-path fixtures run from the wrong cwd,
not gate failures. Real udmabuf import skipped.

G24.4 patch 0010 adds a process-local accepted-timestamp ledger at BOTH
GPU_COMMAND call sites (guest and autonomous keepalive) in the pinned
renderer. A closed backend ticket suppresses keepalive and rejects any
unexpected guest submit. Polls owned fd/context timestamps using one
WAITTIMESTAMP_CTXTID timeout=0 ioctl, up to 16 timestamps per call.
Ambiguous submit errors, non-forward/zero timestamps, observed reset,
lost identity, terminal wait failures latch unconfirmed state. No
automatic thaw or reboot. A verified ticket does not prove global GPU
idle, successful rendering, or CPU/IO quiescence. Context destruction
checks pending timestamps before identity loss, adding a non-retrying
poll on normal teardown; ledger bookkeeping adds open-path overhead
which is not yet measured. No new frequency votes. Existing firmware
thermal protections stay intact.

All 11 earlier patches and the new patch were reconstructed against
virglrenderer pin `7e17c8e814e963912fc1e4e737137a31b5efa027` with exact
hunk context matching; local actual patch application, sanitizer ledger
test and KGSL Android link are still pending. No admitted live caller:
host+backend ticket coordination, independent supervisor, safe resume
and frequency provider remain blockers. No phone access or new
kernel/recovery audit requested.


G24.4 intermediate local CI at `40c3472f4986010285726027472ebc57ffef4bb3`: KGSL ledger regression
159 checks PASS; Android build stopped during GNU patch application,
1/14 hunks rejected with -F0. The hunk at old line 1887 has zero trailing
context; the next hunk starts immediately at old line 1892. Exact-text
matching alone was insufficient to model GNU patch's boundary matching.
Reproduced failure using actual GNU patch -F0 on a host fixture containing
the two exact original hunk bodies, and confirmed the merged 14-old /
15-new-line hunk succeeds. Only hunk boundaries/line counts changed;
the full patch's non-hunk-header lines are byte-identical. No C source or
ledger test changes. Full patch-chain application and Android link still
require the operator's local build. No device access or new kernel work.


### G24.4 local acceptance / G24.5 combined GPU quiesce (2026-11-26)

Operator WSL G24.4 ledger at 40c3472: 159 checks PASS. At
OneiOS `5c4dc620b90e5ddb7dbbd2a3baed992526f08d9f` after the hunk-only fix, the full KGSL Android
patch/build/link succeeded, all three drain symbols found, ARM64 static
Android 30 / NDK r28c. XNUHost SHA256
`a8d9d01a8d448f95e00539261b3ed11ce13f8328b7341e6a3a95ba28c50e9a93`;
evidence `/tmp/oneios-g244-resume.aGrjFc`; DEVICE_ACCESS=NONE.

G24.5 connects the actual KGSL renderer callbacks to the VirtIO device
and adds combined close/poll/resume. One host ticket owns an independent
private backend ticket. Host ingress parks first; both host lanes must
be idle before backend close, but pending host fences must NOT delay the
backend close. Poll checks both receipts and rechecks host reset and
callback state after backend work. Stale callers cannot mutate a new
ticket. Raw host resume cannot bypass combined admission. Resume
requires a verified combined ticket and opens the backend then host
under device lock -> fence bookkeeping lock (reset uses the same order);
the backend resume is a try-lock-only state change with no ioctl or
callback. Terminal errors latch the gate closed; no automatic reopen.
Tests drive real host lanes with mock KGSL responses: missing provider,
pending fence, backend retry, queued work preserved, exact-once resume,
backend terminal error, reset inside polling, stale tickets and raw
resume refusal. Local sanitizer native CI / Android compile/link pending.

The API is in-process, not a deployed root supervisor. A combined receipt
attests host work + recorded KGSL timestamps only, not global physical
GPU idle, IO drain, or safe temperature. Poll syscalls may block despite
timeout=0. There is no independent post-freeze verification or external
session-bound control channel yet; no live admission. The remaining
integration must provide independent deadline/ownership and fault
handling, display/IO lifecycle, CPU freeze/resume, and an independently
owned adaptive frequency provider. No fixed cap 40%, temperature-triggered
return/reboot, Android kernel changes or new physical recovery tests.


### G24.5 acceptance / G24.6 frequency-provider evidence inventory

Operator WSL at OneiOS `4b12df8e7f2617238087f9a3adbb322a50211b29`, pinned OneOS
`2967fda7d727babbb52b8b8675543cc326e97890`: 19,824 native checks, 0 failed;
Android ARM64 static link and three combined quiesce symbols PASS;
SHA256 `c36826976b9763d5874412fb89a7e3fb99d23095f58b28180f69105699a7e2e4`,
evidence `/tmp/oneios-g245.SNrfRT`, DEVICE_ACCESS=NONE. Prior G24.1–G24.4
offline acceptance unchanged. No hardware certification.

G24.6 adds a focused read-only firmware inventory, not another simulated
frequency provider. `scripts/phone/sm8850-frequency-inventory.py` checks
SM-S948B/S948BXXS4BZIG, normal boot and absent xnuhost, then reads CPU
policy, candidate shared nodes, service names/states, resource config
paths/mappings and static candidate library exports. Vendor ELF bytes
are read into a temporary host directory for readelf only and deleted
on exit. There is no vendor function invocation, vote write, device file
creation, mount, service stop, SELinux change, push, or benchmark. Scope
is bounded; missing/filtered/truncated evidence is not absence proof.
The script is not yet run on the exact firmware. Its completion is not
provider qualification. No guessed numeric perf-lock ID or test vote.

Need exact max-frequency resource semantics, independent client
ownership/readback, aggregation and release/expiry proof and service
availability during takeover. Linux scaling_max_freq readback alone
cannot show request ownership. No adaptive frequency implementation
is enabled. Independent supervisor and display/IO lifecycle remain
unfinished; no live admission or kernel/recovery audit.


G24.6 operator inventory completed on exact SM-S948B/S948BXXS4BZIG:
`/tmp/oneios-g246-frequency.nIpqAc.txt`, DEVICE_WRITES=NONE,
FREQUENCY_PROVIDER=NOT_QUALIFIED. Both Qualcomm PerfLock client variants
export acquire/release; native perf2 HAL is running. CPU max resource
major 0x2/minor 0x1 target override points at
`/sys/kernel/msm_performance/parameters/cpu_max_freq`. The initial
probe missed that path; corrected inventory node list. Policy0 max
3628800 kHz; policy6 advertises 4742400 kHz but available OPP list ends
4396800 kHz. Do not guess packed IDs/cluster selectors or round to an
unlisted OPP. See pinned OneOS 2332c069eb207de9668fdc3795ef8056db66c03a for detailed receipt.
Only a narrow follow-up for the real nodes, complete relevant XML
resource blocks, SoC identity, native service membership and optional
default dump is needed; do not repeat broad inventory. No write or
actual vendor API invocation, kernel changes, stage/rearm or live
admission. Provider aggregation, ownership and lifetime still unproved.


G24.6 targeted follow-up receipt (2026-11-27 ICT):
`/tmp/oneios-g246-perflock.sqOJGh.txt`, SM8850 SoC ID 660/canoe,
real max/min nodes under /sys/kernel/msm_performance/parameters,
sampled max all INT_MAX and min all zero. Exact packed MAX resource IDs
0x40804000 (big) and 0x40804200 (prime) in firmware launch/animation
configs; MIN resource IDs 0x40800000/0x40800200 are not to be submitted.
Native HAL and service belong to /system/uid_* not /apps/uid_* in the
sampled stock boot. Default perf2 dump empty; no ownership/readback
proof, no runtime vote tested.

Pin OneOS 0e04adb2a5ab1565e3146d185a5e51f180b0074a for the full receipt. The next step is targeted static
analysis of the exact client/server ELF and supporting libraries, rather
than another inventory or guessed perflock request.
`scripts/phone/sm8850-perflock-static-evidence.py` reads seven fixed
firmware paths into a host ZIP with size, ELF architecture and SHA256
checks. No arbitrary path selection, no serial in archive, no vendor
execution, device-side file creation or control write. Archive is for
private analysis only; never commit the proprietary binaries. The
collector is unrun; it does not qualify the provider. No live admission
change, device staging or thermal-triggered reboot.


### G24.7 static analysis result (2026-11-27 ICT)

Received perflock-static.zip, all seven exact firmware ELF images
verified against manifest. Host readelf/LLVM objdump and APS2 relocation
inspection identified CPU MAX queue index 9, lower_is_better comparator,
ordinary lower-wins application, normal MHz -> kHz conversion and
upward OPP selection. Server supports request timers and release
infrastructure. Positive acquire handle is asynchronous queue submission,
not apply ACK. Client perf_sync_request has an active-table diagnostic
but server gates it on ro.debuggable or vendor.debug.trace.perf.level.
The earlier empty default binder dump did not establish those values.
See pinned OneOS `19f8a93118e5713b06aa1d79298c3fa0d807ba35` for binary hashes and exact ELF
addresses. No vendor binary committed or executed, no phone access/write.

G24.7 static analysis COMPLETE; frequency provider NOT QUALIFIED.
Do not equate effective cpufreq readback or a returned handle with
independent request ownership. Read the two stock diagnostic property
values only; no enabling trace/debug, shared writes, or speculative
resource calls. If no existing diagnostic is accessible, stop PerfLock
qualification at that blocker; continue independent supervisor/IO
development offline without silently replacing the user's adaptive
frequency-ceiling requirement with duty or utilization. No live
admission, benchmark, stage/rearm or thermal-triggered reboot.


### G24.7 diagnostic result / G24.8 block I/O ingress gate (2026-11-27)

Operator: ro.debuggable=0, vendor.debug.trace.perf.level empty,
ro.build.type=user. Stock diagnostic readback is not available under the
statically identified PerfLock gate. PERFLOCK_QUALIFICATION=
BLOCKED_NO_OWNED_READBACK. No property change or vendor call. OneOS
`fc7754d1e095d775c082d2c2261583380abc5e27` records the disposition. The frequency provider remains
unqualified; no substitution with duty/utilization, no live admission.

G24.8 implements the actual synchronous VirtIO block transport gate.
Close uses the transport lock to park at a chain boundary (handler and
used publication are synchronous under that lock). While closed, kicks
are retained without popping avail chains, and the real block callback
flushes accepted writes with xh_blk_flush/fdatasync. Poll releases the
transport lock across the potentially blocking flush and rechecks the
ticket; a flush error or queue/reset mutation latches failure. Resume
requires a verified ticket and signals a lazy, process-lifetime worker
which replays saved kicks without making the control caller do I/O.
A regular kick may consume pending chains first; queue mutation cancels
saved old-generation notifications. No worker is started on normal
never-closed sessions. Only synchronous single-queue block devices with
the explicit flush callback are supported. No automatic thaw/reopen.

Regression covers real file-backed Data writes, retained kicks,
no premature or stale resume, exact-once replay without a new kick,
reset invalidation, injected flush failure and reset during flush.
Local native regression and Android ARM64 link pending. No phone access.
This receipt is host block I/O only, not APFS unmount/guest-cache
durability or all device/bridge/display quiescence. fdatasync and thread
creation have no guaranteed wall-clock bound. The future independent
supervisor must own deadline, membership, lifecycle, and whole-session
coordination; it must not call these APIs from a device handler.
No new live caller, no thermal-triggered return or reboot, no kernel
change. Display/bridge IO and actual supervisor integration remain.


### G24.8 receipt / G24.9 SHM display helper barrier (2026-11-27)

Operator local G24.8 OneiOS `b0e5f3c60a6c75c612ff7f2ae317f2d336c8baa5`, pinned OneOS
`fc7754d1e095d775c082d2c2261583380abc5e27`: 19,858 native checks,
0 failed, Android ARM64 build and three block quiesce symbols PASS.
Runtime SHA256 `b2e343abe3c1e460eb3ed34aaab92c1fb36f4308265fd64360c8a11afb87eba8`;
evidence `/tmp/oneios-g248.Dudezu`, DEVICE_ACCESS=NONE.
Real udmabuf import skipped as in earlier offline runs.

G24.9 adds ticketed Q/A (park/ACK) and R/B (resume/ACK) records on
the existing SHM display SOCK_SEQPACKET connection. No physical panel
fence claim. The caller must first park every producer of shadow pixels
(including GPU and boot-console writers); a late notification latches
fault. The helper parses a barrier in FIFO order but emits its ACK only
at a native-window boundary outside lock/copy/unlockAndPost. A barrier
received by post-lock drain completes the outstanding buffer attempt
before ACK. Park discards unposted damage/trace metadata; explicit
resume schedules a full redraw, not a new guest-generated frame.
No new producer posts while helper parked. An older helper cannot ACK
and must time out; it is not treated as quiesced. Host wire operations
are nonblocking and ticket-checked; new helper connections are refused
while closed and previously replaced connections cannot qualify.
Both sides must be updated together for barrier use; regular frame
protocol remains backward compatible when gate not used.

Local tests pending: helper parser/ACK and real host-to-helper socket
with simulated native-window boundaries, stale ACK/refusal, full
redraw, late producer and Android XNUHost + JNI link. No real
ANativeWindow, SurfaceFlinger, HWC, panel fence, hardware power or
physical quiesce is tested. Independent helper identity/lifetime,
remaining bridge and input producers, whole-session coordination,
freeze/thaw and independent supervisor still missing. No live caller
or admission change. Frequency provider remains blocked at stock
owned-readback requirement. No device access, thermal-triggered
return/reboot, Android kernel change or shared frequency write.

### G24.9 operator receipt / G25.0 offline unified coordinator (2026-11-27 ICT)

Operator G24.9 OneiOS 2a6386731030c1f2dcd469b4eb08c614c6fb337e:
display helper 276/276, frame_perf 55/55, six socket scenarios PASS,
Android XNUHost and display JNI builds and four barrier symbols PASS.
Evidence /tmp/oneios-g249.thFpQ4, DEVICE_ACCESS=NONE.
XNUHost SHA256 1fe50a76f97fba84c10e37d4fd572909e0ccf9f942d0e381b42fad5d87343155;
display JNI SHA256 707f8d91b220bd0834acc5f8b454f0edb849f9b84cda42d933c5b64003f2caba.

G25.0 implements the offline worker-side coordinator and actual runtime
dispatch for combined GPU, every configured block transport (up to six),
and SHM display. Membership rejects null, duplicate and count-mismatched
block pointers; an external owner must still prove exact membership and
lifetime. One owner/cycle and absolute CLOCK_BOOTTIME deadline cover
close, drain, hold and explicit resume. First close GPU and block ingress,
drain them, then park the display helper and refresh all receipts.
A parked receipt is sequential, not atomic global idle. Resume requires
fresh validation and external authorization; reopen display first, blocks
next and GPU last. Record attempted and successful reopen separately;
latch faults without automatic reopen, rollback or thaw. Stale caller
tickets cannot mutate the current cycle.

Standalone Clang ASan/UBSan test with minimal ABI header shims and
stand-in providers: 701 checks, 0 failed. Includes six-block dispatch,
retry, invalid membership, stale cycle, expired deadline before/during
provider, helper disconnect, denied resume, reset/stale receipt and
partial resume. Full repository native regression and Android ARM64
cross-link pending operator local CI; no device access. New test is
part of make test and the actual adapter is linked into the Android
target, but there is NO live caller.

Important: this is the coordinator core, NOT the independent watchdog
or a whole-session freeze/thaw implementation. Guard callback is an
explicit prerequisite, not a claimed identity/producer proof. Still
need independent lifecycle and deadline enforcement (including a
worker stuck in fdatasync/ioctl), actual complete device membership,
helper identity/liveness, boot-console and other producer park, bridge
and input lifecycle, vCPU/reset fencing, and external authorization
before considering live admission. No physical present/panel idle or
APFS unmount claim. Frequency provider remains BLOCKED_NO_OWNED_READBACK.
No recovery, thermal policy, kernel, staging or frequency write change.

### G25.0 operator receipt / G25.1A independent supervisor transport (2026-11-27 ICT)

Operator WSL G25.0 OneiOS 47646c137fc96498f0d14d632a06d29d7e960ca8:
701 coordinator checks, 19,858 XNUHost native checks, 159 KGSL
accepted-timestamp checks, six display socket scenarios, zero failures.
Android ARM64 XNUHost link and all five coordinator symbols PASS.
SHA256 4bd41d601166341803a6186ffabde02db4f8be1afacf56ae64f5356bdd7ac49c.
Evidence /tmp/oneios-g250.YPm0Bj, DEVICE_ACCESS=NONE. Real udmabuf
import skipped. Starship directory-scan warning after completion is
unrelated to CI. No physical GPU, display, IO or thermal qualification.

G25.1A adds the separate-process owner/worker transport for the G25.0
coordinator. Private AF_UNIX SOCK_SEQPACKET, nonblocking sends and reads,
SCM_CREDENTIALS on every packet, expected distinct PID/UID/GID, pidfd
liveness, absolute CLOCK_BOOTTIME timerfd, one outstanding command, exact
owner/cycle/sequence/deadline validation, and phase/receipt-mask checks.
The trusted launcher must pin identities and keep endpoint ownership
exclusive; credentials are not protection against privileged root.
Unsupported pidfd_open or timerfd fails initialization. One immutable
deadline covers park, hold and explicit resume; completed cycles can
start a fresh cycle with a new sequence. The owner independently bounds
each exchange even when a worker callback blocks; its event loop must
poll timerfd, peer socket and pidfd between exchanges. No production
event loop or launcher is installed. Fault shuts down the channel and
latches without automatic retry, cancellation, kill, thaw, reboot or
return. Worker binding preserves the upstream guard and checks channel,
deadline and owner lifetime before/after it at coordinator boundaries.
This prevents another provider call after a detected owner loss, not the
completion of an operation already in flight. Observed partial resume
masks are retained for valid error receipts; no receipt on timeout is
not proof of absence of side effects.

Standalone Linux GCC and Clang ASan/UBSan: 141 parent checks, zero failed,
child assertions and exit statuses checked. Real fork/socketpair/pidfd/
timerfd, exact G25.0 quiesce.c blob 4c4bcc34b70cdaa94804cdae9d99744713f88e74
and an equivalent minimal public coordinator header, stand-in providers.
Two complete cycles, independent timeout with live blocked child,
owner loss during a callback (no next provider), child death, denied and
partial resume, bad inbound command, bad ACK sequence, wrong PID
credentials, ancillary FD rejection/no retained FD, short/unsolicited
packet, and parked deadline expiry. ASan/UBSan enabled; leak sanitizer
disabled for process fixture, separate descriptor-count assertions.
New native test in make test; production transport linked into Android
XNUHost, no live caller. Full repository header/build and Android
cross-link pending operator local CI.

G25.1A is transport only. G25.1B must establish actual producer lifecycle
(boot-console, GPU shadow writers, vCPU/task/reset and bridge/input
ingress), complete immutable device membership, exact helper identity/
lifetime and owner launch/event-loop integration with owned-group
freeze/thaw. A blocked kernel syscall, scheduler starvation or platform
suspend is not magically interrupted; no real-time guarantee or
automatic physical quiescence proof. Frequency provider remains
BLOCKED_NO_OWNED_READBACK. No OneOS change, live admission, staging,
rearm, thermal policy, kernel, recovery or frequency write change.

### G25.1A operator receipt / G25.1B1 board membership and boot-console producer

Operator WSL G25.1A OneiOS 955f1ff560f11640b78643942568536f4bcb53d8:
141 independent IPC parent checks, zero failures, Android ARM64 XNUHost
link and all eleven supervisor symbols PASS. Runtime SHA256
9026aa7e822c2005d8213207d70fdc19bde9f1038773e911f940f69ac8f412a0.
Evidence /tmp/oneios-g251a.mQ43GO, DEVICE_ACCESS=NONE.

G25.1B1 records actual mapped VirtIO membership from xh_virtio_create
under a boot-time registry: configured disk count, contiguous MMIO
addresses and SPIs, unique transport pointers, device types and the
board's published device count. Failed registrations do not count.
Seal before publishing the guest board; refuse attempted late VirtIO
mapping and latch stale membership. Nonqualified board receipts do
not stop existing boot profiles. Snapshot all transports, including
unquiesced input and bridge devices; never infer their drain from
membership alone. No extra lock on ordinary MMIO, GPU submissions or
input delivery. A 2D GPU is not thereby a qualified drain provider.

Wrap the real boot-console BGRX8 and RGBA16F compare/copy/flush path
with a ticketed producer gate. Close is try-lock only and cannot
succeed while the console writer holds it; defer console updates
while parked, without stopping the main event loop or dropping
guest input. Explicit release after verification is the external
lifecycle owner's responsibility. The board-bound adapter obtains
GPU and all block transports from the sealed registry instead of an
arbitrary pointer list, and rechecks membership and the parked console
ticket before and after the independent guard. It does not supply the
remaining guard proofs. A binding is tied to its console ticket;
future multi-cycle control must explicitly manage release and reticket
without resetting a faulted coordinator.

Standalone GCC and Clang ASan/UBSan: 717 checks, zero failed. Exact
G25.0 quiesce.c and quiesce_runtime.c sources, equivalent minimal
ABI headers and mock device/map providers, real pthread writer
contention, 12 fork-isolated fixture cases, six-block coordinator
dispatch, normal resume and refusal on late mapped-device attempt.
Native full-repository regression, actual main/VirtIO integration
compile and Android ARM64 link pending operator local CI. No production
quiesce caller enabled, no physical drain or panel idle proven.

Remaining G25.1B work: helper process identity/liveness and credentialed
barrier, vCPU/task/reset and input/bridge producer lifecycle, and
control-path ownership including repeated console cycles. G25.2
whole-session freeze/thaw and independent actuator qualification remain
separate. Frequency provider remains BLOCKED_NO_OWNED_READBACK. No
OneOS change, live admission, staging, rearm, thermal policy, kernel,
recovery or frequency write change.

### G25.1B1 operator receipt / G25.1B2 display-helper identity

Operator WSL G25.1B1 OneiOS 6b60a1871ff9e811b0bfd1999f5a8be1df178974:
717 board/console checks, 19,858 XNUHost native checks, zero failed;
Android ARM64 link and eleven board/console symbols PASS.
SHA256 bb6b726ce643ac7e4bfef58586adb2b11306973aaf6cf2f796d101bc473a7c1c.
Evidence /tmp/oneios-g251b1.UDOV3D, DEVICE_ACCESS=NONE.
Actual udmabuf import still skipped.

G25.1B2 adds fail-closed identity binding on the real SHM helper
connection. A trusted launcher must supply the intended distinct
helper's already-pinned pidfd and expected UID/GID; match SO_PEERCRED
and the actual socket SO_PEERPIDFD with the supplied live pidfd
using read-only /proc/self/fdinfo and the same PID namespace.
No numeric-PID reopen fallback. The pin is process-lifetime, and
new helper connections are refused after binding, even between
cycles. Previous replacement history cannot qualify. Enable
SO_PASSCRED before listen, verify SCM_CREDENTIALS on every barrier
record, reject short/truncated/ancillary-FD/incorrect-sender packets,
close any delivered ancillary FDs. Recheck process/socket lifetime
before and after reception and before each barrier operation; the
board-bound guard also checks the bound identity. Invalid identity
or an unbound helper cannot produce a valid quiescence receipt.
Normal non-quiescing rendering stays compatible; an unsupported
SO_PEERPIDFD/credential interface blocks the new control path.
This is not a security boundary against privileged root, a malicious
trusted helper, exec/image changes, or a full session membership proof.

Standalone GCC and Clang ASan/UBSan on Linux: 199 parent checks,
zero failed; real fork, AF_UNIX accept, pidfd_open and SO_PEERPIDFD,
queued pre-accept packet, mismatch UID/GID/pidfd, same-socket
impostor, truncated SCM_RIGHTS with FD-count check, short/long packet,
disconnect, and exact helper death while a descendant still holds
the socket. Child assertions and relevant exit statuses checked.
LSan disabled for process fixtures. Three standalone source/test
blobs matched the tested originals. Real display integration fixture
updated to use a distinct helper process, check missing/wrong bind,
post-bind replacement refusal, real helper parser boundary, wrong
ticket and right ticket from wrong sender. The integrated display/
board tests and Android link are pending WSL; standalone test does
not prove actual Android process identity or physical panel idle.
Requires kernel SO_PEERPIDFD support for the new identity tests.

No production launcher passes the helper pin yet; no live caller.
Remaining: vCPU/task/reset and bridge/input producer lifecycle,
complete session membership, repeated console ticket ownership,
production independent owner loop and freeze/thaw integration.
Frequency provider remains BLOCKED_NO_OWNED_READBACK.
No OneOS change, live admission, staging, rearm, thermal policy,
kernel, recovery or frequency write change.

### G25.1B2 operator receipt / G25.1B3 cooperative vCPU and tracked-task lifecycle

Operator WSL G25.1B2 OneiOS aa90c7289bed54a2f32887193439fc9d9ab762a0:
199 peer checks, seven display socket scenarios, 719 board/console checks,
zero failures; Android ARM64 link and nine identity symbols PASS.
SHA256 cb4d34ada1a9f34b198bad72cc0826f054218d738b7c9333938bd0aaa2a77984.
Evidence /tmp/oneios-g251b2.VYEtXu, DEVICE_ACCESS=NONE.

G25.1B3 implements a process-lifetime cooperative vCPU rendezvous.
Every configured vCPU (up to eight) registers before kernel entry;
close requires all configured vCPUs to have registered. Actual
checkpoints are at initial entry, cpu_idle (including WFI emulation),
and before/after the thread_run hostcall with no outstanding prior
user release or host task/device lock at those boundaries. Park
publishes a per-vCPU bit on a lock-free atomic word, then waits on
a private futex. No synthetic IRQ, signal-driven arbitrary suspension,
SIGSTOP, forced guest trap, scheduler/frequency change or guest ABI
change. A busy vCPU may never reach a checkpoint: poll remains EAGAIN
and the independent owner must enforce the deadline. Open path is an
atomic load per checkpoint, no extra mutex or syscall; performance
impact not measured. No claim that guest lock dependencies permit
every vCPU to arrive, or that ARM64 signal context is qualified.

Task audit checks the actual tracked task table and stub service/trap
slots while all configured vCPUs are parked; no outstanding user
release, in-flight unmap, service request, clone/exit ambiguity or
unreturned thread command allowed. Deferred unsent maps are allowed,
not flushed. Try-lock the table and task order locks; fail on
contention/inconsistency. Factory lifecycle events during a closed
cycle and ambiguous service/spawn/setup/exit paths invalidate the
receipt; halt/reset and shutdown invalidate without changing existing
stop behavior. No new task signals, forced cancellation, restart or
return. Board adapter requires the vCPU ticket and task audit in
addition to console, board and bound helper. Explicit resume only
after verified park and external authorization; no automatic thaw
on fault. The adapter remains tied to cycle tickets, no live caller.

Standalone exact quiesce_vcpu.{c,h} and test_quiesce_vcpu.c:
GCC and Clang ASan/UBSan, three runs per compiler, 651 checks per run,
zero failures. Real eight pthreads, missing registration, withheld
checkpoint, unverified resume refusal, stale tickets, repeated cycles,
no progress during park, explicit wake, duplicate registration and
fault refusal. LSan disabled for fork-isolated fixtures that exit
with intentionally parked threads. Three blobs matched tested files.
Full tracked-task code, board adapter fixture changes, host regression
and Android ARM64 compile/link pending operator local CI. This is a
cooperative checkpoint fixture, not execution of a real hosted guest.

Remaining: independently verified factory/descendant and thread
membership (including orphan/untracked processes and lifecycle races),
input and all remaining bridge producers, release authorization and
repeated-cycle ownership, production independent owner/launcher and
owned-group freeze/thaw. No proof of complete guest quiescence or
physical GPU/IO/thermal behavior. Frequency provider remains
BLOCKED_NO_OWNED_READBACK. No OneOS change, live admission, staging,
rearm, thermal policy, kernel, recovery or frequency write change.

### G25.1B3 operator receipt / G25.1B4A input source lifecycle

Operator WSL G25.1B3 OneiOS 3174df6fe3fd35060ee2e4da2e8868270175d503:
651 vCPU, 967 board/console and 19,858 XNUHost native checks,
zero failures; Android ARM64 link and ten requested symbols PASS.
SHA256 8dfdd410821e8327d84b2b4dd70a9770e6890a88236044c5db49791494f1798c.
Evidence /tmp/oneios-g251b3.NBQWfF, DEVICE_ACCESS=NONE.
Real udmabuf import remains untested.

G25.1B4A captures the known native evdev reader (touch, pen and
side keys) and the script source before they start, seals membership
after setup, refuses late/duplicate starts and ambiguous setup failures.
The native reader cooperates at the outer poll loop and before
each read; park cannot be acknowledged in a read/feed/power-key
callback. Normal open checkpoints use one atomic load. No change
to filter/guest report format, EVIOCGRAB policy, side-key recovery
reader, input timing settings or bench deadline. A running script
prevents close (EBUSY) until it exits; do not pause and retime the
workload or synthesize gesture cancellation. In a valid native
reader park, no further read/feed is started; kernel evdev data may
accumulate or overflow, so this is not a lossless physical-event
buffer or proof of neutral contacts. Existing SYN_DROPPED handling
is unchanged. A terminal input stop invalidates the ticket and
wakes a parked reader for the existing join/descriptor cleanup,
not normal resume. A blocked operation still needs the independent
owner deadline. Exact input ticket required by board-bound guard
before/after external checks; no automatic reopen.

The board adapter now refuses any mapped transport other than
block (2), GPU (16) and input (18) with ENOTSUP, even if an
external guard would be permissive. Hardware bridge, camera,
audio, encoder, network and unknown VirtIO devices require their
own actual provider qualification. This deliberately blocks the
current full-bridges profile until those providers are implemented;
the ordinary boot/render path and existing admission are unchanged.
Non-VirtIO workers, external process membership and asynchronous
hardware/DMA boundaries are not proven by this transport allowlist.

Standalone exact quiesce_input.{c,h} and test_quiesce_input.c:
GCC and Clang ASan/UBSan, three runs each, 155 checks/run, zero
failures. Seven fork-isolated scenarios; real pthread plus pipe
handshakes for in-flight work and queued input, no post-park feed,
repeat park/resume, stale/unverified tickets, active script refusal,
missing/failed/duplicate source, late registration, terminal stop
after valid or faulted park. Leak sanitizer disabled for process
fixtures. Three new blobs matched tested files. Updated board
fixture uses the real input gate and tests unsupported transport
types; actual input/board integration, native regression and
Android ARM64 build pending operator local CI.

Remaining G25.1B4B: per-bridge actual ingress/drain/stop/receipt
and resume, including callbacks, helper processes, DMA/shared
media pool and non-VirtIO producers; no substitution of a transport
lock for an actuator receipt. Independently verified complete process
membership, repeated-cycle ownership and G25.2 freeze/thaw/owner
launcher remain pending. Frequency provider remains
BLOCKED_NO_OWNED_READBACK. No OneOS change, phone access, live
admission, staging, rearm, thermal policy, kernel, recovery or
frequency write change.

### G25.1B4A operator receipt / G25.1B4B1 report bridge and brightness writer

Operator WSL G25.1B4A OneiOS 4065a2ba7204e592e2e88ad3200633a41f9e08a6:
155 input source, 1,550 board/console and 19,858 XNUHost native checks,
zero failures; Android ARM64 link and nine requested symbols PASS.
SHA256 c1f71da3e9e78d241783721c71bc484f557d2c3f78211011234fef1ccb19e11f.
Evidence /tmp/oneios-g251b4a.e9j3tH, DEVICE_ACCESS=NONE.
Real udmabuf import still not checked.

G25.1B4B1 implements a control/report bridge provider with HCI and
haptics disabled, and its actual brightness worker fence. Close uses
the exact transport's existing try-lock, refuses unqualified actuators
and preserves pending backlog. Brightness close waits for both queued
and in-flight panel/touch writes (including the last write after pending
becomes false) and the ALS worker's periodic enable write. No new
sysfs action on close; no forced cancellation. Write failures, including
short writes, prevent a verified receipt. Late brightness/power/key
requests latch a fault and are refused. ALS re-enable is deferred until
open; ALS reads and the battery/thermal sampling and cap callbacks
continue. This is a host syscall completion boundary, NOT physical
panel/IC readback or a qualified frequency actuator.

During the closed bridge cycle, ALS, battery and thermal reports only
update three bounded host-memory latest-value slots; they do not touch
guest RX or used rings. No lossless history claim. Pre-existing messages
remain in order; close reserves three backlog slots and resume prepares
all payload copies before reopening either gate. The external owner
must authorize release after full coordinator success. Late guest
kick/handler/reset invalidates the receipt; the upstream vCPU/task
fence is still required (generic transport mutation is not fenced by
this provider). The existing explicit return ask remains available
and invalidates the receipt before delivery; no new return trigger.
Terminal brightness shutdown still restores as before. Backend
identity/lifetime must be pinned externally; no production caller.
The board adapter checks the actual single control/report bridge
and its exact ticket on every guard; missing/extraneous ticket or
unqualified media/net/unknown transport is refused. This is not
whole-session admission.

Standalone exact shared gate/telemetry header and unit test:
3,650 checks, zero failures on GCC and Clang ASan/UBSan.
This proves the ticket primitive and bounded latest-value storage,
not the live hardware worker. Added integration fixtures for a real
pthread blocked at the last panel write on fake sysfs, battery worker
host-only report with an already posted RX buffer, stale/missing
bridge ticket, late reset and explicit return invalidation. Actual
bridge and brightness integration, board fixture, ARM64 build pending
operator WSL. Also repair direct virtio.c link dependencies in
bridge/camera/encoder Makefiles following G25.1B1 board registration.

Remaining G25.1B4B: audio helper, camera/encoder media DMA and
shared pools, network, optional HCI/haptics and other non-VirtIO
producers. Full-bridges profile still not admitted. Independent
factory/descendant membership, repeated-cycle release authorization,
owner launcher and G25.2 freeze/thaw are pending. Independent thermal
monitor must not be inadvertently frozen with guest workload.
Frequency provider remains BLOCKED_NO_OWNED_READBACK.
No OneOS, thermal policy, frequency, kernel, recovery or live
admission/staging/rearm change. No device access.

### G25.1B4B1 operator receipt / G25.1B4B2A idle audio provider

Operator WSL G25.1B4B1 OneiOS 4aa937a2054f786c2f82af485b9c4270a8848323:
3,650 gate/telemetry, 127 brightness, 468 bridge and 2,106 board
checks, zero failures; native camera/encoder compile/link, Android
encctl and XNUHost link and seven requested symbols PASS.
SHA256 1fcf3dd641e9b1cb4be17f79c71a6e43b0afe1d166aa14b298257f116e6bb2bd.
Evidence /tmp/oneios-g251b4b1.Y6JboS, DEVICE_ACCESS=NONE.
Camera/encoder runtime tests were not run in this receipt.

G25.1B4B2A adds an explicitly idle-only sound provider. The real
virtio-snd lock checks both logical directions stopped and capture
thread joined, with no ambiguous STOP/join or backend error. Unknown
backends are refused. The exact null backend is locally idle; for
AAudio, close sends a monotonic FIFO control packet to the actual
spawned helper, poll requires its exact ACK, and explicit authorized
resume requires its exact ACK. No synchronous wait while holding
the transport lock. The already stopped capture thread's pre-barrier
PCM and successful status records can be retired, not delivered to
guest memory. No new normal PCM buffering or pacing change. Late
guest handle/kick/reset invalidates the sound ticket (upstream guest
fencing still required; not a generic transport gate).

The helper's ordinary STOP is not a drain receipt: output can linger
and play silence for the configured duration (default 60 seconds).
The new barrier does not shorten linger or stop an active stream.
It waits until both AAudio streams and workers are absent, local
output ring empty, no live logical playback, and no reported I/O
or stream close/join ambiguity. The control loop forbids further
START/PCM/STOP while held, and explicit resume only opens the gate;
it does not start a stream. Bad tickets/late packets fault the link
without automatically starting/stopping hardware. Existing EOF
cleanup remains. No physical DAC drain or HAL idle readback claim.

Parent qualification pins its own unreaped posix_spawn child with
pidfd, checks child status before/after acquisition (requires no
competing child reaper), enables SO_PASSCRED before spawn, verifies
each control reply's PID/UID/GID and exact length/ticket, rejects
ancillary FD injection and truncation. No PID-only fallback;
unsupported pidfd/credentials block the receipt, not legacy audio.
This is a trusted local launch protocol, not isolation from root.
SO_PASSCRED adds kernel credential work to ordinary received PCM;
performance/latency impact is not yet measured. The existing
internal helper ring is not a cross-process shared PCM ring.
The board adapter requires the single exact sound ticket whenever
a sound transport is present; unknown/other media remain refused.

Exact standalone audio/quiesce_link.h and test_audio_quiesce_link.c:
58 checks on GCC and Clang ASan/UBSan, zero failures, real forked
processes and sockets; stale/wrong ACK, pre-barrier PCM/state,
inherited-socket wrong sender, ancillary FD, helper exit, repeated
close/resume. Both blobs matched tested files. Added fake-HAL
actual helper idle/linger/capture/fault scenarios, actual posix_spawn
backend-to-helper integration, null sound transport/active and
unknown backend refusal, and board receipt fixtures. Integrated
tests and Android oneios-audio/XNUHost build pending operator WSL.

Active playback or capture remains a BLOCKER, as does linger beyond
the independent deadline; a persistent guest audio engine cannot
be qualified by this idle-only provider. G25.1B4B2B must implement
a separately qualified active-stream drain/release/restart design,
without silently dropping accepted playback or inventing guest STOP.
Camera, encoder, net, optional HCI/haptics and other producers,
independent complete membership, owner launcher and G25.2 remain
pending. Frequency provider remains BLOCKED_NO_OWNED_READBACK.
No OneOS change, thermal policy change, live admission/staging/rearm,
kernel, frequency write, recovery or device access.

### G25.1B4B2A operator receipt / G25.1B4B2B1 active speaker drain

Operator WSL G25.1B4B2A OneiOS 5b699d37bf5a4ed369e92a3418d02a6e362955e4:
58 IPC, 26 idle helper, 18 actual spawn, 20,460 full fake-HAL audio,
489 bridge and 2,666 board checks, zero failures. Android ARM64
XNUHost and oneios-audio links and seven requested symbols PASS.
XNUHost SHA256 01520023f450f0b7f6c83f2c83bcafce9646d3a35c9acf0e5674783ec06c8017;
helper SHA256 1112308beb1706f6bdadfe8b72dac83936e79a8a80653d369f696e57eac717ca.
Evidence /tmp/oneios-g251b4b2a.vtHjUQ, DEVICE_ACCESS=NONE.
Fake backend notify hop 1.2 us mean / 7.8 us max, not physical latency.

G25.1B4B2B1 adds a separate authenticated AU_QUIESCE_PLAYBACK
marker for logically STARTed output with capture stopped. Guest
vCPUs must already be fenced and the capture thread joined.
No guest STOP/START, RX returns or automatic resume. The sound
gate preserves logical playback, rejects active capture and
unqualified backend, and verifies the saved state. Null output
has no independent stream or retained data. Ordinary idle-only
barrier and linger remain unchanged; a mismatched legacy helper
cannot ACK the new request.

The actual helper processes the FIFO marker after prior PCM
messages, seals the normal writer's next ring selection under
ring_lock and lets its previously selected write finish. After
worker acknowledgement and join, control thread exclusively drains
the retained ring, consuming exactly the frames accepted by each
nonblocking AAudio write. No additional drift resampling, overflow
eviction or silence cutting after cutover. Earlier normal PCM loss
and drift policy are unchanged, so this is NOT a lossless claim
about all historical guest submissions. Snapshot the final
FramesWritten position and require a real, fresh nonregressing
AAudio CLOCK_MONOTONIC presentation timestamp covering it; never
extrapolate FramesRead. Bounded zero-only padding may help mixer/
DSP pulls finish. The fence does not move with padding. Stop/close
is requested only after that proof, then ACK only with no stream
or worker and no I/O/join/close ambiguity. Physical DAC and vendor
HAL behavior remain unverified; this is an AAudio API receipt.

Local active-drain bound is 3 seconds CLOCK_BOOTTIME including
rendezvous, with at most 48,000 padding frames and timestamp age
at most one second. These conservative offline implementation
choices are not thermal settings and do not replace the owner
deadline or guarantee cancellation of a blocked HAL call.
Missing/invalid timestamp, ambiguous count, peer loss/late command,
deadline or close failure faults without automatic reopen.
Explicit resume recreates the saved 48 kHz stereo output stream
and worker before replying (start request success, not presentation
proof); logical START remains unchanged. Startup latency and any
audible discontinuity at reopen are not measured. No live caller.

Exact playback_drain.h and test_playback_drain.c passed GCC and
Clang ASan/UBSan, 99,669 checks each, zero failures. This count
includes per-sample assertions on retained PCM and bounded silence;
not 99,669 separate scenarios. Both blobs matched tested files.
Added actual fake-HAL mixer/MMAP short-tail, missing timestamp,
active-capture rejection, stale resume, repeated cycles; actual
spawn backend-to-helper and null transport checks. WSL integration
and Android builds pending. Active microphone remains a blocker
requiring a separate FIFO/read-worker/guest-RX and permission
lifecycle, not silent capture discard or synthetic STOP.

Remaining G25.1B4B2B2 capture, camera/encoder, net and other
producers, independent membership, repeated-cycle release,
owner launcher and G25.2 remain pending. Frequency provider
BLOCKED_NO_OWNED_READBACK. No thermal policy, OneOS, kernel,
frequency write, recovery, live staging/admission or device access.

### 2026-11-27 — scope correction and PERF-P1-03 timer hot path

Record operator G25.1B4B2B1 PASS at 412efe31a7a280417baefdacac7fed31b3ee8178:
99,669 drain, 58 IPC, 56 active, 26 idle, 28 spawn, 20,516 full
audio, 492 bridge and 2,666 board checks, zero failures. Android
XNUHost/audio build and eight requested symbols PASS.
Evidence /tmp/oneios-g251b4b2b1.513HER, DEVICE_ACCESS=NONE.
Preserve this branch history; no new microphone/provider lifecycle.

Resume existing PERF-P1-03/PERF-P0-06, not a new G25 subphase.
Historical 180.6s baseline had about 1,895,124 actual host timer
calls (all kinds, not the redundant-cancel count). Existing same
future deadline skip already exists; the physical fraction of zero
programming duplicates is not measured. Source audit shows repeated
cancel/already-due requests still call timer_settime with an all-zero
spec even after a successful disarm. The vCPU owner now caches the
last successful host programming, skips only identical zero writes
after proven zero, and invalidates the cache on any syscall failure.
Same-future-deadline skip additionally requires last successful
nonzero programming; never reuse a failed arm. Do not infer expiry
from the cache. Guest timer_armed/deadline publication, GIC line
recomputation, signal delivery, counter conversion, idle and futex
semantics unchanged. Host call totals count actual attempted syscalls;
existing opt-in perf-timer fields retain their meanings; separate
perf-timer-skip line counts cancel/due skips, no per-event logging.
This does not implement a new timer-failure recovery policy.

Exact timer_program.h and test_timer_program.c: 14,028 checks each
under GCC and Clang ASan/UBSan, real Linux signal POSIX timer,
timer_gettime, EINVAL and actual expiration/rearm signal delivery.
Synthetic 1,000 repetitions of arm/cancel/cancel/cancel: 4,000
old calls versus 2,000 new calls; NOT a real workload speedup or FPS
measurement. The initial fixture used SIGEV_NONE, whose observed
readback was unsuitable for this signal-timer test; final fixture
uses SIGEV_SIGNAL with blocked SIGUSR1. Host/ARM64 integrated CI
pending operator WSL. No OneOS, thermal policy, kernel, recovery,
staging/rearm or phone access. Frequency still BLOCKED_NO_OWNED_READBACK.
Next performance decisions: use existing G2.2/Phase F frame and
task evidence, prioritize measured CPU/VM and GPU/display hot paths;
no re-opening the deferred hardware lifecycle without operator scope.

### 2026-11-27 — PERF-P1-01/02 service-order hot path

Operator WSL PERF_TIMER_OFFLINE=PASS at
257f7ee7fd5737855bf4ccb9459acb6139aa7261: 14,028 timer, 67 task
profile, 19,858 native checks, zero failures; QEMU test kernel all
passed (timer interrupt/preemption and 200-round unmap race),
RAM_AUTO_LOG PASS, Android build PASS. The initial native test
had run from the repo root and could not open two relative fixtures;
re-running from runtime/xnuhost resolved both, no source fix needed.
Evidence /tmp/oneios-perf-timer.d2vCgH, DEVICE_ACCESS=NONE.
Android XNUHost SHA256
b8fcf5c8bf580175b1d38754ab5cf4b2615f1b835d9060f91c2108a4a6ed0900.
QEMU skips process_vm_{readv,writev}, no KGSL/udmabuf physical test.

Do not proliferate IPC protocols for unproven performance benefit.
Historical G2.2 baseline: 340,790 direct and 19,315 deferred service
order ACK samples. Standalone conditional-wake two-flag candidate
passed 20,000 process-shared orders each on GCC/Clang, but used
39,079/39,274 of 40,000 unconditional wake calls. A second candidate
used a single IDLE/WAITING/POSTED atomic futex word; 160,000 alternating
legacy/new orders per compiler passed. New wake calls ranged
39,180–39,634 per 40,000; elapsed time did not demonstrate a gain.
These are x86_64 process-shared synthetic receipts, not SM8850
latency measurements. Reject both candidates; no shared ABI,
stub, futex protocol, spin policy, guest scheduling or new gate.

Instead skip an actually empty deferred-only service flush when
the pending observation in flush_pending raced an already completed
drain. Under both existing task order and queue locks, with live
task, no requested or pending operation, no outstanding unmaps,
and service request=0/done=1, no service IPC is necessary. Never
skip a nonempty batch, initial/unacknowledged or busy service, or
an ambiguous unmap state. All actual map/unmap/protect operations
and their ACKs retain the existing ordering and protocol. Preserve
the opt-in real-order ACK histograms; do not fabricate a sample for
an IPC that was never performed. Separate vCPU report counter
perf-order-skip: empty_flushes records the skipped exchanges.
Reuse order()'s existing monotonic start sample for its 10-second
wait deadline, eliminating one clock_gettime read per real order;
boot/thread readiness still use their own start sample. No
change to wait polling, interrupt handling or timeout policy.
The empty-flush frequency in the real workload is unknown.

Exact task_order_fast.h and test_task_order_fast.c passed GCC and
Clang ASan/UBSan, 1,086 checks per compiler (486 predicate cases
plus deterministic stale observation/worker drain interleavings).
Portable model test only, integrated WSL/ARM64 CI pending.
Do not claim a measured latency or FPS improvement. Continue to
GPU/display hot paths rather than further speculative futex
protocol changes. No OneOS, thermal policy, kernel, recovery,
live admission, phone operation or GitHub Actions.

### 2026-11-27 — PERF-P2-03/04 GPU dispatch and same-layout scanout

Operator WSL PERF_TASK_ORDER_OFFLINE=PASS at
bb950679edf3f95d903284c16201b7dd3f4e3d4e: 1,086 empty-order,
11 order diagnostics, 67 profiler checks, 20,000 process-shared
futex releases and 19,858 native checks passed. ARM64 test kernel,
profiler OFF/ON and Android build PASS, zero reported invalid ACKs
in the supplied profiler excerpt. Evidence
/tmp/oneios-perf-order.CSNWTY, DEVICE_ACCESS=NONE. XNUHost SHA256
0f137b7c17073c34eb884ab14db9a943f070f2a1c3695979fe4bf16e60bd99ed.
No native physical latency improvement established.

P2 source batch: historical frame evidence includes active cadence
34.44/s, GPU fence max 55.354ms and frame copy max 14.87ms.
These are different stages and not proof of a causal frame stall.
The ordinary fast lane in virtio_gpu.c used two cmd acquisitions
(classify then serve) plus a separate pl acquisition to read the
slow-job watermark for every chain. Keep cmd held across successful
fast classification and the initial work call. work() still
reconciles generation immediately before execution; reset and
generation checks, pending fences, used ring/IRQ, gate and backend
calls are unchanged. Slow jobs release cmd before allocation/enqueue.
Only the front worker increments slow_queued, so it can snapshot
that same watermark under pl only on actual dependency retry.
Release cmd before waiting and recheck generation on retry. No
new lock order: work already takes pl under cmd. One cmd and one
pl lock/unlock pair are removed per non-retried fast command,
excluding locks inside work/other providers. This does not eliminate
a wait for the slow worker's existing cmd hold during a backend
call. Actual contention and scheduling impact remain to be measured.

Also use the existing same-layout raw memcpy branch for padded
or partial-width dirty rectangles, rather than passing each segment
through pixel carry and format dispatch. Only BGRX/BGRA to BGRX
and RGBA16F to RGBA16F qualify. The original linear predicate
still decides when an entire unpadded full-width span can be copied.
Per-segment address translation, length/alignment checks, clipping,
dirty rectangle, format conversions and notification timing are
unchanged. RGBA16F split across a disjoint page boundary is copied
as its constituent bytes; no change to HDR, bytes copied or buffer
ownership. A standalone differential segment-walker model passed
40,000 checks (20,000 rectangles against independent flat-memory
reference, both old and new algorithms) each under GCC and Clang
ASan/UBSan; includes padded strides, partial/tight full rows, 4/8
bytes per pixel and noncontiguous segments. This is a model test,
not a complete production build or throughput benchmark. Extended
the real fake-backend VirtIO test with exact full-buffer comparison
for padded split-pixel damage and a slow-create/fast-attach pair
under one kick; it checks exactly-once completion regardless of
whether scheduling actually exercises retry. Existing reset, fence,
random-chain and gate regressions remain. Integrated WSL build/test
pending. No claim of physical FPS or lock-wait savings. Do not
change fence semantics, guest/Android refresh, HDR, thermal,
recovery, frequency ownership, OneOS or live admission in this
batch. No device access or GitHub Actions.

### 2026-11-27 — PERF-P2-04/05 covered late damage in display helper

Operator WSL PERF_GPU_DISPATCH_OFFLINE=PASS at
8be9ec186907b4a4e5e2742c8e778f6a7af316cd: 29 fence, 166 GPU policy,
159 KGSL drain and 19,866 native checks, zero failures; Android
XNUHost build PASS. Evidence /tmp/oneios-perf-gpu.RXMxcd.
SHA256 32dfc58e53d9201cb717da7e2cdab1b68e9619ed29a2a8492f3765be2ac4203d.
DEVICE_ACCESS=NONE; not a real KGSL or FPS measurement.

Historical full-bridges Framework-OFF receipt (180.2s):
ANativeWindow lock/copy/post maxima 11.37/14.87/11.13ms, not
simultaneous or additive. The existing full-frame post-lock drain
already coalesces at most 32 records. It was not available for
partial locks. Extend the same bound to partial locks, but consume
only the covered prefix of the pending FIFO. Peek at the 20-byte
legacy prefix without consuming, clip to the frame, require
containment in the exact granted rectangle. Use the same complete
record parser and trace accounting on consumption. Stop BEFORE
the first uncovered, non-damage or incomplete-prefix record; do
not reorder or discard a record behind it. Requires the existing
single socket reader. Full locks retain the existing single recv
per record, including barrier receipt; partial locks leave control
records queued for the normal drain outside the lock. No new
sleep, refresh policy, dirty-rectangle enlargement, format or
resolution change. No claim of coherent SHM snapshot or unique
physical frame presentation. Only successful valid-content posts
are counted. Keep the existing trace sequence and provenance
rules and original first four full copies.

Late covered-only damage may already be included by the current
copy, so no second damage-driven post is needed for that batch.
This can remove redundant buffer work, not manufacture animation
frames. Partial path adds a nonblocking peek per candidate (also
one empty peek if nothing is queued); whether this is a net gain
depends on actual workloads. Extend existing late-drain total
counters/histogram to both full and partial locks, with
post_lock_partial_attempts and post_lock_partial_damage_packets
as separate subsets. Old receipts had full-only totals; compare
using these fields and do not infer saved posts from packet counts.

Extracted exact coverage/peek helper, real Linux SOCK_SEQPACKET
fixture with 20,000 varied records per GCC and Clang ASan/UBSan:
2,998 covered / 17,002 deferred; byte-identical records still
queued after every peek. Empty socket, edge clipping and EOF
also passed. This is a focused helper test, not the integrated
Android or WSL CI. Added real parser/trace test for covered FIFO
prefix, uncovered record and later covered record, cap, clipping,
short prefix, Q boundary and EOF; added profiler counter regression.
WSL native display, mode and Android helper builds pending.
No change to XNUHost code, OneOS, thermal/frequency, recovery,
kernel, display pacing policy or live admission. Next use the
existing P2 evidence and benchmark criteria; no new lifecycle.

### 2026-11-27 — P2 display receipt and Phase H direct-Metal feasibility decision

Operator WSL PERF_DISPLAY_OFFLINE=PASS at
9abed4b5670ad92c37528e4a13e87a36b9f15ea3: 340 display native,
57 frame-profiler, 10 Java mode checks, seven XNUHost display/socket
integration cases, zero failures; Android display builds PASS.
Evidence /tmp/oneios-perf-display.Ygd9bO, DEVICE_ACCESS=NONE.
Artifact SHA256:
- oneios-display: 93a1dee53e6f00b31a368377a7ff44f1b82a1baa63777853ff2722d79bd575e6
- liboneios-display.so: 3c18caf23b4c294f5b2c0b6e12db1ddeba9b1d5e07b4636f0d998dd10984361c
- oneios-display.dex: 44cc35c41dfeeea389301cd01f54bbdc8813a1515565650af9887ea3f3e98ced
- displayctl: c50cc555961b0c8b590cfae1998961d9bb99158405a1508c91266ed095e6dafd

Scope: close the offline HakiOS architecture review, not initiate a
second GPU driver project. Inspected exact upstream snapshots:
- https://github.com/oosexgang/hakios-metal/tree/d36f329e2684a1968b7c1a0ceee1661472cb707a (2026-11-05)
- https://github.com/oosexgang/hakios-xnu-kernel/tree/63fc2b4633bac3af8e57dadab9f5a8d4cb940438 (2026-11-06)
- https://hackios-web.vercel.app/en/guide/metal
- https://hackios-web.vercel.app/en/docs/reference/metal-measurements

Use these as dated evidence, not a statement about every subsequent
upstream revision. HakiOS's published Nov 3–4 benchmarks are POCO X5
Pro, SM7325/Adreno 642L, Darwin 16.5 userland, GPU 550 MHz, 120 Hz
panel, synthetic gestures and specified wallpaper/deferred settings.
At 1125x2436 its direct Metal path reports 100–104 swipe FPS,
approximately 90 scroll; Metal-on-Vulkan 50–57 and 41 respectively.
At 750x1624 its direct path reports swipes 107–118, scroll 118–120,
roughly 110 across gestures. Not a sustained 120 claim or a game
compatibility result. HakiOS measurements are not equivalent to our
host post cadence or a matched workload; do not extrapolate the
ratio to SM8850, iOS 27 or full-resolution HDR.

Source comparison: hakios-metal src/iokit_transport.cpp opens
HakiosGPU and uses IOConnectCallStructMethod plus handle-based
IOConnectMapMemory64. Its include/hakios-metal/a6xx.hpp targets
0x06030500, with Mesa-derived A6xx device/register assumptions; the
pinned kernel docs/porting/index.md explicitly describe the chip
restriction. That is not OneiOS's guest AGXDeviceUserClient /
DroidVMVirtioGpu3D / VirtIO DRM capset 6 / drm2kgsl / stock KGSL
contract. OneiOS userland/metal/build.sh builds NativeAdrenoMetal
with pinned NativeMetal/metal2vulkan/Turnip for iOS 27 arm64e and
specific cache hooks; docs/gpu.md documents the current host path.
Do not transplant A6xx register state, fake the chip ID, or assume
a native HakiosGPU IOKit driver works with the hosted XNU ABI.
Replacing the renderer would require a separately scoped A830
render/compute/ISA, compiler, IOKit/IOSurface and synchronization
port, with independently verified transport and license provenance.
No such source imported, no dependency pin or guest kernel changed.

Useful concepts to reconsider only against matched traces:
eliminate tiled-image to IOSurface merge passes where actual
attachment/layout/coherence conditions allow; defer command
encoding or batch submits only when latency and ordering improve;
reuse buffers under existing generation/lifetime/coherence rules.
The published HakiOS Vulkan measurements identify a merge pass
and limitations on linear attachments, not proof that our iOS 27
workload has the same cost. Its scanline write method is specific to
direct panel control, not the Android Surface/BufferQueue path.
Do not silently apply wallpaper freezing, reduced UI effects,
lower render resolution or different GPU power settings.

Decision for the original PERF-P0–P4 roadmap: keep current backend;
do one consolidated offline local CI/package for the cumulative
timer/order/GPU/display optimizations, not another sequence of
speculative micro-patches or hardware lifecycle gates. Preserve
the existing instrumentation and matched-workload P3/P4 criteria.
Next performance decisions require evidence of GPU submit/retire,
queue/lock, scanout/copy, post and presentation behavior; no
physical FPS gain is yet established. The original P2/P3/P4
physical acceptance remains open. A passing package does not
authorize staging or launch. Live benchmark still blocked by
BLOCKED_NO_OWNED_READBACK and incomplete qualified quiescence/
admission. Keep operator thermal/recovery constraints unchanged.
No runtime or OneOS changes, device access or GitHub Actions in
this documentation receipt.

### 2026-11-27 — consolidated performance runtime package receipt

Operator WSL at OneiOS 8d463fad4832afb20d3415474f8881f566da853c:
PERF_BATCH_OFFLINE=PASS, DEVICE_ACCESS=NONE,
evidence /tmp/oneios-perf-batch.l9oagL. The initial all-mode
CI reached packaging after successful host regressions, then
package.sh rejected the version 0.0.0-perf-8d463fa (second
hyphen is not permitted by its version regex). The corrected
suffix 0.0.0-perf.8d463fa passed packaging and the remaining
archive/checksum/backend/ELF checks without repeating the
host suite. Mock legacy takeover messages in the CI log are
not device-launch or current thermal-policy evidence.

Runtime-only archive:
out/release/oneios-runtime-0.0.0-perf.8d463fa-arm64.tar.zst
5,817,329 bytes; SHA256
dac7d7b8ade3ae66cc94f6cd4951f5a66de3b46940be09df6f8df5c6007b9cab.
Companion tool:
out/release/oneios-tool-0.0.0-perf.8d463fa-android-arm64
14,795,432 bytes; SHA256
bf5f255b2bf668819b9b9d5b680793095677d0fc8cdf2fa526210d8f9aee7aa2.
Archive checksum and expected executable checks PASS; xnuhost
and gpuctl passed the no-2D-only-fallback string check.
Seven dynamic ELF files validated against API 30 NDK stubs,
nine static files, zero failures. No kernel at out/kernel/current.
Two unused-field Rust warnings are nonfatal. These are operator
reported local receipts, not independently retrieved artifact
bytes, physical GPU validation or FPS measurements.

The cumulative timer, service-order, GPU dispatch/scanout and
display coalescing batch is offline-validated. Retain this exact
archive and its source provenance; this documentation-only
receipt does not change the build commit. Stop speculative
runtime micro-optimizations until new performance evidence.
The HakiOS review is complete for this scope; no direct-Metal
port planned. Physical P3 A/B and P4 stable 60 FPS acceptance
remain blocked by the retired live-admission policy:
BLOCKED_NO_OWNED_READBACK plus incomplete independently
qualified guest quiescence/admission. No staging, rearm,
thermal-policy change, or live run is authorized by this pass.
Do not reopen individual peripheral lifecycle milestones or
repeat the successful offline suite merely to make progress.
The next operator decision is whether to address the existing
live-admission blocker in its separate workstream or retain
this candidate offline. No OneOS change or GitHub Actions.

### Operator correction: stock-managed thermal authority (2026-11-27)

Do not require an independent Qualcomm PerfLock provider simply to run
OneiOS. The supplied native thermal handoff shows stock One UI already
reduces effective CPU/GPU ceilings, e.g. at Moderate SKIN 42.8 C:
policy0 1555.2 MHz, policy6 1497.6 MHz, GPU 500 then 422 MHz.
These are successive stock gaming snapshots, not proof of policy after
Framework OFF. The earlier 104.8 C OneiOS peak is a separate session.
Prefer retaining Samsung/Qualcomm adaptive clock policy, limiting our
own workload, and keeping independent raw protection. Valid high
temperature is a throttle/quiesce/resume input, not a reason to refuse
a session or request a thermal reboot. Invalid or unprotected controller
state is different.

Pinned OneOS d1ff94975c355a219de4a13d667465eef91b3a65 adds explicit stock-managed controller
mode (no frequency callbacks or vote), uses qualified fresh native
severity as an additional demand constraint, preserves the raw
70/80/70 policy, and retains verified session/group/quiesce requirements.
This OneiOS slice exposes separate read-only native-raw/native-hal
thermalctl probes via existing discovery/Binder helpers and strict
complete AIDL v3 snapshot decoding; the current guest bridge ABI and
defaults remain unchanged. See runtime/bridges/thermal/README.md.
No automatic shared clock writes, no new mandatory PerfLock
qualification, no new peripheral milestone. Existing live launch
retirement stays in place: these are source components, not the
connected stock-managed root runner or proof of Framework-OFF
mitigation. Local focused regression/build pending. Retain the previous
tested performance runtime artifact and source hash; no stage/rearm,
live benchmark, stock-service restart or GitHub Actions.

### 2026-11-28 — stock-managed thermal source CI receipt

Operator WSL NATIVE_THERMAL_OFFLINE=PASS at OneiOS
99f40bb4f1df1b53eb8e72fb1b0e31c1494d4f4b / OneOS
d1ff94975c355a219de4a13d667465eef91b3a65 (exact app gitlink).
Thermal parser/bridge 120 checks, zero failures; native-raw fixture PASS;
stock-managed controller 414 checks; existing C/Python parity 8640 samples;
takeover/full-takeover fixtures 35+16 tests PASS. Android thermalctl and
both controller/owned-group objects compiled. thermalctl SHA256
52dcece4826a716bbdc8a2d5149d63f17c13379dfaf8792f56d86cd6438d40a8.
Evidence /tmp/oneios-native-thermal.n9dZzx. DEVICE_ACCESS=NONE.

Next concrete observation: run the exact new thermalctl's native-raw and
native-hal in stock One UI, independently and with bounded timeout,
without any framework stop or guest, clock/property/service change,
or persistent runtime staging. This is an operator-selected diagnostic
transfer of only that binary to a temporary directory; verify SHA,
model/firmware, root context, boot identity and readback. Do not repeat
the full offline suite or the earlier inventory. A successful native
HAL reply demonstrates the reader/permissions on stock, not vendor
policy survival after Framework OFF. The current root switcher still
has no production caller for the stock controller, and the quiesce
supervisor/board binding still needs its real session owner/providers.
Removing the retired gate alone would enter the old thermal path.
The separate frequency actuator is not required by the new design.
Do not launch via the legacy profile or change any safety thresholds.
No runtime code change in this receipt; the performance-only artifact
at 8d463fa remains the tested offline candidate.

### 2026-11-28 — native reader stock One UI physical receipt

Operator diagnostic at /tmp/oneios-stock-thermal.GU1Pan; the earlier
identity probe reported boot 99e016d0-42e9-451f-bfc1-973ac7fb32d7
(the final diagnostic did not independently print boot ID). Tested thermalctl SHA256
52dcece4826a716bbdc8a2d5149d63f17c13379dfaf8792f56d86cd6438d40a8:
RAW_RC=0 HAL_RC=0. SM-S948B/S948BXXS4BZIG, root ksu:s0,
SELinux Enforcing and five native services running at initial identity
probe. 28 accepted zones, CPU 31900, GPU/DDR 30800 mC; BAT 265,
LRP 286, board AP 272 deci-C. XO and gpu_busy_percentage unavailable;
not fabricated zeroes. Effective policy0 3187200 and policy6
3398400 kHz; Samsung virtual max 3398400 and min sentinel -1;
KGSL 222000000 current/902000000 max Hz, thermal level 5.
Raw acquisition BOOTTIME 24471901..24471910 ms. AIDL v3 returned
AP 27.2, BAT 26.5, PA 27.4, SKIN 28.5, USB 26.1 C, all
severity 0; SUBBAT=0 invalid, native_max_severity=0, OK.
HAL acquisition 24471952..24471953 ms. The samples are sequential,
not a synchronized physical measurement. The reader and its permissions
are verified in stock One UI; no native policy qualification after OFF.

The narrowly scoped sm8850-native-thermal-observe.py reuses the existing
20s Framework-only reboot-smoke launch callback, with explicit separate
operator consent. It transfers only the exact diagnostic binary to a
unique root-private directory, confirms hash and stock read, and
captures before/after verified OFF with the same boot, launch,
generation and deadline. It never boots an iOS guest, consumes APFS
Data, extends a deadline, issues thermal writes or invents a return
path. Existing smoke admission and recovery semantics remain in force,
including unqualified legacy watchdog risk and possible root loss
after reboot. Temporary cleanup can be unverified on lost root.
The observer is diagnostic only, not a live guard or root controller.
A single idle OFF read cannot demonstrate active mitigation; no
forced heating, new recovery experiment or automatic launch. Run
the new script's self-test offline before considering the optional
physical observation. No runtime rebuild or new peripheral work.

### 2026-11-28 — observer transport correction

Operator observer self-test passed at dee712f; live request was confirmed
but the binary transfer timed out after 30 s in adb shell -T / su -c
cat, before the ON probe or launch callback. No Framework-OFF observation
was made; no launcher invocation followed from this failure. Temporary
root path /data/adb/.oneios-natm.3ed036a16bc2432caa4eec68285721fc
cleanup was unverified. Evidence /tmp/oneios-native-observer.o2vidE and
/tmp/oneios-native-off.yzg7pbes. Exact cause of the stalled stdin transport
is not established. Reuse the proven adb push sync transport instead:
unique shell-owned scratch, verified root-owned private copy, SHA256
readback before execution, explicit -n -T / DEVNULL for non-streaming
commands, bounded per-step logs and exact-file cleanup. No runtime or
OneOS changes; existing 20 s smoke lifecycle, consent and launch gates
unchanged. New fake transport fixture and shell syntax checks pending
operator local self-test. No physical run performed by this change.

### 2026-11-28 — observer subprocess completion correction

Operator a6e33ee self-test PASS; the real ADB sync printed one file
pushed (2,521,920 bytes / 0.009 s), then the Python invocation timed
out at 30 s before root copy. Evidence /tmp/oneios-native-observer.kaI7Z8
and /tmp/oneios-native-off.o9xj5zuc. Scratch cleanup was attempted;
the root-copy step and launch callback were not reached. Do not
interpret the progress message as an exit status or OFF observation.
A similar inherited-stdout pipe wait was reproduced independently on
a Linux host: shell printed completion and exited, descendant retained
stdout, pipe-based run timed out at 2 s; file-backed run returned 0
with the same output in ~5 ms. Binary stdin and genuine timeout
preservation also passed the isolated helper test. This does not prove
the exact cause on the operator's ADB/WSL setup.

The observer now uses a scoped file-backed subprocess adapter for
captured output/input and explicit disabled stdin on non-streaming
shell calls. It does not change the existing smoke's scripts, deadline,
consent or thermal/return policy. If an actual ADB push timeout still
occurs, a single independent root-private copy/hash/ownership receipt
is required before execution; a progress line never substitutes for
that receipt, and a nonzero push exit still aborts. No automatic push
retry, no runtime rebuild, no change to OneOS. Added local real-child
and fake transport fixtures, including failed readback. Exact committed
observer self-test remains pending operator WSL execution. No device
access in this change.

### 2026-11-28 — native reader Framework-OFF physical observation PASS

Operator receipt at OneiOS 20eb35a218deda56a4c1de2d78a34d534308a638 /
OneOS d1ff94975c355a219de4a13d667465eef91b3a65. Evidence
/tmp/oneios-native-observer.LRoHZE and /tmp/oneios-native-off.68qg01ry.
NATIVE_FILE_BACKED_TRANSPORT=PASS, NATIVE_TRANSFER_FIXTURE=PASS,
NATIVE_OFF_OBSERVER_SELFTEST=PASS. Timeout cases printed during
self-test are fixtures, not failures of this live transfer. Actual
ADB push 2,521,920 bytes in 0.007 s; NATIVE_ROOT_COPY_VERIFIED.
No live transfer timeout. Boot-pinned manifest: 28 zones (CPU 16,
GPU 11, DDR 1). Operator explicitly accepted the existing 20 s
Framework-only reboot smoke; no guest boot, APFS rearm or observer
thermal-control writes. Existing recovery scripts refreshed with
rollback preserved (.rollback/oneos-compat.ousMDf6F).

ON/OFF snapshots bound to boot 99e016d0-42e9-451f-bfc1-973ac7fb32d7,
root ksu:s0. OFF launch a6e025952b1d4256bed0fdf362235224,
generation 99e016d0-42e9-451f-bfc1-973ac7fb32d7.5913.2940951,
deadline BOOTTIME 29478 s. Both NATIVE_RAW_RC=0 and NATIVE_HAL_RC=0.
ON raw 29358068..29358071 ms, HAL 29358192..29358193 ms;
OFF raw 29460734..29460737 ms, HAL 29460893..29460894 ms.
OFF read completed before the armed deadline with phase verification
on both sides. NATIVE_OFF_OBSERVATION=READERS_OK.

Native service PID/birth pairs unchanged across snapshots: thermal-engine
9927/93576, Samsung thermal-default 2411/1119, Samsung power-default
2385/1117, poweropt-service 2387/1117, perf2-hal-1-0 2399/1119;
all running. CPU hotspot 32.7 -> 37.0 C, GPU and DDR 30.8 -> 33.6 C,
battery 26.1 -> 26.4 C, LRP 28.3 -> 28.7 C, board AP 27.2 -> 29.5 C.
HAL AIDL v3 six named entries, AP 27.0 -> 28.3 C, SKIN 28.3 -> 28.7 C,
native max severity 0 both; SUBBAT=0 invalid, XO and GPU busy unavailable.
Effective policy0 3187200 kHz, policy6 3398400 kHz, Samsung max
3398400 kHz/min -1, KGSL max 902000000 Hz and thermal pwrlevel 5
unchanged. Current CPU clocks differ; these are successive low-load
diagnostic snapshots, not matched stress workloads.

EXISTING_SMOKE_EXIT=4 / OBSERVER_EXIT=4 are separate from successful
native observation: new Android boot observed by unprivileged ADB,
root status unavailable (possibly ephemeral DirtyFrag lost), no
independent unassisted return/deadline attribution qualification.
Root temporary cleanup unverified at
/data/adb/.oneios-natm.c2735fa7b20743fa813dead384073804.
Do not claim that stock mitigation under sustained iOS load is proven:
NATIVE_MITIGATION_AFTER_FRAMEWORK_OFF=NOT_QUALIFIED remains accurate.
No more Framework-only smoke or PerfLock inventory is needed for this
reader/lifecycle question. The next development objective is actual
stock-managed session integration: a root-owned runner consuming the
raw/native samples, independently verified guest demand ownership and
bounded quiesce/resume with real runtime providers; not new diagnostic
or peripheral milestones. Existing legacy full-run block remains;
this receipt is not live admission. No runtime/OneOS changes and no
new device action or GitHub Actions in this docs-only commit.

### 2026-11-28 — operator-requested boot animation attribution

OneOS d1ff949 switcher/assets/oneios_switch.sh:
bootui_begin returns immediately for FRAMEWORK=1 (line 906);
--stop-loop stops bootanim only in the FRAMEWORK=0 branch
(lines 1618..1629). SurfaceFlinger and Qualcomm display composer
are retained, and smoke exits before any xnuhost/display helper
launch (lines 2935..2940). This supports the operator's hypothesis
that Android's own boot animation or retained display path might
remain active when "Powered by Android" is visible. Prior OFF
receipt did not record bootanim state, CPU-time deltas, raw KGSL
gpubusy or layers; it cannot attribute the 4.3 C rise to display.
The old native-raw GPU busy integer parser reported invalid; keep
the original raw strings in this additional diagnostic.

Optional --display-probe reuses the existing 20s Framework-only
smoke, same exact binary, no extra build. Observe two snapshots
3s apart in each phase: bootanim/bootanimation, surfaceflinger,
display composer, system_server, and OFF takeover helpers;
PID/birth-paired utime+stime against aggregate CPU ticks, raw
KGSL gpuclk/max/pwrlevel/gpu_busy_percentage/gpubusy and backlight,
and one optional bounded SurfaceFlinger --list AFTER the sample.
No screen capture, brightness/refresh changes, bootanim stop,
thermal writes or new recovery mechanism. All extra OFF work
requires sufficient remaining existing deadline, and is skipped
or marked incomplete otherwise. Raw GPU counters are not FPS or
proof of continuous composition. CPU percentages use the total
measured ticks across all CPUs, not per-core percentages.
This is a targeted operator-requested observation, not a new
performance milestone or causal A/B intervention. Source-only
patch and added host fixture; WSL validation pending, no phone
access. Separate explicit consent for existing mandatory reboot
still applies. Root may be lost after reboot.

### 2026-11-28 — Samsung boot animation reactivation observed

Operator display observer 6044782 / OneOS d1ff949, evidence
/tmp/oneios-display-observer.e488Ws and /tmp/oneios-native-off.xh16d3di.
DISPLAY_OBSERVER_FIXTURE and NATIVE_OFF_OBSERVER_SELFTEST PASS.
Real ADB push printed 2,521,920 bytes in 0.008 s but timed out at
30 s; independent root-private hash/ownership readback PASS.
ON/OFF same boot 4b8ed790-7970-459d-a490-457aa5a6d78e,
OFF launch fd5edf65ed1443029941193ed0a3e848. NATIVE_ON and
NATIVE_OFF=READERS_OK, DISPLAY_ON/OFF=SAMPLED. Five native
service PID/birth pairs unchanged. Deadline request and One UI
observed; smoke exit 4, unassisted return remains unverified.
Root diagnostic cleanup returned without warning.

ON bootanim stopped, service.bootanim.exit=1; OFF bootanim
running PID 4013 birth 141053, service.bootanim.exit=0;
SurfaceFlinger layer list only samsungani565#193 z=3000000.
Samsung boot animation reactivation is observed, not inferred.
ON 3.300 s total CPU busy 3.58%; OFF 3.180 s 12.57%.
OFF bootanim 25 ticks / 0.99% aggregate CPU time,
surfaceflinger 6 / 0.24%, display composer 5 / 0.20%,
watcher 6 / 0.24%, stop-loop 4 / 0.16%, feeder 0.
bootanimation alias duplicates bootanim PID/birth: count ONCE.
These are direct process CPU times, not power, and exclude
unattributed child/kernel work. The three display processes
account for ~1.43% aggregate CPU time in this OFF interval,
not the whole 8.99 percentage-point difference. Raw KGSL
gpu_busy_percentage "0 %" and gpubusy "0 0" both ON/OFF;
this parser-format observation does not prove no GPU activity
between reads or no display engine power. Actual brightness
nodes 0 both phases; panel0-backlight requested 493 unchanged.
Physical panel state/luminance not established by these nodes.

ON/OFF native-raw samples 1328089..1328094 and
1414220..1414223 ms (~86 s apart); CPU max 40.5 -> 41.3 C,
GPU 39.3 -> 38.6, DDR 39.3 -> 39.0, battery 31.3 -> 29.9,
SKIN 34.4 -> 32.6. Raw thermal snapshots precede display
CPU windows. Not matched causal intervention or power A/B.
No proof boot animation explains prior +4.3 C hotspot change.
The confirmed unnecessary boot animation is a display-handoff
optimization candidate for the replacement runner: stop only
the stock animation after verified Framework stop at the
appropriate display handoff, keep SurfaceFlinger/composer
and stock thermal/recovery intact, verify layer/process exit.
Do not infer an existing live guest overlay conflict from a
guest-free smoke. No further standalone smoke required for
the reactivation question. Include effect in future admitted
session validation rather than opening another diagnostic
milestone. No source or phone change in this receipt; full-run
admission remains blocked.
