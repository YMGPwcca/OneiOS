# OneiOS documentation

**Galaxy S26 Ultra · SM-S948B / m3q / SM8850 · iOS 27.0.1 · experimental**

[← Project home](../README.md) · [Current evidence](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md) · [Companion OneOS](https://github.com/YMGPwcca/OneOS/tree/feat/sm8850-reboot-smoke/docs)

> [!CAUTION]
> **Booted is not accepted.** A physical full-run reached guest-ready and first frame for ~600.6 s with KGSL acceleration. The device was very hot and visibly laggy. Unassisted recovery, independent watchdog qualification and a separate thermal guard are not yet proven. Normal OneOS app switching is blocked for SM8850.

## Find what you need

| Question | Start here |
| :--- | :--- |
| What works on the S26 Ultra today? | [Physical status & proof](SM8850_LIVE_STATUS_2026-11-20.md) |
| What do we fix next? | [Safety-first roadmap](TODO.md) |
| How does this system work? | [Architecture](architecture.md) |
| How do I build and test without touching the phone? | [CachyOS local build](building.md) |
| Why did the phone lag and heat up? | [Interactive performance triage](SM8850_IOS_INTERACTIVE_PERF_TRIAGE.md) |
| How did reboot/takeover behave? | [Framework timeline](SM8850_FRAMEWORK_TAKEOVER.md) |

---

## 01 · Start here

| Document | What to use it for |
| :--- | :--- |
| [SM8850 LIVE STATUS 2026-11-20](SM8850_LIVE_STATUS_2026-11-20.md) | Current verified state · physical run, limitations and evidence |
| [TODO](TODO.md) | Engineering queue · P0 safety through P3 acceptance |
| [architecture](architecture.md) | How hosted XNU, iOS tasks and Android hardware integrate |
| [building](building.md) | Build, test, verify and package locally on CachyOS |
| [SM8850 FULL IOS 10MIN](SM8850_FULL_IOS_10MIN.md) | Full Framework takeover record and one-shot staging — **historical; not a retest instruction** |

## 02 · Device, safety & recovery

| Document | What to use it for |
| :--- | :--- |
| [SM8850 PORT](SM8850_PORT.md) | SM8850 hardware facts and acceptance boundaries |
| [SM8850 FRAMEWORK TAKEOVER](SM8850_FRAMEWORK_TAKEOVER.md) | Executed takeover timeline and current blockers |
| [SM8850 REBOOT SMOKE](SM8850_REBOOT_SMOKE.md) | Reboot-only smoke and observed return receipts |
| [SM8850 WATCHDOG ACCEPTANCE](SM8850_WATCHDOG_ACCEPTANCE.md) | Watchdog provenance and missing independent qualification |
| [SM8850 WATCHDOG SUPERVISOR](SM8850_WATCHDOG_SUPERVISOR.md) | Watchdog supervisor design and heartbeat semantics |
| [SM8850 TAKEOVER RETURN GATE0](SM8850_TAKEOVER_RETURN_GATE0.md) | Original read-only gate, now a historical decision memo |
| [SM8850 RECOVERY DRY RUN](SM8850_RECOVERY_DRY_RUN.md) | Non-disruptive recovery audit and physical input evidence |
| [SM8850 ORIGINAL AUDIT](SM8850_ORIGINAL_AUDIT.md) | Detailed passive device/safety audit (historical evidence) |

## 03 · iOS graphics, touch & performance

| Document | What to use it for |
| :--- | :--- |
| [SM8850 IOS INTERACTIVE PERF TRIAGE](SM8850_IOS_INTERACTIVE_PERF_TRIAGE.md) | CPU/GPU lag analysis, A/B results and hypotheses |
| [SM8850 IOS INTERACTIVE PERF CAPTURE](SM8850_IOS_INTERACTIVE_PERF_CAPTURE.md) | Capture format and matched touch/UI benchmark method |
| [SM8850 IOS TOUCH PREVIEW](SM8850_IOS_TOUCH_PREVIEW.md) | Bounded non-takeover touch preview |
| [SM8850 IOS GPU VISUAL](SM8850_IOS_GPU_VISUAL.md) | Physical visual GPU trial and criteria |
| [SM8850 IOS GPU BENCH](SM8850_IOS_GPU_BENCH.md) | Bounded GPU-auto bench without Framework stop |
| [SM8850 IOS GPU BENCH RETRY](SM8850_IOS_GPU_BENCH_RETRY.md) | Earlier preflight failure and follow-up |
| [SM8850 GPU HARDWARE ACCEPTANCE](SM8850_GPU_HARDWARE_ACCEPTANCE.md) | KGSL/Adreno hardware evidence |
| [SM8850 GPU DATA SNAPSHOT](SM8850_GPU_DATA_SNAPSHOT.md) | Isolated APFS Data clone protocol |
| [SM8850 GUI CRASH](SM8850_GUI_CRASH.md) | Guest GUI crash investigation |

## 04 · Build, image & runtime reference

| Document | What to use it for |
| :--- | :--- |
| [booter](booter.md) | xnuhost internals, hostcalls, memory and vCPUs |
| [gpu](gpu.md) | virtio-gpu, drm2kgsl, native Adreno path and policies |
| [hardware](hardware.md) | Device bridges, backend selectors and hardware inventory |
| [userland](userland.md) | iOS 27 userland, caches, signing and the Metal bundle |
| [image-format](image-format.md) | Manifest, APFS images, hashes and trusted Data seed |
| [releases](releases.md) | Artifact format and release verification |
| [SM8850 IMAGE READINESS](SM8850_IMAGE_READINESS.md) | Image provenance and staged trust checks |
| [SM8850 NO COPY IMAGE ADAPTER](SM8850_NO_COPY_IMAGE_ADAPTER.md) | Image staging design exploration |
| [references](references.md) | Source provenance and research links |

## 05 · Project workflow & historical decisions

| Document | What to use it for |
| :--- | :--- |
| [agents](agents.md) | Contribution rules, evidence handling and local-first checks |
| [plan](plan.md) | Current S26 Ultra engineering plan |
| [newtodo](newtodo.md) | Redirect for the former pause log and superseded work queues |
| [STYLE GUIDE](STYLE_GUIDE.md) | Layout, status vocabulary and link conventions |

---

## Reading the evidence

- **OBSERVED** — directly supported by device output or an archived run; never an automatic acceptance of related behavior.
- **PASS** — a named test, with stated device/fixture scope, met its exact criterion.
- **NOT VERIFIED** — missing evidence; do not silently convert it to failure or success.
- **BLOCKED** — a safety or technical precondition prevents the next action.
- **HISTORICAL** — accurate for an earlier point in the project, not a current recommendation.

> [!NOTE]
> These files intentionally retain older diagnostic evidence where it is useful, but the **current device and decision scope is the Galaxy S26 Ultra**. Current results always take precedence over outdated pretrial plans. See [documentation style](STYLE_GUIDE.md).

Last documentation review: **2026-11-20**. Device and firmware are intentionally pinned; do not generalize the results to a different build.
