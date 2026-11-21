# SM8850 direct-parent parity: implementation inventory and one-command local gate

**Date:** 2026-11-21. **Target:** Samsung SM-S948B / m3q / Qualcomm SM8850, firmware S948BXXS4BZIG, OneiOS iOS 27.0.1 24A446 hosted under One UI's Linux kernel. **No new takeover is justified by this document.**

## Which upstream?

- **OneiOS fork:** `YMGPwcca/OneiOS`, immediate parent `akshaynexus/OneiOS` **main at `92886287724d3f9aa097dc17157281e585457500`**.
- **OneOS fork:** `YMGPwcca/OneOS`, immediate parent `akshaynexus/OneOS` **`oneios` at `53abb04e7bd87c785fff7a1db3ebd0742e777eb5`**.
- `fahadalijaved/OneOS` is a **more distant ancestor**, not the requested OneOS immediate parent.
- Fork and parent histories are deeply divergent: wholesale merges would overwrite SM8850-specific Framework, APFS one-shot, watchdog and diagnostic code, as well as S26-specific haptic/encoder patches. Use a selective source-level backport and verify every resulting binary.

## What the direct parents actually do, versus this fork

| Domain | Parent source/behavior | Fork action / status |
|---|---|---|
| CPU topology | `runtime/bridges/cpu/topology.c`: MIDR 0x51 Oryon physical P cores, borrow slowest P cores as guest E class (8 vCPU -> 2 synthetic E / 6 P) | **PORTED** parent `topology.c`; S26 8-core sysfs fixture updated; isolated bench uses this parent host-core order when MIDRs and allowed cpuset match |
| CPU load and scheduling | vCPU-to-host core pairing; no device-global governor writes; optional per-thread uclamp when CPU bridge runs | **ADAPTED** guest-only 8-vCPU affinity with `cpu-affinity-bench=1`; `bridges=0` intentionally means no virtual cpufreq device or runtime thermal bridge |
| Idle CPU overhead | `setway-skip=1` avoids repeated guest set/way cache flushes (parent reports significant idle CPU reduction); spins default zero | **PINNED** `setway-skip=1`, `spin-host=0`, `spin-task=0` on the conservative OneOS SM8850 bench path |
| RAM/swap | `ram-giveback=0`, prefault and mlock guest RAM; avoid host zram swap and its CPU overhead; keep memory headroom | **ALREADY PRESENT/PINNED** 4 GiB guest RAM, `ram-giveback=0 ram-prefault=1 ram-lock=1`, hugepages off for current SM8850 benchmark; no speculative RAM increase |
| Thermal pressure | Parent `runtime/bridges/thermal/thermal.c` and its kernel driver read zones every ~5 s; adjust guest thermal pressure; CPU affinity cap only when skin or battery reaches ~50 C, not directly on a CPU hotspot | **SOURCE ALREADY IDENTICAL**, but **INACTIVE in the isolated `bridges=0` guest**; do not enable all HAL bridges to import this one service. Independent OneOS root guard remains authoritative |
| Thermal abort | Parent relies on kernel thermal/LMh and case/battery policy; no evidence its policy is a safe SM8850 early CPU hotspot limiter | **S26-SPECIFIC** root guard CPU/GPU/DDR 55 C; battery 38 C; LRP/board AP 42 C; fail-closed and timestamped telemetry every five ticks. Separate experimental CPU90 run saw **101.1 C CPU**, exceeding the 90 C cutoff by 11.1 C |
| Original OneOS SM8850 CPU heat cap (not a OneiOS bridge) | **Ancestral** `fahadalijaved/OneOS` main `813cc976` documents real S26 Ultra/SM8850 **Android guest** sessions and `ONEOS_HEAT_CAP=1`, driving CPU 80/65/50% from Android guest SKIN 45/47/50 C, with 2 C hysteresis | **ADAPTED IN OneOS P0 SOURCE ONLY**: a root CPU-cap worker consumes independent SM8850 thermal heartbeat, caps `scaling_max_freq` downward 80/65/50% before xnuhost starts, never undoes lower Samsung caps and keeps the CPU55/GPU55/DDR55 emergency abort. Thresholds differ from SKIN and need hardware qualification; GPU Fold8 sysfs is not assumed for S26 |
| CPU load evidence | Parent `thermalctl top` prints host load, xnuhost percentage, swapping and sensor samples | **ADAPTED** independent root `P0_XNUHOST_LOAD=READ_ONLY` cumulative /proc CPU ticks and birth identity even with bridges disabled. It is not yet runtime % and does not change CPU load |
| GPU host 3D | Droid-VM `drm2kgsl` over KGSL and udmabuf; chunked imports, priority/deadline dynamic GPU power policy | **ALREADY PRESENT** KGSL runtime; **PORTED** missing `virgl_fence_table_init()` plus parent `0007-a830-waittimestamp-fences.patch`. Requires pinned virglrenderer and runtime GPU3D compilation |
| GPU power/heat | `gpu-level=deadline` requests top KGSL clock only when a render-server frame needs it; `gpu-priority=1` separates foreground/background work; avoid legacy `gpu-level=hold` | **PINNED** deadline policy and per-context priority in conservative bench args; no hard global GPU clock cap or forced top-frequency hold |
| Metal shader/Vulkan | Parent's three rebased `metal2vulkan` patches address oversized indexed constants, GEP constant pointers, and optional per-process pooled block sizes | **PORTED** 0101/0102/0103 byte-identical from parent; staged as 9xxx after Droid-VM base patches via `userland/metal/build.sh`. Must compile/link against pinned iOS 27 arm64e Metal/Turnip refs |
| Adreno identity | Parent's Adreno 830 waittimestamp bug concerns SM8750; A830 fence event path caused SIGSEGV on its firmware | **PORTED GENERIC DEFENSIVE DEFAULT** waittimestamp path while leaving opt-in A/B environment; this is not SM8850 GPU certification |
| Display / refresh | Parent has newer direct blob-to-display helper pathway and panel fallback settings; frame-adaptive display must match panel Hz | **NOT BLINDLY MERGED**: fork has custom GPU tracing, queue-generation tracking, SM8850 display perf work. The current isolated risk-contained bench **explicitly fixes 1080x2340 at 60 Hz**; it cannot establish 110-118 displayed FPS, and raising Hz while the CPU has reached 101.1 C would be irresponsible. Cross-file ABI changes remain a separate engineering integration |
| Touch and keys | Evdev/virtio HID, display helper, optional exclusive touch | **RETAIN FORK** exclusive-touch `bench/shm/bridges=0`; switching to `bridges=1` is rejected by runtime configuration |
| Haptics | Parent vibrator bridge/Actuator; S26 fork has additional native preset impact and hardware HEAVY_CLICK acceptance | **RETAIN FORK** S26-specific ABI and tests; unavailable in current `haptics=off` isolated bench |
| Audio and encoder | Parent AAudio and media bridge helpers | **RETAIN FORK** S26-specific audio error handling and encoder fixes; full guest hardware bridge inactive |
| Camera | Parent Camera HAL and guest camera bridge source | **ALREADY MATCHES** primary backend sources; guest session camera not verified and bridge disabled |
| Wi-Fi/network | Parent nl80211/AIDL supplicant and host network bridging | **ALREADY MATCHES** core sources; `wifi=off` in isolated experiment to avoid altering One UI networking |
| Battery/backlight/ALS | Parent battery and backlight/brightness bridge sources | **ALREADY MATCH** primary source files; bench exposes no bridge for safety, do not assume iOS-visible function |
| Bluetooth | Parent has newer LE scan files not present in fork | **NOT ENABLED** (bench `bluetooth=virtual`); parent LE scan depends on current host HAL and needs a dedicated optional bridge with source/test compatibility |
| Device profiles / host selection | Parent S25 hardware table, `host-device` profile and panel fallback configuration | **NOT PORTED AS A DEVICE DEFAULT**: S25/SM8750 is not S26/SM8850; map from actual firmware/sysfs and fork profile, do not misidentify S26 |
| Framework / recovery | Parent watchdog feeder, returner and in-place fallback built for its phones | **RETAIN FORK** SM8850 root-owned sensor manifest, PID birth, APFS one-shot, deadline, hard reboot-only return, P0 lock. Parent's safety evidence is not transferable to Samsung SM8850 watchdog `legacy a:82` |
| OneOS Android app | Parent app includes phone probes, guest manager and Android GSI switches | **KEEP DISTINCTION** OneOS Android guest switching is not OneiOS SM8850 certified; local Gradle JVM/Probe build is a source gate only |

## Why a wholesale parent sync is unsafe

The parents' SM8650/SM8750 hardware assumptions, vendor thermal thresholds, key input mapping, KGSL behavior, charger/coordinator, and recoverability are not SM8850 firmware evidence. OneiOS's fork also carries independent SM8850 improvements in `main.c`, `virtio_gpu.c`, GPU tracing, native haptic/encoder, and stage scripts that a naïve parent overwrite would remove. The appropriate definition of "parity" here is: **all compatible algorithms backported; distinct hardware defaults kept separate; full binary build validated; unqualified physical functions disabled until recovery and thermal qualify**.

## First-run known limitations

The integrated runner is a **one-shot source/build gate**, not a phone-deployment command. Some operations use Android SDK/JDK 21 and iOS 27 SDK/ld64/Rust+Mesa pins; when a dependency is unavailable, the script retains successful runtime artifacts and emits one summary with blocked stages/logs instead of calling it a full PASS. This is intentionally preferable to repeatedly requesting individual physical tests. The full build may take substantial resources on the host. The OneOS Probe Debug APK is a read-only diagnostic app, **not** a sideload of OneOS/OneiOS switching logic.

## One-command integrated local gate

From the operator's CachyOS machine, invoke the exact `scripts/sm8850-parent-integration-all.sh` on the fork's `feat/oneios-sm8850-m3q` branch. The runner:

1. Fetches both forks' current feature tips and **only the immediate parents** for comparison; records every exact commit.
2. Checks static cross-repo CPU/thermal/GPU/Metal/Framework admission invariants.
3. Runs the full OneOS P0 offline regression suite and OneiOS `scripts/ci-local.sh all` (GPU3D mandatory, host tests, ARM64 runtime package, SHA and ELF validation).
4. Attempts an Android **OneOS Probe Debug** Gradle build and an iOS 27 **Metal/Turnip** build using pinned external sources and existing SDK/toolchain, preserving artifacts and a combined report. Missing SDK/JDK/pins are reported as **blockers**, never silently marked PASS.
5. Does **not** use ADB, touch the phone, reset APFS, change system governors, stop Framework, trigger a watchdog or run a hot guest. A success is `PASS_OFFLINE` only; physical thermal/recovery remain unqualified.

**Actual first comprehensive CachyOS run, 2026-11-21T092054Z:** `STATIC_PARITY=PASS`, `ONEOS_P0_ALL=PASS`; the runtime packaging was blocked by an invalid temporary version suffix, Metal was blocked before compile by a truncated AdrenoPM4 pin, and the OneOS Gradle root unit tests failed for an **as-yet-unidentified test**. Fixed the two wrapper errors and added version/pin/shell selftests, `--continue` Probe APK build, and persistent JUnit XML/HTML/failure summary. The direct OneiOS parent moved one docs-only commit to `a29dde8ffe81936476b619c6343f0beceded2f00` (`docs/releases.md` only); reviewed and pinned. **No rerun of the repaired complete suite and no actual Metal compile result yet.** See `SM8850_LIVE_STATUS_2026-11-20.md` for exact receipt.

No single command can safely claim that CPU 101.1 C thermal runaway has been cured or that a formerly unverified watchdog recovery is reliable. Those are separate hardware properties; a new 300/600s hot takeover is not part of the integrated host gate.


**New acceptance gate 2026-11-21:** Original S26 OneOS heat cap adaptation added after the earlier 670/670 Android JUnit + hashed GPU3D/Metal PASS. The new OneOS P0 suite expects **193** source/simulated tests; OneiOS `scripts/sm8850-parent-integration-resume.sh` now reuses unchanged hashed GPU3D/Metal but reruns OneOS P0/Gradle and cross-fork parity on current source. **New cap test and physical cpufreq behavior have not been observed yet.** Full 600s takeover remains blocked and the CPU101.1 C sample is not mitigated evidence.
