# SM8850 native synthetic P0 profiler receipt — 2026-11-24

## Provenance and limitations

Operator reported `NATIVE_BENCHMARK=PASS` at OneiOS `08a5b8576e8da8c10c3a2ac3d989bf75240cba3f`, OneOS `f5c1b4a44fc45d78987694a230f7ffabb213e99c`. Raw logs/summary remain on the operator's CachyOS host: `/tmp/oneios-native-profiler.rKeztr`. The values below are the supplied console receipt; raw per-run distributions have not been independently inspected.

- SM-S948B / SM8850 / firmware S948BXXS4BZIG, native aarch64, Android running, shell UID 2000; 4 KiB host pages, 39-bit user VA, 19.2 MHz counter, PAC supported, task factory/seccomp selftest passed.
- 3 vCPUs, 256 MiB, synthetic freestanding test kernel, 2D, no display/input/bridges, cpu-pin=0, map-defer enabled, no root or takeover. One discarded warmup pair + three measured alternating profiler OFF/ON pairs, all eight runs accepted by parser with 11 metrics.
- Selftest warned that vm.max_map_count could not be read/raised (reported 0). This is not an established actual kernel limit, and does not justify changing sysctl, elevating privileges or bypassing security. The small workload completed.
- SHA256: xnuhost `16587e4c88e4ab5d0bc23b80e00fc711ebb13c5265ebff79264f8b742f2c8a10`; kernel.kc `c42b4df38ab1f0ee2a7e737a048b76683c1b79e4a802ce5eb72d30689c51e9d0`; os.img `90cefe7883d605d209801b83af9561e0ce16a577f5f96dc3dbce90d39537d1f7`.

## Median per-run means (us) and median paired changes

| Metric | OFF | ON | Paired % |
|---|---:|---:|---:|
| syscall_round | 81.711 | 81.874 | +0.28 |
| syscall_up | 42.126 | 42.390 | +1.24 |
| syscall_down | 39.508 | 39.333 | -0.34 |
| fault_resolve | 33.556 | 31.863 | -6.43 |
| task_map | 0.109 | 0.105 | -7.89 |
| task_unmap | 0.104 | 0.102 | -12.82 |
| timer_kick | 21.429 | 21.396 | -3.61 |
| discard_one | 2.977 | 2.946 | -3.42 |
| discard_64 | 98.469 | 98.762 | -2.51 |
| fill_resident | 0.755 | 0.743 | -2.17 |
| fill_given | 4.456 | 4.435 | -4.26 |

Profiler syscall round-trip overhead observed +0.28% in this workload; negative deltas are not evidence of acceleration. Three pairs are insufficient to establish universal overhead or statistical significance. Map/unmap values measure the enqueue calls, not completion or VM/TLB cost.

## Last profiled run (not pooled)

| Host wait stage | n | mean us | p95 bucket us | p99 bucket us | max us |
|---|---:|---:|---:|---:|---:|
| order_locks | 115 | 0.06 | 1 | 1 | 0.94 |
| order_with_deferred_ack | 107 | 505.55 | 1000 | 1000 | 910.10 |
| order_direct_ack | 8 | 84.09 | 256 | 256 | 153.07 |
| release_locks | 10510 | 10.19 | 1 | 512 | 928.28 |
| release_ack | 10310 | 34.75 | 64 | 256 | 912.45 |

No aborted/invalid acknowledgment samples. Deferred orders have larger individual waits but only 107 samples, compared with 10,310 release acknowledgments and 25,001 classified BSD intervals on vCPU0. Approximate sums (54.1 ms and 358.3 ms respectively) are overlapping wall-wait observations, not a disjoint CPU-time breakdown. vCPU0 futex wait outcomes: 32,323 returned, 28 EAGAIN, 2,000 EINTR, no timeout/other; timer calls had zero host errors and one same-future skip. vCPU masks 0-7, migrations 160/18/2. No observed classified >=16.667 ms intervals in this synthetic run. None of these are full iOS UI or frame metrics.

## P1 decision

Prioritize the frequent trap/handoff/release path (round-trip 81.7 us; both directions about 40 us). Keep map-defer and TLB ordering intact; no evidence to disable batching. Do not change timer policy based on a deliberately rearming timer workload. Existing cpu-pin=2 requests co-location of vCPU and its task/service threads, and docs/booter.md documents earlier synthetic ARM64 improvement; existing spin knobs default OFF and shared-core spins previously regressed latency. Before altering runtime, compare existing unpaired and paired placement in one bounded experiment with the exact same inherited CPU set (0-2), fixed 3 vCPUs, profiler ON, map-defer=1, spin-host=spin-task=0.

`python3 scripts/phone/bench-sm8850-task-placement.py --self-test` checks parsers; `python3 scripts/phone/bench-sm8850-task-placement.py` executes only the validated artifacts on normal Android. It verifies artifact hashes, device/firmware/shell, allowed CPUs and final vCPU masks, uses isolated Data directories, alternates one warmup plus three measured pairs, collects per-run logs and summaries, fails closed if any run or mask check fails. A battery temperature admission check is only for this synthetic experiment, not a substitute for firmware thermal protection. Task/service-thread affinity is requested by the existing implementation but not independently proven by vCPU masks. This compares placement within CPUs 0-2, not the previous full allowed 0-7 baseline, not 4/6/8 vCPU topology, and not an FPS guarantee. No default, global policy, recovery or OneOS change.


## Native CPU placement A/B — operator receipt PASS

Checkout `a56a49e30cc2a38842daa74569d7de9599adf822`; the same verified P0 binary and test image hashes above. Android shell, 3 vCPUs, 256 MiB, profiler ON, map-defer=1, spin-host/task=0; both conditions inherit CPUs 0-2. Eight successful runs, one warmup pair discarded and three measured alternating pairs. Final vCPU masks 0-2 for all unpaired runs and 0/1/2 for all paired runs. Individual task/service affinity was not independently verified. Battery 29.4-29.5 C (battery temperature only, not SoC junction). Raw receipts: `/tmp/oneios-native-placement.b6erwbod`.

| Metric | Unpaired us | Paired us | Paired delta % |
|---|---:|---:|---:|
| syscall_round | 6.199 | 8.302 | +33.92 |
| syscall_up | 3.314 | 4.318 | +30.51 |
| syscall_down | 2.881 | 3.982 | +37.94 |
| fault_resolve | 15.320 | 19.936 | +30.13 |
| task_map | 0.031 | 0.031 | +3.33 |
| task_unmap | 0.028 | 0.032 | +7.14 |
| timer_kick | 12.883 | 17.991 | +39.56 |
| discard_one | 2.353 | 2.685 | +14.11 |
| discard_64 | 79.127 | 79.998 | +0.98 |
| fill_resident | 0.604 | 0.605 | +0.17 |
| fill_given | 3.604 | 3.749 | +4.02 |

Reject the tested same-core pairing candidate for this synthetic 3-vCPU configuration. The prior unrestricted 0-7 run reported 81.874 us with profiler ON, versus 6.199 us here: approximately 13.2x between sessions, not a matched mask speedup. CPU frequency/residency and scheduler/background state were not controlled between these sessions. Do not extrapolate to an eight-vCPU full bridge configuration, change production defaults or claim UI FPS gains.

## P1 first code batch (design and test plan)

Optimize the freestanding stub's signal-state copies: use volatile, naturally aligned, alias-safe 64-bit/32-bit scalar accesses where possible, exact byte fallback otherwise. The old byte loop touched GPR, FPSIMD, ESR and SVE state each trap; this reduces scalar copy iterations without modifying the ABI, register values, memory ordering, seccomp, wait/wake protocol, VM mapping, timer policy, or thermal/CPU policy. No SIMD instructions are allowed by existing stub compiler flags. Host ASAN/UBSAN tests cover every offset pair 0-15, exact lengths including GPR/FPSIMD and guard pages; test kernel checks all 32 vectors, untouched GPRs, FPCR/FPSR/NZCV. Full local CI required.

Archive the exact old xnuhost binary before rebuilding; its hash is pinned above. The extended placement script accepts `--baseline-binary PATH` and compares that binary with the new CI-built binary on the **same current test kernel and OS fixture**, using four conditions (old/new on 0-2 and 0-7, both unpaired), one warmup block and three measured rotating blocks. Each run verifies native selftest/admission, artifacts and vCPU masks, records raw metrics and battery checks. This distinguishes code improvement from mask/session effects without changing production CPU affinity. Timing remains synthetic, not representative iOS or an eight-vCPU benchmark; no change to OneOS or physical release gates.


### P1 CI launch correction and CPU topology

The operator's first P1 local CI attempt at `f56964b` stopped before compilation with `Permission denied`: the consolidated Git tree edit accidentally changed `scripts/ci-local.sh` from mode 100755 to 100644. Restore the original executable bit without altering its contents. Recursive tree comparison against `a56a49e` found no other tracked mode changes. The old binary was successfully archived and its hash validated; reuse it. The corrected CI and native receipts are recorded below.

For both placement conditions in the previous A/B, the inherited allowed mask was 0-2; CPUs 6 and 7 were excluded in both conditions. vCPU0 did most of the trap benchmark, so a difference among CPUs 0-2 or scheduling within that group is still plausible. The matrix now records read-only per-CPU capacity, cluster/core ID, related CPU list and reported hardware/configured maximum frequencies in kHz from Android sysfs, with unknown for unreadable fields. Those are static topology/policy values, not measured sustained clock rates. The old/new 0-2/0-7 matrix remains unchanged; a separate equally sized prime-rich CPU set would require topology evidence and a matched experiment, not assumed numbering. No affinity or thermal policy change.


## P1 register-copy validation — full local CI and native Deep Doze matrix PASS

Operator receipt at `f9893c73ddec1b583cd1efbe6e010c0c02a8a2e7` (OneOS remains `f5c1b4a44fc45d78987694a230f7ffabb213e99c`): executable bit restored; full CachyOS CI PASS, 11,051 stub-copy checks, 67 task-profiler checks, 14,354 XNUHost host tests, 956 GPU leak checks, ARM64 profiler OFF/ON and placement parser PASS. CI log: `/tmp/oneios-p1-copy-ci.M9GFh7.log`.

First native P1 matrix passed at `/tmp/oneios-native-placement.ezxz2_lo`, but the operator used the phone concurrently; timing is confounded (do not use it as the primary comparison). Second matrix: `/tmp/oneios-native-placement.7igxs42l`, console `/tmp/oneios-p1-doze.DareBS.log`, 16 valid runs, three measured rotating blocks after one warmup. Deep IDLE and screen=false confirmed at start/end, battery 30.7-30.9 C, forced idle released at exit. Not a guarantee of suspend, steady clock, or no background activity. Raw runs.json remains on operator host.

Firmware confirms CPUs 0-5 share cluster 0, capacity 741 and advertised max 3,628,800 kHz; CPUs 6-7 share cluster 1, capacity 1024 and max 4,742,400 kHz. Both scaling maxima match at observation. These are advertised limits, not observed residency or actual clock traces.

| Metric | Copy code on 0-2 paired delta | Copy code on 0-7 paired delta | Old code widening mask paired delta | New code widening mask paired delta |
|---|---:|---:|---:|---:|
| syscall_round | -7.39% | -2.94% | +51.80% | +104.82% |
| syscall_up | -8.54% | -1.80% | +48.71% | +104.77% |
| syscall_down | -6.58% | -4.15% | +55.06% | +104.77% |
| fault_resolve | -1.89% | +0.88% | +0.16% | -1.74% |
| timer_kick | -14.61% | +5.31% | +2.36% | +19.65% |

Separate per-condition median syscall means: old/new on 0-2 = 8.325/5.853 us; on 0-7 = 12.613/11.988 us. Do not calculate the paired median delta from ratios of separate medians. Only three measured blocks; mixed secondary metrics (especially tiny enqueue costs near counter resolution) do not establish universal improvements. Retain the exact scalar copy candidate provisionally based on correctness and favorable syscall signal, not a proven full iOS speedup. Wider mask is unfavorable for this synthetic workload, not evidence that Prime cores are intrinsically slower or that production affinity should change.

Next optional focused topology study uses only the existing validated P1 candidate binary and fixture hashes from the completed Doze runs.json. Three equal-cardinality masks: 0-2 (hex 7), 3-5 (hex 38), and 5-7 (hex e0; one regular plus two Prime cores). All cpu-pin=0, same 3 vCPU workload and existing safety/admission checks. Require Deep IDLE and screen off before/after every run, exact final vCPU mask, and unchanged runtime source. One warmup and three measured rotating blocks. No rebuild, full CI rerun, root, takeover, clock/thermal changes or new default. This isolates mask composition at fixed cardinality better than 0-2 vs 0-7 but does not isolate Prime-only behavior, actual CPU residency, or full iOS scaling. Keep P1 VM, timer and fault optimizations evidence-gated; P0 frame/ABI and physical release gates remain open.


## Equal-size CPU topology study — operator receipt PASS

Checkout `fabab2d0c5d3be48f415ca03f78359aa2abb7716`, unchanged candidate runtime from `f9893c7`, fixture hashes verified by prior Doze runs.json. All 12 runs passed, one warmup block plus three measured rotating blocks. Same 3 vCPU workload, profiler ON, cpu-pin=0, spin=0 and map-defer=1. Final vCPU masks match each requested CPU set. Deep IDLE and screen=false checked before/after every run; battery 29.6-29.9 C, normal idle policy restored. Logs on operator host: `/tmp/oneios-native-placement.d_yxo9l1`, `/tmp/oneios-p1-topology.Fr2nZT.log`.

| Metric | 0-2 us | 3-5 us | 5-7 us | 3-5 vs 0-2 paired % | 5-7 vs 0-2 paired % | 5-7 vs 3-5 paired % |
|---|---:|---:|---:|---:|---:|---:|
| syscall_round | 5.673 | 5.641 | 14.011 | +0.18 | +144.21 | +149.66 |
| syscall_up | 2.972 | 2.968 | 6.722 | +0.34 | +121.03 | +129.42 |
| syscall_down | 2.697 | 2.678 | 7.285 | -0.44 | +169.97 | +172.03 |
| fault_resolve | 15.655 | 15.374 | 28.673 | -2.25 | +83.16 | +87.37 |
| task_map | 0.033 | 0.033 | 0.030 | -12.12 | -12.12 | -9.09 |
| task_unmap | 0.033 | 0.032 | 0.029 | -3.03 | -12.12 | -9.38 |
| timer_kick | 15.264 | 14.639 | 122.438 | -4.09 | +913.81 | +754.49 |
| discard_one | 2.389 | 2.449 | 3.581 | +4.04 | +52.08 | +49.08 |
| discard_64 | 82.421 | 81.852 | 80.556 | +0.43 | -0.89 | -0.19 |
| fill_resident | 0.603 | 0.607 | 0.601 | +0.83 | -0.33 | -1.15 |
| fill_given | 3.728 | 3.712 | 7.443 | -0.97 | +101.27 | +103.25 |

The two 3-core masks inside cluster 0 were similar for syscall round-trip. The mixed 5-7 mask (one 3.6288 GHz core and two 4.7424 GHz Prime cores) regressed syscall, fault and timer latency. This measures mask composition, not a controlled Prime-only test or individual core IPC; no residency/frequency trace proves the cause. The old same-core pairing regression is specific to its tested mask/workload. Do not automatically favor Prime cores for trap-heavy paths or remove them from production 8-vCPU use. No additional CPU microbenchmark required for this source batch. Preserve full-bridge affinity defaults, governor/thermal safeguards and all release gates.

## Consolidated VM/display source batch (local CI receipt PASS)

- P1.1: extend existing deferred map coalescing to immediately adjacent descending virtual and RAM file ranges with equal protection. No queue-capacity, unmap, TLB barriers or lock changes. Unit tests reject noncontiguous/protection/overlap cases; freestanding test exercises both backing pages and later unmap. One fewer host mmap per eligible join; occurrence rate and latency benefit remain unmeasured.
- P2.4: collapse full-width, tightly packed, same-layout BGRX/BGRA or RGBA16F copy into one exact memcpy. Preserve per-row copies for padding/partial damage and all conversions. Test both formats, nonzero y, padding and surrounding bytes.
- P0.3/P2.1: distinguish post attempts, errors and successful valid-content posts. A locked buffer must be released; failed unlockAndPost or invalid copy terminates the helper with an error, preserves pending trace for final reporting, does not increment valid post cadence or trace latency. This is not physical presentation.
- P0.3: use MSG_TRUNC to distinguish oversized XHDF records from valid v3, preserve complete legacy rectangle for unknown extensions, count malformed metadata even before the first valid trace, and mark batches with missing/invalid/legacy metadata or seq gaps as unknown rather than single-source. No protocol layout change.
- Full local CI once, no ADB/physical benchmark as part of CI. Physical GPU/frame acceptance remains pending.


## VM/display local CI and CPU scaling — operator receipt PASS

Runtime source `72a54f6b13f725756500c23e0c4c370813647b31`; benchmark checkout `cbab66aa1f551f5c2c943d84ef4d0fdadf7f84f0`. The scaling harness accepted the successful full local CI log at `/tmp/oneios-vm-display-ci.9UPjHk.log` for the exact runtime source. The operator supplied the harness receipt, not the complete CI log; detailed individual VM/display check counts are not asserted. Native run directory `/tmp/oneios-cpu-scaling.vf6i0k4v`. Parser self-tests PASS; all 40 runs passed, one warmup block and three measured blocks. Normal Android shell, forced Deep Doze checked per run, battery 28.8-28.9 C, idle policy restored. Same synthetic fixtures, profiler on, no bridges, no input, 2D/no display, no clock or governor changes.

### Latency (3 vCPUs; inherited mask; no per-core pin)

| Metric | 0-2 us | 0-5 us | 0-7 us | 0-5 paired delta | 0-7 paired delta |
|---|---:|---:|---:|---:|---:|
| syscall_round | 5.632 | 11.704 | 11.987 | +107.81% | +112.26% |
| syscall_up | 2.962 | 5.983 | 6.069 | +101.99% | +106.71% |
| syscall_down | 2.692 | 5.698 | 5.871 | +111.66% | +117.69% |
| fault_resolve | 15.132 | 15.025 | 14.951 | -0.71% | -2.08% |
| timer_kick | 14.187 | 14.570 | 16.865 | +4.45% | +19.79% |

The 0-5 regression occurs without access to either Prime core, so cross-cluster migration alone cannot explain prior results. Scheduler placement, idle/wake behavior, frequency and cache effects remain hypotheses; no measured causal attribution.

### Parallel (all configured vCPUs active)

| vCPUs | Allowed host CPUs | Placement | Median wall ms | Median rounds/s | Median reported scaling |
|---:|---|---|---:|---:|---:|
| 2 | 0-1 | shared | 28 | 35714 | 1.96x |
| 2 | 6-7 | shared | 18 | 55556 | 2.89x |
| 6 | 0-5 | shared | 35 | 85714 | 4.12x |
| 6 | 0-5 | one core per vCPU | 23 | 130435 | 6.19x |
| 6 | 0-7 | shared | 38 | 78947 | 4.57x |
| 8 | 0-7 | shared | 39 | 102564 | 5.54x |
| 8 | 0-7 | one core per vCPU | 51 | 78431 | 3.61x |

Matched median wall-time deltas: 2 regular -> 2 Prime -35.71%; 6 shared 0-5 -> 6 pinned -34.29%; 6 shared 0-5 -> 6 shared 0-7 +8.57%; 8 shared -> 8 pinned +8.33%. Reported per-condition medians and medians of per-block deltas are different statistics. Parallel workload is 500 rounds of 100,000 guest loop iterations plus one syscall per active thread, with integer-ms wall time; reported scaling is relative to that run's own single-thread phase, not a common baseline. No universal scaling efficiency or actual iOS UI FPS is inferred from apparent superlinear values.

### Decision

The six-core individually pinned candidate wins this parallel benchmark; small shared masks win the earlier single-dominant-vCPU latency workload. Prime cores are faster in the matched two-core compute-plus-trap workload. Eight individually pinned cores are unfavorable in this sample; 8-vCPU shared is the better measured 8-vCPU candidate. This overturns a blanket recommendation against per-core pinning. The 6+2 mixed policy (six vCPUs restricted to cluster 0 and two to cluster 1 within one guest), 4-vCPU scaling, and representative full-bridge iOS workloads remain untested. Do not set guest cluster roles or production affinity based on these results alone. Stop repeated synthetic CPU benchmarks for now; proceed to GPU submission/fence/scanout attribution and evidence-driven optimization. No physical takeover, default CPU-policy changes, thermal changes or release-gate relaxation.


## Framework ON/OFF exploratory CPU comparison — 4/4 matched cases PASS

Operator console receipt: checkout `e0389854b6209bfff036e486f6bc262c114e42b0`, unchanged runtime source `72a54f6b13f725756500c23e0c4c370813647b31`, CI receipt `/tmp/oneios-vm-display-ci.9UPjHk.log`, evidence directory `/tmp/oneios-framework-cpu.1_czgvws`. All parser/plan self-tests passed. Four ON baseline cases and their four OFF counterparts passed with the requested vCPU masks, using the existing 20-second Framework-only smoke window. Framework stop confirmed by existing lifecycle; subsequent new Android boot observed via unprivileged ADB. No full iOS/GPU3D run, APFS rearm, thermal policy switch or production placement change. Root-side stage upgrade reported PASS and preserved its rollback backup. No independent recovery qualification is inferred.

| Workload | Framework ON | Framework OFF | OFF vs ON |
|---|---:|---:|---:|
| 3 vCPU mask 0-2, syscall round (us) | 7.912 | 7.986 | +0.9% |
| 3 vCPU mask 0-2, fault resolve (us) | 19.754 | 15.554 | -21.3% |
| 3 vCPU mask 0-2, timer kick (us) | 15.264 | 16.091 | +5.4% |
| 3 vCPU mask 0-5, syscall round (us) | 12.220 | 11.353 | -7.1% |
| 3 vCPU mask 0-5, fault resolve (us) | 15.554 | 15.003 | -3.5% |
| 3 vCPU mask 0-5, timer kick (us) | 15.187 | 17.221 | +13.4% |
| 6 vCPU pinned 0-5, parallel wall (ms) | 18 | 31 | +72.2% |
| 6 vCPU pinned 0-5, rounds/s | 166667 | 96774 | -41.9% |
| 8 vCPU shared 0-7, parallel wall (ms) | 43 | 32 | -25.6% |
| 8 vCPU shared 0-7, rounds/s | 93023 | 125000 | +34.4% |

This is **one** matched block, not medians over three measured blocks. The ON arm was forced Deep Doze, then idle force released before Framework stop; OFF idle state, CPU frequency, residency, thermal readings and task-thread placement were not independently matched. Thus no isolated causal estimate of Framework overhead, or statistical significance, is claimed. The raw native logs remain on the operator host. The near-unchanged 0-2 syscall latency suggests that stopping Framework alone is not sufficient to eliminate handoff cost. The two parallel candidates reverse their throughput ranking after Framework stop; do not select a production affinity based solely on the earlier Deep Doze ranking. Retain 8-vCPU shared and 6-vCPU pinned as workload-dependent candidates. The prior seven parallel conditions have only two matched Framework OFF observations: 2-regular, 2-prime, 6-group, 6-wide and 8-pinned remain unmeasured OFF, as does 3-vCPU latency mask 0-7. Do not label the full matrix completed or require another live run simply to repeat the four observations. GPU/display development can proceed independently.


## Full Framework ON/OFF matrix — 30-second window, 10/10 matched PASS

Operator receipt: OneiOS `c2934ae556a245271c39dc93d7e1b3c11e3df43a`, OneOS `51a05e95c2a14ecc1d0ca981229d8481ec882c29`, unchanged runtime source `72a54f6b13f725756500c23e0c4c370813647b31`. Local CI receipt `/tmp/oneios-vm-display-ci.9UPjHk.log`; full console log `/tmp/oneios-framework-30s.K45P2F.log`; evidence directory `/tmp/oneios-framework-cpu.ctnn_ija`. Bash syntax and all 29 host-only takeover tests passed; parser/plan self-tests passed. Existing root stage upgraded with backup preserved. Requested 30-second smoke confirmed at preflight and live state; all 10 ON and 10 OFF workloads passed with expected vCPU masks; a new healthy Android boot was subsequently observed. No full guest, GPU3D, APFS rearm or thermal-policy change. This is a bounded synthetic CPU observation, not production iOS performance or recovery acceptance.

### Latency (3 vCPUs, per-run means in us)

| Host mask | Metric | ON | OFF | OFF vs ON |
|---|---|---:|---:|---:|
| 0-2 | syscall_round | 8.076 | 7.239 | -10.4% |
| 0-2 | fault_resolve | 19.305 | 16.109 | -16.6% |
| 0-2 | timer_kick | 19.231 | 15.568 | -19.0% |
| 0-5 | syscall_round | 11.815 | 11.428 | -3.3% |
| 0-5 | fault_resolve | 15.492 | 15.361 | -0.8% |
| 0-5 | timer_kick | 14.927 | 14.959 | +0.2% |
| 0-7 | syscall_round | 11.859 | 11.218 | -5.4% |
| 0-7 | fault_resolve | 15.243 | 14.905 | -2.2% |
| 0-7 | timer_kick | 15.560 | 16.341 | +5.0% |

### Parallel (all configured vCPUs active)

| Placement | ON wall ms | OFF wall ms | ON rounds/s | OFF rounds/s | OFF throughput vs ON |
|---|---:|---:|---:|---:|---:|
| 2 regular, shared 0-1 | 19 | 20 | 52632 | 50000 | -5.0% |
| 2 Prime, shared 6-7 | 16 | 14 | 62500 | 71429 | +14.3% |
| 6 shared 0-5 | 24 | 25 | 125000 | 120000 | -4.0% |
| 6 individually pinned 0-5 | 23 | 17 | 130435 | 176471 | +35.3% |
| 6 shared 0-7 | 35 | 32 | 85714 | 93750 | +9.4% |
| 8 shared 0-7 | 44 | 66 | 90909 | 60606 | -33.3% |
| 8 individually pinned 0-7 | 48 | 23 | 83333 | 173913 | +108.7% |

Throughput is the fixed number of rounds (500 per active vCPU) divided by reported integer-millisecond wall time. Percentages here are single-pair changes, not median paired deltas across repeated blocks. The 8-vCPU pinned result is 66/23 = 2.87x the throughput of 8-vCPU shared in the OFF arm of this run. Six pinned is 176471 rounds/s and eight pinned is 173913 rounds/s (six about 1.5% higher); the difference is too small and the timing too coarse to rank them confidently or trade away two guest vCPUs. In the OFF arm, Prime vs regular equal-count throughput is 20/14 = 1.43x.

### Reconcile the two Framework-state sessions

The earlier 20-second run had six pinned throughput 166667 -> 96774 and eight shared 93023 -> 125000. This 30-second run has the opposite directions: six pinned 130435 -> 176471 and eight shared 90909 -> 60606. Both receipts are valid synthetic workload completions. Neither proves a stable causal Framework effect. The 30-second matrix completes all previously missing conditions but has one ON/OFF block; OFF CPU frequency, residency, task-thread masks, thermal and idle state were not independently matched. Do not pool these unlike sessions as a controlled multi-block A/B or infer panel FPS from parallel throughput.

**Decision:** Framework removal does not eliminate handoff cost; the 0-2 shared mask remains the best measured syscall latency among the three masks in both arms. Per-core pinning can be strongly beneficial in all-active parallel workloads when Framework is absent. Keep the existing production eight-vCPU placement unchanged (the synthetic cpu-pin=2 identity mapping is not the full-bridge topology plan). Prioritize six/eight pinned as candidates, with eight shared retained as comparison. The distinct 6+2 mixed assignment and representative iOS workloads remain unmeasured. Close the operator-requested full synthetic matrix; no additional CPU run needed before GPU submission/fence/scanout source work. No assertion of a production performance win or safety/recovery qualification.
