# SM8850 P0 thermal preflight (passive evidence only)

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
