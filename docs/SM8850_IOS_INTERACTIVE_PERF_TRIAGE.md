# SM8850 iOS 27 interactive performance: 2026-11-19 evidence and next acceptance

## Scope and facts

The **first physical touch-enabled, non-takeover** visual session on S26 Ultra
used a 4,096 MiB guest, four vCPUs, 1080 x 2340 SHM display, DRM-native
Adreno GPU, 240-second device-side timeout, and an independent one-shot APFS
Data clone. It displayed a real iOS 27.0.1 lock screen, Home Screen, and
Settings > About, with responsive-enough raw touch to navigate.

Captured logs: `out/sm8850/gpu-acceptance/20261119T170632Z-visual-xnuhost.log`
and the corresponding display log and JSON report. **Do not rerun the used
Data clone.** The session was terminated by the designed timeout and
returned input/display to One UI.

Observed measurements, **not** causal proof:
- 857 display buffers posted in the 240-second run. This is NOT active FPS:
  it includes boot/idle time and frames that only changed when guest drew.
- 677 backboardd fences reported in periodic windows. Most
  submit->retire means were around 0.8-8.6 ms, but one window reported
  a **517 ms maximum**, which can produce a visible frame stall.
- Five completed physical gestures, with raw evdev scan->read around
  25-39 microseconds on average, and **touch-down->next guest frame**
  readings of 742.2 ms and 342.7 ms; two gestures logged no subsequent
  guest frame. Thus the raw touch reader is not the observed seconds-long
  bottleneck.
- SpringBoard's PID changed **30 -> 262**, and backboardd's PID changed
  **52 -> 260**. The UI subsystem restarted; the precise crash or
  watchdog trigger is not yet known.
- `iconservicesagent[111]` used up to **216% of one CPU** in a 10-second
  sampling interval. User reports **~3 seconds** for Settings category
  icons to populate on first opening. The icon service, cache misses and
  guest CPU emulation are prime hypotheses, but not proven root causes.
- `xnuhost` handled ~8.68 million task traps across 240 seconds
  (~36k/s). Its syscall/fault paths and handoffs may impose high
  scheduling overhead.
- Guest RAM was 4,096 MiB prefaulted and mlocked; host
  `MemAvailable` dropped to ~1,552 MiB, plus ~605 MiB page tables,
  and the guest GPU reported ~823 MiB of own blobs late in the run.
  Long trials can put Android under memory pressure even though its
  Framework remains alive.
- Repeated `host_statistics64()` count mismatch
  `actual 104 > HOST_VM_INFO64_COUNT 62` is an ABI correctness warning
  and should be fixed/understood before blaming only graphics.

## Next steps (local CI and offline evidence first)

1. **UI-restart root cause.** From the saved *complete* xnuhost log,
   inspect around the first new SpringBoard/backboardd PID and extract
   all launchd/runningboardd/backboardd/SpringBoard death, watchdog,
   jetsam, signal and crash lines. If no termination is visible, look
   for guest .ips / CrashReporter evidence **read-only**, never modify
   the original APFS source.
2. **Separate icon-service startup from GPU FPS.** On a fresh one-shot
   session (only after offline work), record four timestamps: touch
   Settings, list text appears, category icons appear, exit/reenter
   Settings. If the *second* opening is faster, cold cache or
   `iconservicesagent` initialization is implicated. Every current
   session uses a newly copied Data clone, so across-session cold starts
   are expected; don't yet patch cache persistence.
3. **Frame pacing instrumentation (implemented; device acceptance pending).**
   The `oneios-display` helper now reports five-second posted-buffer
   rate, active-post cadence, `ANativeWindow_lock`, frame copy and
   `unlockAndPost` histograms; the guest already reports
   input-to-frame latency. The offline
   `sm8850-ios-interactive-perf.py` parser correlates it with GPU
   fences, CPU trap load and UI restarts. Run
   [the bounded 10-minute capture](SM8850_IOS_INTERACTIVE_PERF_CAPTURE.md)
   only after local CI passes. A full-session average of
   posted buffers is never interactive FPS.
4. **CPU path profiling before governor tuning.** Investigate
   high syscall/page fault rates and iconservicesagent's 216% CPU,
   including 30-second `perf:` windows, task handoff p99 and
   host thermal/frequency; improve measurable bottleneck only.
5. **Memory/ABI stability.** Triage repeated host_statistics64
   warnings; check whether iOS GPU blob pools and Android available
   memory trend upward. Introduce a guarded memory-pressure
   cancellation policy before claiming longer bounded runs stable.

## Practical read-only drilldown, CachyOS repo root

```bash
LOG=out/sm8850/gpu-acceptance/20261119T170632Z-visual-xnuhost.log
test -s "$LOG"
# The first post-restart SpringBoard process was seen around guest time 23958.
grep -nEi 'SpringBoard\[(30|262)\]|backboardd\[(52|260)\]|iconservicesagent\[111\]|jetsam|watchdog|crash|SIGABRT|terminated|exited|memorystatus' "$LOG" |
  tail -n 150
# GPU fence latency and frame interval are separate from rendering FPS.
grep -E 'gpu: .*host: backboardd fences|gpu: .*level: frames|input: touch:' "$LOG" |
  tail -n 80
```

No global sysctl, kernel/boot partition, display manager, touch driver or original
Data mutation is required for this analysis. Prioritize **crash/restart +
CPU/first-icon latency** before pushing FPS policies or taking over Android.
