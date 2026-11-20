# SM8850 takeover / Return-to-Android: Gate 0

Target: Samsung SM-S948B (m3q/SM8850), firmware S948BXXS4BZIG.

**This gate is read-only.** It never stops Android Framework, writes
kernel/CPU/watchdog controls, opens a watchdog FD, or stages/boots iOS.
A passing audit does NOT independently qualify the hardware to switch.

## What was proved, and what was not

The iOS 27 guest has passed independent APFS Data-snapshot, Adreno GPU,
physical-touch SHM preview, USB detach and timeout/collect testing.
The opt-in host CPU pairing reduced mean two-way trap handoff from
26.53us to 8.38us. All of those tests left Android's Framework alive.
They do NOT establish same-boot return after stopping system_server.

The separate experimental Framework path still exists:
- `scripts/phone/sm8850-takeover.py` (host CLI)
- `app/switcher/assets/oneios_switch.sh` (OneOS)
- `app/switcher/assets/oneios_return.sh` (OneOS)

Its full guest mode currently uses **240 s, GPU 2D, 1080x2340/60Hz**,
NOT the recent native GPU-3D touch benchmark. Do not combine the
first Android Framework stop with new GPU, CPU, RAM or display changes.

## Gate 0 commands (CachyOS + authorized USB ADB)

Run from the parent repo with One UI healthy and unlocked:

```bash
cd ~/projects/OneiOS
git status --short
git submodule status app
python3 scripts/phone/test-sm8850-takeover.py -v
ONEIOS_RECOVERY_REPORT=out/recovery/takeover-gate0.json scripts/ci-local.sh recovery
python3 scripts/phone/sm8850-takeover.py --readiness --adb "$HOME/Android/Sdk/platform-tools/adb"
```

`--readiness` runs the pinned OneOS read-only `--framework-audit` and
captures service/state metadata. It writes `audit.txt`, `status.txt`
and `readiness.json` under a fresh `out/sm8850/takeover/readiness-*`
directory. It prints specific `BLOCKER=` lines and unconditionally
`LIVE_TAKEOVER_AUTHORIZED=NO` because software metadata cannot
authorize physical watchdog handoff.

To update the independent, read-only watchdog evidence:

```bash
python3 scripts/phone/s26-watchdog-attribution.py --serial YOUR_USB_SERIAL --output out/recovery/s26-watchdog-takeover-gate0.json
```

Obtain the exact USB serial from `adb devices -l`. This metadata
collector does not open/ping/close watchdog devices. Choose a new
output filename if the old report exists.

At Gate 0, **do not run** `--storage-probe`, `--prepare`,
`--recovery-smoke --confirm` or `--run --confirm`: all are
separate, state-changing operations.

## Existing OneOS Android-guest experience: relevant but separate

On this SM-S948B the owner has previously switched to ColorOS/PixelOS using
the original OneOS Android-guest path. That path is implemented by
`app/switcher/assets/oneos_switch.sh`, `guest_prepare.sh`, and
`return_to_oneui.sh`. It is not the iOS-specific
`oneios_switch.sh`/`oneios_return.sh` path tested by this gate.

The Android-guest path attempts a magic-close `V` on the legacy watchdog
node after stopping One UI and uses a separate periodic watchdog feeder.
Its default return mode is reboot (an explicitly selected in-place path
has additional preconditions). It does not require the iOS lab's
native watchdog supervisor, `GETTIMELEFT` ioctl, or signed
`watchdog.qualification` admission. Successful Android-guest switching
therefore supports the device's general feasibility, but it neither
establishes an iOS same-boot watchdog handback nor qualifies the native
supervisor.

Current physical SM8850 evidence: `system_server` has an FD pointing to
`/dev/watchdog` (`10:130`); `/dev/watchdog0` is `242:0`. No exposed
`identity`, `state`, `timeout`, `nowayout`, `pretimeout`, or `timeleft`
attribute identifies their effective driver and timing. On Linux watchdog
core, the legacy misc node may alias the numbered watchdog despite a
different character-device number; do not infer separate drivers from
different major/minor pairs. `CONFIG_WATCHDOG_SYSFS` is unset and the
presence of `softdog` does not identify the actual FD's callback. An
upstream v6.12 softdog has no `.get_timeleft` callback; verify any Samsung
differences against this exact firmware before choosing a handback
contract.

Do not require the user to reinstall an older OneOS app or search for
deleted `/data/local/tmp/oneos` logs. Work from the pinned current OneOS
scripts and the independent passive S26 attribution report. Investigate
whether the Android-guest implementation can provide a separately
qualified recovery adapter; do not copy its unbounded writes or bypass
the iOS gate merely because an Android guest returned successfully.

The Bash/mksh fake-phone fixture now injects fixture-only `cat`/`sleep`
wrappers into *copies* of the pinned production scripts. This is needed
for mksh R59, where both commands are builtins and bypass PATH test
doubles. A green fixture validates simulated scripts, not a physical
watchdog transfer. This change does not alter any device-side code.

## Blocking conditions and required closure

1. **Watchdog.** On S948BXXS4BZIG the prior passive evidence saw
   system_server own legacy /dev/watchdog at 10:130, while the numbered
   node was 242:0. The exact mapping, nowayout/stop callback, timeleft,
   released-owner state and new-framework first keepalive are unverified.
   A reviewer-qualified, firmware-matched source and timing budget is
   required. Never forge `watchdog.qualification` to bypass this gate.
2. **App cgroup drain.** The OneOS Framework probe needs readable
   `cgroup.events` and a writable `cgroup.kill` for each app group.
   Prior SM8850 observation reported missing `cgroup.kill`. Refuse until
   there is a separately tested bounded app-only fallback with proof
   that protected services remain alive.
3. **Storage.** The old stage reserves at least 30 GiB free even after
   an independent, hash-checked snapshot. Prior free-space evidence
   did not meet this once an additional snapshot was accounted for.
   Never reuse a mutable original Data inode or bypass trust hashes.
4. **Return independence.** The physical Volume Up + Volume Down 3s
   return chord, root-cgroup watcher and deadline, watchdog handback,
   same-boot return guards and a separately verified out-of-band
   stock recovery must all work independently of USB ADB.
5. **Guest/runtime alignment.** Verify the signed GPU 3D image,
   framebuffer/input handling, Data clone, expected hardware backend
   and staged ELF before upgrading the existing 2D takeover profile.

## Gate 1-5 rollout (each needs a separate approval)

- Gate 1: qualify the exact watchdog owner/timeout/handoff, solve app
  drain, verify storage, physical keys and out-of-band recovery. Run
  local Bash+mksh fake-phone fault injection, return races, feeder
  stale-but-alive, PID reuse, and absent input/watchdog tests.
- Gate 2: **recovery smoke without guest**. Only after Gate 1, stop
  Framework briefly under an independent device timer and verify
  same-boot in-place return, unlock and physical touch. A reboot is a
  failsafe, not an in-place PASS.
- Gate 3: isolated 2D takeover under the already verified 240s window,
  existing return guard and a freshly verified image.
- Gate 4: migrate the previously validated 3D GPU and physical touch
  path one variable at a time, retaining the same return contract.
- Gate 5: repeatable Android -> iOS -> Android user-facing switch after
  positive hardware acceptance and deterministic rollback.

## What counts as an in-place return PASS

- Same boot ID; original protected daemon PIDs, including adbd,
  SurfaceFlinger and the composer, remain unchanged.
- No surviving guest tasks, host mount namespace or exclusive touch
  grab; the independent watchdog has returned to its known owner with
  a measured keepalive.
- Fresh, stable system_server PID; zygote and zygote_next running;
  user 0 unlocked; input services healthy and an actual One UI
  physical tap and swipe succeed.
- Original vm.max_map_count and other guarded host state restored.
  A reboot may recover Android but does NOT count as in-place PASS.

Hardware qualification and live switches must not be inferred from
prior fake-phone or bench-only tests.
