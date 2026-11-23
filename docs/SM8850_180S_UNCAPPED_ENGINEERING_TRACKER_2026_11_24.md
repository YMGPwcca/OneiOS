# SM8850 180s uncapped engineering tracker — P0 through P3

> **Tracked in-repository because GitHub Issues is disabled (`has_issues=false`).** Each `ONI-*` ID is a durable unit of work. Updating the checkbox without supporting evidence does not close an acceptance gate. This file tracks source work; the raw 180s device archive stays local.

**Primary evidence:** [exact-session report](SM8850_180S_UNCAPPED_SESSION_FINDINGS_2026_11_24.md); [OneOS root-side tracker](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-no-root-cpu-cap-180s/docs/SM8850_180S_UNCAPPED_ROOT_TRACKER_2026_11_24.md). Executed source: OneiOS `f244b5c` + OneOS `f5c1b4a`; session token `7434ae27f8e84b76806f7a4b506e90c9`; P0 safety remains blocked.

## ONI-P0-01 · Block unsafe physical performance reruns pending verified thermal/recovery [OPEN]

**Observation:** guard OFF + root cap OFF with chat-reported CPU junction peak **104.8°C**; normal reboot observed but independent return requester still unverified. The 180s preflight PASS was never a thermal certificate.

**Tasks**
- [ ] Keep all full-framework live acceptance behind OneOS [OOS-P0-01/02](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-no-root-cpu-cap-180s/docs/SM8850_180S_UNCAPPED_ROOT_TRACKER_2026_11_24.md) and explicit operator risk review.
- [ ] Treat kernel/vendor thermal unchanged as insufficient evidence of a separately bounded abort.
- [ ] Ensure automation/CI never launches real phone takeover just because local tests or a docs commit pass.
- [ ] Require same-boot provenance, recovery receipt and cool baseline before separate physical device acceptance.

**Close only when:** independent guard and unassisted return are demonstrated; no over-temperature regression. **No live rerun authorized by tracker.**

## ONI-P1-01 · Fix NULL `ops[0]` dereference on zero-count task order error path [OPEN, source-confirmed]

**Source:** `runtime/xnuhost/src/task.c`: `flush_pending()` can invoke `order(t,NULL,0)`. In `order()` the branch `if (rc || took_ms >= 1000)` logs `ops[0].op/va/size/prot` even when `count==0` and pointer is NULL.

**Failure mode:** a slow or errored pending-batch flush can turn an original service-thread timeout into a host NULL dereference. **Not observed in the supplied live run.**

**Tasks**
- [ ] Use a dedicated “pending batch flush” diagnostic for `count=0` without accessing `ops`.
- [ ] Cover both nonzero error and ≥1000ms timeout paths in host fault-injection tests.
- [ ] Preserve the original rc, pending operation order, lock ownership, rollback/fail-closed behavior and no accidental continued guest execution on failure.
- [ ] Run `make -C runtime/xnuhost test` with ASan/UBSan locally before merging.

**Close only when:** deterministic fault/timeout tests prove no NULL dereference and unchanged correct failure status.

## ONI-P1-02 · Attribute VM fault and mapping churn to guest process and critical path [OPEN]

**Physical evidence (cumulative 180.6s):** **8,889,193** task traps; **4,897,306** VM faults, **3,921,008** syscalls, **70,879** interrupts; **4,897,152** deferred maps, **2,716,095** queued unmaps, **379,903** ordered unmaps and **5,471,784** “maps by release” histogram observations. These last two map counters are not identical definitions.

**Latency:** fault mean 8.50µs/p99 65.53µs/**max 596.22ms**; syscall mean 23.57µs/p99 196.61µs/**max 286.60ms**. Maxima are independent lifetime outliers, **not proven frame-critical**.

**Tasks**
- [ ] Produce per-vCPU / per-guest-process trap counts by fault type and map/unmap operation, using bounded aggregated telemetry with no frame dumps.
- [ ] Profile `task.c` deferred queue length, joined operations, service-thread waits, `order` batching and fault recovery, preserving memory ordering/TLB coherency.
- [ ] Separate expected guest VM lazy mapping from pathological repeated faults; avoid interpreting VM faults as defective physical RAM.
- [ ] Pair worst latency windows with guest compositor and post timing under one validated monotonic clock.
- [ ] Use local portable concurrency/fault-injection tests before changing `map-defer=1` or `xs_queue_join`.

**Close only when:** an identified operation/process causes measurable, repeatable frame-critical delay and a local-tested change improves p95/p99 without guest memory corruption.

## ONI-P1-03 · Investigate timer churn, long-tail handoffs and vCPU placement [OPEN]

**Evidence:** ~**8,887,087** handoffs each direction; **1,910,107** timer sets (**1,895,124** host-timer calls); **10,993,281** vCPU futex sleeps, **3,380,216** iOS-thread sleeps. Handoff up/down mean **3.49/3.60µs**, p99 **10.24/12.29µs**, max **13.58/10.94ms**.

**CPU topology:** the last-sampled host CPUs for vCPU0..7 are `4,5,0,1,2,3,6,7` (distinct), but these are **last positions**, not proof of persistent 8-way pinning. vCPU0/1 each showed ~18k traps/s while the rest were far lighter. Peak guest CPU sampler **338%**, not 8-core saturation.

**Tasks**
- [ ] Inspect `runtime/xnuhost/src/cpu.c`, `perf.c`, `task.c`: record actual affinity masks and task-thread migrations, not only last CPU.
- [ ] Trace redundant timer arm/cancel and scheduler wakeup intervals with bounded local profiling.
- [ ] Separate user, kernel and idle accounting; do not interpret the printed vCPU “18–24% of a core” as thermal frequency.
- [ ] Avoid increasing vCPU count, global governor changes, forced priority or disabling safeguards as a performance shortcut.

**Close only when:** a specific placement/timer/handoff bottleneck is demonstrated and a controlled workload benefits.

## ONI-P1-04 · Establish source of 22 `host_statistics64` count warnings [OPEN]

**Exact warning:** `actual:104 > HOST_VM_INFO64_COUNT:62`; guest says buffer count must be in units of `integer_t` and warns of possible memory corruption. Logged **22** times, mentioning `cameracaptured` and `PerfPowerServices`. This is **guest-side output**, not proof XNUHost has incorrect ABI or that memory corruption occurred.

**Tasks**
- [ ] Read the pinned guest/XNU Mach `host_statistics64` MIG request interface, expected buffer length and return sizing.
- [ ] Attribute each count to caller or host ABI path; inspect whether `104` describes a larger valid structure or malformed requested output count.
- [ ] Add safe boundary and invalid-count unit/integration tests around relevant bridge (where controllable).
- [ ] Preserve diagnostics until resolution; do not merely suppress the warning.

**Close only when:** validated caller/ABI cause, correct count semantics and regression coverage.

## ONI-P2-01 · Investigate 61.656ms KGSL backboardd fence outlier without forcing GPU clocks [OPEN]

**Current-run facts:** KGSL real 3D; **GPU_ERRORS=0**, `fence timeouts +0`, no logged `EPROTO` or `backboardd`/`SpringBoard` respring, `SpringBoard PID=30`, `backboardd PID=52`. Host fence max **61.656ms** around monotonic t **5248.873**, window mean 8.068ms over 31 fences. Other busy windows: t 5191.840, 409 fences mean 2.445ms/max 6.864ms; t 5293.922, 477 mean 3.503ms/max 26.132ms.

**Policy:** `gpu-level=deadline`, available clocks **160–1300 MHz**; deadline-related top boosts already occur (566 policy “frames”, 552 at top in one 10s window). “Frames” here are **GPU policy events**, not actual display FPS.

**Tasks**
- [ ] Examine `runtime/xnuhost/src/gpu3d_kgsl.c` and `drm2kgsl/oneios_gpu_policy.h`; time-align per-fence submit/retire with guest command, compositor flush and actual post.
- [ ] Identify whether outlier is GPU execution, waittimestamp callback, scheduling, blob import, queue priority or guest wake.
- [ ] Preserve `0009-kgsl-reset-aware-submit-errors.patch` semantics and test errors/resets with fake KGSL; do not replay ambiguous IB.
- [ ] Do not claim the old 684.274ms EPROTO/respring is “fixed” solely because this new run had no errors. Not a controlled A/B.
- [ ] Do not force 1300 MHz or alter thermal policy.

**Close only when:** attributed fence tail, no regressions in fault injection/slow-path, verified frame-latency benefit under safe controlled evidence.

## ONI-P2-02 · Measure real displayed FPS/jank, not buffer-post or GPU frame rate [OPEN]

**Evidence:** 36 five-second display windows; 26 with posts, 10 without; peak post rate **57.42/s**; median `active_cadence` estimate **43.91Hz**. Source `runtime/display/src/frame_perf.c` uses only short posted-buffer gaps ≤250ms and ≥3 gaps. Operator's “~30FPS” was subjective; **neither figure proves actual FPS**.

**Tasks**
- [ ] Add a per-session bounded timeline of guest render completion, scanout flush/damage, display socket receipt, `ANativeWindow_lock`, copy, `unlockAndPost`, and presentation timestamps where available.
- [ ] Track panel/display mode and VSync timestamps; distinguish dropped/repeated guest frames, damage-less idle intervals and Android BufferQueue holding.
- [ ] Report p50/p95/p99 frame intervals and jank buckets only during **identified active animation** windows; no fake 120Hz claim from GPU policy 8.3ms deadline.
- [ ] Preserve low overhead/zero frames copied by default; show overhead of any instrumentation.
- [ ] Build and host-test `runtime/display` and companion parser locally.

**Close only when:** measurable visible 60FPS goal is testable under accepted thermal limits; no post-rate substituted for FPS.

## ONI-P2-03 · Resolve 9/16 touch gestures without next frame before summary close [OPEN]

**Evidence:** `touch_summaries=16`, `touch_without_frame_before_summary_end=9` (**56.25% of captured gesture summaries**), max logged successful touch→next guest frame **263.9ms**. These are **not proof of 9 dropped taps**. The highest candidate `gap_p95=31,754.794ms` crosses prior windows and can reflect idle, **not proved 31s touch freeze**.

**Tasks**
- [ ] Improve `runtime/xnuhost/src/input.c` timing with a bounded event ID that survives until next frame or explicit timeout, even after gesture summary ends; preserve the current no-extra-input semantics.
- [ ] Link touch down → guest input receipt → compositor flush → post/presentation using the same monotonic timebase and explicit pairing limits.
- [ ] Include late-match/unmatched categories; distinguish static UI, animations and no guest response.
- [ ] Replay existing 7 candidate windows, including t 5249.328 (touch nearby 263.9ms), 5269.912 (125.7ms) and 5280.176 (unmatched), with no new phone run.
- [ ] Add synthetic empty/late/paired gesture fixtures.

**Close only when:** p95/p99 touch-to-visible-frame and unmatched rates can be compared without false dropped-input labels.

## ONI-P2-04 · Brightness functional but slider stutters: isolate bridge scheduling [OPEN]

**Physical observation:** the user manually adjusted brightness to the desired panel level during full bridges=1 guest; the slider appeared to jitter/stutter. No brightness-specific timestamps or response accuracy data have been captured.

**Tasks**
- [ ] Trace Samsung panel brightness request → bridge callback → Android display/control invocation → observed panel state in existing `runtime/bridges` and `runtime/display` code.
- [ ] Identify synchronous waits, excessive notifications, repeated property sets or guest/UI scheduling contention, without changing verified brightness semantics.
- [ ] Distinguish visual stutter of UI animation from brightness hardware lag.
- [ ] Build deterministic mock bridge tests with rapid slider changes, ordering and clamping; no device-wide brightness writes in local CI.
- [ ] Keep the working brightness implementation intact until a specific cause is proven.

**Close only when:** no missing/out-of-order levels and bounded response under a controlled, thermally safe run.

## ONI-P3-01 · Audit memory footprint and GPU import lifecycle [OPEN]

**Evidence:** guest **4096MiB** prefaulted/locked, 0MiB guest-swapped-out in cited sample, Android `MemAvailable` minimum **3066MiB**, sampled page tables ~**503MiB**, KGSL `imported_mem=1,012,707,328` bytes, `ShmemPmdMapped=0`. No leak or OOM proved.

**Tasks**
- [ ] Build a monotonic per-session guest RAM/page-tables/host swap/KGSL object/import graph with allocation ownership.
- [ ] Test import/unref/failed allocation and reset leak handling using host fake KGSL.
- [ ] Separate retained pools and one-shot APFS guest startup cost from actual monotonic growth.
- [ ] Keep host memory budget checks; never globally tune hugepages/sysctl to chase FPS.

**Close only when:** memory is stable and resources reclaimed under repeated bounded local test lifecycles.

## ONI-P3-02 · Versioned exact-session offline reporting and fair A/B design [OPEN]

**Evidence handling:** initial `find` did not discover current `device-logs.tar`, later read-only collection did; token `7434ae27f8e84b76806f7a4b506e90c9` uniquely matched current traces (339,854-byte XNUHost, 10,203-byte display) among 16 archived sessions. Previous capped EPROTO/respring run is a **different workload/profile** and cannot be treated as measured speedup caused by removing cap.

**Tasks**
- [ ] Emit manifest with exact commit+submodule, session token, boot/generation, staged binary SHA256, guest/data provenance, clocks, recovery status, and per-file hashes without leaking ADB serial.
- [ ] Keep a strict same-session join by token AND boot/generation; report missing GPU/display/thermal evidence as missing, not zero/success.
- [ ] Preserve source-independent offline parser fixtures for cross-window idle gap, thermal clock mismatch, rootless postboot, and legacy log formats.
- [ ] Define matched touch/brightness/Settings sequences and separate sensor-source sample time bases; A/B only **after OneOS P0 safety acceptance**.
- [ ] Gate final code acceptance on CachyOS local native, Python and package CI. GitHub Actions only final PR checks.

**Close only when:** reproducible hashed offline reports and no false claimed FPS/cause/safety from incomplete logs.

## Summary: status and priority order

| ID | Priority | Status | Module / responsibility |
| --- | --- | --- | --- |
| ONI-P0-01 | STOP | OPEN | Thermal/recovery physical gate; companion OneOS P0 |
| ONI-P1-01 | P1 correctness | OPEN | `task.c` 0-count order error path |
| ONI-P1-02 | P1 | OPEN | `task.c` VM fault/deferred map churn |
| ONI-P1-03 | P1 | OPEN | `cpu.c`/`perf.c` timers, topology, handoffs |
| ONI-P1-04 | P1 | OPEN | guest `host_statistics64` ABI |
| ONI-P2-01 | P2 | OPEN | KGSL policy/fence |
| ONI-P2-02 | P2 | OPEN | display/VSync/actual FPS |
| ONI-P2-03 | P2 | OPEN | touch pairing |
| ONI-P2-04 | P2 | OPEN | brightness stutter |
| ONI-P3-01 | P3 | OPEN | memory/graphics ownership |
| ONI-P3-02 | P3 | OPEN | evidence/CI reproducibility |

**No new fixes or performance acceptance performed by writing this tracker.**
