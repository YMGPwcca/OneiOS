# Roadmap & engineering checklist

**OneiOS 27.0.1 · Galaxy S26 Ultra · last evidence review 2026-11-21**

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

The proposed [thermal guard](SM8850_THERMAL_GUARD.md), [independent recovery acceptance](SM8850_RECOVERY_ACCEPTANCE.md) and [measured performance baseline](SM8850_PERFORMANCE_BASELINE.md) describe outstanding work; writing them has **not implemented or verified** these gates.

## P0 · Must fix before another long takeover
**Direct-parent port status (2026-11-21):** the missing Qualcomm Oryon MIDR topology from `akshaynexus/OneiOS` main `92886287724d3f9aa097dc17157281e585457500` is now in the SM8850 fork, with synthetic 2E/6P guest placement tests, retained S26 haptics ABI and an optional bench-only 8-vCPU affinity path. Companion OneOS conservative P0 source now selects that opt-in `cpu-affinity-bench=1` while keeping `bridges=0`, and its independent root guard logs session-bound thermal samples each 5 successful heartbeats. **All changes source-only; CachyOS unit/native build and phone validation not performed yet**. This is not an early CPU temperature cap: the previous CPU **101.1 C** fault at a 90 C experimental threshold remains an explicit STOP condition. Next code gate: local-first unit/build checks, then review thermal/recovery before any guest repeat. Do not enable hardware bridges or remove the full-run source lock.

**2026-11-21 new physical CPU90 300s-request result:** launch now advanced beyond the former `no_pid_birth` failure: `THERMAL_GUARD_ARMED=TRUE`, `FRAMEWORK_STOP_MARKER=TRUE`, `XNUHOST_LAUNCH_MARKER=TRUE`, external host witnessed a new normal One UI boot and operator reported an automatic reboot. The **actual guest runtime/first frame, exact original return requester and independently certified recovery remain UNVERIFIED**; the **new CPU thermal peak is now verified at 101.1 C on zone 27** (101100 mC, 11.1 C above this experiment's 90 C cutoff). Saved root thermal stream shows **FAIL_CLOSED soft_temperature_abort crossed=cpu**, distinct from earlier CPU55=75.2 C fault. Host saw ADB offline t=48.473s and new normal One UI boot t=70.541s. A return-request deadline at uptime 26646 was armed after Framework stop at 26346, but the guest did **not** last 300 s. Postboot root log still inaccessible. **Next: investigate guest CPU load/capacity and returner provenance from existing host evidence; no more CPU90 physical reruns or threshold increases**; preserve 600s lock and conservative P0 profile. See [physical status](SM8850_LIVE_STATUS_2026-11-20.md).

**2026-11-21 read-only physical subgates:** corrected OneOS CPU90-branch guard returned `P0_THERMAL_PID_BIRTH=PASS_READ_ONLY` and `P0_THERMAL_GUARD=READ_ONLY_CURRENT_BOOT_READY_NOT_CERTIFIED` on S26 Ultra. The first proves PID-birth parsing; the second proves current-boot manifest/sensor acceptance. **Neither qualifies the detached guard heartbeat, watchdog or unattended reboot-return.** Next: non-disruptive independent heartbeat/lifecycle qualification design and separate returner provenance review. No APFS rearm or guest retry needed for these receipts.

**CPU90 experiment diagnosis (2026-11-21, isolated OneOS branch):** a physical attempt never stopped Framework because the root guard source used `BIRTH=$(birth $)` instead of `BIRTH=$(birth $$)`, producing `no_pid_birth`. `control/state=failed`; no new boot or guest launch; freshly rearmed APFS Data was still marked consumed. OneOS source fix adds a passive guard PID selftest before the APFS claim and before the wrapper's rearm. **Next: validate PID selftest on the actual phone read-only**, not another physical takeover. The 75.2 C fault recorded earlier belongs to the *preceding* 55 C attempt, not this CPU90 failure.


**2026-11-21 physical 300s-request forensics:** one-shot APFS rearm PASS; 28-zone preflight PASS; *actual* root guard `soft_temperature_abort` captured CPU `cpu-0-2-1@10=75.2 C` over the conservative 55 C cutoff. Source passed `stop_android_framework()` but later comprehensive stop/deadline receipt and guest-launch proof were absent. Host saw a different normal One UI boot (ADB offline t=50.567s, new boot t=72.615s), and the operator reports no manual reset; exact root returner and watchdog transfer remain unverified. **P0 remains OPEN / no new takeover**; existing 3,358-byte switch log and thermal stream have been reviewed. Do not retry to fill missing receipts. See [live ledger](SM8850_LIVE_STATUS_2026-11-20.md) and [OneOS probe record](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-p0-thermal-reader-sim/docs/SM8850_SHORT_GUARDED_IOS_PROBE.md).

- [ ] **P0.1 — Independent thermal telemetry.** Read SoC, battery and skin sensors using an isolated, read-only component available with `bench/bridges=0`. Define trustworthy sensor selection, units, missing-sensor behavior and session-token ownership. Do **not** enable unrelated hardware bridges.
- [ ] **P0.2 — Bounded over-temperature response.** Add thermal thresholds, hysteresis and a fail-safe request to the existing OneOS reboot-return path, with deterministic logging. Keep vendor/kernel throttling intact; never force CPU/GPU clocks or disable thermal trips.
  - **Observed subresults (not P0.2 acceptance):** conservative CPU55 probe detected CPU zone 10 at 75.2 C; isolated CPU90 probe armed independently, passed Framework stop and xnuhost launch, then detected **CPU zone 27 at 101.1 C**, triggering `soft_temperature_abort`. GPU 51.3 C, DDR 54.4 C, BAT 29.4 C, LRP 32.3 C and board AP 38.2 C were below experimental limits. Peak overshot 90 C by 11.1 C; **do not raise thermal cutoffs or repeat hot experiment**. Vendor thresholds, sustained load and causal reboot caller remain unqualified. Keep normal 55 C profile unchanged.
- [ ] **P0.3 — Return provenance.** Read the last run's root-owned `return.log`, `return.outcome`, watcher/feeder evidence and `launches/*/switch.log` without another guest boot. Prove which process requested recovery and when. A reboot reason alone is not enough.
- [ ] **P0.4 — Logs that survive root loss.** Preserve per-session CPU/GPU/thermal/display and final return receipts before reboot; report previously observed guest-ready/frame markers independently of rootless new-boot metadata. Reject stale session tokens.
  - **Proven partial:** host captured preboot switch (3,358 bytes) and a separate thermal fault stream across ephemeral root loss. **Missing:** independent original `return.log`/`return.outcome` and authenticated reboot-requester trace. Prioritize a non-disruptive instrumentation design; do not relaunch the guest for logging alone.
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


### 2026-11-21 one-shot direct-parent integration source update

The user requested one completed, **offline-only** integration batch rather than per-fix phone retests. The full audit and per-subsystem status are in [SM8850 direct-parent parity](SM8850_DIRECT_PARENT_PARITY.md) (the OneOS ledger links to the OneiOS matrix). Immediate parent pins: `akshaynexus/OneiOS` main `92886287724d3f9aa097dc17157281e585457500`, `akshaynexus/OneOS` `oneios` `53abb04e7bd87c785fff7a1db3ebd0742e777eb5`. The ancestral `fahadalijaved/OneOS` was deliberately **not** treated as the parent.

Code newly added to OneiOS: `gpu3d_kgsl.c` initializes the missing virgl fence table; exact parent `0007-a830-waittimestamp-fences.patch` uses the stable timestamp wait path with explicit FENCE A/B override; three exact direct-parent Metal2Vulkan patches `0101`, `0102`, `0103` are staged after the base at 9xxx by `userland/metal/build.sh`. The already-ported Oryon CPU plan is retained; the fork's other S26 GPU tracing/thermal and native haptic/encoder fixes are not overwritten. Conservative OneOS `--mode bench --cpus 8` now pins `setway-skip=1`, `spin-host=0`, `spin-task=0`, `gpu-level=deadline`, `gpu-priority=1`, and isolated vCPU affinity, with fixed locked RAM and `bridges=0`. The screen remains limited to **60 Hz** in this hot-risk profile, so it cannot demonstrate 110-118 displayed FPS. Root guard thresholds and the 600s source denial are unchanged.

A complete single-run CachyOS orchestrator is checked into [OneiOS scripts/sm8850-parent-integration-all.sh](https://github.com/YMGPwcca/OneiOS/blob/feat/oneios-sm8850-m3q/scripts/sm8850-parent-integration-all.sh). It fetches fork + **direct parent** snapshots, checks static cross-repo invariants, runs the full OneOS offline P0 suite (179 expected tests) and OneiOS full GPU3D-required native ARM64 CI/package/ELF/hash, attempts a read-only OneOS Probe Debug APK and the pinned iOS arm64e Metal/Turnip bundle, and emits a combined artifact directory, hash list and JSON report. A missing SDK/JDK/Metal pin or build failure is **BLOCKED**, not a silent full PASS. **No ADB/phone, APFS stage/rearm, watchdog/reboot or Framework takeover in the script.**

**No new operator CachyOS run of this batch has been provided**; prior `PASS_HOST_ONLY` covered older source before these GPU/Metal fixes. No native new binary is on the phone. **P0 thermal 101.1 C fault/independently certified watchdog and unattended return remain open; never use the 90 C experiment as an acceptance shortcut.**

**2026-11-21 SM8850 thermal adaptation (source only):** original `fahadalijaved/OneOS` has documented S26 Ultra SM8850 Android guest runs and a 3-level CPU heat cap. Companion OneOS P0 now ports the CPU frequency-control pattern as an independent, root-monitored, PRE-XNU host worker (source candidate 80/65/50%; never raises Samsung limits). P0 thermal abort thresholds, 600s refusal, and reboot-only return remain; OneiOS `scripts/sm8850-parent-integration-resume.sh` reruns new 193-test P0 regression and 670 Android JUnit while reusing hashed unchanged GPU3D/Metal builds. **New cap simulation/CI not executed on CachyOS, new CPU-cap hardware behavior and unassisted recovery not qualified.** Do not use this source-only port to authorize a new CPU90 physical session.
