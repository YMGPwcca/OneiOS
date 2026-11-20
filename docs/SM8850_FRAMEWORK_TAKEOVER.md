# SM8850 Framework takeover test

> **Gate 0 status (2026-11-20): NOT CLEARED.** Use the
> [read-only takeover/return readiness gate](SM8850_TAKEOVER_RETURN_GATE0.md)
> before any disruptive experiment. The watchdog device-to-driver mapping,
> timeout and first-framework-ping handback are not yet qualified, and
> the prior S26 app-cgroup drain and independent snapshot storage gates
> remain unresolved. The examples below describe a future, separately
> authorized procedure; do **not** invoke `--recovery-smoke --confirm`
> or `--run --confirm` as a shortcut. The current legacy full-run path
> still uses GPU 2D, not the validated interactive GPU 3D benchmark.


The lab profile is scoped to the Samsung SM-S948B, m3q, SM8850, fingerprint
`samsung/m3qxxx/m3q:17/CP2A.260605.016/S948BXXS4BZIG_OXM4BZIG:user/release-keys`,
and kernel `6.12.69-android16-6-pb4d3caf-abogkiS948BXXS4BZIG-4k`. It runs over
authorized USB ADB from CachyOS. The device-side assets live in the OneOS
submodule. The CLI installs a root-owned copy under
`/data/adb/oneios-m3q-framework` after a successful audit. The OneOS app
continues to use its S24-only product profile and
`/data/local/tmp/oneios`.

## Commands

Run from the repository root. With multiple attached USB devices, give
each command `--serial YOUR_SM_S948B_USB_SERIAL`.

```sh
scripts/phone/sm8850-takeover.py --dry-run
scripts/phone/sm8850-takeover.py --status
scripts/phone/sm8850-takeover.py --recovery-smoke --confirm
scripts/phone/sm8850-takeover.py --run --duration 240 --gpu 2d --confirm
scripts/phone/sm8850-takeover.py --return
scripts/phone/sm8850-takeover.py --collect
```

The smoke uses a 10-second deadline anchored after zygote and
`zygote_next` stop, `system_server` exits, Android's application groups
drain, and both input services disappear. The smoke can run without a
staged guest. The full test requires a successful smoke on the current
boot. It uses the bench binary and settings with four vCPUs, 2 GiB
prefaulted and locked RAM, software 2D GPU, shared-memory display, input,
and 1080×2340 at 60 Hz. It uses one SurfaceControl display helper with the
bench's socket mode and leaves optional hardware bridges disabled.
Guest boot time is included in the device-side 240-second window.

Both tests verify the watcher, two physical event readers, key-state poll,
wakelock and a separate monotonic deadline supervisor before stopping
Android. The deadline and watcher run in init's mount namespace and the
root cgroup, independent of ADB. The existing OneOS stop lock, stop loop,
watchdog feeder, return guard and reboot failsafe handle lifecycle and
cleanup. The guards check the liveness of the session and the recovery
helpers. In-place return keeps the original protected daemon PIDs,
restores the saved map limit, starts zygote, and checks an unlocked stable
`system_server`, service ownership, touchscreen enumeration and synthetic
input dispatch. Verify an actual tap and swipe in One UI and USB ADB
reconnection before recording a physical result.

The smoke and full run refuse if the independently qualified watchdog
plan or any recovery helper is missing. The native supervisor uses one
exclusive FD, reads capabilities and timeout, and keeps it open through
the session. The return verifies release and the new framework's
first observed keepalive under a separate bounded deadline. See the
[watchdog protocol and live blockers](SM8850_WATCHDOG_SUPERVISOR.md).

The passive audit found the legacy FD at `10:130` and a numbered node
at `242:0`. The exact mapping, actual timeout, nowayout, and recovery
timing remain unresolved. The implementation and local test phase
performed no watchdog opens, Framework shutdowns, or kernel changes
on the handset.

## Isolated image and APFS Data

The validated benchmark is at
`/data/local/tmp/oneios-m3q-ios27-bench`. Build the approved SHA-256 list
from the bench's recorded image and runtime manifests and the verified
additions for `bench/xnuhost-gui-bench`, `image/kernel.kc.trustcache`,
and `image/kernel.kc.gpuaddon`. The 44-entry list used in this checkout
is in [bench.sha256](../out/sm8850/takeover/bench.sha256). The device
agreed with all listed hashes. Keep the bench stopped while staging.

```sh
scripts/phone/sm8850-takeover.py --storage-probe --confirm
scripts/phone/sm8850-takeover.py --prepare --confirm \
  --bench-manifest out/sm8850/takeover/bench.sha256
```

Preparation tries FICLONE on two temporary files. The phone's F2FS
rejected it. The sparse-copy probe retained the content and logical
length of a 2 MiB file and used 128 allocated 512-byte blocks. The
production path uses the same helper on the root-owned snapshot. It
checks source stability, hashes, file sizes and distinct inodes, and
retains the original Data store and unique chip ID. An interruption
before the completion marker cannot admit a full run. Data and app
changes made in a full run persist in the isolated Data snapshot,
which is retained for analysis and retry.

Large benchmark files are writable through their original directory.
A read-only bind would still expose those mutable source inodes. The
profile uses a verified snapshot of the runtime, image and sidecars and
mounts them read-only inside the session. It reserves the bench's 30 GiB
free-space margin on the phone after staging. The measured free space
was only about 30.3 GiB and could not cover the independent snapshot.
The official OneOS image directory was absent.

The [no-copy design](SM8850_NO_COPY_IMAGE_ADAPTER.md) specifies
exclusive Data-store access and a verified off-device backup. It has no
live mode. The tested staging path continues to use separate inodes
and the existing reserve.

## Rollback

1. If USB ADB is available and the software return path is valid,
   `scripts/phone/sm8850-takeover.py --return` may request recovery.
   **Do not hold Volume Up + Volume Down on a USB-connected SM8850**:
   during the 2026-11-20 reboot-only experiment, that combination
   entered Samsung's `Reboot Device - D2` Download Mode gate.
   The reboot-only Framework smoke instead has a 20-second automatic
   deadline that reboots to One UI, with no in-place handback.
2. If the phone stays unresponsive and automatic recovery cannot
   complete, hold Side/Power and Volume Down for more than seven
   seconds to force restart. Release when the Samsung logo appears.
   This is an independent hardware fallback, **not evidence the
   OneiOS software key watcher succeeded**. Use **Reboot system now**
   if Android Recovery appears.
   [Samsung official forced restart instructions](https://www.samsung.com/us/support/answer/ANS10001374/)
3. Unlock One UI. Run `--status` and verify that zygote,
   `system_server`, SurfaceFlinger, the composer and adbd are running.
   Test a tap and a swipe. For an in-place return, compare daemon PIDs
   and the boot ID to `baseline.txt`. Compare `vm.max_map_count` against
   the recorded baseline. The latest passive baseline was `65530`.
   If recovery reported a map-limit mismatch, read the saved values
   before changing anything.

   ```sh
   adb="$HOME/Android/Sdk/platform-tools/adb"
   "$adb" shell -T "su -c 'cat /data/adb/oneios-m3q-framework/control/base/max_map_count; cat /proc/sys/vm/max_map_count'"
   ```

   When no guest process remains and the current value still equals
   the session's recorded temporary value, restore the first number
   from that file and read it back. For the observed baseline and
   this profile's temporary value, use this conditional command.

   ```sh
   "$adb" shell -T "su -c 'test \"\$(cat /proc/sys/vm/max_map_count)\" = 1048576 &&
     test \"\$(cat /data/adb/oneios-m3q-framework/control/base/max_map_count)\" = \"65530 1048576\" &&
     printf \"65530\\n\" > /proc/sys/vm/max_map_count && cat /proc/sys/vm/max_map_count'"
   ```

4. Export evidence with `--collect`. Once verified idle, preserve the
   experimental stage by renaming it. This retains its logs and APFS
   snapshot and removes it from the active command path.

   ```sh
   "$adb" shell -T "su -c 'mv -n /data/adb/oneios-m3q-framework /data/adb/oneios-m3q-framework-retired-\$(date +%s)'"
   ```

## Evidence and remaining risks

Start with [the local evidence folder](../out/sm8850/takeover/). A live
session would add its launch log, return log, watchdog heartbeat
records, guest log and crash output, screenshots, process evidence,
and the host's boot and recovery timeline. Confirm the 240-second timing,
the guest's usable UI and touch on the phone, and the restored One UI
before calling a full test a pass. A first contentful frame can be
the Apple logo.

The observed USB device had physical recovery inputs on event0
(`gpio-keys`, Volume Up) and event3 (`pmic_resin`, Volume Down).
The parser matched capabilities and device names. The Huawei Band
consumer-control device advertised both keys and was excluded.
During the audit, Android's two input services belonged to
`system_server`, and the protected service inventory was readable.
The device later disappeared from USB. No Framework shutdown, iOS
takeover boot or live recovery was performed. The previous bench
run supplies boot, display and touch evidence for the existing
benchmark, with Android's Framework present.

Remaining risks include the unqualified watchdog and handback timing,
locked-memory pressure under Framework takeover, storage capacity,
loss of unsaved Android app work, and actual panel/touch behavior
while the Framework is down. The prior bench and the local simulated
reboot path do not establish physical recovery.
