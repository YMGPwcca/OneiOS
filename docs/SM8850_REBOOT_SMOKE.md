# SM8850 OneOS-legacy reboot-only Framework smoke (EXPERIMENTAL)

**OneiOS · Galaxy S26 Ultra / SM8850 · Recovery smoke chronology**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!NOTE]
> **Historical source or earlier experimental procedure.** The latest S26 Ultra full guest ran ~600.6 s with a displayed frame, but serious heat and unverified recovery remain open. Use the [physical ledger](SM8850_LIVE_STATUS_2026-11-20.md) for current decisions.

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
- **Do not use Volume Up + Volume Down as a test gesture on a
  USB-connected SM-S948B.** If a reboot occurs while both keys are held,
  Samsung can enter Download Mode. Samsung's documented force-restart
  gesture is Side/Power + Volume Down for more than seven seconds.
  That hardware action is a fallback, not proof of the key-reader watcher.

## Local preflight (read-only)

```sh
cd ~/projects/OneiOS
scripts/ci-local.sh recovery
python3 scripts/phone/sm8850-takeover.py --reboot-audit --serial R5GL64LZ9HA
bash scripts/phone/sm8850-flock-probe.sh R5GL64LZ9HA
python3 scripts/phone/sm8850-takeover.py --reboot-stage-check --confirm --serial R5GL64LZ9HA
```

Do not proceed if `--reboot-audit` returns a nonzero code, if One UI
is unhealthy, or if the watchdog owner or device identity has changed.
The standalone temporary-file lock probe must report `LOCK_PROBE=PASS`.
The separately confirmed `--reboot-stage-check` writes only the trusted
recovery scripts and runs the complete `reboot-smoke` preflight without
stopping Framework; it must report `REBOOT_STAGE_CHECK=PASS_NO_FRAMEWORK_STOP`.

The lock probe matters because:
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

**Historical evidence, not the current instructions:** on 2026-11-20,
the chord invoked during early preparation caused a safe same-boot abort
before Framework was stopped. In the next experiment, the host printed
`TAKEOVER_CONFIRMED=YES`; the phone then rebooted automatically and
holding Volume Up + Volume Down while the USB cable was attached led to
Samsung Download Mode (D2/reboot screen with passcode-related text).
Disconnecting USB and using the hardware force restart brought One UI
back. This is **not** a successful volume-chord recovery test. The
subsequent archived evidence confirmed that OneOS's framework deadline
requested the first reboot; this does not establish an unassisted normal
boot because the owner encountered D2 and forced a restart.

**Current SM8850 experiment is deadline-only.** Do not press the two
volume keys when `TAKEOVER_CONFIRMED=YES` appears. The independent
`framework.deadline` is set to **20 seconds after the verified stop**
and automatically requests reboot. The host prints
`AUTO_REBOOT=EXPECTED_AFTER_20_SECOND_FRAMEWORK_DEADLINE`.
The screen may be black with One UI's framework down; that alone is not
evidence of a panic.

After reconnecting, inspect the archived `return.outcome` and
`session/return.request`. The host reports
`REBOOT_SMOKE=DEADLINE_REQUEST_CONFIRMED_ONEUI_OBSERVED` only when the
new boot is healthy, the launch token/takeover marker and deadline return
request match, and boot reason is
`reboot,oneios-sm8850-reboot-return`. Even these facts do not establish
an unassisted normal boot: the phone may have entered Download Mode and
required a manual restart. Therefore the host also prints
`UNASSISTED_RETURN_TO_ONEUI=NOT_VERIFIED` and exits nonzero rather than
claiming full automatic recovery. If the reason is different or missing,
report incomplete. `PHYSICAL_KEY_REBOOT=NOT_VERIFIED` remains. A
hardware force-restart or a software key request is not evidence that
the Samsung bootloader followed the expected normal boot path.
Do not flash firmware or experiment with Download Mode during this test.

Physical-key acceptance will require a **separate, Samsung-safe**
boot-mode procedure and independent evidence. Do not re-enable the
Volume Up + Volume Down instruction merely to obtain a green result.

## Physical acceptance: 2026-11-20, 11:41 local

**Reboot-only Framework Takeover confirmed; watchdog handoff and deadline
request confirmed; independent unassisted return to One UI not yet proven.**

Evidence archive: `out/sm8850/takeover/post-d2-20261120T045443Z`
(this is an operator-local path, not committed evidence). The owner
reported that after the CLI printed `TAKEOVER_CONFIRMED=YES` the screen
went black and reboot began. Holding Volume Up + Volume Down while USB
was connected led to the Samsung D2 Download Mode gate. Unplugging
USB and using Samsung's forced restart returned the phone to normal One UI.

Post-incident root-side artifacts:

```text
TAKEOVER_MARKER=PRESENT
STOP_MARKER=PRESENT
watchdog_feeder.log: initial /dev/watchdog V refused: EBUSY
watchdog_feeder.log: Watchdog feeder ready (legacy, pid 12870)
control/framework.takeover-confirmed=71545c10-23d6-459c-896f-73f0801f851e.5179.274837
session/return.request=framework deadline reached at 2804 (deadline 2804)
return.outcome=reboot-deadline-or-manual 1795149685 who=framework-deadline reason=framework deadline reached at 2804 (deadline 2804)
ro.boot.bootreason=reboot,oneios-sm8850-reboot-return
sys.boot.reason=reboot,oneios-sm8850-reboot-return
PHYSICAL_KEY_REBOOT=NOT_VERIFIED
```

The results demonstrate that the revised original-OneOS `V` feeder
recovered from a transient exclusive-open refusal, and the independent
deadline invoked the OneiOS reboot path **after** verified Framework
stop. They do not demonstrate bootloader-safe volume-key return,
unassisted normal reboot, an in-place return on the same boot, or iOS
guest startup. Do not run additional live reboot-only smokes just to
repeat these proven steps. Keep the normal iOS `--run` acceptance gates
separate; specifically do not bypass watchdog/sysfs qualification,
image staging, or guest rendering requirements.
## Diagnosing a returned session without reboot

If the host prints `REBOOT_SMOKE=SAME_BOOT_RETURNED_NO_KEY_REBOOT` or
`REBOOT_SMOKE=SWITCH_EXITED_BEFORE_VERIFIED_KEY_REBOOT`, do not run another
live smoke. The host's old generic `Recovery or phase verification failed`
message also came from the same-boot `returned` path, which cannot prove
a key-triggered reboot. Inspect the already collected evidence offline:

```sh
python3 scripts/phone/inspect-sm8850-smoke.py \
  out/sm8850/takeover/reboot-smoke-<exact-evidence-id>
```

Read the first failure in `launches/<token>/switch.log`, the watcher in
`return.log`, the original `return.outcome`, and whether
`control/framework.takeover-confirmed` was written. A `control/stopped`
file alone is not proof of a completed Framework stop because it is
recorded before ctl.stop/kill completes.

The currently installed root stage refuses to overwrite changed recovery
scripts. Preserve its evidence and do not delete its files or bypass its
existing-content check to force an update. Only carry out an explicit,
verified no-active-session stage-upgrade procedure after root-cause review.

## Physical reboot incident: 2026-11-20, 10:54 local

**Physical outcome: reboot into One UI, but NO verified Framework takeover
and NO physical-key-reboot acceptance. The current legacy feeder contract
is not qualified for another live attempt.**

On SM-S948B firmware S948BXXS4BZIG, this smoke entered phase 3
(`FRAMEWORK_OWNS -> TRANSFER_PENDING`) and wrote `control/stopped`.
The legacy feeder then logged:

```text
can't create /dev/watchdog: Device or resource busy
OneOS legacy watchdog feeder stopped making progress
```

The watchdog-failure request reached `oneios_return.sh`, which recorded
`reboot-deadline-or-manual ... who=watcher reason=watchdog feeder failed`
and issued `sys.powerctl=reboot,oneios-sm8850-reboot-return`.
After boot the reason properties consistently reported
`reboot,oneios-sm8850-reboot-return`. No panic signature was observed
in the filtered `/proc/last_kmsg` output. The log's `vold`
`reboot_on_failure` message occurred during system shutdown and does
not independently establish the initiating cause.

`control/framework.takeover-confirmed` was absent and the session never
reached `running`. A `control/stopped` marker is written immediately
before stopping zygote; it **does not prove takeover succeeded**.

The Linux watchdog core uses an exclusive-open flag for a watchdog
device; opening a watchdog already held by another file descriptor
returns `-EBUSY`. The misc legacy `/dev/watchdog` can share the
same core state as `/dev/watchdog0` despite distinct device numbers.
An EBUSY here demonstrates failure to obtain a feeder handle; it
**does not by itself identify the owner or prove kernel panic**.
Changing the feeder to ignore EBUSY or claiming it is feeding would
leave recovery unqualified. Do not repeatedly reboot hoping to race
the FD open. See Linux watchdog core `watchdog_dev.c`.

Next evidence (no device changes):

```sh
bash scripts/phone/sm8850-watchdog-owners.sh R5GL64LZ9HA
```

On 2026-11-20, the original all-shell FD inventory timed out with
`EXIT=124` while entering `OPEN FILE DESCRIPTOR REFERENCES` and printed
no owner summary. This is **incomplete evidence**, not an assertion
that no watchdog owner exists. The scanner has been replaced with a
single native AArch64 tool compiled locally with the pinned Android NDK.
It reads `/proc/PID/fd/FD` links in-process, prints every matched
`holder=...` and includes coverage/permission/race counts. Its wrapper
only uploads a temporary executable to `/data/local/tmp` and attempts
cleanup; it never opens a watchdog or stops Android Framework.
The cross-compiled tool should be validated with local host regression
before running it on the phone.
This walks `/proc/*/fd` and reads names/metadata only. It never opens
a watchdog. Its current-boot result cannot reveal with certainty who
owned the device in the short interval after `system_server` stopped.
Resolve the exact firmware's watchdog owner and a provable handback
contract before any further reboot-smoke. The previously PASS local
fixtures do not simulate a kernel's real exclusive-open semantics.

### Measured sole holder

The subsequent native single-process scan on the live One UI boot
`71545c10-23d6-459c-896f-73f0801f851e` completed in 64 ms:

```text
holder=21964 comm=system_server fd=121 target=/dev/watchdog rdev=a:82
WATCHDOG_FDS=1
FD_DIRECTORIES_SCANNED=1109
FD_LINKS_SCANNED=31209
FD_DIR_PERMISSION_ERRORS=0
SCAN_COVERAGE=COMPLETE_FOR_VISIBLE_PROCESSES
```

This rules out a second **visible userspace FD owner in that snapshot**.
It does not establish which process or internal kernel state caused the
`EBUSY` after stopping Framework. Linux watchdog core implements an
exclusive-open gate and normally clears it on the file's final release.
Simply retrying the same `printf V > /dev/watchdog` races with that
gate and is not a verified watchdog handback.

An earlier experimental `pidfd_getfd()` test succeeded only with a
harmless `/dev/null` FD. That experiment did not validate watchdog
ownership or handback and is **not part of the active OneOS recovery path**.

## Reuse of the working OneOS Android watchdog sequence

The reboot-only SM8850 adapter now ports the **actual host-watchdog
sequence** from the OneOS Android guest path (OneOS
`oneos_switch.sh` around `SOFTDOG_V=0`, plus
`guest_prepare.sh`'s repeating `V` feeder):

- Once `stop_android_framework` returns, perform the same single
  `printf V > /dev/watchdog` magic-close attempt as OneOS Android
- Keep OneOS's `V` open/write/close cadence; if open is temporarily
  exclusive (`EBUSY`), log `refused` and retry instead of immediately
  aborting at the first call
- In the **reboot-only** smoke, cap initial retries at 10 seconds;
  unlike the Android guest's best-effort feeder, never issue a
  `feeder.ready` or successful keepalive heartbeat until a real `V`
  write succeeded; repeated EBUSY still invokes recovery and reboot
- Keep the existing Volume Up + Down watcher and independent reboot
  deadline. The normal iOS `--run` remains gated

The original OneOS script also has a **device-specific persistent-property
fallback**, `persist.vendor.softdog=off`, backed by the Android guest's
property store/restore pipeline. OneiOS currently does not have an
equivalent verified post-reboot rollback, so this fallback has
**not** been copied. `/dev/watchdog0` is not touched by this profile.

The OneiOS experimental stage refuses changed scripts by design.
To use this update, run the **confirmed, non-takeover**
`--reboot-stage-check --confirm`. It now explicitly requests an
`upgrade` rather than a fresh `install`, backs up the existing root
scripts and hashes under `/data/adb/oneios-m3q-framework/.rollback`,
and only replaces the scripts when the device is back in healthy One UI
and the previous session is not active on the current boot.
The `oneios-watchdog` native binary must remain identical.
Logs/control artifacts are not deleted.

Local CI now executes the exact production feeder function from the
pinned OneOS gitlink in Bash and mksh, testing initial EBUSY followed
by successful `V`, permanently busy watchdog with no false readiness,
and a failure after the first successful tick. The stage upgrade
function is also tested against a synthetic previous-boot root stage.
These are offline tests, not physical takeover acceptance.

## Not yet enabled

Do not infer full iOS boot approval from a reboot-only smoke. The normal
`--recovery-smoke` (in-place return) and `--run` continue to require
their independent watchdog qualification, prepared APFS snapshot,
and recovery acceptance. No app-side S26 iOS Switch permission is changed.


## Separate full iOS 27 takeover experiment (not a repeat smoke)

> **2026-11-20 outcome:** this separate experiment has now actually
> run: Framework stopped, hosted iOS 27.0.1 reported guest-ready, the
> guest's first frame appeared and `xnuhost` ran ~600.6 s. Post-reboot
> Android was seen, but the device lost ephemeral root and the exact
> deadline caller/unassisted recovery remains unverified. Severe lag
> and a hot device block performance/thermal acceptance. The legacy
> watchdog is still not independently qualified. Current evidence:
> [SM8850_LIVE_STATUS_2026-11-20.md](SM8850_LIVE_STATUS_2026-11-20.md).
> The paragraphs below record the pretrial experiment design, not a
> recommendation to repeat the 600-second run.
>


The 20-second Framework-only reboot smoke already has physical evidence;
**do not rerun it** merely to unlock guest admission. The separate
full iOS 27 experimental path is documented in
[SM8850_FULL_IOS_10MIN.md](SM8850_FULL_IOS_10MIN.md).
It stages the locally built GPU-3D/SHM xnuhost, touch-exclusive input,
8 vCPUs, 4 GiB RAM and a fresh root-owned APFS Data clone. With
a **separate explicit legacy-watchdog risk acknowledgement**, the device
may perform full Framework takeover and start iOS; its independent guard
requires reboot after 600 seconds from verified Framework stop, or earlier
on failure. This is not a qualified native-watchdog handback and does not
certify unassisted normal One UI reboot. No Volume Up+Down key test while
USB is attached.
