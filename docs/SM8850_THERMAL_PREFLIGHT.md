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
