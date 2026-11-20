# SM8850 watchdog supervisor and handback

**OneiOS · Galaxy S26 Ultra / SM8850 · Watchdog supervisor design**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!NOTE]
> **Historical source or earlier experimental procedure.** The latest S26 Ultra full guest ran ~600.6 s with a displayed frame, but serious heat and unverified recovery remain open. Use the [physical ledger](SM8850_LIVE_STATUS_2026-11-20.md) for current decisions.

This is an experimental OneOS integration for SM-S948B / m3q / SM8850
running S948BXXS4BZIG. The native binary is built from
`app/switcher/native/oneios_watchdog.c` for Android arm64 and belongs to
the root-owned lab stage. Keep the app's product switch policy in force.
This phase used link-time fake watchdogs and isolated fake Android
Framework fixtures. It required no access to the phone.

## Feeder audit and Linux v6.12

The legacy Android-guest switch issues one-shot magic closes, then
`guest_prepare.sh` starts a feeder that repeatedly opens candidate nodes,
writes `V`, and closes them. That path serves separate handset and
Android guest profiles. The SM8850 OneiOS lab is driven by
`oneios_switch.sh` and `oneios_return.sh`. [Legacy guest feeder](../app/switcher/assets/guest_prepare.sh) · [Legacy switch](../app/switcher/assets/oneos_switch.sh)

Before this change the OneiOS feeder already had a single shell
redirection around a neutral `.` loop. The S24 product profile still
uses it. The SM8850 lab invokes the native owner, which checks the
opened descriptor, reads capabilities and timeout, and acknowledges
the actual close. It never forks, duplicates the FD, or changes
watchdog parameters.

- Upstream registers legacy `/dev/watchdog` against the watchdog-core
  data for device ID zero. Both names would then share the atomic
  single-open bit. A second open returns `EBUSY`. Open may start the
  watchdog or adopt one already running. An upstream alias rule does
  not establish the actual Samsung registration. [Linux v6.12 open and registration](https://github.com/torvalds/linux/blob/v6.12/drivers/watchdog/watchdog_dev.c#L864)
- A nonempty write clears the previous magic-close permission before
  looking for `V`, then asks the driver to ping. A driver can also
  support `WDIOC_KEEPALIVE`. The native loop uses a single neutral byte
  and accepts a heartbeat only after the write returns successfully.
  It reads `GETSUPPORT`, `GETTIMEOUT`, `GETPRETIMEOUT` and `GETTIMELEFT`
  from that same FD. The standard watchdog ioctl interface has no
  portable nowayout query. The lab requires independently verified
  nowayout metadata. [Linux v6.12 write and ioctl dispatch](https://github.com/torvalds/linux/blob/v6.12/drivers/watchdog/watchdog_dev.c#L697)
- At last file release, upstream tries to stop an active device when
  magic close was authorized or the driver has no magic-close flag.
  Nowayout blocks stopping. On a failed stop or unapproved close, the
  core attempts a final ping and clears the exclusive-open bit. The
  release callback returns success even if stopping failed. The return
  therefore checks the post-close device state independently.
  [Linux v6.12 release](https://github.com/torvalds/linux/blob/v6.12/drivers/watchdog/watchdog_dev.c#L942)
- The core worker can feed inactive devices whose hardware remains
  running when boot handling permits. It can also feed active devices
  whose configured userspace timeout exceeds the maximum hardware
  heartbeat. A zero open timeout uses an unbounded **first-open**
  deadline in the core. Successful open resets that bookkeeping.
  Neither the build option nor the deadline establishes a lease of
  any particular length after the framework releases its FD.
  [Linux v6.12 worker and open-deadline logic](https://github.com/torvalds/linux/blob/v6.12/drivers/watchdog/watchdog_dev.c#L60)
- Upstream SoftDog restarts a software hrtimer on ping and cancels it
  on stop. Its source default is 60 seconds and its module defaults
  are subject to boot and runtime configuration. Upstream v6.12
  SoftDog has no `get_timeleft` callback. The present implementation
  requires an observable remaining timeout and will refuse an
  endpoint that cannot report it. Under upstream panic semantics,
  `softdog.soft_panic=1` with `kernel.panic=0` cannot be treated as
  automatic One UI recovery. The Qualcomm pet interval is a separate
  observation. [Linux v6.12 SoftDog](https://github.com/torvalds/linux/blob/v6.12/drivers/watchdog/softdog.c#L78) · [Kernel panic policy](https://www.kernel.org/doc/html/v6.12/admin-guide/sysctl/kernel.html#panic)

## Protocol and evidence

| State | Entry and evidence |
| --- | --- |
| `FRAMEWORK_OWNS` | Stable `system_server` owns the qualified device. Record original PID, generation, target, and plan. Validate the detached watcher, deadline, readers, and wakelock. |
| `TRANSFER_PENDING` | Under the OneOS stop lock, revalidate endpoint, remaining time and recovery helpers. Mark the transfer and stop the framework. Start the native owner only once the old server is absent and zygote is down. `EBUSY` means acquisition is still pending. Retry only that error, within the three-second startup window. |
| `SUPERVISOR_OWNS` | Exactly one successful native open. Validate character-device identity, driver label, keepalive capability, exact approved timeout, pretimeout zero and a readable time-left ioctl. Publish readiness after a successful timely neutral write. Feed every two seconds. OneOS detects stale progress after five seconds. |
| `RETURN_PENDING` | The return arms an independent handback deadline **before** asking for release. The receipt is generation-, PID-, birth- and mode-bound, and is written only after close returns. The return waits until the owner is gone and verifies the appropriate device state before starting zygote. |
| `FRAMEWORK_REACQUIRED` | Observe the qualified endpoint owned by a new, stable `system_server` and a rising time-left sample while that same owner holds it. The independent review must establish that an increase in this state is attributable to a framework keepalive. Clear the handback deadline, then finish the existing OneOS stability and input checks. |

For `nowayout=0`, the qualified endpoint must advertise magic close and
its reviewed stop callback must actually stop this timer. The native owner
sends one final `V` immediately before planned close and never uses it as
a heartbeat. The return checks for `inactive`. A failed final write
attempts to clear the release permission with a neutral write and fails
the session. For `nowayout=1`, perform a final neutral write and close.
The return requires `active` and readback of at least the whole approved
handback budget plus 15 seconds. It never relies on the kernel's final
close ping to provide this margin.

The admission floors are 100 seconds configured timeout and 45 seconds
observed time remaining before the stop. The handback budget is an
independently justified 5–30 seconds covering release, framework
restart, same-owner reacquisition, and the first observed ping.
These are software thresholds. Qualification must bound stop, transfer,
I/O and fallback time on the exact firmware, including failure after
an unplanned close in either nowayout branch. A missing receipt,
unexpected native exit, failed readback or late ownership is a failed
attempt. The existing reboot path is guarded by the device and does
not depend on SSH or ADB. The 240-second guest deadline stays separate
from the short watchdog handback deadline.

## Qualification boundary

The root-only lab stage would need an independently reviewed
`watchdog.qualification` record. The host CLI does not create this
record. Its fields, in order, are:

```text
kernel-notes-sha256 softdog-build-note-sha256 supervisor-sha256 watchdogN hexadecimal-major:minor nowayout timeout-seconds handback-budget-seconds
```

The hashes bind the exact running kernel notes, loaded softdog build
note and staged native binary. The shell also verifies the exact handset
and firmware, direct numbered FD ownership, observed timeout and time
left, SELinux state, and the existing Framework recovery checks.
Treat this record as reviewer output after evidence has been collected.
A fingerprint, module symbol list, or a file with plausible values
cannot qualify a handset.

The previous passive reports and the new evidence establish a legacy
FD at `10:130`, a numbered node at `242:0`, loaded SoftDog, and Qualcomm
petting near 9.47 seconds. They leave endpoint mapping, exact callback
behavior, nowayout, timeout, readable time-left, post-release behavior,
positive framework ping attribution, and the manual recovery margin
unresolved. The direct-numbered-owner rule remains strict. The original
bench's storage reserve and all existing recovery prerequisites still
apply. Physical acceptance remains blocked. [Earlier passive watchdog audit](SM8850_WATCHDOG_ACCEPTANCE.md)

## Local verification

```sh
ONEOS_TEST_MKSH=/path/to/mksh ONEIOS_RECOVERY_WORKTREE=1 \
  ONEIOS_RECOVERY_REPORT=out/sm8850/watchdog-supervisor/recovery-working-tree.json \
  scripts/ci-local.sh recovery
```

The native test binary wraps open, stat, ioctl, write, and close at link
time. Its fake endpoint opens `/dev/null` in place of the test node.
Binaries and working-tree fixtures require the updated OneOS submodule
checkout. The default recovery mode tests the parent-pinned scripts.
Bash and mksh use an isolated fake phone to verify close-before-zygote
ordering, state readback for both nowayout branches, a new owner's ping
evidence, a stuck init request, and guarded reboot at handback timeout
without transport. See [local logs](../out/sm8850/watchdog-supervisor/).
