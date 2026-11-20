# SM8850 OneOS-legacy reboot-only Framework smoke (EXPERIMENTAL)

## Scope and irreversible boundary

Target only SM-S948B/m3q/SM8850, fingerprint S948BXXS4BZIG and the pinned 6.12.69 kernel.
The host CLI's `--reboot-audit` is read-only; it does not open the watchdog,
stop Framework, stage images or modify the phone. It reports the original
OneOS Android guest's observable legacy holder, without claiming its driver
or timeout has been qualified.

`--reboot-smoke --confirm --accept-legacy-watchdog-risk` is an EXPERIMENTAL
hardware-changing operation. It stops One UI's zygote/system_server,
tries a short interval without the Android Framework, and reboots to
return to One UI. There is no iOS guest in the smoke, and it is NOT an
iOS boot, an in-place return, or a guarantee of recoverability.

The experiment uses the original OneOS Android-guest-style `V` write,
open and close of `/dev/watchdog` every two seconds. This avoids requiring
the missing watchdog sysfs fields but does not prove whether the legacy
node is software or hardware watchdog or its expiration semantics.
Never confuse a green preflight or offline fixture with physical validation.

## Before any real experiment

- Fully back up important data off-device, confirm a working stock restore
  method and an independently accessible recovery/reflash computer. Do
  not rely on this ADB connection as the only escape path.
- Charge the phone and keep it cool; ensure One UI is unlocked and USB
  ADB is already authorized. Use the explicit USB serial because Wi-Fi
  ADB is also connected.
- Validate the exact OneOS gitlink and run local CI: recovery fixture
  in both Bash and Android-like mksh; shell syntax checks for the scripts;
  offline root/host tests. Do not execute this mode if any fail.
- Read `--reboot-audit` and the ordinary `--readiness` results separately.
  The ordinary live iOS takeover stays BLOCKED.
- There are two hardware gestures: hold Volume Up + Volume Down together
  for at least three seconds to request a software reboot via detached
  key readers; if this does not work, Side/Power + Volume Down initiates
  Samsung's hardware forced restart. Neither can be guaranteed in advance.

## Local preflight (read-only)

```sh
cd ~/projects/OneiOS
scripts/ci-local.sh recovery
python3 scripts/phone/sm8850-takeover.py --reboot-audit --serial R5GL64LZ9HA
bash scripts/phone/sm8850-flock-probe.sh R5GL64LZ9HA
```

Do not proceed if `--reboot-audit` returns a nonzero code, if One UI
is unhealthy, or if the watchdog owner or device identity has changed.
The standalone temporary-file lock probe must report `LOCK_PROBE=PASS`:
Android mksh's permanent FD8 is not inherited by external `flock`, so
staging and switch duplicate its open file description into command-scoped
FD0 (`flock -n 0 0<&8`). The holder then retains FD8 until stage/switch
completion. The probe makes and removes only a temporary directory in
`/data/local/tmp`; it does not touch Framework or the watchdog.

## Physically approved smoke (changes running system, risks data loss)

Do not run unattended. Have the owner at the phone and the independent
recovery method ready. The explicit command is:

```sh
python3 scripts/phone/sm8850-takeover.py --reboot-smoke \
  --confirm --accept-legacy-watchdog-risk --serial R5GL64LZ9HA
```

After the screen becomes unresponsive from the Framework stop, hold both
volume keys together for three seconds; the detached watcher should
initiate a reboot. The phase timer requests a reboot automatically after
the short smoke interval. If both paths fail, try Samsung Side +
Volume Down forced restart; this is not evidence of the scripted key
reader working. The deadline and reboot paths do not rely on SSH/ADB.

`REBOOT_SMOKE=PASS_PHYSICAL_KEY_AND_ONEUI` requires a new boot ID, a
recorded verified Framework stop and key-triggered return receipt, running
zygote and zygote_next, a new healthy system_server and SELinux Enforcing.
After reconnecting, personally unlock One UI and test physical touch.
A forced reboot or deadline-driven return is a recovery result, NOT a
physical key chord pass.

## Not yet enabled

Do not infer full iOS boot approval from a reboot-only smoke. The normal
`--recovery-smoke` (in-place return) and `--run` continue to require
their independent watchdog qualification, prepared APFS snapshot,
and recovery acceptance. No app-side S26 iOS Switch permission is changed.
