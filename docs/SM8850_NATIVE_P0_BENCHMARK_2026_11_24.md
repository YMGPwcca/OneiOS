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
