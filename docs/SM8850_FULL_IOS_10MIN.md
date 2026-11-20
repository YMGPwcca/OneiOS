# SM8850 full iOS 27 takeover: 8 vCPU, GPU 3D, 10-minute reboot deadline

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
repeat the reboot-only smoke. It rejects rearming if any bytes in the
consumed Data files differ from the original seed; it archives both
consumed data and its record under root-owned `.retired-data/`,
and only then publishes a new one-shot clone. The existing image
and runtime hashes, GPU sidecars, and watchdog configuration remain
unchanged.

On CachyOS, after temporary DirtyFrag root is available again:

```bash
cd ~/projects/OneiOS
git pull --ff-only origin feat/oneios-sm8850-m3q
git submodule update --init app
bash scripts/phone/sm8850-full-takeover.sh rearm R5GL64LZ9HA
```

Expected staging-only result: `APFS_DATA_REARMED=YES`,
`FULL_TAKEOVER_STAGE=REARMED` and `LIVE_FRAMEWORK_STOP=NO`.
Do not run full takeover unless that succeeds and the user
separately accepts the **still-unqualified** 600s legacy watchdog risk.

The root switch accepts the already archived, root-owned original
smoke evidence, not a fake current-boot marker; no repeated reboot-smoke
is required. It still checks the current boot reason and refuses any
unexpected firmware/root/watchdog changes.
