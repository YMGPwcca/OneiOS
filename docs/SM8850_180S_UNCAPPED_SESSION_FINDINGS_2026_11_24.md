# SM8850 physical 180s uncapped full-bridges run — comprehensive findings (2026-11-24)

> **Evidence report, not a release or safety certification.** This document records the operator's read-only admission, actual physical observations, archived session analysis, source inspection and outstanding hypotheses discussed after the 2026-11-23 UTC session. It **does not** report new code fixes, device runs, local CI or any independently qualified unattended recovery. **Do not rerun guard-OFF/cap-OFF takeover to fill evidence gaps:** a previously summarized CPU sensor sample reached **104.8 °C**.

[Engineering tracker: 11 open ONI findings](SM8850_180S_UNCAPPED_ENGINEERING_TRACKER_2026_11_24.md) · [Roadmap](TODO.md) · [Previous GPU EPROTO/respring investigation](SM8850_GPU_RESPRING_TRIAGE_2026_11_23.md) · [Performance methodology](SM8850_IOS_INTERACTIVE_PERF_CAPTURE.md) · [OneOS ownership and policy](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-no-root-cpu-cap-180s/docs/SM8850_180S_UNCAPPED_ROOT_POLICY_2026_11_24.md)

## 0. Evidence classification and scope

- **P (physical/current-run):** operator-supplied on-device preflight output, guest/display/perf analysis output, physical brightness/UI observations and post-reboot host receipts.
- **A (archive-derived):** the operator verified `control/framework.launch` and extracted `session/xnuhost.log` and `control/display.log` from a single device archive; offline scripts parsed those logs. These values are more reliable than visual FPS guesses, but the scripts themselves state that temporal correlations are **not causal proof**.
- **S (source-confirmed):** behavior verified by reading the exact pinned OneiOS/OneOS source; no patch has been applied by this report.
- **H (hypothesis/open):** proposed root cause, unpaired comparisons, safety qualification and workload-specific conclusions that require additional evidence.
- **Chat-only thermal series:** several T+ temperature/clock samples were summarized earlier in this discussion from host passive telemetry, but the raw `telemetry.jsonl` was not attached to this report. They are explicitly marked as **not independently re-parsed**. Do not time-align them to the archive by assumption.

| Identity | Value / boundary |
| --- | --- |
| Target | Samsung Galaxy S26 Ultra, SM-S948B / m3q / SM8850, firmware `S948BXXS4BZIG`; SELinux Enforcing |
| iOS guest | iOS 27.0.1 (`24A446`), XNU hosted by OneiOS |
| OneiOS executed source | `f244b5cdfdedd592cc68bcbbb0770762def9e140`, branch `feat/oneios-sm8850-m3q` |
| OneOS executed submodule | `f5c1b4a44fc45d78987694a230f7ffabb213e99c`, experimental branch `feat/sm8850-no-root-cpu-cap-180s` |
| Experiment | Full Android Framework takeover, 8 guest vCPUs, `bridges=1`, GPU3D KGSL, 180-second requested duration, root software thermal guard **OFF**, root CPU frequency cap worker **OFF** |
| Safety | Kernel/vendor/firmware thermal controls not intentionally altered; **not** equivalent to a safe or independently bounded experiment |
| Exact session token | `7434ae27f8e84b76806f7a4b506e90c9` |
| Operator archive | `out/sm8850/takeover/collect-180s-uncapped/device-logs.tar` (local-only evidence; **not uploaded to Git**) |
| Verified matching pair | archive's **current** `session/xnuhost.log`: **339,854 bytes**; `control/display.log`: **10,203 bytes** |
| Generated local reports | `.../collect-180s-uncapped/frame-stall-report.json` and `.../collect-180s-uncapped/perf-180s/{gpu-respring.json,interactive-perf.json}` |
| Analysis tools | `scripts/phone/sm8850-frame-stall-report.py`, `sm8850-gpu-respring-forensics.py`, `sm8850-ios-interactive-perf.py` |

**Archive attribution guard (P/A):** the operator found `control/framework.launch` = `7434ae27f8e84b76806f7a4b506e90c9` with `MATCH=True`. Another **16 archived historical sessions** were listed, none matching this token. Their logs must **not** be joined to current-frame timestamps. A previously suggested local `find` for files in the run directory was empty; this did **not** prove the device traces were lost. The later root-readable collection recovered them.

## 1. Preparation / admission sequence — proven, distinct from live acceptance

1. **Exact revision checks (P):** host verified the two SHAs above, clean checkout and the staged XNUHost hash.
2. **Stage-only (P):** `STAGED_NO_GUARD_RUNTIME_PROTOCOL=ADMISSION_180S_SUPPORTED`, `FULL_BRIDGES_STAGE_ONLY=PASS`, `FRAMEWORK_STOP=NO LIVE_TAKEOVER=NO`. OneOS stage backup was preserved at `.rollback/oneos-compat.3w2hGPvv`; native-runtime backup at `.rollback/runtime.BXND7rrV`. Staging never implies iOS was already running.
3. **Staged artifact hashes (P):**
   - `runtime/xnuhost/build/android/xnuhost`: `502b536805e13665817a610d462ac3e8b59e5cc4b25a4d16a05a1731baf420a9`
   - `runtime/display/build/android/oneios-display`: `93a1dee53e6f00b31a368377a7ff44f1b82a1baa63777853ff2722d79bd575e6`
   - `runtime/display/build/android/oneios-display.dex`: `44cc35c41dfeeea389301cd01f54bbdc8813a1515565650af9887ea3f3e98ced`
   - `runtime/display/build/android/liboneios-display.so`: `c524db80be1c6139abd04d8fceb3b5f63379c086674ca2bc20807d62a6f3d61c`
4. **Boot-scoped preflight (P):** 28 pinned thermal zones (`cpu=16 gpu=11 ddr=1`), `SM8850_MOUNT_NAMESPACE_PROBE=PASS_NO_FRAMEWORK_STOP`, `REBOOT_STAGE_CHECK=PASS_NO_FRAMEWORK_STOP`. Android protected services and SELinux Enforcing were still intact.
5. **One-shot APFS Data rearm (P):** `FICLONE: Operation not supported on transport endpoint` was an **expected fallback**, not a failed rearm: on F2FS the script selected sparse clone. Both `data.img` and `unique-chip-id` showed `APFS_DATA_FRESH_CLONE_VERIFIED`; previous consumed Data was preserved under `.retired-data/consumed.4id0TX6O`. `APFS_DATA_REARMED=YES` and `FULL_BRIDGES_180S_REARM=PASS_NO_FRAMEWORK_STOP`. Never reuse consumed guest Data or delete `data.consumed` to bypass checks.
6. **Important profile-preflight nuance (P/S):** the rearm wrapper's **default** read-only check printed `SM8850_FULL_RUN_THERMAL_BRIDGE=ACTIVE_BRIDGES_1_ROOT_MONITOR_MANDATORY`; it was not proof a root monitor had started. A separate **explicit** tokenized preflight subsequently printed:
   ~~~text
   SM8850_SOFT_THERMAL_GUARD=OFF_NOT_SPAWNED
   SM8850_CPU_CAP=DISABLED_NO_ROOT_WORKER
   SM8850_KERNEL_FIRMWARE_THERMAL_PROTECTION=UNCHANGED
   SM8850_FULL_RUN_THERMAL_BRIDGE=NO_ROOT_THERMAL_GUARD; HOST_READ_ONLY_TELEMETRY_ONLY
   SM8850_FULL_RUN_CPU_CAP=DISABLED_NO_ROOT_WORKER
   SM8850_NO_GUARD_XNUHOST_ADMISSION=STAGED_RUNTIME_COMPATIBLE
   NO_USERSPACE_THERMAL_180S_PREFLIGHT=PASS_NO_FRAMEWORK_STOP_NO_DATA_CONSUMPTION
   ~~~
   No second rearm was needed just to check this profile.
7. **Recovery never became certified (P):** `WATCHDOG_QUALIFICATION=UNVERIFIED_REBOOT_ONLY`, legacy candidate `a:82`, `PHYSICAL_THERMAL_WATCHDOG_QUALIFICATION=NOT_VERIFIED`, `UNASSISTED_RETURN_TO_ONEUI=UNVERIFIED`. Preflight PASS was **admission**, not permission to claim safe unattended operation.

## 2. Physical guest, display, brightness and return

| Finding | Observation | Classification / limit |
| --- | --- | --- |
| Actual Framework takeover | `FRAMEWORK_TAKEOVER=CONFIRMED` | P; current trial, not preflight |
| iOS boot/UI | `IOS_GUEST_READY=OBSERVED`; `IOS_DISPLAY_FIRST_FRAME=OBSERVED` | P; real guest and first displayed frame |
| 8 guest vCPUs | Allowed host mask `0-7` | P; not proof of 8 independently pinned CPUs throughout |
| GPU acceleration | KGSL 3D backend log observed and active backboardd fences | P/A; **not** complete Metal/Vulkan conformance |
| Brightness | Operator could move brightness control and the screen adjusted to desired brightness | **Human physical observation**; response jitter during slider drag, no per-brightness latency measurements |
| Perceived animation | Operator estimated ~30 FPS with occasional lag/brief frozen frames | **Subjective observation**, *not* measured continuous FPS |
| Reboot outcome | New Android boot completed, boot reason `reboot,oneios-sm8850-reboot-return`; `BOUNDED_TAKEOVER_RESULT=POST_REBOOT_OBSERVED_SESSION_CAUSE_NOT_PROVEN` | P; root-owned original request and independent watchdog action unverified |
| Host exit | `EXIT=4` after rootless reboot witness | Evidence-qualification failure; **does not prove an iOS crash** |

Rootless post-reboot properties must not be mistaken for a signed receipt from the original OneOS return requester. Reboot-only recovery, not in-place handback, is the expected experimental path on this device.

## 3. High-priority heat and memory evidence

**P0 thermal (chat-reported host passive telemetry, not re-parsed in this document):** one CPU thermal-zone sample reached **104.8 °C** around T+61s; this is an **internal junction sensor**, **not** surface/skin temperature, vendor trip certification or sustained temperature. The guard/cap-OFF mode has **no root software temperature abort or root 28% CPU cap worker**, regardless of remaining kernel/firmware controls. **Do not repeat this profile.**

Earlier chat summary samples (separate from the verified guest/display archive; approximate T+):
| T+ | GPU reported clock | GPU busy sample | CPU sensor maximum |
| ---: | ---: | ---: | ---: |
| ~17s | 222 MHz | 19% | 82.2 °C |
| ~30s | 222 MHz | 24% | 93.1 °C |
| ~61s | 222 MHz | 15% | **104.8 °C** |
| ~91s | 222 MHz | 37% | 96.2 °C |
| ~121s | 1300 MHz | 5% | 89.6 °C |
| ~171s | 1300 MHz | 23% | 65.0 °C |

The chat also reported sampled `KGSL throttling=0`. Sparse GPU sampling **cannot** exclude short thermal/DVFS events or establish that the GPU always operated at 222/1300 MHz. Do not infer CPU and GPU sensors share units, polling windows or thermal safety ceilings.

**A/P memory details:**
- Guest RAM **4096 MiB**, fixed/prefaulted/locked; host reports **0 MiB guest swapped out** in the cited sample, while host Linux swap is a distinct counter.
- `ANDROID_MEMAVAILABLE_MIN_MIB=3066` in the parsed log; thus memory pressure exists as a question, **not** proven out-of-memory or jetsam.
- In a guest host-memory snapshot, page tables about **503 MiB**, `ShmemPmdMapped=0`, KGSL `imported_mem=1,012,707,328` bytes. These are sampled counters, not evidence of a GPU memory leak without a time series.
- A guest thermal message at host monotonic ~5237s showed `case=42.6 °C, SoC=57.2 °C, battery=38.6 °C`. This is a **different sensor/clock observation** and must not overwrite the 104.8 °C CPU-zone peak.

## 4. Display posting, input and frame pacing — measured, not actual FPS

| Archived performance field | Current session | Interpretation |
| --- | ---: | --- |
| 5-second display windows | **36** | Collection windows, not equal-duration animation tests |
| Windows with at least one post | **26** | 10 windows had no post; static UI is allowed to post nothing |
| Peak SurfaceFlinger posted-buffer rate | **57.42 posts/s** | Shows near-60 buffer posting is possible in a window; **not** guest FPS |
| Median **estimated active-post cadence** | **43.91 Hz** | Estimated from short inter-post gaps; **not** certified 43.91 FPS |
| `ANativeWindow_lock` max | **11.63 ms** | Buffer acquisition outlier |
| Framebuffer CPU copy max | **6.504 ms** | Copy cost alone cannot explain hundreds-of-ms input delays |
| `ANativeWindow_unlockAndPost` max | **4.07 ms** | Post outlier |
| Touch summaries | **16** | The parser's logged gesture summaries |
| Touch summaries with no next guest frame **before summary ended** | **9/16** | 56.25%; **not** 9 permanently lost events |
| Largest measured touch-down → next guest frame | **263.9 ms** | Measured among successful touch/frame pairs only |
| Largest `gap_p95` reported | **31,754.794 ms** | Cross-window posting gap; *not* proof of a 31.75-second interactive freeze |

**Source methodology (S):** `runtime/display/src/frame_perf.c` accumulates post timestamps; `xhd_perf_active_cadence` admits inter-post gaps ≤250 ms and ≥3 observations; a post to SurfaceFlinger is not proof the user saw a distinct iOS animation frame. `runtime/xnuhost/src/input.c` measures next guest frame after touch-down on a previously still screen; when the gesture summary closes first, it prints “no guest frame after the touch-down,” even if a later frame arrives. Therefore 9/16 means **unpaired within the metric's observation window**, not a 56% guaranteed dropped-input rate.

Candidate windows from `frame-stall-report.json`, in device-monotonic seconds:
| Monotonic t | Posted buffers | Cross-window gap p95 | Nearby guest CPU / traps | Touch evidence | Classification |
| ---: | ---: | ---: | --- | --- | --- |
| 5172.278 | 6 | 8,037.430 ms | 323%; 39,508/s | None paired | Possibly idle |
| 5182.291 | 52 | 1,000.000 ms | 338%; 87,011/s | None paired | Possibly idle |
| 5208.879 | 11 | 12,815.003 ms | 229%; 87,011/s | None paired | Possibly idle |
| 5249.328 | 1 | 31,754.794 ms | 169%; 39,254/s | next-frame 263.9 ms nearby | **Touch-linked candidate**, not a proven 31-second stall |
| 5264.905 | 9 | 1,000.000 ms | 163%; 39,254/s | None paired | Possibly idle |
| 5269.912 | 1 | 3,845.770 ms | 11%; 39,254/s | next-frame 125.7 ms nearby | Touch-linked candidate |
| 5280.176 | 24 | 1,000.000 ms | 117%; 19,404/s | no next frame by summary close | Touch-linked candidate |

The parser intentionally labels these as `READ_ONLY_CANDIDATES_NOT_CAUSAL_PROOF` and `SAME_SESSION_ONLY_NOT_CROSS_BOOT_PROOF`. A high CPU trap count does **not** timestamp an individual delayed frame's critical path.

## 5. Real GPU 3D, KGSL fences and policy

**Current-run negative findings (A):** `GPU_ERRORS=0`, `BACKBOARD_EXITS=0`, `SPRINGBOARD_EXITS=0`, `ASSOCIATIONS=0`; the guest reports `fence timeouts +0` in the shown 10-second windows, the tracked UI PIDs stayed `SpringBoard=30` and `backboardd=52`, and `GPU_VERBOSE_TRACE_LINES=0`. These mean **no logged fault/restart in the captured current session**, *not* zero latent GPU errors, a fully correct Metal implementation or guaranteed long-run stability.

| XNUHost monotonic time | backboardd fences | Host submit→retired mean | Host max | Notes |
| ---: | ---: | ---: | ---: | --- |
| 5171.830 | 6 | 1.444 ms | 5.739 ms | Initial activity |
| 5181.837 | 27 | 3.074 ms | 23.824 ms | First outlier |
| 5191.840 | 409 | 2.445 ms | 6.864 ms | Busy window, relatively fast fences |
| **5248.873** | **31** | **8.068 ms** | **61.656 ms** | Main observed GPU fence outlier |
| 5258.927 | 208 | 3.960 ms | 15.671 ms | Continued 3D |
| 5293.922 | 477 | 3.503 ms | 26.132 ms | Continued 3D |

The guest reports its own render-frame timing (`oneios-gpu-report`), with some windows showing `frames +426` or `frames +435`. These are **guest/bridge internal reports**, *not* 42.6/43.5 actual displayed FPS. No recorded host fence exceeded the guest's 100-ms wait slice in this session, but **61.656 ms can still cause stutter** if it blocks the frame's critical path.

**GPU policy (S/A):**
- `gpu-level=deadline`, **not** permanently top clock. Reported KGSL available bounds **160–1300 MHz** and top/lowest ratio ~8.12; foreground/render queue priority **4**, default/background **8**.
- Default predicted budget **8.3 ms at 120 Hz**, with up to **16.7 ms** interval budget, is a *policy input*, **not proof the panel posts 120 Hz or the guest hits 120 FPS**.
- `gpu: 10 s level: frames 413, at the top 51` (~5191.840); `frames 277, at the top 257` (~5258.927); `frames 566, at the top 552` (~5293.922). Deadline policy already chooses top on many busy frames; **do not blindly force 1300 MHz**.
- GPU backend is demonstrably active and no global 30-FPS cap was proven. Metal translation correctness, Vulkan conformance and sustained 60/120 FPS remain **unverified**.

### Earlier, different 180s session: EPROTO and respring (not a matched A/B)

The **prior** 2026-11-23 profile had a best-effort **28% root CPU cap**, disabled software overtemperature trip and different source/run timing. Its saved forensic report observed `GPU_COMMAND EPROTO` near 1679.681s, backboardd exit 0.557s later, SpringBoard respring, host fence max **684.274 ms**, touch-to-frame up to **725 ms**, display gap p95 **28.319s**, copy max **8.655 ms**, peak traps **34,439/s**. See `SM8850_GPU_RESPRING_TRIAGE_2026_11_23.md`. The current uncapped session had **0 recorded EPROTO/resprings** and **61.656 ms** max fence, but **different conditions/interaction and source changes make any causal performance improvement or patch cure UNPROVEN**.

## 6. CPU/virtual-memory/handoff findings from the same current XNUHost log

The end-of-session line is cumulative for **180.6 seconds**, distinct from the separate peak 30s windows:

| Metric | Cumulative count / value | Interpretation |
| --- | ---: | --- |
| Task traps | **8,889,193** (49,214/s average) | High host/guest trap throughput |
| Syscall traps | **3,921,008** (~44.1%) | Guest-to-host syscalls, not necessarily pathological |
| Fault traps | **4,897,306** (~55.1%) | *Virtual-memory faults* requiring map/fault handling; not 4.9M physical RAM failures |
| Interrupt traps | **70,879** (~0.8%) | Guest interrupts |
| Hand-offs | **8,887,087 each direction** | Host/guest release/return accounting |
| Futex sleeps | vCPU **10,993,281**; guest thread **3,380,216** | Scheduling/synchronization demand, not independently verified latency cause |
| Task map carried on release | **4,897,152** | Deferred map path |
| Task unmap | **2,716,095 queued**, **379,903 ordered** | Many TLB / mapping operations |
| Maps by release histogram | **5,471,784** | Do **not** equate this counter one-for-one with task-map count |
| Timer sets | **1,910,107**; **1,895,124** to host timer | Investigate rate and redundant re-arming |
| Peak 30s trap rate | **87,011/s** | Peak observation, **not** entire-session mean |
| Peak guest CPU percentage sample | **338%** | ~3.38 cores worth in guest sampler; not host CPU % and not saturation of all 8 vCPUs |

End-of-session histogram (microseconds unless marked otherwise):
| Operation | Mean | p50 | p90 | p99 | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| Trap→vCPU (up) | 3.49 | 3.07 | 5.12 | 10.24 | 13,577.4 µs |
| vCPU→guest task (down) | 3.60 | 2.56 | 5.12 | 12.29 | 10,936.5 µs |
| Kernel syscall | 23.57 | 3.58 | 40.96 | 196.61 | **286,599.1 µs (~286.6 ms)** |
| Kernel fault | 8.50 | 1.02 | 7.17 | 65.53 | **596,217.1 µs (~596.2 ms)** |
| Kernel interrupt | 28.25 | 14.34 | 40.96 | 196.61 | 23,415.3 µs |
| Ordered unmap | 15.44 | 10.24 | 20.48 | 49.15 | 34,922.0 µs |
| Maps by release | 12.86 | 12.29 | 20.48 | 49.15 | 13,624.8 µs |

These are **aggregated** extrema, not proved synchronous with a specific input event. The host does not show a uniformly slow handoff: mean **3.49/3.60 µs**, with rare long tails. Investigation should prioritize attribution of fault/map churn, frame-critical waits, timer re-arms, lock contention and which guest process creates the work; do **not** assume reducing raw trap count always improves displayed FPS.

**vCPU evidence:** the final `last on host CPU` sequence for vCPU0…7 was `4,5,0,1,2,3,6,7` (8 distinct last-seen CPUs). This **does not certify sustained one-to-one affinity**; inspect the configured affinity and thread placements over time. The last cumulative snapshot showed vCPU0/vCPU1 about **18,414/18,158 traps/s**, while others ranged about 1,003–3,600/s. Work is not evenly distributed; increasing the total vCPU count without profiling is unjustified.

**S source behavior:** `runtime/xnuhost/src/task.c` uses `map-defer=1` by default. Deferred map/unmap ops are carried on the next guest-thread release or ordered service batch, enforcing memory-order/TLB invariants. The source already has queue joining and a batch path; **never** disable defer/batch or relax locking to reduce counters without concurrency tests and memory-visibility proof.

## 7. Specific code correctness risk: null `ops` on an error path (source-confirmed)

In pinned `runtime/xnuhost/src/task.c`:

- `flush_pending(task *t)` can call `order(t, NULL, 0)` when pending ops exist.
- `order(task *t, const struct xs_op *ops, unsigned count)` may log an error or ≥1000-ms service wait using the **unconditional** `ops[0].op`, `ops[0].va`, `ops[0].size` and `ops[0].prot`.
- With `count == 0` and `ops == NULL`, that diagnostic branch dereferences NULL. **This is a verified potentially crashing source path**, not proven to have been exercised during the 180s session. Error/timeout handling must not create a second crash while handling the original failure.
- **Remedy proposal:** log queued op details when valid, or explicit “flush pending batch” diagnostic with safe sentinel values when `count=0`; add host regression/fault injection for timeout/error with `order(t,NULL,0)`. Preserve service locking, queued-op order and fail-closed behavior. No code fix is claimed by this document.

## 8. Guest `host_statistics64` warnings: correctness investigation, not established origin

The current guest log contains **22** occurrences of:
~~~text
vm: host_statistics64() count is larger than expected
(actual:104 > HOST_VM_INFO64_COUNT:62)
The buffer count must be passed in units of integer_t's.
~~~

Guest messages implicated callers such as `cameracaptured` and `PerfPowerServices`. This is an **Apple guest-side warning** about the request's count/buffer contract and possible memory corruption; **not direct proof** that OneiOS's XNUHost ABI translation is faulty or that corruption actually occurred. Some messages are concatenated with unrelated guest log lines, so raw line rendering must not be treated as one complete stack trace.

**Next:** examine the exact XNU `host_statistics64` MIG/ABI definition, guest call sites/count units and any OneiOS host shims at the pinned revision; prove whether the caller passes the wrong count or the port misreports a contract. Cover boundary counts with unit tests, preserve the warning until correctness is established.

## 9. Background work, UI continuity and competing hypotheses

- `ICONSERVICE_CPU_PEAK_PERCENT=68` (current), `SPOTLIGHT_CPU_PEAK_PERCENT=13`, `SPOTLIGHT_OBSERVED_WINDOWS=1`, `SPOTLIGHT_GE_80PCT_WINDOWS=0`. The earlier sessions with Spotlight ~98–102% and iconservicesagent 216% cannot be projected onto **this** session. Unobserved windows mean **unknown**, not zero.
- The UI PIDs `SpringBoard=30` and `backboardd=52` were stable in the captured log; no logged backboardd exit/SpringBoard respring. This is an important *current* improvement in observation, not proof of a permanently fixed race.
- Touch/brightness jitter could arise from CPU guest work, GPU fence waits, SurfaceFlinger, VSync, buffer acquisition, guest compositor or synchronous brightness control. No brightness callback/latency trace currently identifies the exact source.
- `SETTINGS_ICON_COLD_WARM_LATENCY=MANUAL_OBSERVATION_REQUIRED`: no standardized same-session cold/warm Settings measurement was made; do not claim a cold-cache fix.

## 10. Ordered work / acceptance gates (do the work offline first)

| Priority | Owner | Finding → actionable work | Evidence needed to close |
| --- | --- | --- | --- |
| **P0 / STOP** | **OneOS + OneiOS** | **104.8 °C CPU sample** on guard-OFF/cap-OFF. Restore and independently qualify a root-owned fail-closed thermal monitor, trusted sensors, bounded abort, do not bypass vendor controls | Same-boot, session-bound sensor and recovery evidence; validated thresholds/cutoffs; no more unguarded full-run retries |
| **P0 / STOP** | **OneOS** | Reboot-only watchdog candidate `a:82` and rootless return receipts insufficient | Exact root-owned requester/deadline/feeder records and verified unattended One UI return, without assuming boot reason suffices |
| **P0–P1** | **OneOS + OneiOS** | Preserve complete matching logs/return receipts across reboot and root loss | Consistent archive token, boot generation, pre/post provenance; no empty/ambiguous success |
| **P1 correctness** | **OneiOS** | `task.c` null `ops[0]` on `order(t,NULL,0)` diagnostic path | Host fault-injection test covers 0-count timeout/error with no crash and correct return status |
| **P1 performance** | **OneiOS** | 8.89M traps, 4.90M faults, 2.72M queued unmaps and long-tail syscall/fault latency | Per-vCPU/per-process fault reason, batching/ordering latency, p50/p95/p99 and mapped touch-to-frame timeline |
| **P1 ABI** | **OneiOS / guest** | 22 `host_statistics64` count warnings 104 vs 62 | Proven caller vs ABI root cause; count/buffer tests; no suppressed diagnostics |
| **P1–P2 GPU** | **OneiOS** | KGSL 3D present, max 61.656ms fence despite no EPROTO this run | Frame-correlated submit/retire + guest completion timing; controlled safe optimization, no forced max clocks |
| **P2 display** | **OneiOS** | Estimated 43.91 Hz active-post cadence, 9/16 no paired guest frame, some 0-post windows | One-clock event pairing: touch→guest composition→flush→buffer lock/copy/post→physical presentation; actual FPS/jank histogram |
| **P2 brightness** | **OneiOS** | Panel brightness changes but slider may stutter | Trace brightness service/callback and scheduling without breaking working functional path |
| **P2–P3 scheduling** | **OneiOS** | 8 distinct last-seen CPUs, not affinity proof; workload skew and timers | Explicit vCPU/task placement, scheduler waiting/blocking times, no global governor changes |
| **P3 memory** | **OneiOS** | 4GiB locked RAM, 503MiB page-table snapshot, GPU imported memory | Longitudinal memory/blobs/leaks, no global hugepage/sysctl hacks |
| **P3 reproducibility** | **OneiOS** | Current posts are not actual FPS; previous sessions differ | Versioned immutable evidence with SHA/session pairing, matched gesture A/B only after P0 clearance |

### Offline-only reproduction and validation (no new takeover, no ADB required)

~~~bash
cd ~/projects/OneiOS
ARCHIVE=out/sm8850/takeover/collect-180s-uncapped/device-logs.tar

python3 scripts/phone/sm8850-archive-forensics.py --archive "$ARCHIVE"
python3 scripts/phone/sm8850-gpu-respring-forensics.py --archive "$ARCHIVE"
python3 scripts/phone/sm8850-frame-stall-report.py --archive "$ARCHIVE"

make -C runtime/xnuhost test
make -C runtime/display test
python3 scripts/phone/test-sm8850-ios-interactive-perf.py -v
JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci
~~~

**Do not count the commands above as executed by this GitHub documentation change.** Device logs, APFS images, device serial numbers and ephemeral root credentials are intentionally not committed. New physical acceptance is a **separate, risk-reviewed milestone after P0**, not a request to repeat uncapped 180 seconds.

## 11. Final disposition / facts that remain true

- **Proven functional:** full Framework takeover reached iOS guest ready and first frame; physical brightness changes; KGSL 3D usage with successful fences; current capture shows no logged EPROTO or UI respring.
- **Proven unresolved:** heterogeneous frame submission, touch-to-next-frame outliers, high VM/fault/timer activity, a ~61.7ms GPU fence outlier, 22 guest ABI warnings, source error-path null dereference risk.
- **Not proven:** sustained 30/44/60/120 FPS, seamless brightness, kernel/GPU conformance, root cause of jank, superiority of disabling CPU caps, full-device thermal safety, independently qualified watchdog and unattended recovery.
- **Release gate:** **BLOCKED P0**. Do not change power/thermal limits, force GPU 1300 MHz, loosen APFS isolation, or use a second long live run to measure FPS. Diagnose existing evidence and fix source/tests locally first.
