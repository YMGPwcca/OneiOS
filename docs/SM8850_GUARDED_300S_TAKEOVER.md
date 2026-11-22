# SM8850 bounded 3D takeover: duration, root thermal policy and stall evidence (draft)

**Status: NOT PHONE-QUALIFIED. DO NOT EXECUTE A LIVE FULL TAKEOVER YET.**
This branch is for local CI, review and *read-only* physical admission checks.
It does not claim a hard maximum below 80°C or independent watchdog certification.

## Planned interface (once all admission gates pass)

```bash
cd ~/projects/OneiOS
python3 -u scripts/phone/sm8850-600s-thermal-telemetry.py \
  --duration 300 \
  --i-accept-10-minute-legacy-watchdog-risk
```

`--duration` accepts **60..600**; **600 is the default**. The deadline
is applied by root OneOS and measured from verified Android Framework stop,
not from Python launch. Telemetry captures the last snapshot at approximately
`duration-10`: 300→290 s, 600→590 s. `--no-rearm` skips the one-shot
APFS Data refresh; after a previous guest write **do not use it** unless
a separate verified rearm has already finished. A consumed Data clone
must never be reused. The existing long-form 10-minute risk acknowledgement
names the maximum risk profile; selecting 300 does not certify watchdog safety.

## Read-only admission and default duration

After a fresh Data clone has been rearmed and both staged scripts have been
upgraded (these operations **never stop Framework**), verify the exact
requested deadline without consuming APFS Data:

```bash
cd ~/projects/OneiOS
python3 -u scripts/phone/sm8850-600s-thermal-telemetry.py \
  --duration 300 --preflight-only
```

This requires rooted One UI and checks a current-boot pinned thermal manifest,
temperature readings and writable-but-not-yet-written CPU policies. It does
not itself prove subsecond reaction, thermal safety, or independent watchdog
hardware recovery. Exit zero/terminal PASS is **read-only admission only**.

Once genuinely qualified by local tests and the physical recovery checks,
the preferred command for the FIRST session after the previous consumed
600s snapshot is the top-level telemetry invocation **without**
`--no-rearm`; it will first archive the consumed Data and prepare
a fresh one-shot clone. The explicit user-requested `--no-rearm` form is
valid ONLY AFTER that separate rearm has already finished. Never re-use
the consumed snapshot. Omit `--duration` for the 600s default.

```bash
python3 -u scripts/phone/sm8850-600s-thermal-telemetry.py \
  --duration 300 \
  --i-accept-10-minute-legacy-watchdog-risk
```

After an observed root-capable return, `sm8850-takeover.py --collect`
includes `thermal-guard.log`, `thermal-cap.log`, both heartbeat records
and `thermal.guard.manifest`. It automatically runs the offline frame
stall correlator, producing `frame-stall-report.json`, if the archive is
complete. The report is evidence of *candidate* missing-frame windows;
it is not yet a per-thread CoreAnimation critical-path profiler.

The staged OneOS commit is pinned as the `app` submodule on this branch.
Do not update only one repository; OneiOS's host stager must package the
root workers from precisely the matching OneOS revision.

## CPU/vCPU behavior

* Guest runs `--cpus 8`, GPU `3d` required (no 2D fallback), `bridges=0`
  to preserve exclusive touch setup.
* `cpu-affinity-bench=1` and `cpu-pin=1` instruct xnuhost to map
  **each vCPU and its runnable guest user threads to one distinct allowed
  physical core**. Success MUST be confirmed in 8 per-vCPU
  `cpu: bench-affinity vCPU ... -> host CPU ...` log lines and the
  `bench-affinity=1` summary, not assumed from the 0-7 cpuset.
* An independent root thermal monitor is staged with a boot-pinned CPU/GPU/DDR
  junction manifest. It runs outside the guest cgroup and starts BEFORE
  Framework stops; it must publish fresh boot/generation/PID-birth heartbeats.
* The separate root CPU frequency-cap worker starts **AFTER** confirmed
  Framework stop, but BEFORE xnuhost. This prevents an aborted pre-stop
  attempt leaving One UI under an unexpected CPU cap.
* Current experimental monotonic levels: <55C→60%; >=55→40%;
  >=65→28%; >=72→18%; >=77→12%; >=80→8% of hardware max, never less
  than the greater of the hardware minimum and Samsung's *current dynamic*
  `scaling_min_freq` vote and never overriding a tighter external cap.
  It intentionally favors heat reduction over frame rate. If Samsung's
  active minimum is above the computed cap, the worker logs
  `P0_CPU_CAP=MIN_FLOOR_LIMITED` and uses the minimum without modifying
  `scaling_min_freq` or `cpufreq_max_limit`. The requested 8% cap
  is NOT guaranteed to be the effective cap.
  These percentages are frequency ceilings, NOT a guaranteed fraction of
  CPU work or power.
* At >=80°C the controller throttles; it does **not** normally return.
  Independent return is still a last-resort emergency at >=90°C CPU
  junction, missing sensor, lost/stale worker heartbeat or failed sysfs
  verification. The phone's own kernel/firmware thermal trips remain enabled.
* A software controller cannot promise to *always* stay <80°C: sensors,
  effective Samsung frequency QoS, scheduling, and sampling latency need
  SM8850 physical measurements under supervised cold conditions.

## Local-first host CI (CachyOS)

```bash
cd ~/projects/OneiOS
git fetch origin feat/sm8850-guarded-duration-tracing
git switch feat/sm8850-guarded-duration-tracing
git submodule update --init app
test "$(git -C app rev-parse HEAD)" = "$(git rev-parse HEAD:app)"
python3 scripts/phone/test-sm8850-takeover.py -v
python3 scripts/phone/test-sm8850-full-takeover.py -v
python3 scripts/phone/test-sm8850-stage-upgrade.py -v
python3 scripts/phone/test-sm8850-oneos-legacy-feeder.py -v
python3 scripts/phone/test-sm8850-guarded-duration.py -v
python3 -u scripts/phone/sm8850-600s-thermal-telemetry.py --self-test --duration 300
python3 -u scripts/phone/sm8850-600s-thermal-telemetry.py --self-test --duration 600
python3 app/tests/test_sm8850_guarded_full.py -v
```

The commands above contain no ADB and no Framework stop. Do not infer a
full production CI PASS from source-level checks; all executed suites and
CachyOS results still need evidence. Before any live run, validate under
normal One UI: 80/90°C sensor units, emergency trip provenance, worker
heartbeat reaction timing, Samsung CPU min/max readback, root process
independence and recovery after injected monitor death (with a
**non-destructive fixture**, never by overheating the phone).

## Observed SM-S948B hardware evidence (2026-11-22)

Root-backed One UI inventory verified CPU0–5 policy0 and CPU6–7
policy6 with hardware ranges 384000..3628800 and 768000..4742400 kHz.
Samsung's `cpufreq_max_limit=2112000` applied an existing vendor ceiling.
Five read-only thermal/cpufreq policy checks passed, including 16 CPU,
11 GPU and 1 DDR temperature zones; each ADB round trip took ~1.0s,
which is NOT the resident worker's reaction latency.

A supervised **1-second per-policy write/readback** under healthy One UI
accepted a 40% policy request and rounded down:
`policy0: 1451520 → 1440000 kHz` and
`policy6: 1896960 → 1862400 kHz`. Both restored to the
original `2112000 kHz`. This verifies *one* level on real
hardware; it does NOT certify stronger caps or the runtime worker.

Crucial: Samsung `policy0/scaling_min_freq` was initially observed at
`384000` kHz but later at `1228800` kHz without us changing that
minimum. The revised worker validates and clamps to the live minimum
on **every tick**, continues to lower `scaling_max_freq` where possible,
and logs when the requested cap is blocked by Samsung's current vote.
If the floor remains at `1228800` kHz at 80°C, the nominal 384 MHz
policy0 target CANNOT be reached by this non-invasive controller.
The root 90°C emergency/heartbeat failure path remains unqualified.
No thermal runaway, death-of-monitor, watchdog or full 300s
live takeover test was performed to obtain these data.

After syncing an updated `app` submodule into an already rearmed
phone, use the **reboot-stage-check upgrade** to install revised
OneOS scripts without consuming or recloning the current one-shot
APFS Data. Run the exact 300s read-only preflight again. Neither
step qualifies unassisted recovery or authorizes the live run.

## 2026-11-22 300s physical run: guest boots, panel/touch interaction fails

The actual S26 Ultra run from the original 300s guest clone verified
`IOS_GUEST_READY=OBSERVED`, first frame, 8-host-CPU mask and KGSL GPU 3D
logs. The guest remained under the bounded 300s deadline, and Android
`sys.boot_completed=1` was observed on a new boot afterwards; ephemeral root
was lost, so the post-reboot result correctly stayed unverified.

The operator **could not swipe to unlock** and saw a dim/sleeping panel.
This is an **interactive FAIL** despite the successful guest boot markers.
The telemetry alone does not prove the physical touch IC's `enabled`
state or whether raw touch gestures reached the guest: it did not include
the session's complete `xnuhost.log`.

Root cause candidates directly visible in pinned source:
* The 8-vCPU exclusive bench deliberately runs `bridges=0`. No
  brightness bridge is initialized, so the host will inherit any sleeping
  One UI display/touch IC state; OneOS only recorded and restored the
  backlight, not its live wake transition.
* `touch-exclusive=1` filtered out all key-only devices, including
  the physical Power key. There was no way to wake an iOS lock screen
  through Power even if it had entered guest sleep.

**Source mitigation (not physically certified):** OneOS now sends
`input keyevent KEYCODE_WAKEUP` to healthy Android **before** the Framework
stop and refuses takeover if the wake event cannot be delivered.
The touch-exclusive xnuhost code now listens, without `EVIOCGRAB`,
to exactly one Power key source and forwards only Power to guest HID.
Volume keys remain reserved for the root recovery watcher and are
suppressed even after SYN_DROPPED resync. No active Samsung sysfs
touch/panel control or `bridges=1` shortcut was added.

This mitigates inheritance of a dark host panel and loss of Power wake
events. **It is not proof** of backlight power transitions after an iOS
sleep event or functioning end-to-end touch. Before another live run,
build the UPDATED xnuhost runtime locally, run native and shell tests,
prepare a fresh one-shot APFS Data clone, then check physical touch
gesture logs and TSP state while the guest is live. Never reuse the
consumed 300s Data clone or deploy only the updated switcher against
an obsolete xnuhost binary and claim the bug fixed.

## Diagnosing 1–2 second UI frame stalls

`sm8850-frame-stall-report.py` correlates already collected
`session/xnuhost.log` and `control/display.log`: touch summaries,
5-second display windows, guest CPU load and trap rates. Example:

```bash
python3 scripts/phone/sm8850-frame-stall-report.py \
  --archive out/sm8850/takeover/post-run-20261121/device-logs.tar \
  --output out/sm8850/takeover/post-run-20261121/stall-report.json
```

This is a **read-only offline correlator**, not a complete live
touch→CoreAnimation→GPU fence→display correlation tracer. It produces
candidate gaps, including genuine idle periods; it does not prove
causation. Exact per-thread blocking stacks and true per-frame
timestamps are still future instrumented work. Changing the guest 60 Hz
configuration cannot repair 1–2 second freezes; prioritize CPU/VM
contention and the stage where no new frame is produced.

## Critical known blockers

1. Full physical thermal response/readback and independent watchdog
   behavior have **not** been validated with this code.
2. Both `cpuinfo_min_freq` and Samsung's dynamically changing
   `scaling_min_freq` can prevent 8% of maximum from applying to
   Snapdragon Oryon; preserve external minimum votes and report clamped
   limits instead of claiming the nominal target was applied.
3. A root-owned cpufreq limit may persist if the hardware unexpectedly
   escapes the designed reboot-only return path; production recovery
   needs explicit restoration assurance.
4. Aggressive clamping can significantly worsen first-boot iOS
   frame starvation. It is a user-requested thermal-priority trial,
   not a completed performance fix.
