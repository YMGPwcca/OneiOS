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

## 2026-11-22: Physical thermal abort BEFORE xnuhost (session 6dd8f9d5)

**Physical result: thermal FAIL-CLOSED / mandatory reboot, not an iOS guest
crash and not a 300-second deadline return.** On boot
`7c0491a7-38ba-4e65-8330-57e9844d9371` the OneOS switch entered
Framework stop at 15:45:29 local. At 15:45:42 the independent thermal
guard recorded `soft_temperature_abort crossed=cpu`:
`cpu_mC=95000 cpu_zone=cpu-1-0-1@25`,
`gpu_mC=50500`, `ddr_mC=50200`. Its preceding heartbeat had
`cpu_mC=84500`. The watcher/return path requested
`reboot,oneios-sm8850-reboot-return`, and the next Android boot completed.
The `control/state=starting` record and absence of
`control/framework.deadline`, `session/ready` and current display first
frame mean **the guest did not start**. Do not attribute this run to
Power/HID/Metal or call it a successful 300-second takeover.

The *append-only* `thermal-cap.log` tail includes repeated
`P0_CPU_CAP=MIN_FLOOR_LIMITED` messages showing
`scaling_min_freq=2112000 kHz` on both policies, higher than the
requested 40% ceilings (`policy0=1451520`,
`policy6=1896960` kHz). **Those lines did NOT contain boot ID or
generation**, so they cannot conclusively be attributed to this
aborted session; earlier statements calling them concurrent were
overstated. OneOS now appends `boot` and `generation` to future cap
floor messages. A high active Samsung minimum is a plausible
contributor to overheating, not an established cause. The switch
recorded `MemAvailable: 8828480 kB` after Framework stop, so the
earlier low-RAM hypothesis is refuted. The 95 C reading was reported
by the kernel sensor; corroborating sensor evidence was not captured.
Treat it as a real safety event until shown otherwise.

### 2026-11-22: Conservative boot CPU ceiling (not disabling thermal guard)

Operator reports repeated CPU kernel-zone readings around 90-100 C
during iOS bring-up and proposes removing the script thermal guard to
avoid early reboot. **Do not remove the emergency exit at 90 C on the
present unqualified SM8850 firmware/watchdog setup.** The threshold is
a conservative *experiment* cutoff, not a verified silicon critical
temperature; nevertheless, a 95 C reading has already been observed
before xnuhost starts, and the kernel/firmware thermal behavior during
Framework takeover is not independently qualified.

Instead, in the live `--run-prearmed` CPU cap, start at thermal
policy **level 2 (40% of hardware max)** on the first successfully
validated, post-Framework-stop thermal sample, even when all sensors
are cool. Previously the initial level was 0 and idle samples selected
level 1 (60%). Existing stricter transitions remain monotonic:
65 C -> 28%, 72 C -> 18%, 77 C -> 12%, 80 C -> 8%.
A stricter policy also applies based on GPU, DDR, battery, LRP and
board sensors. At 90 C CPU or the other emergency cutoffs, the
independent guard STILL returns via the same recovery chain.

For the measured hardware max values 3,628,800 and 4,742,400 kHz,
the initial 40% requested ceilings are 1,451,520 / 1,896,960 kHz.
Samsung `scaling_min_freq` may rise to 2,112,000 kHz or more; when
that makes the requested ceilings impossible, the cap correctly
fails closed rather than lying about enforcement. It **never writes**
`scaling_min_freq`, thermal trips or kernel temperature policies.
No changes were made to 8-vCPU pinning, the GPU-3D requirement, or
reboot-only recovery.

The new regression verifies this boot baseline, later monotonic
throttle bands, and the unchanged 90 C emergency. Success in local
offline CI and script staging does not imply full iOS boot or
physical thermal safety. Test in the prior required order: local
CachyOS CI, then non-takeover stage check. **No destructive live
takeover is authorized by this change alone.**

### 2026-11-22: Close the Framework-stop / CPU-cap activation gap (offline only)

Before this change, the independent root CPU-cap process was created only
AFTER `stop_android_framework()`, the legacy watchdog FD handoff, the
watchdog feeder, app cgroup drain, Android input service checks and
`vm.max_map_count` setup. The 2026-11-22 physical incident showed a
95 C CPU guard fault during this window, BEFORE xnuhost launched.
Even the later strict cap could not protect CPU clocks before its worker
existed.

OneOS now **prearms** the CPU cap worker in the root context
before `KEYCODE_WAKEUP` and the 45-second Framework cutoff. It
publishes generation-bound PID/birth metadata and remains **read-only**
while the Android Framework is alive. The switch verifies that the
prearmed worker is alive before stopping One UI. The independent
framework-deadline guard also checks that the worker stays alive.

The worker does **not** call `apply_cap` until all these conditions
hold together: the same session's `control/stopped` marker exists,
`init.svc.zygote` and `init.svc.zygote_next` are stopped,
any secondary zygote is stopped, and `pidof system_server` fails.
Only THEN does it start applying strict thermal ceilings using the
existing fresh, boot/generation-matched root thermal heartbeat. On an
unachievable minimum-frequency vote it emits
`P0_CPU_CAP=UNENFORCEABLE_MIN_VOTE`, sets
`thermal.cap.fault`, and the existing return path fails closed.
On a pre-stop refusal/return it exits without any cpufreq sysfs write.
The switch still requires a current active CPU-cap heartbeat before
allowing a guest boot, and its watchdog guard observes worker/fault state.

Host-only synthetic tests exercise the actual framework-down gate
with absent marker, running zygote, running `system_server`, and
verified-down cases; other regression tests assert the worker is
started before Framework stop and strict cap is enforced only after.

**Safety status:** Not yet validated in a live takeover on the SM-S948B.
A transient CPU thermal peak can still occur despite quicker capping,
and independent watchdog/unassisted return qualification remains
UNVERIFIED. Do not rearm Data or run a new 300-second session merely
because local tests pass. Stage-only updates are the permitted next step
after clean CachyOS CI.

### 2026-11-22: Passive 30-s One UI CPU-floor experiment (no wake sent)

On fresh boot `2206c054-cc72-4e47-9598-3a17fe872b25`,
the operator captured 30 one-second passive samples from thermal zones
6/24/25/26/27, GPU43, DDR47 and cpufreq policies 0/6.
There was no scripted `KEYCODE_WAKEUP`, no guest, no Framework stop,
and no APFS rearm.

* Background: policy0 min=384000, policy6 min=768000 kHz; CPU zones
  around 33-38 C.
* Sample 19: CPU zone6=68900 mC, zone25=55200 mC,
  zone27=61400 mC; BOTH policy minima=2112000 kHz.
  This is correlated multi-zone activity rather than an isolated
  single-sensor spike.
* Sample 23: policy0 minimum=maximum=3398400 kHz,
  policy6 minimum=maximum=3763200 kHz.
* Sample 28: policy0 minimum=maximum=3513600 kHz,
  policy6 minimum=maximum=3974400 kHz.
  These are high performance votes in normal One UI, not proven to be
  caused by the previous wake event. The measured maximums also vary.
* Sample 29: minimums fell to 1228800 / 883200 kHz.

**Confirmed safety gap in the old independent cap worker**:
`apply_cap` raised its requested ceiling to Samsung's higher
`scaling_min_freq` and then still published heartbeat `OK`, even
when the required 40% / 28% / lower thermal throttling could not be
enforced. It did NOT change the vendor minimum, but it could give
misleading assurance of a successful cap.

The OneOS worker now uses a **strict mode in live --run only**:
if a policy's observed minimum exceeds its requested ceiling
(after clipping the request to the hardware minimum), it logs
`P0_CPU_CAP=UNENFORCEABLE_MIN_VOTE` with boot and generation,
fails its thermal-cap heartbeat, and publishes `thermal.cap.fault`.
The existing independent return path can then abort instead of
waiting for the last-resort 90 C thermal fault. The strict preflight
checks both policies before writing either ceiling and rechecks
immediately before a write to handle racing external votes.
Synthetic fixture tests cover the observed 2.112 GHz and min=max
cases and normal ceilings after votes release.

This is **fail-closed, not permission to run live**. CPU minima may
rise after the gate or before the worker starts; the earlier 95 C
physical incident remains unproven as to initiating cause.
No unconditional sleep/wake, session duration, or temperature
threshold was relaxed. No new live takeover is authorized solely by
passing the offline CI for this patch.

### Physical wake CPU-frequency vote (read-only experiment)

With One UI healthy, a single `input keyevent KEYCODE_WAKEUP`
produced a transient `policy0 scaling_min_freq` rise from
`384000` to `1228800` kHz and `policy6` from `768000` to
`883200` kHz for about 7-8 seconds, then both returned to baseline.
Instantaneous observed CPU frequencies reached
`3628800` / `3648000` kHz, and thermal_zone25 rose from
`32800` to `40900` milli-C before cooling.
**This experiment did not reproduce 2.112 GHz minimum votes or
the 95 C abort**, so it does not prove causation.

OneOS previously sent wake only 0.5 s before stopping `system_server`,
during the performance boost window. The updated source sends exactly
one wake **after the root thermal guard is armed but BEFORE** the
45-second Framework-stop cutoff starts. It then waits at least
8 seconds and requires three consecutive fresh guard-healthy samples
with `policy0/policy6` minimums at their hardware floors and
CPU/GPU/DDR peak readings below 60 C. If not settled within
20 seconds, the switch requests an ordinary pre-stop refusal, leaving
the Framework running. It never writes either CPU minimum, relaxes
the thermal trip, or overrides a fault. The single wake remains
unproven for panel/TSP behavior until an actual iOS gesture test.

This addresses one avoidable race but **does not establish why
thermal_zone25 reached 95 C**. Do not certify or rerun live takeover
solely because the local tests of the mitigation pass.

**No more live takeover runs with this thermal configuration.** Do
not lower the 90 C guard threshold, silence the guard, or force down
Samsung's `scaling_min_freq` by an unqualified sysfs write.

Host-only telemetry bugs repaired for future analyses:
`PRE_ONEUI` now suppresses `guest_ready`, display and SpringBoard
markers from a different boot; after an observed Android reboot, the
host telemetry wrapper bounds the waiting time and terminates ONLY its
isolated local process group. It never signals the phone. Both fixes
have offline tests; they do not address thermal overheating.

## 2026-11-22: Rebuild existing runtime without reusing consumed APFS Data

The local NDK build and all native tests passed after the touch/Power
patch, but `sm8850-full-takeover.sh prepare` correctly refused with
`STAGING REFUSED: one-shot Data was already used`. A first-time
`prepare` installs a complete isolated image only when there is no old
Data. It does NOT replace an existing guest runtime in place. The old
`rearm` command cloned Data but silently kept the previously built
`xnuhost`, which would have defeated the touch fix.

**Updated procedure on the confirmed SM8850 branch**:

```bash
bash scripts/phone/sm8850-guarded-local-ci.sh
bash scripts/phone/sm8850-full-takeover.sh rearm R5GL64LZ9HA
```

`rearm` now (1) checks/updates OneOS scripts, (2) builds the current
Android `xnuhost` and display helpers on CachyOS, (3) uploads and
SHA-256-checks exactly four native artifacts, (4) archives the previous
runtime and manifest under `.rollback/runtime.*` before replacing them,
and (5) archives the consumed private APFS Data and its marker before
cloning fresh Data from the separate benchmark seed. **No guest starts
and Android Framework is not stopped.** The native runtime upgrade
requires `data.consumed`; it never makes consumed Data bootable.
`NATIVE_RUNTIME_UPGRADE=PASS_BACKUP_PRESERVED`,
`APFS_DATA_REARMED=YES`, and `FULL_TAKEOVER_STAGE=REARMED`
must all be observed before any later live session.

The new host-only synthetic test
`scripts/phone/test-sm8850-native-runtime-upgrade.py` executes the
actual upgrade function on fake native files, rejects corrupt hashes,
and checks that the consumed Data stays untouched. On a failure AFTER
the ready marker is disarmed, the stage remains fail-closed until
investigated; do not delete `.rollback` or forcefully bypass markers.

No further live takeover should be claimed successful until physical
Power wake and raw swipe interaction are actually observed. Source
mitigations are not proof that Samsung display/TSP power state survives
an iOS sleep/wake cycle.

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
