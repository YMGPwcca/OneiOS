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
