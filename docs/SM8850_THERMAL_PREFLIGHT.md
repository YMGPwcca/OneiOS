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
