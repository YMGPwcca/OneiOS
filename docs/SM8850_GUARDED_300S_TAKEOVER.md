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
  than the CPU policy's validated min and never overriding a tighter
  external cap. It intentionally favors heat reduction over frame rate.
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
2. `cpuinfo_min_freq` clipping may prevent 8% of maximum from
   applying to Snapdragon Oryon; verify effective limits.
3. A root-owned cpufreq limit may persist if the hardware unexpectedly
   escapes the designed reboot-only return path; production recovery
   needs explicit restoration assurance.
4. Aggressive clamping can significantly worsen first-boot iOS
   frame starvation. It is a user-requested thermal-priority trial,
   not a completed performance fix.
