# SM8850 full iOS 27 takeover: 8 vCPU, GPU 3D, 10-minute reboot deadline

**OneiOS · Galaxy S26 Ultra / SM8850 · Full takeover · tested procedure**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!CAUTION]
> **Historical test procedure, not a new-run recommendation.** Guest boot and first frame have been observed, but severe heat, CPU lag and incomplete unattended recovery require P0 safety work before another long takeover.

## Recorded result: 2026-11-20 physical full run (not a rerun authorization)

**Observed:** the repaired on-device namespace probe and APFS Data-only rearm passed;
the next full Framework takeover reached the real guest's ready marker and first
displayed frame, with 8 host CPUs **allowed** (not independently pinned) and live
Adreno/KGSL 3D fence/import traffic. The final `xnuhost` counters say **600.6 s
since host process start**. After reboot Android reported `sys.boot_completed=1`
and `reboot,oneios-sm8850-reboot-return`, while DirtyFrag root had disappeared.
The host exited `4` for **missing root-owned post-return proof**, not because
the iOS guest failed to start.

**Not accepted:** severe lag, a very hot device, no independent case/SoC
temperature trace, no demonstrated 60 Hz UI, no verified precise deadline
requester or unassisted normal One UI recovery. The full-run `bench/bridges=0`
path **does not start OneiOS's thermal bridge or usual CPU placement bridge**;
kernel/firmware thermal limits still exist. The original legacy watchdog is
still `UNVERIFIED_REBOOT_ONLY`; GPU-auto may fall back in a future run even
though KGSL 3D was observed in this one.

**Current decision: do not repeat the destructive 600-second run while hot or
before a separate thermal guard and recovery evidence gate.** The consumed
Data clone must never be reused. Follow the
[physical evidence ledger + P0–P3 blockers](SM8850_LIVE_STATUS_2026-11-20.md).
The commands below document the tested mechanism and previous staging
procedure, **not a recommendation to execute it again now**.



**Target only:** Samsung SM-S948B / m3q / SM8850, firmware
`S948BXXS4BZIG`, Android SELinux Enforcing, KernelSU root, USB ADB.

## What this tests

This is **FULL Framework takeover**, not another no-takeover GPU demo
or a 20-second reboot-only smoke. It reuses the previously observed
OneOS Android legacy watchdog V feeder and independent Framework deadline.
Once Android Framework (zygote, system_server and app groups) has stopped,
the switch enters an independent mount namespace and starts the same
locally built GPU 3D `xnuhost` and SHM display bridge used by the earlier
successful visual bench.

Configuration:

- 8 guest vCPUs, with all host CPU IDs 0–7 both online and in the
  `xnuhost` cpuset at launch; otherwise fail closed. No thermal/governor
  bypass or fixed maximum-frequency writes
- 4096 MiB guest RAM, protected ram-prefault/lock checks
- `--gpu auto`, 3D-enabled signed GPU addon, `--display shm`,
  1080×2340 at 60 Hz, exclusive touchscreen capture
- Root-private mount namespace; `/data` in the guest is an isolated
  one-shot APFS Data clone, never original Android `/data` or source Data
- 600 seconds **from confirmed Framework stop**, enforced by the
  independent device-side `framework-deadline` helper; early guest/feeder
  failure can cause reboot sooner
- **Return path is mandatory reboot, not in-place One UI handback**
  (`oneios-sm8850-reboot-return`), following original OneOS legacy
  watchdog writes. The first `V` may fail `EBUSY`, then retry for at
  most ten seconds; no false feeder readiness is published
- Never press Volume Up and Volume Down together while USB is attached:
  Samsung may boot into the D2 Download Mode gate

## Risk and provenance

The exact prior physical reboot smoke stopped Framework, overcame an
initial EBUSY and generated a deadline return request; Android later
reported `reboot,oneios-sm8850-reboot-return`. The operator also
encountered Samsung Download Mode and had to unplug USB and force-restart
to get back to normal One UI. **Unassisted normal One UI reboot is
not yet proven**. The legacy `a:82` watchdog is
`UNVERIFIED_REBOOT_ONLY`, NOT an independently-qualified native
handoff. This full-run is an explicit experimental risk acceptance,
not a promise of safe recovery.

The root switch refuses the full-run unless the device still holds
the previous-boot verified smoke's original marker, mode, deadline
return receipt, and expected boot reason. It also requires:
`I_ACCEPT_LEGACY_WATCHDOG_FULL_600S_RISK` passed by the host,
a complete verified image/3D-runtime stage,
`data.consumed` absent, source integrity checks, 30 GiB space reserve,
healthy One UI, required root capabilities, physical recovery helpers,
watchdog feeder and an independently armed deadline. **Nothing silently
disables SELinux, watchdog monitoring, thermal protections, or the
device-side return guard.**

## Commands on CachyOS

First update the two pinned repositories:

`git pull --ff-only origin feat/oneios-sm8850-m3q && git submodule update --init app`

### Prepare (does NOT stop One UI)

`bash scripts/phone/sm8850-full-takeover.sh prepare R5GL64LZ9HA`

This builds with `nproc` local CPU jobs; verifies native GPU 3D
xnuhost/display artifacts and hashes the current source iOS image tree
on the phone. It executes local regression tests, stage-checks the
recovery scripts (with root-owned rollback copies) and creates an
isolated one-time APFS Data clone. The image manifest is captured under
`out/sm8850/takeover/full-image-*.sha256`. A freshly generated local
manifest is source inventory, **not an independent off-device Apple
signature verification**; the previously validated trust files and
signed GPU addon remain required.

`FULL_TAKEOVER_STAGE=PREPARED` is only a staging receipt and
does not authorize launch by itself.

### Run FULL takeover (DOES stop One UI)

Only after successful prepare and with local backup/force-reboot
recovery understood:

`bash scripts/phone/sm8850-full-takeover.sh run R5GL64LZ9HA --i-accept-10-minute-legacy-watchdog-risk`

The host must print `FULL_TAKEOVER=REQUESTED` and uses ADB to
observe real guest/CPU/display status. Device-side recovery continues
independently if ADB or the USB cable fails. Expected milestones include
`FRAMEWORK_TAKEOVER=CONFIRMED`, `IOS_HOST_CPU_MASK=0-7`,
`IOS_GUEST_READY=OBSERVED`, and
`IOS_DISPLAY_FIRST_FRAME=OBSERVED` when guest and screen work.
Missing markers are **not** silently counted as success.

A timer-based return that later shows healthy One UI is recorded as
`FULL_TAKEOVER_DEADLINE_RETURN=REQUESTED_AND_ONEUI_OBSERVED`;
`UNASSISTED_RETURN_TO_ONEUI=NOT_VERIFIED` is retained because the
host cannot rule out a bootloader detour or operator force restart.
A non-zero host exit after physical recovery is not automatically
a kernel panic; inspect the session's evidence archive.

If frozen, Samsung Side/Power + Volume Down for more than seven
seconds forces a restart. Do **not** use both volume keys as the
recovery test, do not unlock Odin/D2, and do not factory reset.

## Repeat runs

The switch atomically writes the root-owned `data.consumed` marker
**before** stopping Android Framework. A failed or successful run
must not reuse that APFS clone. Retain logs and prepare a fresh
independent stage for any subsequent attempt. This release intentionally
does not automatically erase earlier image/Data snapshots.

## Remaining qualification

Full iOS on the screen is the goal of this experiment; it does not
establish robust 10-minute legacy watchdog hardware ownership,
unassisted return to One UI, Vulkan API conformance, or production
readiness. Do not claim these without physical evidence.


## 2026-11-20 first live FULL takeover: root cause and retry procedure

**Confirmed from on-device switch.log and xnuhost.log (not inferred):**
Android Framework stopped, the OneOS `V` magic close succeeded,
and an independent 600s deadline was armed. Then BusyBox rejected
a **single-file bind-remount**:

```text
oneios inner: making /data/oneios_switch.sh read-only
mount: can't find /data/oneios_switch.sh in /proc/mounts
oneios inner: ... ended with status 70
Return to One UI (switch-failed)
```

The guest never reached `xnuhost` exec; no GPU/iOS failure is proven.
This was an intentional **early reboot-return on launcher failure**,
not the 600s timeout. DirtyFrag temporary root may disappear after the
normal hard reboot, so host telemetry now falls back to unprivileged
ADB boot metadata instead of polling a missing `su` for 1000s.

The fix does **not** weaken guest isolation: it remounts the **whole
staged `/data` parent read-only**, including root-level scripts,
runtime, image and control, after isolating `/data/data` and
`/data/session` as independently writable bind mounts. Negative
write probes verify these boundaries BEFORE guest PID publication.
This approach was tested in a Linux user+mount namespace with BusyBox;
the exact Samsung BusyBox and F2FS namespace still require live evidence.

**The APFS Data clone was already marked consumed BEFORE Framework
stop. Never use it again.** The new `rearm` operation does not
re-copy the 24 image files, rebuild the image, rerun takeover, or
repeat the reboot-only smoke. When a real guest has modified the
consumed Data, rearm verifies the separate original benchmark Data seed
(two expected files, sizes, distinct single-link inode identities and
SHA-256), creates a fresh independent clone, and archives the entire
consumed guest Data and `data.consumed` record under root-owned
`.retired-data/`, together with both hashes. A separate historical
pristine archive is **not** a mandatory prerequisite; however, a hash
computed today cannot independently attest the seed's historical state.
Do not unlink the marker manually. Existing image and runtime hashes,
GPU sidecars, and watchdog configuration remain unchanged.

On CachyOS, after temporary DirtyFrag root is available again:

```bash
cd ~/projects/OneiOS
git pull --ff-only origin feat/oneios-sm8850-m3q
git submodule update --init app
bash scripts/phone/sm8850-full-takeover.sh rearm R5GL64LZ9HA
```

Expected staging-only result: `APFS_DATA_REARMED=YES`,
`SM8850_MOUNT_NAMESPACE_PROBE=PASS_NO_FRAMEWORK_STOP`,
`FULL_TAKEOVER_STAGE=REARMED` and `LIVE_FRAMEWORK_STOP=NO`.
Do not run full takeover unless that succeeds and the user
separately accepts the **still-unqualified** 600s legacy watchdog risk.

The root switch accepts the already archived, root-owned original
smoke evidence, not a fake current-boot marker; no repeated reboot-smoke
is required. It still checks the current boot reason and refuses any
unexpected firmware/root/watchdog changes.


## 2026-11-20 second rearm attempt: BusyBox one-operand remount

The local full-run regression passed **8/8**, and updating the staged
OneOS recovery scripts passed without stopping One UI. The on-device,
isolated mount-namespace probe then failed BEFORE any APFS Data copy:

```text
mount: can't find /data/adb/.oneios-m3q-upload.*/mount-target in /proc/mounts
STAGING REFUSED: Android BusyBox cannot create read-only guest stage and writable Data/session mounts
```

Root cause: both the probe and full guest `--inner` used a **single
target operand** for BusyBox `mount -o remount,bind,ro`. On this
Android BusyBox build the single-operand form looks up the target in
`/proc/mounts` and rejects an otherwise successfully bind-mounted
directory. Both now use explicit SOURCE and TARGET operands:
`mount -o remount,bind,ro "$dst" "$dst"` in the private probe, and
`mount -o remount,bind,ro /data /data` in the guest namespace.

The root-stage read-only and Data/session-writable negative write probes
remain mandatory. The next `rearm` first executes the **exact same
two-operand remount** in an unshared namespace on the phone, and after
replacing only the APFS Data clone, executes a **passive full-run
admission check** (no Framework stop). Do not claim device confirmation
until `SM8850_MOUNT_NAMESPACE_PROBE=PASS_NO_FRAMEWORK_STOP` and
`FULL_TAKEOVER_ADMISSION=PASS_NO_FRAMEWORK_STOP` appear.


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
