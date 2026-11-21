# SM8850 P0 thermal preflight (passive evidence only)

## P0 short-probe timebase correction (2026-11-21)

The experimental OneOS `--framework-session probe` **does not promise 90 seconds of native iOS execution**. Its independent Framework recovery helper publishes a **reboot-return request deadline** at *device monotonic time of verified Framework stop + 90 seconds*, after mandatory memory checks/configuration. The earlier 45-second pre-stop fallback only protects initial preparation. Later guest setup/exec uses part of the deadline window; thermal/watchdog/watcher faults may return earlier, and the physical reboot may finish after the request. This clock is **not** started by the CachyOS ADB command.

From recovered physical root logs, `04:23:34` was the **beginning** of Framework-stop phase (NOT the exact verified-stop timestamp); native xnuhost was launched at `04:23:46`, then independent thermal monitoring aborted at `04:23:47`, around one second after the guest launch. **The short probe ended early because of thermal fail-closed**, not because 90 seconds elapsed. Do not infer a precise verified-stop-to-exec interval from the phase header. Host observation time and device monotonic time have different origins.

The OneOS draft now adds distinct `ONEIOS_GUEST_EXEC_ATTEMPT_TICK` and `P0_SHORT_PROBE_TIMING` log markers for future investigations, without moving or lengthening the +90-second return deadline or changing any thermal thresholds. Exact full guest-runtime-from-exec timing would require a separately reviewed exposure budget and explicit authorization; P0 hardware watchdog and unattended recovery remain unqualified. The owner does not have reliable physical-key-use attestation for the prior reboot, so `UNASSISTED_RETURN=UNVERIFIED`.

This step does **not** implement, enable, or qualify a thermal guard. No guest session, root, watchdog, or Android Framework takeover is required.

## Run on CachyOS with stock One UI fully booted

```bash
cd ~/projects/OneiOS
git fetch origin feat/sm8850-p0-thermal-preflight
# Use a temporary worktree to keep the current checkout and its changes untouched:
git worktree add --detach /tmp/oneios-p0-thermal-preflight origin/feat/sm8850-p0-thermal-preflight
python3 /tmp/oneios-p0-thermal-preflight/scripts/phone/test-sm8850-thermal-preflight.py -v
python3 /tmp/oneios-p0-thermal-preflight/scripts/phone/sm8850-thermal-preflight.py --print-commands
python3 /tmp/oneios-p0-thermal-preflight/scripts/phone/sm8850-thermal-preflight.py --adb "$HOME/Android/Sdk/platform-tools/adb" --output "$HOME/projects/OneiOS/out/sm8850/thermal-preflight"
```

The script requires exact model `SM-S948B`, device `m3q`, firmware `S948BXXS4BZIG`, SELinux Enforcing, a completed Android boot and running `system_server`. It reads only `getprop`, `getenforce`, `pidof`, two named `/proc` files, and Android `dumpsys thermalservice` / `dumpsys battery` services. The script never uses `su` and does not access /dev/watchdog, run a guest, enumerate sysfs thermal zones or alter power/clocks.

Output is saved under a timestamped and random directory with restricted permissions (`summary.json`, `thermalservice.txt`, `battery.txt`). Raw logs may contain device-specific metadata: review before sharing. A missing SKIN reading is reported, never interpreted as a safe temperature. HAL observations may not be valid after Android Framework is stopped, and are **not** a validated real-time thermal guard. The parser keeps the raw dump because vendor formatting varies.

**Next:** inspect this snapshot, then do a *separate* explicitly allowlisted, firmware-reviewed targeted sensor inventory before adapting the reusable OneiOS thermal reader into an independent OneOS root-side supervisor. The Android HAL's current temperatures are not sufficient to certify sensor availability after framework shutdown.

**Safety status:** `RECOVERY_ACCEPTANCE=BLOCKED`; `THERMAL_GUARD=NOT_IMPLEMENTED`. No physical guest run is authorized by this preflight.


## First S26 Ultra physical HAL sample (operator output, 2026-11-20)

- Exact model SM-S948B, device m3q, firmware S948BXXS4BZIG, SELinux Enforcing.
- Preflight reported `READINGS=6`, `SKIN_OBSERVED=True`, and `acceptance=NOT_QUALIFIED`.
- Current HAL values (C): `AP` / CPU 28.7; `BAT` / BATTERY 26.6; `PA` / POWER_AMPLIFIER 28.5; `SKIN` / SKIN 28.9; `SUBBAT` / BATTERY 0.0; `USB` / USB_PORT 25.7.
- `SUBBAT=0.0` is suspicious (possibly unimplemented); never accept as a proven cool battery sensor.
- HAL `AP` is TemperatureType.CPU (0), not a proven match for Samsung's board AP thermistor.
- These observations are from the operator's text output. No raw logs were uploaded to or committed in this repository.

## P0.1 follow-up: read only three already documented Samsung kernel nodes

The Samsung backend in [runtime/bridges/thermal/thermal.c](../runtime/bridges/thermal/thermal.c) already reads these paths, and its [README](../runtime/bridges/thermal/README.md) describes an SM8850 `thermalctl` check from 2026-11-16. A standalone OneOS thermal supervisor cannot rely solely on Android `dumpsys` after Framework stops. Cross-check known paths without enumerating other sysfs nodes.

Run on CachyOS while **stock One UI is fully running**:

```bash
cd ~/projects/OneiOS
git fetch origin refs/heads/feat/sm8850-p0-thermal-preflight:refs/remotes/origin/feat/sm8850-p0-thermal-preflight
git -C /tmp/oneios-p0-thermal-preflight switch --detach origin/feat/sm8850-p0-thermal-preflight
python3 /tmp/oneios-p0-thermal-preflight/scripts/phone/test-sm8850-thermal-preflight.py -v
python3 /tmp/oneios-p0-thermal-preflight/scripts/phone/test-sm8850-thermal-known-nodes.py -v
python3 /tmp/oneios-p0-thermal-preflight/scripts/phone/sm8850-thermal-known-nodes.py --print-commands
python3 /tmp/oneios-p0-thermal-preflight/scripts/phone/sm8850-thermal-known-nodes.py \
  --adb "$HOME/Android/Sdk/platform-tools/adb" \
  --output "$HOME/projects/OneiOS/out/sm8850/thermal-known-nodes"
```

The sole kernel paths read are:
- `/sys/class/power_supply/battery/temp` — tenths of a degree C; possible HAL BAT correlate.
- `/sys/class/power_supply/battery/lrp` — tenths of a degree C; possible HAL SKIN correlate.
- `/sys/class/sec/sec-ap-thermistor/temperature` — tenths of a degree C; Samsung board reading, **not** the HAL CPU AP by definition.

The script uses unprivileged `adb shell cat` by default. **If a known node is UNAVAILABLE from permissions**, an operator may explicitly retry with `--allow-root`. This option retries only the three hardcoded paths with root after an unprivileged read fails, never a thermal-zone scan. Avoid root fallback if the device is not healthy or its firmware differs.

Review `summary.json` and `thermalservice.txt` before sharing, since raw diagnostics may include device-specific metadata. The report logs samples with identity and an exact boot ID, plus any denied/malformed readings. A small difference does **not prove** the same physical sensor, synchronous sampling, or sensor reachability after Android Framework stops. No firmware thresholds, monitor TTL, reboot guard, or production behavior are qualified by this passive check.

**Safety remains:** `P0.1=PARTIAL`, `INDEPENDENT_GUARD=NOT_IMPLEMENTED`, `600S_TAKEOVER=BLOCKED`.


## Physical targeted kernel reading — completed 2026-11-20

The operator ran all **12/12 offline regression tests** on CachyOS successfully. The targeted non-root probe showed `BOARD_AP=READ 32.6C`, but `battery/temp` and `battery/lrp` both returned `Permission denied` (not missing files). The opt-in, exactly-three-nodes root retry then reported:

| Node | Reader output | Interpretation |
| --- | --- | --- |
| `battery/temp` | `BATTERY=READ 28.5C via root_named_cat` | Verified this named kernel node is readable as root with One UI running |
| `battery/lrp` | `LRP=READ 30.3C via root_named_cat` | Verified named Samsung LRP file is readable as root with One UI running |
| `sec-ap-thermistor/temperature` | `BOARD_AP=READ 29.7C via shell_named_cat` | Verified board node is readable without root |

Original output paths: `out/sm8850/thermal-known-nodes/20261120T170502Z-3cb4d781` (unprivileged) and `out/sm8850/thermal-known-nodes/20261120T170748Z-335f6407` (root fallback) on the operator's machine. The raw JSON and `thermalservice.txt` from the root fallback were **not attached** to this discussion.

At an earlier different sample, HAL BAT was 29.5 C and HAL SKIN was 31.8 C, versus root-read battery 28.5 C and LRP 30.3 C at a later time. **Do not compute sensor calibration or assert alias identity from asynchronous readings.** Board AP is not the HAL's CPU-labeled AP. `SUBBAT=0.0` remains suspect and is excluded from any safety evidence.

The independent OneOS reader and fail-closed **simulation** groundwork are now in draft [OneOS PR #6](https://github.com/YMGPwcca/OneOS/pull/6). This proves neither post-Framework availability nor a running independent safety monitor; **P0.1 remains PARTIAL and P0.2 remains NOT PHYSICALLY IMPLEMENTED**.


## Follow-on OneOS P0.2 local CI checkpoint

On CachyOS, the operator's **14/14 original OneOS thermal reader / policy simulation tests PASS** using the checkout at `~/projects/OneiOS/app`. The companion [OneOS draft PR #6](https://github.com/YMGPwcca/OneOS/pull/6) subsequently added **19 more fixture-only end-to-end regression cases** that exercise the real shell reader, strict boot/run/launch identity, synthetic watcher health and bounded read time; the operator has now independently run **all 19/19 new E2E tests PASS on CachyOS**, completing **33/33 OneOS offline tests PASS**.

No new S26 phone experiment was performed. The new driver only emits `WOULD_REQUEST_RETURN_NOT_EXECUTED`, never an actual reboot. These tests **do not prove an independent live thermal monitor**, post-Framework sensor availability, threshold calibration or watchdog recovery. The long takeover remains blocked.

## Source-level safety lock in companion OneOS draft

[OneOS PR #6](https://github.com/YMGPwcca/OneOS/pull/6) now blocks the actual `--framework-session run` code path with `P0_FULL_600S_TAKEOVER=BLOCKED_UNQUALIFIED_THERMAL_GUARD` **before any APFS Data consumption or Framework stop**; check-only diagnostics remain available. It also adds a bounded read-only thermal shadow observer and **17 new offline test methods** (14 shadow observer cases locally exercised by the assistant with the real shell reader, plus 3 source-gate contract tests awaiting operator CachyOS verification).

**Critical distinction:** this source gate is currently only in the draft GitHub branch, **not the old script already staged on the phone**, and the shadow observer is neither a live independently supervised guard nor a reboot-return implementation. The 600-second iOS run remains prohibited from a safety-acceptance standpoint regardless of old script functionality.


## OneOS P0 next checkpoint: 50 local PASS, heartbeat supervision contract pending

The operator subsequently executed **50/50 OneOS offline regression tests PASS** on CachyOS against the exact OneOS commit `5185a642ab7c7d29aa0f2d758fd04ac7b2f3af15` (14 reader/policy, 19 E2E, 17 shadow/source-gate tests; syntax PASS).

[OneOS draft PR #6](https://github.com/YMGPwcca/OneOS/pull/6) now also contains a **fixture-only** independent heartbeat/PID-birth consistency check, with 17 new offline regression cases and an exact 67-test local runner. The new tests still require the operator's CachyOS run; this is NOT a sensor supervisor installed on the S26 Ultra and is NOT a substitute for an authenticated, bounded reboot return.

The `--framework-session run` source-level refusal remains on the **GitHub draft branch only**; old code already staged on the phone remains unchanged. P0 is not accepted, long Framework takeover remains prohibited, and no new device experiment was performed by these changes.


## P0 current local baseline and safe passive sampling plan

The operator's CachyOS completed **67/67 OneOS P0 offline tests PASS** at exact commit `d8759313e90da0f2af849b7150bc9aede36dcbf2`: 14 reader/policy, 19 E2E, 17 shadow/safety-gate, 17 heartbeat. No actual iOS or Android Framework stop was part of those tests.

The companion [OneOS draft PR #6](https://github.com/YMGPwcca/OneOS/pull/6) subsequently added `scripts/phone/run-sm8850-thermal-shadow-oneui.sh`: a disposable, **three-sample read-only One UI thermal collector** using the two previously audited thermal scripts and exact model/firmware/SELinux/boot preflight, SHA-256 verified temporary staging, strict output checks, 30-second host-side timeout, and cleanup. It touches only a dedicated temporary `/data/local/tmp` directory on phone; never OneOS takeover stage, watchdog, kernel governors, thermal trip settings or reboot. `--audit-only` makes zero ADB calls; `--run-readonly` requires explicit invocation and existing root access.

The new host fake-ADB test module adds 5 tests, bringing the strict combined runner to 72. The new 5 cases and physical 3-sample observation are **pending operator verification**. Any successful read-only shadow log will be **evidence only**, not P0 safety acceptance. Full 600-second takeover remains blocked, and the source-level block is not retroactively deployed to the old phone script.


## Verified 72-test local CI and physical three-sample thermal shadow (2026-11-21)

- **Exact OneOS revision:** `79e04bafd0f897551eacdee301f56fe18809be4f` checked on the operator's CachyOS.
- **Offline:** all `72/72` local tests PASS (67 previous + 5 fake-ADB collector cases); strict runner printed `ONEOS_P0_OFFLINE_72=PASS` and `P0_SAFETY_STATUS=OFFLINE_SIMULATION_ONLY_NO_PHYSICAL_GUARD`.
- **Physical:** the explicit `--run-readonly` One UI-only observer completed 3/3 read-only, root-sourced samples, all with same boot ID `a6007f1e-4fc3-4e99-82dd-267ccb249656` and `physical_action=NO`.
- **Temperatures (all three ticks, deci-C):** `battery=266` (26.6 C), `lrp=285` (28.5 C), `board_ap=270` (27.0 C). These are reported values, not firmware thresholds.
- **Post-check:** `P0_SHADOW_ONEUI=PASS_READ_ONLY_EVIDENCE_NOT_GUARD`; One UI and original boot ID still present. Host evidence was saved at `out/sm8850/thermal-shadow-oneui/readonly-20261120T180943Z-m4etYr.log`.
- Identical three samples over the observer's short interval demonstrate repeatable reads, **not** sensor refresh dynamics under heating, physical equivalence to HAL channels, independent reachability after Framework stop, or calibrated limits.
- The operator's log shows two audited scripts were staged and the host-script reported successful post-check; cleanup is designed into the host script, but the log alone does **not** prove the temporary directory was removed. No watchdog/governor/reboot path was intentionally invoked.
- **Next sensor mapping:** the existing OneiOS thermal backend documents 28 genuine zones including real CPU zone `cpu-0-5-1` around 40.5 C on a 2026-11-16 S26 Ultra pass, while `cpu-hw-trip-0/1` were constant 105 C pseudo-zones and must never be treated as live sensors. The three battery/LRP/board paths do **not** cover the SoC junction. Before expanding the OneOS reader, positively map the exact firmware thermal-zone path for a genuine CPU sensor and verify stable units/sampling with read-only, bounded access; do not attempt root recursive sysfs scans.
- **Safety gate:** the `--framework-session run` source refusal remains on the draft branch only; the phone's prior staged switch is unchanged. Independent thermal protection and unassisted reboot-return are still NOT QUALIFIED. Full 600-second takeover remains BLOCKED.


## CPU thermal zone candidate mapping (next operator read-only check)

The existing OneiOS Samsung thermal backend (`runtime/bridges/thermal/thermal.c`) already discovers genuine `cpu-*`, `cpuss-*`, `gpuss-*`, DDR and XO thermal zones and excludes `cpu-hw-trip-*` pseudo-zones. Its 2026-11-16 hardware report recorded a true CPU candidate `cpu-0-5-1` at approximately 40.5 C in one sample. Battery/LRP/board nodes are insufficient to monitor SoC junctions under iOS load.

Companion OneOS draft PR #6 now contains `scripts/phone/sm8850-soc-candidate-map.py` that, when explicitly run on intact One UI, does a **bounded unprivileged one-level read of only thermal-zone `type`**, matches exactly `cpu-0-5-1` and samples only the validated matching `/temp` node. It never reads the pseudo-zone temperatures or recursively traverses sysfs. Root fallback is restricted to the exact matched temperature file after permission denial. It remains a **candidate mapping**, not thermal protection or certified thresholds.

Nine additional offline tests are pending user's CachyOS, bringing OneOS P0 test count from the verified 72 to 81. No additional physical iOS/Framework takeover is authorized.

## 2026-11-21 verified CPU candidate mapping checkpoint

- Operator's CachyOS: exact OneOS revision `289b306a0315d448a3d6be7cb4da96882a47bf32`, **81/81 offline tests PASS** (previous 72 plus 9 exact SoC type mapping tests); shell syntax and audit modes passed.
- Physical One UI read-only candidate: `CPU_TYPE=cpu-0-5-1` matched **`/sys/class/thermal/thermal_zone16/temp`** on the current boot, three **unprivileged** reads of **30.0 C / 30.0 C / 29.6 C**, output `SOC_MAP=COLLECTED_NOT_QUALIFIED`.
- Local operator JSON: `out/sm8850/soc-candidate/cpu-candidate-20261120T181955Z.json` (its raw JSON was not uploaded here). This is source-supported output only, not a review of JSON internals.
- Thermal-zone number 16 is **not stable across boots**; future thermal reads must validate exact `type=cpu-0-5-1`, unchanged boot identity and plausible millidegree values rather than trusting the index alone.
- The candidate is a **genuine changing CPU temperature read** in this short sample, not certified as the hottest SoC junction or the only needed CPU/GPU thermal input. No safety thresholds or post-Framework availability are accepted. Full 600s takeover remains blocked.

## Read-only 4-sensor prototype added in OneOS (follow-up)

The operator's last physical `cpu-0-5-1` readings were **30.0/30.0/29.6 C**, mapped to `thermal_zone16` on that specific boot; the exact OneOS commit `289b306a0315d448a3d6be7cb4da96882a47bf32` passed **81/81 CachyOS tests**.

OneOS draft PR #6 now contains a **boot-pinned four-sensor reader prototype**: `oneios_sm8850_thermal_pinned_reader.sh`. It extends the three known Samsung BAT/LRP/board AP nodes with **one genuine CPU candidate**. It requires explicit expected boot UUID and zone index, validates `type=cpu-0-5-1` before and after sampling (so zone 16 is not assumed permanent), verifies the boot ID after reading, and refuses missing/invalid readings. Root-only live mode is locked to stock One UI with exact firmware; no Framework-stopped mode exists.

13 additional offline tests passed in assistant-side Linux, bringing the proposed OneOS suite to **94 tests**, but these 13 have **not yet been verified on the operator's CachyOS**. This is not a production thermal guard and does not prove the CPU candidate is the hottest SoC sensor. P0 remains unqualified; do not rerun a 600-second Framework takeover.


## 2026-11-21 operator confirmation: 94/94 local offline PASS

- At exact OneOS commit `934988c9b493cf37d18dd72a1e4f09e1cd6928de`, CachyOS fetched and unpacked the branch, ran the strict local CI runner and reported **`Ran 94 tests ... OK`**, `ONEOS_P0_OFFLINE_94=PASS`, and `ONEOS_FOUR_SENSOR_CI=PASS`.
- The new 13 `test_sm8850_thermal_pinned_reader.py` cases ALL PASS on the operator's own host, in addition to previous 81. This validates the fixture-mode four-sensor prototype and source syntax on Linux, NOT an actual four-sensor run on the phone.
- No live four-sensor sample was collected in that command. The last physical CPU mapping remains `cpu-0-5-1` -> `thermal_zone16/temp` on a prior verified boot, with 30.0/30.0/29.6 C. A numeric zone index must be freshly rediscovered and checked per boot.
- The physical 3-node BAT/LRP/board sampler and offline policy are evidenced separately. Independent post-Framework sensor access, full SoC hottest-junction coverage, vendor-calibrated thresholds, root monitor/supervisor lifecycle, recovery and unassisted reboot are still **NOT QUALIFIED**; full 600-second takeover remains BLOCKED.

## Four-sensor live One UI **read-only** verification workflow (not yet executed)

- After **94/94 offline PASS on user's CachyOS** at `934988c9b493cf37d18dd72a1e4f09e1cd6928de`, OneOS adds `scripts/phone/sm8850-four-sensor-oneui.py` as a separate opt-in physical diagnostic. It **defaults to audit-only with no ADB contact**.
- Explicit `--run-readonly` invokes the existing bounded unprivileged `cpu-0-5-1` **type-only mapping** on the current boot, refuses a missing, duplicated, or out-of-range zone, verifies exact firmware/One UI/SELinux/boot, and maps the verified zone number to the previously written one-shot four-sensor reader.
- The host copies **only** `oneios_sm8850_thermal_pinned_reader.sh` into a fresh random `/data/local/tmp/oneos-p0-four-sensor-*` directory, verifies the remote SHA-256, then uses KernelSU `su -c` to read exactly **three** snapshots (CPU millidegrees; battery, LRP, board AP decidegrees). Each one-shot sample checks CPU `type` and boot ID before and after; host validates all fields, units, uptime, same identity and sensor path. It then explicitly removes its own script and directory; cleanup failure cannot be reported as a successful run.
- No guest start, no Framework stop, no sysfs writes, no governors, no watchdog open or reboot. The new reporter outputs `FOUR_SENSOR=COLLECTED_NOT_QUALIFIED` on success; it **cannot authorize** a 600-second takeover.
- `tests/test_sm8850_thermal_four_sensor_host.py` adds **13 offline mock tests** for wrong mapping/type, stale boot, field injection, impossible CPU units, hot genuine CPU values (>120 C), missing/bad sensor, SHA mismatch, root reader errors and cleanup failure. The strict local test runner now expects **107 tests**. **These 13 new tests and the physical four-sensor run are still pending CachyOS verification**.
- This one-CPU candidate is *not* the complete hottest CPU/GPU/DDR junction set, and the prototype requires stock One UI; after-Framework availability remains unproven. The independent thermal guard, calibrated thresholds, watcher, return and reboot remain **NOT QUALIFIED**. The source-level 600-second takeover block stays in place.


## 2026-11-21 operator-verified four-sensor One UI result

- Exact OneOS commit `a8042e3dd6ff5a1e55ad436a75b52df0b16fb0b4`: **107/107 offline test PASS** on operator's CachyOS, strict runner reporting `ONEOS_P0_OFFLINE_107=PASS` and `P0_SAFETY_STATUS=OFFLINE_SIMULATION_ONLY_NO_PHYSICAL_GUARD`.
- Explicit, same-session **four-sensor, three-tick read-only run** completed on SM-S948B/m3q/S948BXXS4BZIG, with `FOUR_SENSOR=COLLECTED_NOT_QUALIFIED`, dynamic exact `cpu-0-5-1` found at `/sys/class/thermal/thermal_zone16/temp` on that boot.
- Tick 1: CPU **35.8 C**, battery **29.6 C**, LRP **31.5 C**, board AP **31.3 C**. Ticks 2 and 3: CPU **36.2 C**, battery **29.6 C**, LRP **31.5 C**, board AP **31.3 C**.
- Host JSON path as reported: `out/sm8850/four-sensor-oneui/four-sensor-20261120T185153Z-59381e.json` (raw JSON has **not** been uploaded for direct inspection). The success marker means matching SHA, accepted output, post-check and cleanup workflow completed according to the tool; no iOS run was requested.
- This proves repeated four-node access with normal One UI and a changing CPU read, **not** complete SoC junction coverage, thresholds, post-Framework availability, independent watchdog/recovery or a running thermal guard.

## P0.2 next source groundwork: bounded CPU/GPU/DDR/XO junction inventory (pending operator run)

- The OneiOS Samsung backend in `runtime/bridges/thermal/thermal.c` reads the **maximum** of the real `cpu-*` or `cpuss-*` zones, the `gpuss-*` zones and `ddr`, optionally `xo-therm`, after explicitly rejecting the `cpu-hw-trip-*` fixed 105 C pseudo-zones. A single candidate `cpu-0-5-1` cannot qualify thermal protection.
- New OneOS tool `scripts/phone/sm8850-thermal-junction-inventory.py` defaults to **audit-only, zero ADB**. Explicit `--run-readonly` verifies correct booted One UI firmware/SELinux, performs a **bounded nonrecursive unprivileged type-only scan** (at most 256 zones, 96 selected maximum matching backend capacity), then reads the *exact* mapped `/temp` path for each legitimate CPU/GPU/DDR/XO type, revalidating type before and after. Only a named permission-denied temperature gets a root retry; no root scan, sysfs writes, guest, framework stop, watchdog or reboot.
- Report records individual temperatures, maximum by group, unreadable types and missing readings. `COVERAGE_COMPLETE=NO` for any type/read failure or missing required CPU/GPU/DDR category. Even if complete, `acceptance=NOT_QUALIFIED`: this is a sensor inventory, **not** vendor thermal guard calibration or recovery certification.
- `tests/test_sm8850_thermal_junction_inventory.py` introduces **16 new offline test methods** for strict type parsing and groups, pseudo-zone exclusion, bounded enumeration, root escalation scope, mid-read type change, invalid sensor, maximum aggregation, missing DDR and run identity drift. The branch runner now demands **123** tests; prior **107/107** is operator-verified, but the 16 added tests **await CachyOS**. No new device survey has been run yet.
- The OneOS draft-source `--framework-session run` admission refusal still applies before APFS Data consumption and Android Framework stop. The old staged script on the physical phone is unchanged; full 600s takeover stays BLOCKED.


## P0.2 independent supervisor/return acceptance reference

The companion [OneOS P0.2 guard acceptance contract](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-p0-thermal-reader-sim/docs/SM8850_P0_INDEPENDENT_GUARD_ACCEPTANCE.md) now specifies root monitor ownership outside xnuhost/guest cgroups, genuine CPU/GPU/DDR sensor admission, versioned boot/generation/launch/heartbeat binding, independent liveness supervision, mandatory reboot-only return escalation, persistent next-boot verification and the no-bypass source gate. **This is documentation of required future behavior, not a running implementation.**

OneOS's proposed next sensor inventory has 16 additional host tests; the operator last confirmed 107/107 tests on the previous revision. Full takeover remains blocked until genuine vendor limits and independent recovery are physically certified.

## 2026-11-21 acceptance checkpoint: 123/123 offline + 28 genuine junction zones

- Operator verified exact OneOS revision `cdcc89d211fe8af4b10833dd248aad0405897664` on CachyOS: **123/123 local offline tests PASS**, with `ONEOS_P0_OFFLINE_123=PASS` and `P0_SAFETY_STATUS=OFFLINE_SIMULATION_ONLY_NO_PHYSICAL_GUARD`.
- Explicit stock One UI read-only thermal inventory: **28 selected real CPU/GPU/DDR zones**, `ERRORS=0`, `UNREADABLE_TYPES=0`, `COVERAGE_COMPLETE=YES`. The optional XO group was `UNAVAILABLE`; do not silently treat it as a present or validated sensor.
- Current-boot group maxima: CPU **37.0 C** from `cpu-0-5-1` at `/sys/class/thermal/thermal_zone16/temp`; GPU **35.1 C** from `gpuss-2` at `/sys/class/thermal/thermal_zone38/temp`; DDR **35.1 C** from `ddr` at `/sys/class/thermal/thermal_zone47/temp`. These are current-boot mappings, **not stable thermal_zone numbers**.
- Host evidence path reported: `out/sm8850/thermal-junction-inventory/junction-20261120T190828Z-74aab3.json` (raw JSON was not uploaded for independent direct inspection).
- `COVERAGE_COMPLETE=YES` means the survey's selected relevant zones all yielded valid reads and CPU/GPU/DDR were represented during that brief One UI snapshot. It does **not** prove vendor-calibrated limits, post-Framework sensor access, independent monitor survival, or successful unassisted reboot.
- Next engineering action is an independent, **inert** root-side monitor/heartbeat integration and mocked death-supervision, initially with no physical return action and no bypass of the 600-second admission block.


## P0.2 boot-specific sensor manifest builder (new, offline only)

The last **user-verified** checkpoint remains **123/123 CachyOS tests PASS** at `cdcc89d211fe8af4b10833dd248aad0405897664`, with physical stock-OneUI inventory covering 28 real CPU/GPU/DDR zones, zero errors/unreadable types, and an optional absent XO zone. Current-boot peaks were CPU 37.0 C `cpu-0-5-1`, GPU 35.1 C `gpuss-2`, DDR 35.1 C `ddr`; no vendor threshold is inferred.

The branch now contains `scripts/phone/sm8850-thermal-manifest.py`: by default **audit-only, no ADB and no disk writes**. Explicit `--build --inventory FILE --output-dir DIR` consumes the operator's local previously collected JSON and validates the entire report: exact firmware, same source boot ID, valid read methods, full CPU/GPU/DDR groups, matching per-index sysfs paths, exclusion of `cpu-hw-trip-*`, unique zone indices, complete zone count, plausible and internally consistent temperature units, no failed/unreadable zones and peak reports consistent with individual readings. Output is a **boot-bound, non-authorizing JSON manifest** of all named sensor paths with a SHA-256 fingerprint that is explicitly **not a signature**.

Manifest creation cannot establish that this is the phone's **current** boot, that sensor paths remain valid, or that code outside One UI can access the nodes. Any future root-side monitor MUST independently verify boot ID and zone types before and during monitoring. The manifest explicitly sets `takeover_admission_granted=false`, `independent_guard_running=false`, `firmware_limits_qualified=false` and `recovery_certified=false`.

`tests/test_sm8850_thermal_manifest.py` adds **16 new host-only integrity/anti-spoof regression cases** and the strict local runner now expects **139** total. These new 16 have **not yet been verified on the operator's CachyOS**; do not claim 139/139 PASS.

Offline-only manifest construction command (against the real operator JSON):

```bash
python3 scripts/phone/sm8850-thermal-manifest.py --build \
  --inventory "$HOME/projects/OneiOS/out/sm8850/thermal-junction-inventory/junction-20261120T190828Z-74aab3.json" \
  --output-dir "$HOME/projects/OneiOS/out/sm8850/thermal-manifests"
```

This is the sensor manifest **foundation** for a future independently supervised root monitor, not that monitor itself. P0.2 recovery, watchdog and the 600-second takeover remain BLOCKED.


## 2026-11-21 P0.2 root observer/supervisor test status

The user's latest exact OneOS revision `efe371475b92f5d7e27abfbb8f1b2983bfb16ca6` completed **139/139 CachyOS offline tests PASS** and created the boot-bound 28-zone non-authorizing manifest SHA256 `6d327fd8aedf33101317cbb8b6cb19b00fd175f322f59a3acd8ff0a073910ee8` from a prior real One UI inventory. That manifest is not a safety license or current-boot attestation.

Companion [OneOS PR #6](https://github.com/YMGPwcca/OneOS/pull/6) now adds a separate finite real root observer/supervisor diagnostic. A root worker reads all genuine type-mapped CPU/GPU/DDR sensors and known BAT/LRP/board AP nodes with atomic heartbeat; a sibling process checks boot/generation/launch/worker PID-birth/heartbeat and detects an intentionally short-lived worker. It runs **only on intact One UI** with a fresh exact-boot manifest in a temporary private stage and **does not reboot or issue a return request**.

Nine shell-fixture and six host mock-ADB regression tests passed on assistant Linux, bringing the proposed suite to **154**. New 15 are **pending user's CachyOS CI and live S26 physical smoke**. Even if passed, P0 is NOT complete until thermal limits, independent survival after Framework stop, supervisor last-resort, and reboot-only return with verified boot outcome are proven. Full 600-second takeover remains blocked.


## Operator-proven 154/154 CI and physical root monitor/supervisor (2026-11-21)

On exact OneOS commit `906309940e7fcd4b75a634c1feca5eecfa475768`, the operator's CachyOS ran **154/154 offline tests PASS** (`ONEOS_P0_OFFLINE_154=PASS`). They then performed an explicit physical stock-OneUI root trial on SM-S948B/m3q/S948BXXS4BZIG with **28 type-verified genuine junction zones**.

- Normal: monitor emitted three snapshots; CPU group maxima **34.2, 32.7, 32.3 C**; GPU **31.2, 31.2, 31.2 C**; DDR **31.2, 30.8, 30.8 C**. Monitor reported `MONITOR=FINITE_SMOKE_DONE`, separate-PID supervisor reported `SUPERVISOR=MONITOR_COMPLETED_SEPARATE_PID`, host reported `THERMAL_TRIAL=PASS_OBSERVER_SUPERVISOR_ONLY_NO_PHYSICAL_RETURN`.
- Safe fault injection: monitor exited after two readings; CPU maxima **35.0, 32.3 C**, GPU and DDR **30.8 C** each tick. Supervisor independently detected monitor death and emitted `SUPERVISOR=WOULD_REQUEST_RETURN_NOT_EXECUTED reason=monitor_dead`; host reported `THERMAL_TRIAL=EXPECTED_MONITOR_DEATH_DETECTED_NO_PHYSICAL_RETURN`.
- Host final result: `LIVE_THERMAL=ROOT_OBSERVER_AND_SUPERVISOR_TESTED_NO_PHYSICAL_RETURN`; local evidence file `out/sm8850/live-thermal-trial/root-thermal-smoke-20261120T193146Z-da448d.json` (JSON not uploaded here).
- **This proves actual root process liveness and worker-death detection only while One UI is running.** The finite sibling processes still share the trial launcher and are **not** shown to survive launcher/ADB/Framework/xnuhost loss. No actual `return.request`, physical reboot, root permanent service, vendor-qualified critical limits, or unassisted normal-OneUI recovery was demonstrated.
- **P0 remains incomplete.** The unconditional source-level `--framework-session run` admission block must stay intact; old on-phone staged script is not retroactively updated.



## Next root-side acceptance: protected staging + detached ADB launcher (2026-11-21)

The operator physically confirmed **154/154 offline P0 tests PASS** on exact OneOS `906309940e7fcd4b75a634c1feca5eecfa475768` and ran the real finite root sensor worker plus separate sibling supervisor on intact SM-S948B stock One UI. **28 genuine type-validated CPU/GPU/DDR zones** sampled successfully. A normal 3-sample trial completed; an intentional two-sample worker exit was detected as `SUPERVISOR=WOULD_REQUEST_RETURN_NOT_EXECUTED reason=monitor_dead`. The observer reported `P0_RECOVERY=NOT_QUALIFIED` and never rebooted or issued a return request. The physical host evidence path was `out/sm8850/live-thermal-trial/root-thermal-smoke-20261120T193146Z-da448d.json` (JSON not directly inspected).

**New source (awaiting operator CachyOS and phone test):**
- The live-trial host now transfers ownership of its random temporary stage, root observer script, manifest and identity to **UID 0** before launching the child processes. It verifies root ownership and then rechecks their **SHA256 as root**. This closes the prior shell-owned staging replacement window; a failed hash/owner check refuses a run and tries bounded stage cleanup.
- The shell trial records the parent process' PID, process birth and Linux **session ID**, and the supervisor's PID and birth separately from the worker. A new, explicitly opt-in **`--run-detached-readonly`** mode launches a **4-tick finite trial** with the root manager's BusyBox `setsid` and redirected file descriptors. The original ADB shell command terminates; the host then reconnects through **new** ADB shell commands to inspect real completion records and to verify the parent SID/PID binding and three distinct process IDs. It deletes its own temporary stage afterward.
- The original **`--run-readonly`** normal/fault smoke remains available. The two modes are mutually exclusive and **default to a no-device audit**. Neither controls Framework, kills Android services, changes thermal limits, touches `/dev/watchdog`, issues `return.request`, reboots nor launches iOS.
- Five new source-level/fixture/mock host test cases were added compared with the operator's previous 154-test checkpoint, so `tests/run_sm8850_thermal_local.sh` now requires **159 tests**. The impacted 20-case live-trial test subset (including detached and ownership cases) **PASS in assistant Linux**, but **159/159 has not yet been executed by the operator's CachyOS**.
- A successful detached trial would prove independence from **the initiating ADB shell command/session only**. `setsid` does **NOT** establish independent cgroup/namespace ownership, survival after `adbd` or Android Framework stop, or safety if the supervisor itself dies.

**P0 remains OPEN.** Before lifting the unconditional 600-second source lock, we still need a real independent deadline that survives Framework and supervisor failure, vendor-grounded critical temperatures, authenticated reboot-only return generation binding, and a recorded physical **unassisted reboot into healthy One UI**. No passing test or new stage manifest authorizes a full takeover.


## P0 detached trial regression found by operator (2026-11-21)

- User's CachyOS fetched exact OneOS source revision `77761d26f774b3e63d6c084de2ce5f7c8ac8a6e0` and started strict 159-case local CI. **154 tests succeeded; five fixture live-trial tests FAILED** before any phone trial, with `THERMAL_TRIAL=BLOCKED reason=parent_identity_unavailable`.
- Root cause in the newly added PID/SID receipt source: POSIX shell `$$` was accidentally collapsed to a single `$` in five places in the parent/supervisor identity code. As a result the attempted parent path was `/proc/$/stat`, not `/proc/<actual-pid>/stat`. Those five observed failures stemmed from this source defect; there is no evidence of a physical sensor/reboot failure.
- **Fixed source**: restore `$$` in both `birth_ticks` calls, both identity records and the parent `/proc/$$/stat` SID path. Strengthened existing `test_syntax` to assert all exact required PID tokens, without increasing the 159-case count. Verified updated GitHub blob contains the intended five `$$` sites and test assertions; **combined 159/159 and detached physical run must still be confirmed on operator CachyOS**.
- Important: prior physical root worker + supervisor test **154/154 local PASS** and actual One UI 28-zone read with safe monitor death injection remain valid. No 600-second Framework takeover, thermal return/reboot or watchdog action was initiated by this failed CI; source P0 admission lock stays unconditional.

## 2026-11-21 operator: detached root process accepted on physical S26 Ultra

- Operator's CachyOS fetched **exact OneOS `98ca3482c762677b76c1fb3dd6f24ef626e76059`**, executed the strict suite: **`ONEOS_P0_OFFLINE_159=PASS`**. All previously failing parent/session identity tests now pass.
- Explicit `--run-detached-readonly` on physical SM-S948B/m3q (One UI intact): `ZONES=28`; four root-side sensor ticks, followed by `MONITOR=FINITE_SMOKE_DONE samples=4 physical_return=NO` and `SUPERVISOR=MONITOR_COMPLETED_SEPARATE_PID samples=4 physical_return=NO`. Host reported `LIVE_THERMAL=ROOT_OBSERVER_AND_SUPERVISOR_TESTED_NO_PHYSICAL_RETURN`, scenario `detached-normal` and `P0_RECOVERY=NOT_QUALIFIED`.
- Four ticks (C): CPU peak **34.2, 31.9, 30.7, 31.5**; GPU peak **30.1, 30.1, 29.7, 29.7**; DDR peak **30.1, 30.1, 29.7, 30.1**.
- Physical evidence path (not uploaded as raw JSON): `out/sm8850/live-thermal-trial/root-thermal-smoke-20261120T195642Z-c3d826.json`.
- **Accepted for only this subgate:** root-owned staging, independent PID/SID identities, and monitor/supervisor completion after the initiating ADB shell disconnects under stock One UI. This does not prove actual Framework-stop independence, supervisor death fallback, hardware watchdog, or reboot-to-OneUI recovery; no return/reboot action occurred.
- P0 remains incomplete. Source P0 full 600s Framework takeover refusal remains unconditional. Next work must focus on recovery contract/provenance and independent deadline rather than expanding thermal readers.


## P0 recovery provenance read-only inspector (2026-11-21)

- **Operator-verified:** exact OneOS `98ca3482c762677b76c1fb3dd6f24ef626e76059` completed **159/159 CachyOS offline PASS** and an actual detached `setsid` four-tick thermal root monitor/supervisor trial across all **28** selected CPU/GPU/DDR zones: finite monitor completed, separate-PID supervisor completed, no physical return/reboot. The initiating ADB shell disconnected successfully; the result still reported `P0_RECOVERY=NOT_QUALIFIED`. Original host evidence: `out/sm8850/live-thermal-trial/root-thermal-smoke-20261120T195642Z-c3d826.json`.
- **New OneOS source**: `scripts/phone/sm8850-recovery-provenance.py` (default **audit-only**, zero ADB). The explicitly opt-in `--run-readonly` path checks current stock One UI boot identity, `init.svc.zygote`, boot reason and **only fixed** historical root-owned OneOS control/return evidence paths under `/data/adb/oneios-m3q-framework`; emits a restricted-permission JSON. Missing/unreadable historical files remain **unknown** rather than PASS. It does not write phone state, operate guest/watchdog or reboot.
- It can report that an old reboot-outcome marker and a changed boot ID are **consistent** with a historical reboot-only return. **This cannot establish unassisted recovery, intact root across reboot, independent guard survival or hardware watchdog certification**, even when a correlation exists; `unassisted_return_proven=false`, `recovery_certified=false` and `full_takeover_allowed=false` are unconditional.
- **Nine new offline test cases** in `tests/test_sm8850_thermal_recovery_provenance.py` passed 9/9 in the assistant's Linux container using mocked Android property and ADB responses. Strict combined runner now expects **168**, with the operator's accepted baseline at 159/159; operator CachyOS validation of new 9 and physical read-only provenance inspection **pending**.
- **Next mandatory P0 gate:** independently observed short **reboot-only** recovery with the physical device, plus verified next-boot One UI, and separately qualified thermal deadlines/guard survival. This historical inspector deliberately does not and cannot replace that disruptive acceptance.


## 2026-11-21 P0 historic reboot-only marker correlation verified on physical phone

- Operator fetched exact OneOS commit `a46074ded2a33dfdcf6ff57feff12b5ca1c5039d`, executed the **9 new offline provenance tests** on CachyOS: **9/9 PASS**. This was a targeted test run, not the full proposed 168-case suite.
- The opt-in live **read-only** provenance inspector on intact S26 Ultra reported: `NORMAL_ONEUI_NOW=YES`, `PREVIOUS_BOOT_DIFFERENT=TRUE`, `HISTORICAL_REBOOT_RETURN_CORRELATION=TRUE`, `UNASSISTED_RETURN=NOT_PROVEN` and `P0_RECOVERY=NOT_QUALIFIED`. Evidence path reported as `out/sm8850/recovery-provenance/recovery-evidence-20261120T200612Z-c6706c.json` (raw JSON was not uploaded for direct inspection).
- The historical markers are consistent with the phone having rebooted through the OneOS reboot-only pathway on a previous boot. Neither the marker nor a different current boot proves it occurred without human intervention, that it was caused by the independent deadline, or that a thermal sensor failure triggers an actual reboot.

### New host-only active-witness groundwork (not yet operator verified)

- Added `scripts/phone/sm8850-reboot-witness.py` with **default zero-ADB audit**. Explicit `--observe-only` performs ONLY host ADB reads: saves intact One UI identity and boot ID **before** a separately authorized short recovery smoke, observes an ADB transport interruption, then requires a **new boot ID and fully running One UI** within a bounded interval (30–600 sec). It can afterward correlate historical control/outcome evidence to the exact pre-smoke boot.
- This observer **does not trigger reboot, Framework stop, guest, watchdog or return.request**. A USB disconnect alone cannot count as a new healthy boot. Even with a postboot and matching marker, output always includes `unassisted_return_proven=false`, `recovery_certified=false`, `p0_complete=false`, and `full_600s_takeover_allowed=false` because physical key use cannot be ruled out from ADB alone.
- Ten new offline-only fault cases verify mode audit, transport loss, postboot identity, marker mismatch, missing events, false USB flaps, and mandatory non-certification. Strict test runner now requires **178** total. **These new 10 have not yet run on the operator's CachyOS**. Only start a future witness just before a separately approved short reboot-only recovery smoke; do not use a 600-second full takeover for this validation.
- Remaining P0 blockers remain a real Framework-independent thermal monitor/deadline, vendor-grounded critical temperatures, supervisor-death last resort, and a **witnessed unassisted** successful reboot-only return. No source full-takeover bypass was added; PRs stay draft.


## 2026-11-21 opt-in REAL iOS takeover short probe integrated in OneOS

- The S26 Ultra owner explicitly requested a physical iOS takeover experiment, rather than further blocked fixture tests. The OneOS P0 draft branch now introduces `--framework-session probe`: a REAL xnuhost/iOS guest session, not just a Framework-only smoke, bounded to **90 s after verified Framework stop** and followed by existing **mandatory reboot-only** return. Source `--framework-session run` **600 s remains blocked unconditionally**.
- `switcher/assets/oneios_sm8850_thermal_takeover_guard.sh` reads the **current boot's complete mapped CPU/GPU/DDR sensor set plus BAT/LRP/board AP** once per loop, from init's namespace/root cgroup outside xnuhost. The script uses root-only stage manifest, exact per-zone type and boot checks, and publishes atomic generation/PID-birth/sequence/monotonic heartbeat. It **does not itself reboot or touch watchdog/governors**. The already-existing independent `framework-deadline` and watcher each check liveness/heartbeat, triggering the **existing OneOS reboot-return** when sensor read fails, values exceed early-abort cutoffs, worker dies, or heartbeat stalls.
- **Deliberate experimental early-abort cutoffs, NOT vendor-qualified hardware critical limits:** real CPU/GPU/DDR peak >=55 C, battery >=38 C, LRP/board AP >=42 C. If a sensor vanishes after Framework stop the guardian fails closed and recovery helpers should request immediate return. This is not production safety certification.
- New `scripts/phone/sm8850-takeover-short-probe.py` has default **zero-ADB audit**. The explicit `--run-90s` action re-inventories sensors on intact One UI, creates a fresh boot-bound manifest, root/SHA-verifies and backs up the staged switch, checks the original OneOS image/runtime/APFS one-shot clone/legacy-watchdog/previous smoke preflight, starts an independent host reboot witness, and **then intentionally starts the REAL disruptive iOS guest** via root setsid. `--prepare-probe` only stages sources and does not change Framework. After a new normal One UI boot, it records host witness and launch markers separately; no guest-start PASS is inferred merely from reboot.
- `docs/SM8850_SHORT_GUARDED_IOS_PROBE.md` documents the single command, actual phone reboot risks, emergency hardware restart, and data clone preconditions.
- **Important validation distinction:** the previously confirmed 159/159 CachyOS and live 28-zone detached trial/9+10 target tests were for earlier source. This new takeover integration has **NOT** been executed on the operator's CachyOS or S26; all physical results from the new probe are **pending**. Existing 178-case CI runner now syntax-checks the two new files without adding more test methods; it continues to require the original 178 cases.
- This is **experimental opt-in enablement**, not closure of P0 production acceptance: real Framework stop + rebinding risks remain, vendor watchdog and unassisted physical recovery not yet independently certified. But unlike the 600s branch, the short iOS probe is source-enabled and may be exercised at the owner's explicit request.


## 2026-11-21: 90s guarded probe refused before Framework stop — consumed APFS Data

- The operator ran pinned OneOS `818e7c4a2e5d716bd887a2872aabfa3cab65c105`. Root 28-zone discovery and passive `--framework-check probe` returned PASS, but the **real `--framework-session probe` refused before stopping Android Framework** with `PREFLIGHT REFUSED: isolated APFS Data clone was already consumed`. There was **no 90s iOS takeover** and no recovery/reboot event in this attempt. The host had already installed switch/guard/manifest during preparation, so the preflight message `Nothing on the phone was changed` applies to the refused switch run, not all host staging.
- OneOS now checks `data.consumed` and `image.ready.rearm-pending` **before saying probe preflight PASS or staging its new source**. The 600s source block stays unchanged.
- For a **fresh isolated Data clone**, use only the existing OneiOS `sm8850-full-takeover.sh rearm` path. Do **NOT** delete/touch `data.consumed`, copy the consumed APFS image back to seed, or rebuild the 24 OS image files. Rearm re-verifies existing root-stage/runtime, performs a private mount-namespace probe, requires storage reserve and clones the original `bench/data` source into a new root stage while archiving the entire previous consumed clone and marker under `.retired-data/`.
- The existing `framework-stage.sh` rearm now also handles a consumed clone **modified by the previous real iOS guest**, BUT ONLY when the original seed matches both files in one *older*, root-owned, verified **pristine archived clone**. The modified guest Data is never reused and is preserved as evidence. If no archived pristine baseline matches, it refuses and the operator must investigate the original source integrity; no `data.consumed` bypass is allowed.
- **Only after** rearm prints `APFS_DATA_REARMED=YES`, `SM8850_MOUNT_NAMESPACE_PROBE=PASS_NO_FRAMEWORK_STOP`, and `FULL_TAKEOVER_STAGE=REARMED`, use the new pinned OneOS 90s probe host source; it will stage the latest guard and switch again. **Never invoke the old 600s `run` command**. This update is a source-level repair; fresh-phone rearm and real 90s probe have not yet been tested in this turn.

## 2026-11-21 observed rearm failure and corrected source workflow

- The operator fetched exact OneiOS `53ac110700f43f950126a1e4c2c71a0fa151eb06`, performed all **9/9 existing local full-takeover tests PASS**, and successfully upgraded the on-phone OneOS recovery scripts (`ONEOS_STAGE_UPGRADE=PASS_BACKUP_PRESERVED`). The device's isolated BusyBox mount-namespace probe reported `SM8850_MOUNT_NAMESPACE_PROBE=PASS_NO_FRAMEWORK_STOP`, with One UI still running.
- Physical rearm then explicitly refused **before replacing Data**: `STAGING REFUSED: consumed Data differs from seed, but NO root-owned archived pristine baseline matches the original source; preserve all snapshots`. This was caused by the prior code incorrectly assuming that a consumed clone must match the original seed (or a separate pristine historical archive), even though the prior iOS guest ran for ~600s and can legitimately write to its own private clone.
- The source now treats the **fixed, separately stored original benchmark seed** as the source for rearm, not the consumed guest's Data. It requires two exact regular files at fixed paths with expected sizes (8 GiB `data.img`, 8-byte `unique-chip-id`), distinct single-link inodes, stable file identity across read/copy, SHA-256 before/after copying, and available storage. The whole consumed guest Data directory and `data.consumed` are **moved into a root-owned .retired-data archive**, not reused or deleted.
- It additionally records the **consumed guest** and **new source** hashes in separate root-owned archived `consumed-data.sha256` and `rearm-source.sha256` receipts. If guest Data changed, logs include `APFS_CONSUMED_GUEST_DATA=MODIFIED_PRESERVE_OLD` and `APFS_REARM_ORIGINAL_SOURCE=EXISTING_BENCHMARK_SEED_NOT_HISTORICALLY_ATTESTED`. The latter is important: reading a SHA-256 NOW cannot independently prove the original seed was unchanged over past experiments. This is an **operator-selected existing source**, not independently authenticated historical provenance. Do not claim otherwise.
- No pristine historical archive is required solely to distinguish guest-written Data from its original seed. A missing source, unexpected path/link/size, changed source identity/hash, insufficient storage or partial prior rearm still refuses.
- The `sm8850-full-takeover.sh` optional `wl-copy` integration now **skips clipboard access without a live Wayland socket**, avoiding misleading errors on SSH/headless sessions. The earlier caller error `zsh: PIPESTATUS[0]: parameter not set` was external to the Bash wrapper; use a Bash shell or `bash <<'BASH'` for pipeline-status capture. The actual rearm command returned **exit 2**, not an unknown ADB failure.
- **Status:** SOURCE FIXED IN PR; physical rearm using this revision and a real 90s guarded iOS guest probe are **NOT YET VERIFIED**. Do not unlink `data.consumed`; do not invoke 600s takeover.


## 2026-11-21 operator: first real opt-in 90s probe — reboot observed, guest not proven

- Owner ran pinned OneOS **`dff7f139fa569eb933e2ff1dea1901aefc07acd2`** after a verified fresh APFS Data rearm (OneiOS `4ae8874bac37c66e1214f68bc2606543ad941a1b`). On-device 28-zone prepare and passive short-thermal preflight returned PASS. Host dispatched `--framework-session probe`.
- Host reboot witness observed **ADB transport loss, a different boot ID, and healthy normal One UI**: `SHORT_PROBE=NEW_NORMAL_ONEUI_BOOT_OBSERVED_AFTER_PROBE_REQUEST`.
- However host report printed **`THERMAL_GUARD_ARMED=FALSE`**, **`FRAMEWORK_STOP_MARKER=FALSE`**, **`XNUHOST_LAUNCH_MARKER=FALSE`**, and **`HISTORICAL_RETURN_CORRELATED=FALSE`**. These are **missing positive evidence**, NOT proof that guard, Framework stop or xnuhost never ran. Recovery attribution and absence of manual key use remain unverified. Do **not** record an iOS takeover PASS.
- Owner's JSON file path (not uploaded or directly inspected here): `out/sm8850/short-ios-probe/short-probe-20261120T212416Z-b95b8c.json`. Its existing `postboot_root_log_accessible`, `switch_launch_log_tail`, and nested witness fields will distinguish inaccessible postboot root from an actual error in the switch output. **Do not rearm or initiate another guest run until diagnosing this session**; APFS clone may already be consumed.
- **Host collector source bug fixed in OneOS (new code, NOT involved in the just-run probe):** the original host read ONLY the last 110 lines of the switch log after reboot; it returned **exit 0 as soon as a healthy new One UI boot was observed**, even with all three guest-launch markers missing. New host captures best-effort live pre-reboot switch-log milestones while the initiating root session remains accessible, combines with postboot log evidence if available, persists the log excerpts and `postboot_root_log_accessible`, and returns **exit 4 / `SHORT_PROBE=INSUFFICIENT_GUEST_LAUNCH_EVIDENCE_NOT_PASS`** when guest markers are incomplete. Return 0 now requires *all three* positive log milestones; recovery remains non-certified.
- **No new offline tests and no further physical experiment were performed for this collector-only code change**. The existing 600s source admission remains unconditionally blocked.


## 2026-11-21 exact host witness details for 90s probe; no further phone actions

- Operator inspected existing `short-probe-20261120T212416Z-b95b8c.json`: `postboot_root_log_accessible=False`, `switch_launch_log_tail` empty/`LOG_NOT_CAPTURED`. Host witness events: `INITIAL_NORMAL_ONEUI` at `0s`, `OFFLINE` at `44.436s`, `NEW_BOOT_NORMAL_ONEUI` at `66.496s`, duration `67.109s`.
- This proves ADB transport loss followed by a new healthy One UI boot, **not** Framework stop, thermal worker, xnuhost, guest frame, return mechanism or unassisted reboot. The earlier three `FALSE` launch markers are **missing log evidence** because root log was unavailable after boot, not direct negative observations. A possible early return around the stage's initial 45s `framework.cutoff` is a hypothesis only; host time zero is not the device-side monotonic cutoff start.
- `provenance_available=True` means the inspector returned a JSON dict, **not** that it read root-owned return markers. `sm8850-recovery-provenance.py` deliberately maps a failed `su`/cat read to `None`, returns device/zygote facts and `recorded_outcome_consistent_with_reboot_return=False`. Inspect the JSON `witness.historical_provenance_snapshot.evidence` entries to tell whether markers are missing, not simply the outer bool.
- **Host-only instrumentation changed in OneOS for any future separately authorized session:** start a read-only root `/system/bin/tail -n +1 -f` stream of this session's switch log to an on-host CachyOS `preboot-switch-<token>.log` file **BEFORE launching** the guest. When ADB is disconnected or temporary DirtyFrag root disappears on reboot, prior log bytes are preserved on the host. It does not change reboot path, Framework control, thermal policy, watchdog or APFS data; a failure to establish this observer stops the host before launch. Its log is considered positive milestone evidence alongside the already added periodic live reads and postboot reads. New streaming collection is code-only and **not physically exercised yet**.
- **Do not rearm, reboot or rerun iOS just to diagnose this previous session.** The current APFS Data clone may have been claimed; preserve the on-device stage/consumed marker. If root can later be restored in normal One UI, optionally inspect existing root logs then, without launching a new guest. Both PRs remain draft, 600s remains locked.


## 2026-11-21: physical 90-second probe forensics — root cause VERIFIED

**This section supersedes earlier assertions that the physical guest/Framework stop/thermal supervisor was unobserved.** The operator recovered the root-owned logs after the normal One UI reboot; the original host JSON had `postboot_root_log_accessible=False` only at the time it attempted capture. That was a collector evidence gap, **not** proof that the switch did not run.

- The root switch recorded `APFS_DATA_CLONE=CONSUMED_ONE_SHOT_BEFORE_FRAMEWORK_STOP`, then `P0_SHORT_PROBE_THERMAL=ARMED_ROOT_SENSOR_GUARD_NOT_PRODUCTION_CERTIFIED` at 04:23:33.
- Android Framework was **verified stopped** and app groups drained; input absent; `system_server` gone. `vm.max_map_count` changed from `65530` to `1048576` with saved baseline. The independently requested **90-second deadline** was armed at device monotonic uptime `44592`, target `44682`.
- At **04:23:46**, OneOS recorded `xnuhost pid 23992`, a separate mount namespace `mnt:[4026536369]`, session state running and `=== ONEIOS SESSION LAUNCHED ===`. The original guest log confirms actual native `xnuhost` exec, 8 accessible CPU mask `0-7` (not independent vCPU pinning), a 4096 MiB guest, APFS disk mounts, runtime GPU capability not yet proven and a connected display helper. **No iOS guest-ready marker, posted display frame or KGSL 3D success** was present in the supplied excerpt.
- At **04:23:47**, the independent root monitor logged `P0_THERMAL_GUARD=FAIL_CLOSED soft_temperature_abort` and its root fault file recorded the same reason. OneOS `framework.guard` immediately requested a **reboot-only return** because the thermal monitor faulted. Root-owned `return.outcome` confirms `reboot-deadline-or-manual ... who=framework-deadline reason=root thermal monitor lost, stale, or requested early return`. Host witnessed ADB loss and a **new normal One UI boot** with bootreason `reboot,oneios-sm8850-reboot-return`. This is **an early thermal-triggered return, not expiry of the 90-second deadline**; the exact physical sensor/temperature above the abort threshold was not preserved by the old guard.
- Original **experimental soft cutoffs** remain CPU/GPU/DDR >=55°C, battery >=38°C, LRP/board AP >=42°C. These are NOT manufacturer hardware limits. Do not raise cutoffs, disable monitoring or retry guest merely to evade the abort. A new guard source revision records `crossed=...` and precise CPU/GPU/DDR max zone/index (millidegrees Celsius) plus battery/LRP/AP values (deci-Celsius) in its `thermal.guard.fault` and `thermal-guard.log` for any *future, separately approved* run. **This diagnostic improvement does not retroactively reveal which sensor crossed in the prior run.**
- Original legacy `/dev/watchdog` magic-close returned `EBUSY`, with a bounded feeder retry. Reboot-return was requested and One UI returned, but **hardware watchdog independence, unassisted return with no physical key intervention, vendor thermal calibration and sustained guest performance are NOT yet qualified**.
- **P0 status revised:** `LIVE_ROOT_THERMAL_MONITOR_AND_REBOOT_ONLY_ABORT=OBSERVED`, `FRAMEWORK_STOP_AND_NATIVE_XNUHOST_EXEC=OBSERVED`, `GUEST_IOS_READY_FIRST_FRAME=NOT_VERIFIED`, `PHYSICAL_SOFT_THRESHOLD_IDENTITY=NOT_RECORDED`, `UNASSISTED_RECOVERY_CERTIFIED=NO`, `FULL_600S_TAKEOVER=BLOCKED`. No additional device takeover was performed for this documentation update.


## 2026-11-21: historical last-good thermal heartbeat physically recovered

The operator read the original root-owned `control/thermal.guard.heartbeat` after the 90s probe: `v1 a6007f1e-4fc3-4e99-82dd-267ccb249656 a6007f1e-4fc3-4e99-82dd-267ccb249656.15737.4455553 19863 4457946 8 44590 OK 44800 37800 37400 290 314 332`.

- This is **the last successfully published OK sample, not the sample that triggered the `soft_temperature_abort`**.
- Decoded CPU peak **44.8 C** (cutoff 55 C, 10.2 margin), GPU peak **37.8 C** (55 C, 17.2 margin), DDR peak **37.4 C** (55 C, 17.6 margin), battery **29.0 C** (38 C, 9.0 margin), Samsung LRP **31.4 C** (42 C, 10.6 margin), board AP **33.2 C** (42 C, 8.8 margin). Raw CPU/GPU/DDR readings are millidegrees C; BAT/LRP/AP are deci-Celsius.
- Sequence **8**, device monotonic uptime **44590 seconds** (not milliseconds), while Framework-stop log recorded **44592 seconds**. These observations are close in monotonic time, but do not identify the failing sensor. Device wall-clock logs and host witness time need not have the same zero point.
- The original thermal guard's `read_all` returned code 2 only when the sensor value comparison hit one of the above experimental cutoffs. This supports a **measured threshold abort in that subsequent sample**, but the prior source did not persist the failing values, so the **identity/actual temperature and possibility of an anomalous sensor measurement remain unresolved**. Do not claim the healthy sample itself was overheating or that CPU definitely crossed 55 C.
- No additional guest run is justified solely to re-create this fault. The already committed OneOS guard change preserves exact violated groups/zones and values on a future separately approved run without changing any threshold.

## 2026-11-21: operator-verified CachyOS local CI for post-abort diagnostic guard

- Operator fetched exact OneOS commit **`9f79c5afb40224c69fc8b084e5bf5b0569933829`** from `feat/sm8850-p0-thermal-reader-sim`, created a separate pinned `git archive` and executed **`bash tests/run_sm8850_thermal_local.sh`** locally on CachyOS (no device writes).
- Output: **`ONEOS_P0_OFFLINE_178=PASS`** and **`P0_LOCAL_SOURCE=PASS`**. The source/syntax/tests for the modified root thermal guard, added culprit-zone/value fault metadata and host log collector passed the existing 178 regression cases.
- Explicit suite warning remains **`P0_SAFETY_STATUS=OFFLINE_SIMULATION_ONLY_NO_PHYSICAL_GUARD`**. This PASS is not a second physical test, not thermal cutoff calibration and not evidence of iOS first frame or unassisted reboot qualification.
- Next diagnostic gate: read-only normal-One-UI baseline from fresh exact-boot 28-zone CPU/GPU/DDR inventory plus the existing 3-sample CPU/BAT/LRP/board AP reader; preserve the previous thermal guard cutoff values unchanged. No APFS rearm or guest experiment is justified from the CI PASS alone.

## 2026-11-21: actual post-reboot normal-OneUI thermal baseline collected; healthy 28-zone survey

- Operator ran a **read-only physical baseline** on real SM-S948B/m3q/S948BXXS4BZIG with source pinned at `9f79c5afb40224c69fc8b084e5bf5b0569933829`, after **178/178 CachyOS offline P0 tests PASS**. No guest, APFS rearm, Framework stop or watchdog action performed.
- `sm8850-thermal-junction-inventory.py --run-readonly`: **`SELECTED=28 ERRORS=0 UNREADABLE_TYPES=0 COVERAGE_COMPLETE=YES`**. CPU peak **31.9°C** at `cpu-0-0-1 /sys/class/thermal/thermal_zone6/temp`; GPU peak **29.3°C** at `gpuss-1 /sys/class/thermal/thermal_zone37/temp`; DDR peak **29.7°C** at `ddr /sys/class/thermal/thermal_zone47/temp`. `XO_PEAK=UNAVAILABLE` is not required for the accepted CPU/GPU/DDR `scan_coverage_complete` contract.
- `sm8850-four-sensor-oneui.py --run-readonly`: pinned CPU path `/sys/class/thermal/thermal_zone16/temp`; three samples: (CPU/BAT/LRP/AP) **31.1/25.5/27.6/26.1°C**, **29.6/25.5/27.6/26.0°C**, **29.6/25.5/27.6/26.0°C**. Output `FOUR_SENSOR=COLLECTED_NOT_QUALIFIED` (not vendor thermal certification).
- Relative to *unchanged experimental early-abort* thresholds (CPU/GPU/DDR >=55°C; battery >=38°C; LRP/board AP >=42°C), the steady OneUI baseline has minimum margins: CPU **23.1°C**, GPU **25.7°C**, DDR **25.3°C**, BAT **12.5°C**, LRP **14.4°C**, board AP **15.9°C**.
- For the **previous real 90s Framework stop + xnuhost exec**, its last healthy guard heartbeat at uptime 44590 recorded CPU **44.8°C**, GPU **37.8°C**, DDR **37.4°C**, BAT **29.0°C**, LRP **31.4°C**, AP **33.2°C**; CPU is already 12.9°C above this newer idle baseline, but these are *separate physical sessions*, not a controlled paired thermal comparison. The later `soft_temperature_abort` was logged without the failing sensor values; **cannot determine which sensor crossed** from these healthy samples.
- Engineering decision: mark **read-only OneUI baseline PASS**, but leave **post-Framework thermal qualification, culprit sensor, vendor-critical thermal limits, iOS guest READY/first frame, Vulkan KGSL and unassisted recovery UNVERIFIED**. Do **not** raise experimental abort limits, disable sensor checks, claim a production thermal guard, or unlock 600s mode. The next *disruptive* probe, only with physical risk accepted and recovery available, should use already-committed exact-fault diagnostics and preboot host log streaming. No extra physical takeover is implied by this documentation.
- On-host evidence files: `out/sm8850/oneui-thermal-baseline-20261120T233413Z/zones/junction-20261120T233416Z-57b8f5.json` and `.../four-sensor/four-sensor-20261120T233421Z-88b3c2.json`.
