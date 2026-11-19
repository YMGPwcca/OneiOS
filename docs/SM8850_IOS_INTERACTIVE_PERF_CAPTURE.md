# SM8850 iOS 27: interactive GUI frame-pacing and cold/warm Settings test

This is **measurement only**. The 2026-11-19 S26 Ultra interactive run
already demonstrated iOS lock screen, SpringBoard, touch and Settings > About,
but not usable UI responsiveness. It also had SpringBoard/backboardd PID changes,
slow touch-down -> guest frame (up to 742.2 ms), a 517 ms GPU fence outlier,
high iconservicesagent CPU and repeated host_statistics64 count warnings.
Do not blindly increase vCPU count, force GPU clocks or take over One UI.

## Instrumentation

The `oneios-display` helper logs a `oneios-display: perf:` line every
**5 seconds**, even when static, and a final partial window at exit.
`mono_ms` is the Android CLOCK_MONOTONIC timestamp for comparison to
xnuhost's `[ seconds.millis ]` log. The per-window report has:

- `posts`, `posted_rate`: posted SurfaceFlinger buffers over elapsed time.
  **Not iOS animation FPS**: static screens often post no frames.
- `active_cadence`, `active_gaps`: estimated rate from consecutive posted
  buffer gaps of **250 ms or less**, only shown when at least 3 such gaps
  exist. Does not prove real guest rendering FPS or smoothness.
- `gap_p95_us`: coarse upper bucket of inter-post gap distribution.
- `lock_p95_us` / `lock_max_us`: time waiting for SurfaceFlinger's
  `ANativeWindow_lock` to return a writable buffer.
- `copy_p95_us` / `copy_max_us`: CPU-side framebuffer copy/format conversion.
- `post_p95_us` / `post_max_us`: time in `ANativeWindow_unlockAndPost`.
- `full_copies`, `copied_pixels`: accounting for damage/copy pressure.

The code uses allocation-free histograms and records only bounded summary
logs, not frame dumps. It neither enables guest tracing nor writes APFS.
Raw physical touch scan->read and guest touch-down->next-frame timing are
already emitted from `xnuhost/input.c`. The offline parser cross-references
the display metrics with the per-10s GPU fence reports, 30s trap CPU
reports, iconservicesagent CPU, memory and SpringBoard/backboardd PID changes.
**Actual Settings category icon appearance is a visual observation, not
automatically measurable from these logs.**

## Host-only local CI (before boot)

```bash
cd ~/projects/OneiOS
python3 scripts/phone/test-sm8850-ios-interactive-perf.py -v
python3 scripts/phone/test-sm8850-ios-gpu-visual.py -v
make -C runtime/display test
# The visual runner also builds runtime/display/all for Android automatically.
```

The existing guest runtime, one-shot APFS Data clone isolation, fresh clone
hash verification, `--touch` exclusive `sec_touchscreen`, 4GiB default RAM,
no-Framework-takeover gates and device-side TERM/KILL timeout remain intact.

## One bounded 10-minute interactive capture

```bash
python3 scripts/phone/sm8850-ios-gpu-visual.py run \
  --touch --duration 600 --ram-mib 4096
```

Watch the terminal for **both** `LIVE_TOUCH_GRABBED=YES` and
`LIVE_DISPLAY_FIRST_FRAME=POSTED`. Only then tap the *physical* touchscreen;
scrcpy clicks still do not reach iOS's exclusive evdev input.

1. After the Home Screen is responsive, swipe between pages continuously for
   about **10 seconds**. This is an active-animation window for cadence stats.
2. Open Settings. Note **tap -> list text appears** and **tap -> category
   icons appear** separately (seconds, from observation).
3. Return Home, reopen Settings in the **same** session. Repeat both timings:
   if warm opening is much faster, first-open work/cache is implicated.
4. Scroll Settings > General > About for about 10 seconds.
5. Notice any SpringBoard restart, blank frame, or stuck touch. Do **not**
   increase duration just to work around it. The guest auto-exits at 600s.

In another CachyOS shell, emergency release (scoped to guest only):

```bash
adb shell -n -T "su -c 'pkill -TERM -x xnuhost-gpu'"
```

If the guest is stuck, the device-side timeout has a KILL fallback. No
sysctl or boot partition is changed by the visual runner; if global
`vm.max_map_count` is below the required value, it refuses to boot.

## Analyze saved logs without booting or ADB

The visual runner automatically prints the `INTERACTIVE IOS PERFORMANCE`
summary and writes `performance` into its JSON report. Replay offline:

```bash
python3 scripts/phone/sm8850-ios-interactive-perf.py \
  --json out/sm8850/gpu-acceptance/latest-interactive-perf.json
```

The parser chooses the latest matching `*-visual-xnuhost.log` and
`*-visual-display.log`. For a specific session use `--xnuhost PATH --display
PATH`. Old pre-instrumentation logs correctly display
`DISPLAY_PERF_AVAILABLE=False` instead of claiming a missing FPS result.

Interpretation priority:
- High `DISPLAY_ANATIVEWINDOW_LOCK_MAX_MS` / post duration during swipes:
  investigate the Android BufferQueue / SurfaceFlinger path.
- High `DISPLAY_FRAME_COPY_MAX_MS`: investigate the CPU framebuffer copy
  or the source/destination pixel format and damage rectangles.
- Low active cadence while lock/copy/post are fast: guest rendering,
  backboardd, CPU traps, icon initialization and GPU fence stalls are next.
- A SpringBoard or backboardd PID change is evidence of a restart, **not**
  its root cause; look up guest CrashReporter/launchd death evidence.
- An iconservicesagent CPU spike is correlated activity, not proof that
  icon decoding is the cause of the user's three-second Settings delay.

This instrumented run intentionally does not change `gpu-level`, clock
policy, `ram-prefault`, vCPU count, resolution or frame pacing heuristics.
An A/B optimization follows only after collecting two comparable active
windows and cold/warm Settings observations. The 600s session is unverified
on this new instrumentation until S26 Ultra device acceptance succeeds.


## Unplugged 10-minute preview with deferred log collection

The first physical-USB unplug trial did not necessarily stop the iOS guest.
The old host polling loop failed with `adb: device ... not found` while
the 600-second on-device script continued. Reconnected log analysis had
117 five-second display windows, 19.92 Hz median active-post cadence,
912.5 ms worst touch-to-frame, 32 touches without a subsequent guest frame,
39.42 ms maximum GPU fence, 55,975 task traps/s peak and only 1006 MiB
minimum Android MemAvailable. SpringBoard/backboardd maintained PIDs 30/52.
20 host_statistics64 ABI warnings remain. This does not prove a GPU fault
or isolate exactly why Settings icon loading takes ~3 seconds.

Use an explicit detached run when walking around with the phone:

```sh
python3 scripts/phone/sm8850-ios-gpu-visual.py run \
  --touch --duration 600 --ram-mib 4096 --detach
```

Keep USB attached until `DETACH_READY=YES; SAFE_TO_UNPLUG_USB=YES`,
which requires exact `running` state, the exclusive physical touch grab,
first posted frame and positive guest GPU fence. The runner then stops
host ADB polling and saves the stage path; **the 600-second device-side
TERM/KILL deadline remains armed**. It does not stop the guest or start
another one. The APFS clone is consumed and must never be booted again.

After the phone returns to One UI and USB is reconnected, run:

```sh
python3 scripts/phone/sm8850-ios-gpu-visual.py collect \
  --stage /data/adb/oneios-m3q-gpu-snapshot-REPLACE_WITH_16_HEX
```

Replace the placeholder with the exact `COLLECT_AFTER_RECONNECT_STAGE`
value from the detached run. `collect` does not build, create a snapshot,
launch a guest, write sysctls or perform takeover. It refuses live or
invalid stages and downloads the three existing logs only after the state
is `finished:<code>`, then prints/saves performance metrics in the usual
`out/sm8850/gpu-acceptance/` directory. Read-only collection can repeat.

If USB is disconnected before readiness or while running the old
non-detached CLI, a PC-side ADB error does not prove that the guest died.
Do not launch a second guest. Preserve the printed STAGE_PATH, allow the
on-device deadline to end, reconnect and use `collect`.

The manual ADB emergency-stop procedure is unchanged. Note the small
Android memory reserve in the last measured session: do not increase the
session beyond 600 seconds or leave the phone unattended for now.


### Optional trace-off A/B (new, no runtime policy change)

To test whether verbose GPU command logging adds latency, launch exactly
the same bounded visual guest with one extra opt-in flag:

```sh
python3 scripts/phone/sm8850-ios-gpu-visual.py run \
  --touch --duration 600 --ram-mib 4096 --detach --no-gpu-trace
```

The baseline `run` command still enables GPU trace. `--no-gpu-trace`
UNSETs `ONEIOS_GPU_TRACE` in the device-side shell; `ONEIOS_GPU_TRACE=0`
would be wrong because the native code tests only whether it exists.
Read-only 5-second display timing, CPU task traps, GPU fence summaries
and input-to-next-frame diagnostics remain enabled. The run log records
`GPU_TRACE_MODE=off_for_ab` and the JSON report records the trace mode.
The same 600-second phone-side timeout and no-takeover/one-shot gates
still apply. This does NOT suspend or alter Spotlight or iOS CPU policy.

Use `collect --stage` only after `DETACH_READY` and the guest deadline.
Compare `GPU_VERBOSE_TRACE_LINES`, `SPOTLIGHT_CPU_PEAK_PERCENT`,
`DISPLAY_ACTIVE_CADENCE_MEDIAN_EST`, `TOUCH_TO_FRAME_MAX_MS` and the
observed cold/warm Settings opening times against the preceding
trace-enabled run. The trace-off option is an experiment, not a claimed
FPS fix.
