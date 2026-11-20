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
