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

## 2026-11-20: CPU host management is gated off in physical-touch bench

Source-level finding (not a measured clock-rate result):

- `sm8850-ios-gpu-visual.py` reuses the hardened bench script, and
  `make_visual_script(..., touch=True)` launches native `xnuhost`
  with `--set bridges=0`. `config.c` explicitly enforces bridges=0
  for `touch-exclusive=1` in `mode=bench` with `display=shm`.
- `runtime/xnuhost/src/main.c` currently wraps CPU topology discovery,
  `br_cpu_plan_make`, the `xh_cpu_place` callback (`cpu-pin`),
  the guest `br_cpufreq` MMIO, and the
  `xh_cpu_uclamp` callback in `if (config.bridges)`.
- Consequently those host CPU placement/performance request mechanisms are
  NOT initialized in the current bounded visual touch preview. The host
  Linux scheduler still runs the guest/vCPU threads on its permitted CPUs;
  this is **not** evidence that all guest threads run on LITTLE cores or
  that the Qualcomm CPU frequencies are artificially capped.
  The thermals and actual `scaling_cur_freq` of each core were not
  measured by the existing log. The UI may also wait on I/O, vCPU-to-task
  futex hand-offs, or guest service initialization even when cores have idle
  capacity.

Why this matters: the 600-second guest saw **22,487,167 task traps**
(37,473/s overall), a peak of 55,975/s in 30s samples, and lengthy guest
touch-to-next-frame gaps (up to 912.5 ms). During quiet frames, the real
GPU fence mean was ~0.8 ms and the native display copy ~1.4 ms.
`Spotlight` occupied ~91-103% of one core in many intervals.
GPU acceleration therefore coexists with significant guest CPU work; the
GPU may be idle while waiting for the next scanout.

**Do not switch the touch preview to `bridges=1`**: this violates the
explicit exclusive-touch safety guard and could enable unrelated
hardware/Android bridge mutations. Also do not set global CPU governors
or disable Android thermal throttling for a benchmark.

Recommended next engineering experiment:

1. Collect read-only per-core `scaling_cur_freq`, `scaling_max_freq`,
   `cpuinfo_max_freq`, `Cpus_allowed_list` for xnuhost, vCPU host
   processor IDs, guest-vCPU kernel/user/idle percentages, and the
   `perf:` trap handoff/kernel-fault p90/p99 while reproducing Settings
   first-open and second-open delays.
2. Introduce a **separate opt-in CPU-only bridge for bench**, without
   enabling the existing general `bridges` toggle: host-topology read,
   guest CPU frequency request MMIO, per-vCPU/per-guest-thread affinity
   and `uclamp` only. Restrict it to bench/SHM and prevent haptics,
   Wi-Fi, Bluetooth, takeover, or other system-wide mutations. Keep the
   existing finite phone-side timeout and Data clone isolation.
3. Validate regressions on CachyOS first; conduct matched 600-second
   A/B trials with the same RAM, GPU trace setting and UI interaction
   sequence; compare vCPU % kernel vs guest thread, handoff p99,
   interactive frame pacing, icon load time and Android memory pressure.
4. Only if the results support a scheduling bottleneck should the
   CPU-only bridge become default; otherwise investigate the guest
   per-fault/per-syscall and Spotlight workload paths next.

A short burst of high host CPU frequency is not proof of full throughput.
Likewise, lack of 100% CPU use is not itself a flaw: UI latency is governed
by the slowest dependent stage, and parallel cores cannot accelerate an
unparallelizable serial task.


### After trace-off 600-second guest

The trace-off guest completed at `finished:124`, posted 6236 buffers,
reported 6471 backboardd GPU fences, and released exclusive touch.
The peak posted-buffer rate was 58.05Hz; the median adjacent active-post
cadence was 15.67Hz (vs 19.92Hz trace ON). Worst touch-to-next-frame
was 208.8ms (vs 912.5ms) but the two runs differed in actions,
so a causal gain cannot be claimed. The 55,811/s peak host trap rate
is effectively unchanged from 55,975/s and Spotlight used up to 132%
of one core in reported top-process windows. Android MemAvailable
fell to 928MiB (lower than 1006MiB previously). There was no
SpringBoard/backboardd PID change and no direct guest vkCreateDevice trace.
BufferQueue lock/copy/post remain comparatively short in most windows.
The last display log contained a reset-by-peer on guest timeout; the
layer subsequently cleaned up and Android's system_server remained alive.

Next isolate the CPU frequency/affinity hypothesis before enabling CPU
bridges: the new `--cpu-probe` opt-in makes a *read-only* five-second
on-device log of xnuhost's allowed host CPUs, process CPU time and
schedule/wait times, per-policy scaling_cur_freq/scaling_max_freq/
cpuinfo_max_freq and CPU pressure. It runs while USB is unplugged,
under the same bounded one-shot runner. Use it with `--no-gpu-trace`
to keep the GPU logging workload fixed. Only after reading the actual
clock/scheduling evidence should a separated, host-only CPU scheduling
bridge be considered. In particular do not set `bridges=1`, which the
exclusive-touch bench guard forbids.


### CPU probe zero-sample regression

The 2026-11-19 CPU probe run was ended early with SIGTERM:
`DEVICE_BENCH_STATE=finished:0`, `TOUCH_RELEASE_LOGGED=True` and
`SYSTEM_SERVER_AFTER=yes`. Its 52 display windows mostly contained idle
frames; peak posted rate was 8.13Hz. These metrics are not comparable
to the previous trace-off 600-second session because the guest ran
fewer interactions (7 logged gestures) and longer idle stretches.

The CPU probe was falsely classified enabled despite 0 process and
0 policy samples. Root cause: the generated shell assignment
`CPU_PROBE_PARENT=$` was a lone dollar sign; the `kill -0` condition
aborted every loop before the first sample. This was an instrumentation
bug, not evidence of CPU throttling, a broken CPU scheduler or a
Vulkan regression. Fix: replace parent-PID liveness gating with a
strictly bounded five-second iteration loop and guest-exit kill;
emit start/status diagnostics and treat missing numeric clock
samples as invalid. Added host-only runnable smoke regression.

Run a NEW 120-second one-shot Data clone for CPU measurement.
Do not enable `bridges=1`, force CPU clocks or edit system governors
until sampling confirms allowed cores, scheduling wait, and policy
frequency relative to the limit.


### 2026-11-20: per-vCPU trap evidence and opt-in host-affinity A/B

Read-only log for the 120-second baseline with GPU trace OFF:

- 30-60s: four vCPUs have 0% recorded idle; each vCPU spends
  ~30-34% wall in XNU kernel handling vs ~66-70% in guest task turns,
  with 13-14k task traps/second per vCPU.
- 60-90s: each remains 0% idle; ~27-29% kernel vs 71-73% task;
  trap round trip means 13.78 us (up) + 13.51 us (down),
  p99 57.34 us (up) and 49.15 us (down), at 56,058 traps/s.
- The 120s baseline averaged about 1.74 *host xnuhost* CPU cores from
  `/proc/PID/stat` ticks (assuming USER_HZ=100). That DOES NOT include
  Linux processes and threads hosting guest iOS userspace. In
  `perf: cpuN:`, `% of a core` refers to the host vCPU thread;
  kernel/task/idle percentages classify the vCPU's wall time.
  Do not conclude only 1.74 of the phone's 8 CPUs were active.
- Device cpufreq `scaling_max_freq` declined toward 2.112 GHz on both
  policies in the latter portion of this session. This is real policy
  ceiling reduction but not proof of its cause; thermal/power policy,
  rather than the guest, may be responsible.

The CPU-only stage-1 A/B explicitly limits its scope to **affinity only**:
`--set cpu-affinity-bench=1` is rejected except with
`mode=bench, display=shm, touch-exclusive=1, bridges=0, tasks=1,
cpu-pin=1`. At guest setup, read available host CPU topology and
the current process's allowed cpuset, select four *distinct* allowed
cores in descending capacity/max-frequency rank, and set only per-vCPU
and released guest-task Linux thread affinity through existing
`xh_cpu_place`. The guest-visible CPU cluster type, guest RAM, GPU
config, hardware bridges, frequency limits and thermal settings are
unchanged. This avoids enabling `br_cpu_plan_make`'s 1E + 3P
configuration on a phone that currently exposes only two fast host
CPUs (otherwise 3P vCPUs could contend for the same two cores).
No virtual cpufreq MMIO, `uclamp`, global governor, external affinity,
direct CPU frequency write or host thermal override.

An opt-in local A/B with a fresh, cloned APFS Data, timeout 120s,
GPU trace OFF, CPU probe ON and exactly the same manually performed
Settings/Home interactions should be compared to the
20261119T191842Z baseline. The key metric is whether guest handoff
p90/p99 and touch-to-next-frame improve without more throttling,
faults or Android memory pressure. The primary branch remains the
unchanged default. A 2-4x speedup is *not* claimed.
