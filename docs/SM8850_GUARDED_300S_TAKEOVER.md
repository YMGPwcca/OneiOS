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

## Experimental FULL hardware bridges=1 (local CI PASS; phone not staged)

The user explicitly selected **real `bridges=1`**, not a
brightness-only partial workaround. Both repositories now use the
`feat/sm8850-full-bridges-takeover` branch. OneOS passes
`--set bridges=1 --set sm8850-full-bridges=1 --set touch-sleep=0`
and `--set cpu-affinity-bench=0 --set cpu-pin=1` in the SM8850
8-vCPU GPU3D Framework run, retaining `touch-exclusive=1`.

This runs the GENERIC xnuhost bridges=1 initialization, including
host CPU topology, cpufreq virtio MMIO, brightness with Samsung TSP
power control, battery and the guest thermal-pressure bridge.
`wifi=off`, `haptics=off`, `bluetooth=virtual` and `encoder=off`
remain explicit per-device choices for the first integration.
They are **not evidence that bridges=0**: the generic bridge device
is present with CPU/brightness/battery/thermal channels.
The legacy `cpu-affinity-bench=1` is incompatible with the real CPU
bridge; CPU placement now uses the native bridge's plan and
`cpu-pin=1`. This changes performance/affinity semantics and is not
yet verified on SM8850 hardware.

Before opening any host bridge or grabbing raw touch, xnuhost checks
the rooted OneOS experimental session: current boot ID, current
watchdog generation, `framework.mode=run`, reboot-only return,
independent guard/cap requirements, Framework stopped, absent
`system_server`, and a distinct session mount namespace.
`sm8850-full-bridges=1` is rejected outside this exact
bench/shm/8cpu/GPU3D/exclusive-touch profile. Missing CPU topology,
cpufreq MMIO, Samsung panel/TSP, battery, thermal or virtio
bridge fails closed. Normal phone / PC preview behavior remains
unchanged.

OneOS blocks stale native runtimes before the one-shot APFS Data
claim: it must find the new `SM8850_FULL_BRIDGES=ACTIVE` marker in
the installed arm64 xnuhost. Source-only branch update is not enough:
rebuild and verify the actual runtime package **separately** before
any phone staging. The independent thermal guard (90 C emergency),
40% boot CPU cap, watchdog and reboot-only return are all unchanged.

**Current status (operator log, 2026-11-22):** OneiOS
`9cff1c0cbdddb43bb24d1056ed554556af32d2c2` and OneOS
`3d40343bfc800c49112e2cbebbb4d2c939ecbe82` passed CachyOS local
full-bridges CI: 19 Python tests, 14,327 native assertions (zero
failures), and an NDK r28c arm64 Android 30 xnuhost link with
`SM8850_FULL_BRIDGES=ACTIVE`. This is **local code/build evidence only**;
there is no new full-bridges phone stage, boot, touch, thermal, or recovery
acceptance. `--reboot-stage-check` upgrades OneOS scripts only and must
not be mistaken for installing the new xnuhost.

### Full-bridges stage-only follow-up (non-takeover)

The `feat/sm8850-full-bridges-takeover` wrapper now deliberately rejects
`prepare`, `rearm`, and `run` on this experimental branch until
independent thermal and reboot-only recovery qualification is complete.
The new `stage-runtime` action is restricted to this branch. It checks
that the local prebuilt xnuhost has the full-bridges marker, checks that
all four native artifacts exist, upgrades the OneOS root scripts with
rollback preservation, and upgrades the four native artifacts with
hash verification and the existing rollback archive. It **does not**
start a guest, stop Android Framework, clone/rearm Data, or consume a
one-shot APFS Data image.

```bash
cd ~/projects/OneiOS
git pull --ff-only
git submodule update --init --checkout app
# Only after existing phone state and root are verified:
bash scripts/phone/sm8850-full-takeover.sh stage-runtime R5GL64LZ9HA
```

Stage-only is intentionally refused when the existing phone stage has
not recorded consumed one-shot Data: the underlying `upgrade-runtime`
operation requires a trusted, already-consumed Data marker. Do not
delete or fabricate that marker, and do not rearm a clone merely to
make staging pass. Missing prebuilt display helpers or unavailable
ephemeral root are also blockers; do not treat an offline arm64 xnuhost
build as a complete staged runtime. On failure, preserve existing
`.rollback`, `image.ready`, and `data.consumed` state and inspect the
logs. Before deploying, inspect the wrapper's guard branch and the
current phone state; stage-only is not physical admission.

The original physical 95 C thermal abort before xnuhost, Samsung's
dynamic CPU frequency minimum votes, and unqualified watchdog/unassisted
return remain hard blockers for another live takeover. A staged binary
is not proof that the CPU/thermal/brightness/touch bridges work on the
device.

## 2026-11-23: Short lockscreen auto-sleep and bounded pre-Framework WAKEUP

Operator reports Samsung One UI lockscreen darkens ~5 seconds after a
`KEYCODE_WAKEUP`. Previously, the no-userspace-thermal run sent one
`input keyevent KEYCODE_WAKEUP`, slept 8 seconds, and then proceeded
through additional recovery gates before stopping zygote: the panel
could be asleep by the time XNUHost started.

For this **opt-in 180s experimental profile only** OneOS now sends
four `KEYCODE_WAKEUP` events at 2-second intervals while
`system_server` and zygote are still running, plus a **final** event
immediately before writing `control/stopped` and requesting
`ctl.stop zygote`. If Android input refuses a pulse it fails the
session rather than claiming the panel was woken. The standard
thermal-guarded profile retains its own single wake and strict
thermal/cpufreq checks.

The extra wakeups may temporarily elevate Samsung's CPU minimum votes;
the opt-in cap remains **28% best effort only**. This change does NOT
spam Android's `input` for the full 180 seconds: after
`system_server` stops, Android InputManager can no longer reliably
accept `input keyevent`. There is **no proof** the physical panel
will remain powered on for all 180 seconds under Keyguard. If a
screen-off timeout is temporarily changed on Android to help the
panel remain on, restore the original setting after return to One UI.
Do not disable kernel/firmware thermal policy.

Next action after pulling updated OneOS submodule: run local shell
syntax and OneOS tests, then run `stage-runtime` again to install
the OneOS-only switch change (it does NOT rearm consumed APFS Data).
The XNUHost binary from the previous successful build remains valid
and need NOT be rebuilt. The bounded telemetry live runner automatically
rearms fresh APFS Data (do not pass `--no-rearm`). Never interpret
WAKEUP success as guest first-frame proof.

## 2026-11-23: Actual 180s physical outcome and XNUHost admission mismatch (FIXED IN SOURCE, NOT RETESTED ON PHONE)

Run `20261122T202736Z-b9f152a4`, boot
`dc38c332-7223-48e6-bdcf-672f3cf99ed4`, launch token
`dfb7a37d782e432c98e2c4153e2af62a`:

- Local 47/47 initial Python contracts passed; stage/rearm/preflight
  succeeded. APFS Data was marked consumed before Framework stop.
- Actual switch log confirms `THERMAL_GUARD=OFF_NO_PROCESS_NO_HEARTBEAT_NO_SOFT_RETURN`,
  no mandatory CPU cap worker, `framework.soft-thermal=disabled-180s`.
  The independent best-effort CPU cap wrote
  `cpu.best-effort.status=... pct=28 status=APPLIED_OR_ALREADY_TIGHTER`;
  this is a single successful initial application, NOT proof of sustained
  28% maximum or safe operating temperatures.
- The Framework actually stopped: `MemAvailable: 8856520 kB`, zygote
  `stopped`, system_server gone, 180s deadline `5236` established
  after verified stop at uptime `5056`. Thus the previous RAM 5.5GB
  hypothesis is excluded for this session.
- XNUHost exited before opening physical hardware:
  `SM8850_FULL_BRIDGES=BLOCKED_FRAMEWORK_OR_STAGE_NOT_VERIFIED; no host hardware opened`.
  The switch wrote `control/state=failed`; `oneios_return.sh`
  requested `reboot,oneios-sm8850-reboot-return` immediately, watcher
  subsequently observed the failure. This was not a 180s deadline expiry.
  `return.outcome=... who=watcher reason=` is not a reliable first-caller
  record because two return paths raced after the failure. Guest
  `bridges=1`, KGSL3D backend, boot, first frame and 8-core affinity
  remain UNVERIFIED.
- **Root cause (verified by source):** XNUHost's
  `runtime/xnuhost/src/main.c::sm8850_full_bridge_admitted()`
  unconditionally required `thermal.guard.required` and
  `thermal.cap.required`, although OneOS had deliberately removed
  both markers for the explicit no-software-guard mode. The previously
  staged binary passed only the generic
  `SM8850_FULL_BRIDGES=ACTIVE` presence check, not protocol
  compatibility.

New source contract:

- XNUHost classifies stage proof via `sm8850_stage_admission.h`.
  Default full takeover still requires both thermal workers' matching
  generation. The exceptional `disabled-180s` profile requires:
  exact `framework.mode=run`, `framework.return=reboot`,
  `framework.duration=180`, same-boot `control/boot`,
  exact `framework.takeover-confirmed == watchdog.generation`,
  a nonzero numeric `framework.deadline`, root euid, isolated
  mount namespace, stopped zygotes and absent system_server.
  A different or incomplete token fails closed.
- A matching native binary includes
  `SM8850_FULL_BRIDGES=ADMITTED_NO_USERSPACE_THERMAL_180S`.
  OneOS now REFUSES the old binary during root preflight BEFORE APFS
  consumption; `sm8850-full-takeover.sh stage-runtime` also refuses
  it before staging. The old generic `ACTIVE` marker alone is
  insufficient for this mode.
- Host-only `runtime/xnuhost/tests/test_sm8850_stage_admission.c`
  checks good and bad generation, duration, deadline and markers;
  `scripts/phone/test-sm8850-takeover.py` also checks the cross-repo
  source protocol. Neither test substitutes for hardware qualification.

**Next required operation is build+stage, NOT another live run:**

```bash
cd ~/projects/OneiOS
git pull --ff-only
git submodule update --init --checkout app
make -C runtime/xnuhost build/host/test_sm8850_stage_admission
runtime/xnuhost/build/host/test_sm8850_stage_admission
python3 app/tests/test_sm8850_guarded_full.py -q
python3 scripts/phone/test-sm8850-takeover.py -q
make -C runtime/xnuhost -j8 build/android/xnuhost
grep -aFq 'SM8850_FULL_BRIDGES=ADMITTED_NO_USERSPACE_THERMAL_180S' runtime/xnuhost/build/android/xnuhost
bash scripts/phone/sm8850-full-takeover.sh stage-runtime R5GL64LZ9HA
```

The stage-runtime operation updates scripts/native binaries with backups,
**without APFS Data rearm and without Framework stop**. Display binaries
from the earlier locally validated runtime are reused unchanged.
Because the last physical attempt already consumed Data, any subsequent
physical trial must fresh-rearm Data once before launching (the bounded
telemetry runner does that by default). Do NOT rerun the old staged
binary and do not claim a guest success before independent runtime logs
show the current session's actual bridges=1 activity.

**High risk:** the operator-selected mode has NO OneOS software thermal
cutoff on a device that previously reached 95-101.1C. The 28% cap is
best-effort; kernel and firmware limits are not a guarantee against
hardware damage. Recovery watchdog and unassisted return have not been
fully qualified. Only the device owner, present at the hardware and
prepared for manual recovery, can decide whether to run another live
trial. No new physical test is claimed by the source patch.

## 2026-11-23: Requested exact 180s **NO OneOS thermal guard** and nonfatal CPU cap

The 2026-11-22T190445Z physical 180s attempt aborted after
`thermal.cap.fault=unachievable_cpu_cap_floor level=2 pct=40`.
Root `thermal.guard.fault` was missing: this was a **CPU cap vote conflict**,
not evidence of a 90C sensor cutoff. The returner requested
`reboot,oneios-sm8850-reboot-return` while state was `starting`.
No current-session `SM8850_FULL_BRIDGES=ACTIVE` proof was captured.

The operator rejected the earlier “passive thermal guard” version because
that version still ran `--run-passive` and still treated a CPU-cap fault as
a mandatory reboot. The exact request is now implemented as a **distinct
one-session experiment**, enabled only for `--run --duration 180` through
`ONEIOS_SM8850_SOFT_THERMAL_OFF=I_ACCEPT_SOFT_GUARD_OFF_180S`.

- OneOS `oneios_switch.sh` launches **NO
  `oneios_sm8850_thermal_takeover_guard.sh`** process in this profile.
  No on-phone software thermal heartbeat, invalid-sensor fail-closed
  return or software emergency-temperature abort is present.
- `framework.soft-thermal=disabled-180s` is written into root-owned,
  current-session control after a fresh boot/session setup. Only this marker,
  `framework.mode=run`, `framework.duration=180`, and matching current
  boot are allowed to bypass the software guard/cap health dependencies
  in `framework_recovery_ready()` and `framework_deadline()`.
- CPU cap is instead **optional and nonfatal**. Only after verified
  Android Framework stop, the independent `--run-best-effort` helper
  requests a static max frequency of `28%` of `cpuinfo_max_freq`
  per cpufreq policy, through `scaling_max_freq` only. It repeats
  every second. A Samsung `scaling_min_freq` vote above the request
  is handled by the lowest achievable ceiling and logged as
  `P0_CPU_CAP=MIN_FLOOR_LIMITED`. Any sysfs error is logged as
  `P0_CPU_CAP=BEST_EFFORT_APPLY_FAILED_NO_RETURN` and **does not
  trigger a software reboot**.
- This best-effort request is **NOT** a certified/guaranteed cap.
  An active Samsung min-vote may hold CPU frequency high; if the helper
  exits, there is no cap-health watchdog. GPU frequencies are not changed.
- The panel is woken before Framework stop, followed by 8 seconds for
  Samsung's wake-boost vote to settle, but there is no temperature-based
  pre-stop admission gate in this experimental profile.
- Independent return deadline (180s after verified Framework stop),
  legacy watchdog/reboot return, physical keys, and generic resource and
  guest checks remain. The independent watchdog and unattended return are
  **NOT fully qualified**. The OneOS kernel/firmware thermal governors,
  hardware trips, and battery protections remain untouched.
- The default mode, when the extra flag is absent, still runs the root
  thermal guard, strict CPU cap and fail-closed watch dependencies.

**High hardware risk:** prior physical OneiOS sessions reached CPU peaks
of 95–101.1C. With no software temperature abort, thermal runaway can
cause device damage even if the CPU cap requests 28%. Run only with
operator present at the phone and prepared for manual recovery; do not
disable firmware/kernel/battery protection. A guest run is **not yet
validated** by this source change.

The previous attempt consumed its one-shot APFS Data clone, so fresh
Data must be prepared once before another physical test. The preexisting
bounded telemetry runner does this by default; **do not use
`--no-rearm`** after a consumed clone. The Linux host telemetry is
read-only and still collects USB sysfs snapshots whenever ADB is
available; it is **not an on-device thermal guard**.

Quick host-only tests on CachyOS after pulling the updated submodule:

```bash
python3 app/tests/test_sm8850_guarded_full.py -v
python3 scripts/phone/test-sm8850-takeover.py -v
```

## 2026-11-23: Operator-selected 180-second full bridges=1 trial (not yet executed)

The operator explicitly requested a REAL hardware `bridges=1` trial, not
more offline tests. The OneiOS wrapper on
`feat/sm8850-full-bridges-takeover` now permits an explicit **180-second**
live session when *both* the existing legacy-watchdog risk acknowledgement
and `ONEIOS_SM8850_FULL_BRIDGES_180S=I_ACCEPT_UNQUALIFIED_180S_LIVE_TEST`
are supplied. This is **experimental, physically risky and not safety
qualified**: prior SM8850 physical sessions saw 95-101.1 C CPU sensor
peaks, a feeder-progress failure and unverified independent watchdog
/ unattended recovery. The software deadline is measured from verified
Framework stop; **it is not an independently proven hardware reset
guarantee**. The user must be physically present, able to force a Samsung
restart with Side/Power + Volume Down, and prepared for the Android UI
to become unavailable. Do not press both volume keys with USB attached.

The one-command monitored procedure on CachyOS is:

```bash
cd ~/projects/OneiOS
git pull --ff-only
ONEIOS_SM8850_FULL_BRIDGES_180S=I_ACCEPT_UNQUALIFIED_180S_LIVE_TEST \
  python3 -u scripts/phone/sm8850-600s-thermal-telemetry.py \
    --duration 180 --i-accept-10-minute-legacy-watchdog-risk
```

Its default path first uses `rearm`: confirms the locally built ARM64
`xnuhost` SHA-256 matches the previously installed binary; refreshes
the boot-scoped OneOS thermal sensor manifest with the root-owned
reboot-stage-check; archives the previous consumed APFS Data and
creates a fresh isolated one-shot clone; and runs
`--framework-check run 180` without stopping One UI. It skips redundant
native compilation and previously passed CI. If any step refuses, do
not forge a marker, disable thermal protection, or reuse consumed Data.

Only after the preflight passes does the telemetry wrapper launch the
already-existing `--run` path. The session enforces the same native
independent root thermal guard, strict CPU cap, GPU3D, exclusive touch,
reboot-only deadline watcher, exact SM8850 identity and OneOS current-boot
and generation admission gates; no safety threshold is relaxed.
It does **not** make the OneOS app switch production eligible.

**Evidence to seek** (not pre-certified PASS): a live,
current-launch `SM8850_FULL_BRIDGES=ACTIVE_RUNTIME_LOG` line
from the native `xnuhost` log, with
`SM8850_FULL_BRIDGES_RUNTIME_LOG_SEEN=True`, alongside guest-ready,
KGSL3D and actual visible panel / Power / swipe responses.
A static binary string, the stage-only PASS, a stale historic log,
or a returned Android boot without exact return evidence is **not**
bridge or recovery acceptance. A thermal early abort before
`SM8850_FULL_BRIDGES=ACTIVE` is a blocked trial, not proof that the
hardware bridges themselves failed. The next session after a consumed
one-shot clone always requires a fresh rearm.

### 2026-11-23: Readiness refusal after Data rearm

The operator deliberately selected `--duration 180`; a previous reply
incorrectly treated the displayed 180-second telemetry duration as a
configuration mismatch. The selected duration was correct, but the earlier
OneiOS wrapper still hardcoded a 60-second rearm preflight and limited the
full-bridges run to 60 seconds. This has been corrected in OneiOS so the
explicit 180-second choice is propagated consistently to both phases.

The actual 2026-11-22T184055Z operator log shows
`APFS_DATA_REARMED=YES` and
`PREVIOUS_DATA_ARCHIVED=/data/adb/oneios-m3q-framework/.retired-data/consumed.W87FR9gl`,
then a root-owned, read-only check refused admission with
`verified original smoke proof missing from current or archived session`.
The telemetry process exited `2` and stated
`NO_LIVE_TAKEOVER_ATTEMPTED`. This did **not** verify that live
`bridges=1` works. The new APFS Data clone remains **fresh**, because
the Framework was never stopped and no new session claimed the Data.
Do not rearm it again just because the outer orchestration previously
returned a nonzero status. To preserve it, use the existing
`--no-rearm` option on a subsequent monitored invocation **only after**
the unchanged smoke-proof/reboot admission gate can pass.

**Corrected 2026-11-23:** The operator restarted Android manually and
observed `ro.boot.bootreason=reboot`,
`sys.boot.reason=reboot`, `sys.boot.reason.last=reboot`. The former
OneOS gate erroneously required the CURRENT boot to retain
`reboot,oneios-sm8850-reboot-return`, conflating a historical
Framework-only smoke event with an unrelated later manual restart.
The OneOS source on this feature branch now checks the original smoke
proof using its original session boot ID, framework confirmation,
mode, return action and deadline outcome, regardless of current boot
reason. It still refuses if no genuine root-owned archived/current
smoke record matches. Current boot reason is informational, not proof
of successful recovery. Independent watchdog qualification remains
unverified; no safety sensor or thermal threshold is bypassed.

**Do not rearm Data again after the refused attempt.** Sync the newly
pinned OneOS submodule, update only the root-owned OneOS scripts using
`--reboot-stage-check --confirm` while One UI is running, and run
the `--framework-check run 180` admission again. If it passes, use
the telemetry launcher with **`--no-rearm`** to preserve the already
fresh and unconsumed APFS Data. If it still fails, inspect the
differentiated smoke-proof refusal rather than generating a fake
session marker or invoking live takeover.

## 2026-11-22: Full-bridges stage-only completed (no Framework stop)

The operator's CachyOS log confirms `stage-runtime` exited `0` on
SM-S948B firmware `S948BXXS4BZIG` using OneiOS
`06c108a01ef9488edc123c7cee23eb5c637131d8` and pinned OneOS
`3d40343bfc800c49112e2cbebbb4d2c939ecbe82`. Rooted Android
One UI stayed running. The current-boot thermal sensor manifest pinned
28 zones (16 CPU, 11 GPU, 1 DDR). OneOS scripts were installed with
`ONEOS_STAGE_UPGRADE=PASS_BACKUP_PRESERVED` and the preflight returned
`REBOOT_STAGE_CHECK=PASS_NO_FRAMEWORK_STOP`.

The native runtime was updated with SHA-256 validation and preserved under
`/data/adb/oneios-m3q-framework/.rollback/runtime.KyUycmUk`:

- `xnuhost`: `ea0dd9c977fa1349762e91584d6ad0e5a43944fb90549fe283397de5142f0802`
- `oneios-display`: `93a1dee53e6f00b31a368377a7ff44f1b82a1baa63777853ff2722d79bd575e6`
- `oneios-display.dex`: `44cc35c41dfeeea389301cd01f54bbdc8813a1515565650af9887ea3f3e98ced`
- `liboneios-display.so`: `c524db80be1c6139abd04d8fceb3b5f63379c086674ca2bc20807d62a6f3d61c`

The script reported `NATIVE_RUNTIME_UPGRADE=PASS_BACKUP_PRESERVED`,
`FULL_BRIDGES_STAGE_ONLY=PASS`, `APFS_DATA=CONSUMED_NOT_REARMED`,
and `FRAMEWORK_STOP=NO LIVE_TAKEOVER=NO`. OneOS script rollback:
`/data/adb/oneios-m3q-framework/.rollback/oneos-compat.QoC9Woku`.
The host-side console log is
`out/sm8850/takeover/full-stage-runtime-20261122T175143Z-747484.log`.
These source-reported outcomes are staging evidence, **not** fresh
boot, full-br-hardware functionality, watchdog recovery or thermal
safety evidence. Do not re-use the consumed APFS Data.

**Next P0 action (read-only evidence capture, not a new guest run):**
with rooted, healthy One UI and no active guest, use the existing
`python3 scripts/phone/sm8850-takeover.py --collect --serial
R5GL64LZ9HA` to archive the root-owned prior-session control,
thermal-cap/guard, return and watcher records. Analyze boot/generation
provenance and the reported 95 C pre-guest abort before deciding on any
new physical session. This collector writes only local evidence; it
must not be confused with `--run`, `--rearm-data`, or an independent
watchdog qualification. A clean stage does not close the P0 blocker.

## 2026-11-23: Archived collection post-processing diagnostic

A read-only `--collect` invocation created local evidence directory
`out/sm8850/takeover/collect-pxkkglwo` but printed
`FRAME_STALL_REPORT=UNAVAILABLE Traceback ... raise SystemExit(main())`.
The collector previously truncated the analysis subprocess's stderr to
180 characters, concealing the actual exception. The excerpt does **not**
prove that the device archive or restored-device diagnostics failed, nor
does it identify the missing member or show any new guest crash.

The frame-stall analyzer required both `session/xnuhost.log` and
`control/display.log` even when a prior thermal abort occurred before
guest startup. It now emits `SKIPPED_MISSING_GUEST_TRACE` if those inputs
are absent; otherwise it reports analysis errors explicitly. The collector
preserves full unexpected errors in `frame-stall-error.txt` while keeping
recovery/thermal archive capture independent. The existing archive in
`collect-pxkkglwo` must be inspected **offline**; there is no need to
recollect, rearm APFS Data, or repeat takeover to resolve this message.
Only the actual archive and restored-device receipt can determine which
past-session evidence was captured. Do not treat stale guest logs as proof
of a current full-bridges run.

### 2026-11-23: Archived frame traces are session-scoped

The operator listed the 15 MiB `collect-pxkkglwo/device-logs.tar` contents.
The current `session/xnuhost.log` exists but the current
`control/display.log` is absent. Several prior archived sessions contain
BOTH under the same `logs/session.TOKEN/` prefix, including
`UZNzNZ`, `IzR1hQ`, `XOpCkz`, `JRfwTb` and `iLnG4O`.
That explains why current-session frame analysis cannot proceed, but it
**does not establish** which historical session corresponds to the thermal
abort or to the failed swipe attempt; timestamps/boot/generation still
need inspection from file contents.

The archive analyzer now offers `--list-sessions` and an explicit
`--archive-session TOKEN` selecting both the XNUHost and display trace
from ONE historical session. It refuses to silently join the current
XNUHost trace with a prior display log. These are offline archive-only
operations and cannot qualify live full bridges or watchdog recovery.
The thermal faults, append-only cap/guard logs and return outcomes should
be inspected independently, with boot/generation provenance, before any
new physical trial.

A read-only P0 archive inventory is available for the already-collected TAR:
```bash
python3 scripts/phone/sm8850-archive-forensics.py \
  --archive out/sm8850/takeover/collect-pxkkglwo/device-logs.tar \
  --output out/sm8850/takeover/collect-pxkkglwo/p0-forensics.json
```
It reports the current control directory and each archived session
separately, records the archive SHA-256, and labels global append-only
thermal logs **unattributed**. It does not establish causality or prove
independent watchdog recovery, and it never accesses ADB/device state.


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
