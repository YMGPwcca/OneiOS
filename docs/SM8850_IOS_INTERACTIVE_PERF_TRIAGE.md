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


## 2026-11-19 late-window CPU/GPU timeline: Spotlight and trace A/B

The full read-only drilldown from the 600-second guest confirms that
the guest, not just the display helper, sent about 99-103 scanout flushes
and 99-101 completed backboardd fences per 10 seconds during the last
stable ~70-second period. GPU fence submit-to-retire means were only
~0.80-0.84 ms; framebuffer copy means ~1.37-1.53 ms. Neither proves an
unconditional 10 FPS cap: static/background screens need not redraw
at the display's 60 Hz. Earlier interaction saw up to 407 flushes in
10 seconds. Do not remove a suspected 10 Hz throttle without evidence.

While the 10 Hz cadence was measured, the guest's `Spotlight` repeatedly
appeared among top CPU processes at 91-103% of one core, while
`iconservicesagent` appeared intermittently. CPU virtualization stayed
at 26,540-28,734 task traps/s even in the quiet interval, with hundreds
of thousands of syscalls and faults every 30 seconds. This is strong
evidence of *background CPU load plus expensive host/guest crossings*,
but is not proof that Spotlight alone causes cold Settings icons.

The bounded visual guest has always been launched with
`ONEIOS_GPU_TRACE=1`, which prints detailed 3D resource/fence commands.
The next non-invasive A/B experiment adds `run --no-gpu-trace`: explicitly
UNSET the environment variable (setting it to `0` would still turn it on
in virtio_gpu.c), keeping all 5-second display statistics, periodic
GPU fence summaries, CPU/handoff stats, touch diagnostics, 4GiB RAM,
the exact same device-side TERM/KILL deadline and one-shot clone policy.
It is an optional experiment; the baseline remains the default.

The offline report additionally gives `SPOTLIGHT_CPU_PEAK_PERCENT`,
`SPOTLIGHT_GE_80PCT_WINDOWS`, and `GPU_VERBOSE_TRACE_LINES`. Compare
two runs with **the same interaction sequence** (e.g., 10s Home swipes,
Settings cold/warm open, 10s scroll), ideally 600s each. Better FPS,
touch latency and fewer trace lines would implicate instrumentation
overhead, but a single run does not establish causality. If no change,
retain the next priorities: inspect `perf:` per-vCPU up/down and
kernel fault/syscall p99, the 20 `host_statistics64` ABI warnings and
persistent Spotlight work. Do not disable Spotlight, bypass watchdog,
raise clock governors or touch the original APFS Data just to chase FPS.
