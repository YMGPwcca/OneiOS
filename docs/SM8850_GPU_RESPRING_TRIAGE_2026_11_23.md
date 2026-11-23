# SM8850 iOS 27 GPU/respring evidence (2026-11-23)

## Scope

**One session, read-only physical evidence; not proof of root cause.** Input archive
SHA-256: `533a232ab57c4a5fa9a1e4de458fb60699ccba5325e4d6eea07b5e6a0f2090f9`.
OneOS framework session: 180 seconds, explicit `disabled-180s` userspace
thermal cutoff, best-effort CPU cap 28%; a named framework-deadline return
was recorded. **Neither independent watchdog return nor thermal safety
is qualified.** Never repeat the no-soft-thermal profile as a routine test.

## Timestamped chain

- t=1566.462: KGSL backend opens, full-bridges session reaches GPU.
- t=1615.086: `backboardd[52]` opens the framebuffer.
- t=1679.681: DRM->KGSL `IOCTL_KGSL_GPU_COMMAND` reports `EPROTO`
  (`Protocol error`). This is compatible with a GPU context fault; the exact
  cause/IB is not yet identified.
- t=1680.238: `backboardd[52]` exits with status `0xf` (557 ms later).
- t=1690: new `backboardd[174]` creates GPU contexts.
- t=1696.407: SpringBoard[30] terminated on `backboardd respawn`.
- t=1704..1725: display post-rate windows reach ~21..29/s, so the
  observed user-visible ~2 FPS is **not a uniform rate**.
- t=1740: framework deadline reached; Android return requested.

Cross-layer observations:

- Up to **684.274 ms** host submit->retired GPU fence; prior guest
  diagnostic reports six fence timeouts. Long stalls need more investigation.
- One five-second window contains a **28.319 s p95 inter-post gap**.
  This is a cross-window gap and not proof of interactive stall for its
  full duration; frame output may also be idle.
- Touch->next guest frame up to **725 ms** in the available touch summary.
- Max display copy duration **8.655 ms**; copying pixels alone cannot
  explain these multi-second gaps.
- Host VMM observes up to **34,439 guest traps/s**, and the observed CPU
  cap was 28% (cluster caps seen at 998.4 / 1267.2 MHz).
- The CPU cap, per-frame waits and a potential context reset are separate
  suspected bottlenecks. Never claim that one diagnosis explains all frames.

## Corrective change and its limits

`runtime/xnuhost/drm2kgsl/patches/0009-kgsl-reset-aware-submit-errors.patch`
preserves the original GPU_COMMAND errno and logs bounded queue/timestamp/IB
**metadata only**. On EPROTO it queries KGSL GPU reset status at the failure
site and publishes a guilty/involved reset through the existing
`shmem.global_faults`, in addition to the existing `async_error`.
It deliberately does not replay an ambiguous IB: doing so could duplicate
GPU commands and worsen a fault. This is **fault visibility/recovery signaling,
not proof the crashing GPU command or frame pacing is fixed**.

The host test `test_drm2kgsl` uses a fault-injected fake KGSL ioctl to
check exactly-once submission, guest async error and context-fault telemetry.
Use the host-run test and local CI before installing new native ARM64 assets.

Read-only report on archived evidence (no ADB):
```sh
python3 scripts/phone/sm8850-gpu-respring-forensics.py \
  --archive out/sm8850/ui-triage.quMgUI/collect/device-logs.tar \
  --output out/sm8850/ui-triage.quMgUI/collect/gpu-respring-report.json
```

## Acceptance gates before another physical takeover

1. Current branch checkout and OneOS gitlink exactly match the intended
   tested revisions; clean working trees and unchanged evidence archives.
2. The DRM2KGSL patch applies with `-F0` to the pinned virglrenderer
   checkout; host KGSL fault-injection + full local CI pass.
3. Separate/root thermal guard and return mechanism are **qualified**;
   never substitute read-only guest thermal sensors for root protection.
4. A new short physical run is a *separate*, explicitly accepted experiment,
   not validation-by-merge. Capture XNUHost, KGSL, display and return logs
   from the same generation, compare before/after fence errors and resprings.
