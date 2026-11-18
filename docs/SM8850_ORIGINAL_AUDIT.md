# SM8850 audit against the original S24 Ultra OneiOS switch/return contract

Audit started 2026-11-17. **No new device claims without a local report**.
This is a comparison and passive test harness, not authorization to boot
an iOS guest on Samsung SM-S948B / m3q / SM8850.

## Ground truth and references

- Local feature OneiOS: `YMGPwcca/OneiOS` branch `feat/oneios-sm8850-m3q`, starting audit from `bec7efec`.
- Its OneOS fork: `YMGPwcca/OneOS` branch `feat/oneios-sm8850-m3q` at `b81a6032`.
- Original S24 Ultra source: `akshaynexus/OneiOS:main` at `7b810126`, and
  `akshaynexus/OneOS:oneios` at `bdf3db05`.
- The existing submodule pin in the feature OneiOS tree is `820253bf`;
  that is **not** the OneOS feature-branch head `b81a6032`.
- The device reports OneOS APK versionName 0.5.16, versionCode 145,
  KernelSU root, and no `/data/local/tmp/oneios` stage. It remains
  in One UI with system_server running.
- Prior SM8850 results (GPU submissions, CPU, native vibrator presets,
  S Pen input and passive display probes) are in `docs/SM8850_PORT.md`.
  A prior test is not repeated merely to generate a new PASS.

## One command, passive only

```sh
cd ~/projects/OneiOS
git pull --ff-only
scripts/phone/audit-s24-preflight-m3q.sh
# To read all findings, use the path printed by the command:
# cat ~/oneios-m3q-ci/audits/<TIMESTAMP>/checks.tsv
```

With multiple ADB devices, set `ANDROID_SERIAL`. With a custom local
destination, set `ONEIOS_AUDIT_OUT`. The script refuses any connected
device whose codename is not exactly `m3q`. It uses `adb shell su` to
**read** sysfs, system properties, service registrations, input capabilities,
filesystem metadata and Android power state, and writes reports **only to
CachyOS**. It never writes to the phone, opens a test session, calls the
return script, stages anything, or plays any haptic. Treat the collected
report as local diagnostic data, not a file for a public GitHub issue.

Interpretations:
- `PASS` means this *specific, read-only predicate* passed.
- `WARN` is a deviation or a limited observation; inspect manually.
- `FAIL` is a baseline requirement not met by this snapshot.
- `BLOCKED` means cannot verify passively or without a staged image.
- `INFO` provides context, and proves nothing beyond the printed value.

A green host CI and even zero `FAIL` do **not** mean an S26 session is
safe. The strict S24 model gate is expected to be `BLOCKED`.

## Original S24 switch preflight and SM8850 coverage

This matrix is derived from
`YMGPwcca/OneOS:switcher/assets/oneios_switch.sh` at `b81a6032`
(lines 325-420 and 980-1084) and the `oneios_root.sh` stage verifier.

| Original S24 condition | Passive audit | What remains |
| --- | --- | --- |
| UID root, SHA-256 utility, SELinux | Read UID/commands/SELinux | Compare actual policy AVCs only if needed |
| Exact model SM-S928*, e3q, SM8650 | Record exact SM-S948B/m3q/SM8850; old allowlist **BLOCKED** | Never blindly bypass |
| Stage root ownership, no symlinks; pinned switch/return | Stage inventory | No OneiOS stage exists yet |
| Runtime ABI 1, non-placeholder, ARM64 ELF; full SHA list | Files and signatures when staged | Verify real runtime then; no stage now |
| Image format, manifest, image hashes, changed-file IDs | Image inventory | Kernelcache, iOS image and manifest absent |
| KernelSU/AP/Magisk BusyBox and nine specific applets; resetprop | Query paths and each applet | Need an actually executed rollback for validation |
| Init mount namespace / nsenter | Compare namespace IDs | Runner may re-enter via nsenter |
| Fully booted One UI, zygote, system_server, surfaceflinger | Read props/PIDs | Restart behavior unproven |
| No leftover OneOS/OneiOS session, stage mounts, leaked cgroup | Read current state/mounts/cgroup | Check again immediately before any switch |
| Both Volume Up/Down input capabilities | `getevent -pl` inventory | **3-second chord and key reader are not tested** |
| Battery >=30% or charging, <42 C | Read capacity/status/temp | Dynamic conditions, re-check before testing |
| At least 2 GiB free on /data | `stat -f` | A real image set needs much more |
| Writable wakelock node | Check permissions only | Actual acquisition/release not tested |
| Experimental acknowledgement | Not auto-set | Owner consent during a controlled session |

The original script explicitly stops One UI's zygote/system_server after
arming return workers; it is not a harmless diagnostic. Never run
`oneios_switch.sh --check` directly as a substitute for this audit when the
stage is absent, and never call it in switch mode on an unvalidated phone.

## Original S24 in-place return: Gate A/B/C

Source: `YMGPwcca/OneOS:switcher/assets/oneios_return.sh` at
`b81a6032` (specifically its Gate A/B/C and failsafe).

| Return mechanism | Read-only compatibility evidence | Still unverified |
| --- | --- | --- |
| Session teardown, cgroup kill, mount cleanup | Current mount/cgroup inventory | Actual teardown, D-state task evacuation |
| Gate A: same boot, no stage mounts, unchanged SELinux | boot ID only within current session; SELinux reading | Before/after equality under a session |
| Gate A: vold/keystore2/servicemanager stable | Read service states and PIDs | Uninterrupted PIDs under takeover |
| Gate A: no new mount on One UI partitions | Current mounts snapshot | Delta across a live session |
| Gate B: composer discovery and service registration | Query vendor composer and AIDL/HIDL | **Do not restart composer during audit** |
| Gate B: restarted surfaceflinger, SurfaceFlinger binder | Read process and binder | Restart without black screen |
| Gate B: audio policy, media, camera, wificond, netd | Read init service states and binder presence | Restart behavior |
| Gate B: brightness and CPU/GPU clock restoration | Read original values and nodes | Actual write/restore of each |
| Gate B: boot-loop counters restored via resetprop -n | Verify resetprop exists | Actual counter restoration |
| Gate B: USB gadget/adbd restored to baseline | Read USB props/UDC current state | USB continuity across takeover/return |
| Gate C: zygote start, system_server and user 0 unlock | Current running states; may inspect on demand | 60s+180s+20s recovery timing |
| failsafe reboot and Volume chord | Present command paths, key capability | Actual fallback is **not** triggered |
| Upstream shmem advise/restore | Read `shmem_enabled` options and current mode | Future write, round-trip restore and recovery gate |

For SM8850, the camera, display composer, watchdog, audio and thermal
implementations may differ from S24. A passive report can catch missing
services and unsupported device paths, **not certify a full restore**.
The S24 return script is designed to reboot on failed Gate A/B/C; never
assume it will return in place on an untested One UI 9.0 build.

## The original OneOS app's 14 hardware checks

Source: `OneiosChecks.kt` and `oneios_root.sh check_cmd()` on the S24
fork. The audit explicitly inventories all **14** and checks which tool
binaries are staged. It does **not** automatically invoke any active test.

| Check ID | Original test | SM8850 audit policy |
| --- | --- | --- |
| cpu | `bridgectl cpu` | Already measured in `SM8850_PORT.md`, not repeated |
| gpu | `gpuctl` nodes/routes/probe/submit | Prior device GPU PASS, not repeated |
| display | `displayctl test` overlay | Active screen test; separate consent |
| haptic | `bridgectl haptic 200 1000` | Active buzz, old evdev may fail; native HAL independently tested |
| haptic-pattern | three taps then ramp | Active, no unsolicited playback |
| audio | 440 Hz tone via audio helper | Active output; consent and volume control |
| bt | Bluetooth controller test | Requires Bluetooth off; **do not steal live controller** |
| brightness | `brightctl info` | Passive candidate, requires tool |
| levels | change panel brightness then restore | Active sysfs writes, separate controlled test |
| als | read 10s ambient sensor | May enable sensor node; separate permission |
| camera-list | NDK camera enumeration | Passive candidate, requires tool |
| camera | NDK wide camera capture | Active camera acquisition, picture stored on phone |
| camera-hal-list | experimental direct HAL enumerate | Isolated experiment; not part of Run all |
| camera-hal | experimental direct HAL capture | High-risk active vendor HAL use; defer |

The documented native HEAVY_CLICK and `haptic-native-inspect` were
already tested. Neither substitutes for a guest-originated impact.

## Upstream drift as of 2026-11-17

Verified from actual GitHub compare history:

| Upstream | Our base | New head | Missing commits |
| --- | --- | --- | ---: |
| `akshaynexus/OneiOS:main` | `9f4459b4` | `7b810126` | 25 |
| `akshaynexus/OneOS:oneios` | `c27dc02c` | `bdf3db05` | 14 |

**Candidate syncs, in safety order:**

1. **High:** OneOS `2f7516fa` and `bdf3db05`: save/restore
   `shmem_enabled` (including exact bare mode), test restoration. Adapt
   only after passive SM8850 shmem support is confirmed. Keep strict
   SM8850 switch gate until recovery is actually verified.
2. **High for later guest boot:** OneiOS `432ffd9f` / `7b810126`:
   hosted `0080-shared-region-protect.patch`, shared region / pmap
   corrections. Requires kernel/patch-series validation and prelink,
   not only a runtime package build.
3. **Medium:** OneiOS `da39094f`: include Android `oneios-tool` in
   the runtime package; review our standalone CI and package tests so
   it remains local-first.
4. **Medium:** OneiOS `fc46ae77` (uclamp ceiling removal) and
   `hostcall.h`/task changes; relevant to SM8850 6E/2P topology.
5. **Optional for image setup:** OneOS `bb1ef384`, OneiOS `1ef92a8a`:
   `oneios-tool serve`, resumed/network-aware firmware download and
   import; exercise the updated protocol under test before syncing.
6. **Later:** OneOS `7447a9df` dynamic versionCode; compare with
   installed 0.5.16 / versionCode 145 and preserve signature/data.
7. **Do NOT cherry-pick unmodified:** OneOS `8b27d358`/
   `e5004eb0`: changing S24-only refusal to a warning without
   validated S26 recovery. Also do not replace our m3q `.gitmodules`
   branch with upstream's `app/` pin or restore GitHub Actions builds.

The source trees have diverged; these are **not** safe blind fast-forwards.
First collect the read-only report, then make a separate sync branch or
reviewed selective patches; run `scripts/ci-local.sh all` on CachyOS
for every code batch. No automatic phone stage/switch in CI.

## Stop conditions

- Any missing required root/busybox/resetprop/zygote/battery/wakelock condition.
- Incorrect or unknown composer / critical One UI services.
- No verified image/kernelcache specifically prepared for the device.
- No proven S26-specific return path, including watchdog, USB and keys.
- No local reproduction of upstream changes with SM8850 test coverage.

**A PASS inventory is not a PASS boot.** The test must stop before port or
switch operations whenever any condition remains unverified.

## Actual first-pass S26 Ultra results (owner's passive report)

The owner ran `scripts/phone/audit-s24-preflight-m3q.sh` on the rooted
Samsung SM-S948B (m3q/SM8850, Android 17 SDK 37, Linux 6.12.69) while
One UI was running. The returned breakdown:

| Verdict | Count | Meaning |
| --- | ---: | --- |
| PASS | **71** | Specific passive prerequisites observed |
| WARN | **1** | `init.svc.hwservicemanager=stopped` |
| FAIL | **0** | No failed *measured* passive predicates |
| BLOCKED | **24** | Untested active/rollback tasks or absent OneiOS stage |
| INFO | **36** | Context only |

The return prerequisites observable on an idle One UI passed:
KernelSU root and its BusyBox applets/resetprop, SELinux Enforcing,
init namespace, zygote/system_server/surfaceflinger, critical services,
Binder `SurfaceFlinger` / audio / vold / installd, composer3 AIDL and
the Samsung vendor composer, volume-key capability, battery at 96%,
28.9 C, free storage over 2 GiB, wakelock and cgroup permissions.

**Findings requiring further inspection:**

- `hwservicemanager` is **stopped**. AIDL composer and the required Binder
  services are registered, so this alone does *not* establish an error.
  Inspect HIDL clients (if any) and this vendor build's service topology;
  do not start it manually.
- `/sys/class/backlight/panel` reports 0/0 while
  `panel0-backlight` reports 0/12750. These are passive sysfs values
  only; determine which path is the actual controller and how One UI
  represents current brightness before any sysfs writes.
- `sys.usb.config=adb`, controller `a600000.dwc3` reports
  `not attached`. These readings are consistent with a wireless-only
  ADB connection. A real USB cable and a later controlled session are
  needed for continuity testing.
- `shmem_enabled` lists `advise` and currently selects `never`.
  This meets the *capability* prerequisite for upstream's shmem patch,
  but does **not** prove a mode change/restore round-trip.
- Hardware inventory shows standalone diagnostic `bridgectl`,
  `displayctl`, `brightctl` but no staged `gpuctl`, `camctl`
  or `oneios-audio`. No OneiOS stage exists yet, so absence of staged
  binaries is expected and does not mean they are missing from the
  built archive. A host-side archive inventory is needed.
- The original `SM-S928*/e3q/SM8650` switch guard is **BLOCKED**,
  correctly, on `SM-S948B/m3q/SM8850`; no code should bypass it.
  OneOS APK 0.5.16 (versionCode 145) being installed is not proof of
  staging or switch support.

**Important upstream code-review finding:** at OneOS upstream
`bdf3db05`, `oneios_switch.sh` changes `shmem_enabled` to `advise`
while One UI is still up, but `oneios_return.sh` has an early-return
branch for a session that never stopped One UI *before* its shmem restore
block in Gate A. Consequently, a canceled/failed session before zygote
stop may leave the mode changed. This is a source-level potential defect,
not a confirmed S26 incident. Do not copy that implementation unchanged.
The eventual patch needs a fake-phone regression proving both the
early-return and full Gate A paths restore the **bare** original mode
(e.g., `never`), plus idempotent/no-change cases, before physical testing.

For the second passive pass, run:

```sh
cd ~/projects/OneiOS
git pull --ff-only
ONEIOS_AUDIT_OUT="$HOME/oneios-m3q-ci/audits/followup-s24-vs-m3q" \
  ./scripts/phone/audit-s24-followup-m3q.sh
cat "$HOME/oneios-m3q-ci/audits/followup-s24-vs-m3q/followup.tsv"
cat "$HOME/oneios-m3q-ci/audits/followup-s24-vs-m3q/host-artifact.txt"
```

This reads HIDL/AIDL, display backlight attributes and source paths,
USB gadget and UDC state, shmem options, keys and watchdog presence,
and the **local** package archive's binary names. It never writes to
the device or starts a session. It cannot validate return Gates A/B/C.
A PASS in this follow-up still does not authorize switch.

## Second passive S26 audit: physical key origin, display power and USB (2026-11-17)

Owner-supplied `audit-s24-followup-m3q.sh` result: **PASS=3, WARN=1,
FAIL=0, BLOCKED=5, INFO=49**. The standalone CI archive for commit
`78e4e025` passed SHA-256 and contains `bin/bridgectl`, `brightctl`,
`camctl`, `displayctl`, `gpuctl`, and `oneios-audio`. That archive
inventory does not test those tools on the live device and does not
imply a staged runtime exists.

- **Physical rescue keys, now identified:** `gpio-keys` at
  `/dev/input/event0` advertises Volume Up, and `pmic_resin` at
  `/dev/input/event5` advertises Volume Down. A connected
  `HUAWEI Band 11-F88 Consumer Control` at `/dev/input/event13`
  advertises both keys but is an **external** input device.
  The S24 `oneios_switch.sh` intentionally combines volume events
  from multiple readers using shared `control/keys/up` and `down`
  and also polls all candidate devices. Its fake-phone JUnit tests
  cover separate device readers and split-device polling: separation
  alone is **not** a regression. The existing candidate discovery,
  however, includes the external wearable; do not count the wearable
  as proof of physical recovery capability. Before enabling an m3q
  session, restrict recovery-key selection to proven physical hardware
  sources and add fake tests for a transient/disconnecting external
  input and cross-device chord. Test a *physical* up/down press while
  Android stays live; do not engage the recovery script yet.
- **HIDL:** `init.svc.hwservicemanager=stopped` remains the only
  warning. The vendor QTI composer service and Composer3 AIDL binder
  are **running/registered**, as are SurfaceFlinger, audio-policy,
  camera, networking, keystore2 and servicemanager.
  `lshal` returned no matching legacy HIDL interfaces. A stopped
  hwservicemanager alone is not proof of broken modern AIDL services,
  but any legacy bridge dependency must be inspected before runtime.
- **Brightness:** `panel` (a virtual LCD node) reads `0/0`; the
  actual qcom MDSS backlight sysfs candidate is
  `panel0-backlight` at
  `/sys/devices/platform/soc/9800000.qcom,mdss_mdp/backlight/panel0-backlight`,
  with `max_brightness=12750`. Both reported zero and the latter
  `bl_power=4` *while* `dumpsys display` reported
  `mScreenState=OFF`; that is **not** evidence of brightness failure.
  Re-read while the display is visibly awake to identify the live
  backlight path. Do not write brightness or take display ownership.
- **USB:** `sys.usb.config=adb`, `sys.usb.state=adb`,
  `init.svc.adbd=running`, controller `a600000.dwc3`, and
  `/config/usb_gadget/g1/UDC=a600000.dwc3`; nevertheless
  `/sys/class/udc/a600000.dwc3/state=not attached`.
  This is compatible with the known wireless-only ADB session, not
  proof of USB transport continuity. Attach a data-capable USB cable
  to CachyOS and recheck physical enumeration in a later read-only
  audit. Do not alter `sys.usb.*` yet.
- **Shared memory:** `shmem_enabled` is
  `always within_size advise [never] deny force`, writable as root.
  The host supports the upstream `advise` mode and currently chooses
  `never`. The mode round-trip is **not** tested; the upstream
  early-return restoration edge case remains open.
- **Watchdogs:** `/dev/watchdog` and `/dev/watchdog0` exist.
  The S24 switch closes/feeds Samsung's software watchdog after
  framework stop; presence of character devices alone proves
  nothing about identical semantics on S26. Do not open/write them
  as a read-only test.
- **Cgroups:** root `cgroup.controllers` reports `memory`,
  while root `cgroup.kill` does not exist. The S24 return has a
  per-process SIGKILL fallback where `oneios_session/cgroup.kill`
  is unavailable. This is a **recovery-path compatibility question**,
  not a reason to simulate a kill against the live system.
- **Local-CI timing:** the posted status still reported
  `78e4e025` PASS while the source was already checked out at
  `379f64a5`. This is a prior run, **not proof that 379f64a5 passed**.
  Wait for the standalone watcher to process that commit and inspect
  its own status before treating its new scripts as CI-verified.

### Remaining checkpoints before *any* m3q recovery port

1. With One UI screen visibly on, read the physical MDSS
   backlight and confirm the framework reports ON. No sysfs writes.
2. Verify one **ordinary press each** of physical Volume Up and
   Volume Down with a bounded `getevent` capture. An external wearable
   cannot be an emergency-return dependency.
3. Connect a real USB **data** cable and confirm a USB ADB endpoint,
   USB controller attachment and serial route distinct from Wi-Fi ADB.
4. Reproduce recovery watchdog/USB/key-state logic in fake-phone tests
   specific to the S26 input graph; resolve shmem early-return.
5. Build and test the relevant OneOS fork locally before updating
   the OneiOS `app/` submodule pin; do not install/debug APK or
   touch OneOS 0.5.16 until the tests pass.
6. Later, the 14 original hardware checks still include active
   display, haptic, audio, brightness, camera and Bluetooth tests.
   Run each as a separately bounded diagnostic only with suitable
   prerequisites; do not label the existing passive inventories
   as full hardware PASS. The full return Gates A/B/C cannot be
   certified without a controlled recovery exercise.

**No switch permission follows from this audit.** Keep the
`SM-S928*/e3q/SM8650` root guard and app-level m3q block until
recovery can be demonstrated independently.


## Third passive audit — screen ON, genuine volume keys, no USB cable (2026-11-17)

The owner kept One UI running and used read-only ADB commands:

- Screen **ON**: Android DisplayManager reported
  `mScreenState=ON`, `mScreenBrightness=0.33885762`.
  `/sys/class/backlight/panel0-backlight` (QCOM MDSS) changed
  from the previous screen-OFF reading of 0 to **brightness=865**
  out of max 12750, `bl_power=0`, while its
  `actual_brightness=0`. This identifies the *likely* active
  backlight control node; `actual_brightness` is not reliable
  for reporting screen power/brightness on this kernel without
  additional driver-level validation. The virtual
  `/sys/class/backlight/panel` remains `0/0`.
  Never map the framework's normalized brightness to 865/12750
  as a linear fraction, and do not write either sysfs node yet.
- **Physical Volume Up**: `/dev/input/event0` emitted one
  `KEY_VOLUMEUP DOWN` followed by `UP`.
  **Physical Volume Down**: `/dev/input/event5` emitted one
  `KEY_VOLUMEDOWN DOWN` followed by `UP`. These *individually*
  validate the genuine key event sources on m3q; they do not
  exercise the 3-second simultaneous chord or OneOS readers.
  `/dev/input/event13` is an external Huawei Band, not a
  permissible sole rescue-key source.
- A data-capable **USB cable is not available** at this
  stage. Continue read-only checks over Wi-Fi ADB while One UI
  is up; do not label USB recovery as PASS. Wireless ADB is
  not a reliable recovery path when the Android framework
  or network stack is stopped. Do not switch, attempt in-place
  return, stop zygote, or open watchdog devices until
  independent return conditions are met.

### Correct command for the next brightness probe

The SM8850 brightness README specifically warns that
**`brightctl info` is not passive**: it opens the bridge and
can write panel brightness, touch IC state or ALS enable.
Only `brightctl inspect` uses read-only sysfs access.
The owner already has a standalone diagnostic `brightctl`
at `/data/local/tmp/oneios-m3q-diag/bin/brightctl`;
confirm `inspect` support before use, or deploy the
verified current runtime binary by an explicit diagnostic
procedure. Do **not** call `info`, `levels` or `als`
during passive validation.

```sh
adb shell su -c '/data/local/tmp/oneios-m3q-diag/bin/brightctl inspect'
```

The historical OneOS hardware checklist's `brightness`
entry invokes `brightctl info`, so the app's "Run all"
is **not** safe to run indiscriminately on the unported
S26 Ultra. Tests of actual screen-writing, ALS and
camera acquisition remain separate opt-in exercises.
Keep the standalone app's 0.5.16 installation and
the original SM8850 switch guards unchanged.

## Fourth passive audit — verified backlight selection (2026-11-17)

The owner executed the already-staged diagnostic binary (not an active
brightness test):

```sh
adb shell su -c '/data/local/tmp/oneios-m3q-diag/bin/brightctl inspect'
```

Output:

```text
brightctl: passive inspect (read-only; no panel, touch IC, or ALS writes)
directory: /sys/class/backlight
node panel: max 0; brightness 0; actual 0; bl_power 0; skipped (max=0)
node panel0-backlight: max 12750; brightness 937; actual 0; bl_power 0; selected
brightctl: inspect ok (no state changes)
```

**Result: PASS for passive node enumeration and selection only.**
This also confirms the current `brightctl inspect` code chooses the
first named node with `max_brightness > 0`, which matches
`runtime/bridges/brightness/brightness.c:panel_find()` for this
device: the Samsung-style backend will skip the zero-max `panel`
and choose `panel0-backlight`; the Treble backend also lists
`panel0-backlight` first. The node reports a nonzero current brightness
(937 versus 865 in the prior ON snapshot) and `bl_power=0`.
`actual_brightness=0` still does not reflect the lit panel; do not
treat it as a valid readback for SM8850.

The passive test **does not verify**:
- writing the correct brightness levels or nits mapping;
- restore to the exact One UI brightness after a stopped session;
- touchscreen IC enable/disable semantics on m3q;
- ALS control, animation, or panel modes.

All corresponding active tests remain BLOCKED. Do not run the OneOS
`brightness` button (`brightctl info`) or `Run all` at this stage.

**Next low-impact original hardware check:** NDK `camctl --backend ndk list`
for camera metadata enumeration. This does not request capture frames,
but it *does* initialize a cameraserver client and is not strictly
passive sysfs inspection. Use only the checksum-verified local CI
`bin/camctl`, stage a temporary diagnostic file in
`/data/local/tmp` (not the OneiOS session stage), and run with a
time limit while One UI remains running. Do not run
`--backend hal list` or camera capture until NDK results have been
reviewed. The original S24 run previously enumerated cameras with
the NDK backend, but its camera IDs must not be assumed for S26.

## Fifth audit — Camera2 NDK enumeration on physical m3q (2026-11-17)

The owner used the locally SHA-256-verified runtime archive
`oneios-runtime-0.0.0-ci-arm64.tar.zst` from commit
`78e4e025`, extracted `bin/camctl`, transferred it to
`/data/local/tmp/oneios-m3q-camctl`, checked the on-phone
SHA-256 against the extracted file, and ran
`timeout 30 /data/local/tmp/oneios-m3q-camctl --backend ndk list`
with One UI's `system_server` running.

**Result: PASS for Camera2 NDK camera and metadata enumeration.**
The tool reports **7 entries**, including 3 physical members of
logical camera 0. As enumerated:

| ID | Role | Facing | Native sensor | 35 mm equivalent | Orientation | Member of |
| --- | --- | --- | --- | ---: | ---: | --- |
| 0 | wide | back | 4080 × 3060 | 23 mm | 90° | logical |
| 1 | front | front | 4000 × 3000 | 24 mm | 270° | standalone |
| 2 | ultrawide | back | 4080 × 3060 | 13 mm | 90° | standalone |
| 3 | other | front | 3056 × 2296 | 30 mm | 270° | standalone |
| 5 | other | back | 4080 × 3060 | 23 mm | 90° | physical of ID 0 |
| 6 | tele3 | back | 3648 × 2736 | 66 mm | 90° | physical of ID 0 |
| 7 | tele5 | back | 4080 × 3060 | 113 mm | 90° | physical of ID 0 |

All seven report YUV output sizes including 640 × 480 and
1280 × 720, with ranges including 15–30/30–30 fps for the
main cameras. Tele5 additionally advertises 15–25/25–25 fps.
These are enumerated camera metadata, not proof of available
simultaneous streams or of independently capturable physical IDs.

The historical S24 run in `runtime/bridges/camera/README.md`
printed only 4 listed cameras, *before* the current physical-camera
enumeration enhancement. Differences in the printed list may stem
from both hardware and tool revision, so do not claim the S24 lacks
these camera roles or that the S26 has 7 concurrently open camera
devices.

**Verified only:** NDK client initialization, logical/physical
metadata enumeration and role classification, with no frame request.
**Still blocked:** first frame, sustained capture, exact camera
permission/ownership, tele3/tele5 physical YUV stream, zoom switch,
front/back concurrent capture, native HAL capture, and iOS guest
camera frames.

### Next separately initiated low-impact active test

On a phone with One UI still running and no camera app in use,
run a **bounded single wide-camera NDK capture**, starting
with 640 × 480 / 15 fps / 10 frames. This temporarily opens
the camera and creates an image under `/data/local/tmp`.
It cannot be classified as a passive or read-only probe.
Use the already SHA-matched `oneios-m3q-camctl` executable:

```sh
adb shell su -c 'timeout 45 /data/local/tmp/oneios-m3q-camctl --backend ndk --camera wide --size 640x480 --fps 15 --frames 10 --out /data/local/tmp/oneios-m3q-camera-wide.png -v capture'
```

Before running, stop any app using the camera. Inspect the
exit code, diagnostic output and optional PNG size privately.
If the tool fails or times out, do not automatically retry
with physical tele camera, HAL direct, zoom or more frames.
Re-evaluate the actual error and binder callbacks first.
Never run this capture from unattended CI or in the
OneOS `Run all` batch, and never share a personal test
picture in a public repo.

## Sixth audit — first successful host camera stream on m3q (2026-11-17)

Owner performed the previously requested **active**, single-camera Camera2 NDK test with the checksum-verified `camctl` from the runtime artifact at `78e4e025`, while One UI remained running. No OneiOS session was started.

```sh
timeout 45 /data/local/tmp/oneios-m3q-camctl \
  --backend ndk --camera wide --size 640x480 --fps 15 \
  --frames 10 --out /data/local/tmp/oneios-m3q-camera-wide.png \
  -v capture
```

**Result: PASS, process exit code 0.** The owner-provided diagnostic log independently confirmed:

| Metric | Physical SM8850 result |
| --- | --- |
| Camera/backend | Logical camera 0, NDK |
| Open and session | Opened; 640×480 YUV_420_888 CPU-readable stream configured |
| Requested video mode | 640×480, fixed 15–15 fps |
| First frame latency | 698 ms after starting |
| Camera callback counters | 10 started, 10 completed, **0 failed**, 0 buffers lost, 0 device errors |
| Received images | 10, 0 unreadable; NV12 frames 10 read, 0 missed |
| Measured rate | 13.51 fps (sensor timestamps), 13.95 fps (read wall-clock) |
| Output | 640×480 NV12-derived PNG at `/data/local/tmp/oneios-m3q-camera-wide.png`; mean luma 124.9 |
| Teardown | `session: closed`; normal exit code 0 |

The camera backend reported `binder threads started`, one active
repeating capture request, and matching sensor timestamps in the
capture and frame callbacks. This is positive **real-phone evidence**
for the host Camera2 NDK → YUV frame → NV12 conversion → PNG route.
Earlier original-S24 testing opened the camera but got no frame;
the new result is **consistent with** the source-level binder-thread
fix now working on m3q, not a controlled S24-vs-S26 A/B experiment.

**Still unverified:** any camera other than logical wide,
1280×720/30 fps/90-frame reference Run-all mode, true image quality,
physical tele3/tele5 output, direct vendor HAL backend, concurrency,
camera availability after stopping One UI, and iOS guest camera.
Mean luma alone is not proof of a non-black image; the PNG has not
been visually inspected. Do not upload personal camera images to
public issues or CI.

### Controlled sequence for the next two lenses

After closing One UI Camera and any competing camera apps, validate
`front` and `ultrawide` independently with 10 frames at
640×480 / 15 fps, output to different diagnostic PNGs, and time
limit each command to 45 seconds. Stop immediately if one fails,
returns nonzero, times out or leaves the camera provider unhealthy.
Do **not** fall through to `tele3`, `tele5`, `--backend hal`
or multi-camera testing automatically: those are separate steps.
OneOS `Run all` remains disabled on unported SM8850.

## Seventh audit — Front and Ultrawide NDK streams on m3q (2026-11-17)

The owner ran the same **bounded active Camera2 NDK test**, one camera at
a time, on the root shell while One UI's `system_server` was running.
Both tests used `/data/local/tmp/oneios-m3q-camctl`, the previously
verified diagnostic binary, `640x480`, `15 fps`, `10 frames`, `-v
capture`, separate PNG paths, and a 45-second timeout per test.

| Metric | Front (ID 1) | Ultrawide (ID 2) |
| --- | --- | --- |
| Camera opened and session activated | PASS | PASS |
| Requested / reported mode | 640×480, 15–15 fps | 640×480, 15–15 fps |
| Capture started / completed / failed | 10 / 10 / 0 | 10 / 10 / 0 |
| Images returned / unreadable | 10 / 0 | 10 / 0 |
| Reader frames / missed | 10 / 0 | 10 / 0 |
| First frame | 330 ms | 380 ms |
| Sensor timestamp fps / read fps | 13.57 / 13.73 | 13.51 / 13.51 |
| Buffers lost / device errors | 0 / 0 | 0 / 0 |
| Mean Y | 133.9 | 119.2 |
| PNG output | `oneios-m3q-camera-front.png` | `oneios-m3q-camera-ultrawide.png` |
| Exit code | **0** | **0** |

Both sessions reported binder threads started, session active, a
`YUV_420_888` CPU-read buffer with chroma step 2, 10 successful
capture callbacks and `session: closed`. Logs show actual image
buffers, not only a successful camera open.

**Status:** NDK metadata enumeration and limited 10-frame host
capture are confirmed for three independent roles: Wide (ID 0),
Front (ID 1), Ultrawide (ID 2). This does not certify color
accuracy/image contents, camera operation after framework stop,
camera support within the guest, or opening multiple cameras at once.

### Next: original S24 OneOS camera check in comparable conditions

The OneOS source
`app-android/app/src/full/assets/root/oneios_root.sh` (fork branch
`feat/oneios-sm8850-m3q` at `b81a6032`) specifies:

```sh
camera) TOOL=camctl ARGS="--backend ndk --camera wide --frames 90 --out $CHECKS/camera.png capture" LIMIT=45 ;;
```

In the current `camctl`, the unspecified size defaults to
**1280×720** and fps defaults to **30**. On SM8850 perform the
equivalent standalone check using the already installed verified
binary, without staging an iOS image, and with a unique PNG filename:

```sh
adb shell su -c 'timeout 45 /data/local/tmp/oneios-m3q-camctl --backend ndk --camera wide --size 1280x720 --fps 30 --frames 90 --out /data/local/tmp/oneios-m3q-camera-wide-720p.png -v capture'
```

Accept **only exit 0, 90 frames, zero failed callbacks and clean
teardown** as the result for this exact configuration. A capture
at roughly 30 fps is expected from the metadata but not guaranteed.
If it fails, inspect the callbacks and camera service state; do
not silently count the earlier 10-frame PASS as the 90-frame test.
After this, separate physical Tele3 and Tele5 tests remain
pending and must not start automatically. The direct HAL route,
Bluetooth-controller ownership and OneOS return Gates A/B/C
remain **unverified / BLOCKED**.


## Eighth audit — original OneOS S24 wide-camera test reproduced on m3q (2026-11-17)

The owner completed the **exact capture mode** used by the original
OneOS `camera` hardware check: Camera2 NDK logical **wide ID 0**,
**1280×720 @ 30 fps**, **90 frames**, with a 45-second timeout.
The command ran under KernelSU while One UI's `system_server` was
still running, using the previously verified standalone `camctl`.
No OneiOS session, app installation, or vendor HAL takeover occurred.

| Metric | Observed result |
| --- | --- |
| Camera backend | `ndk` (Camera2), logical ID `0` |
| Capture mode | `YUV_420_888` 1280×720, 30–30 fps, CPU-read buffers |
| Session initialization | Camera opened, session active, repeating request accepted |
| Frames handed to reader | **90 / 90 requested** |
| Missed / unreadable frames | **0 / 0** |
| Capture callback counters at stop | **91 started, 90 completed, 0 failed** |
| Buffer loss / device errors | **0 / 0** |
| First frame after start | **335 ms** |
| Sensor timestamp rate | **29.46 fps** |
| Reader wall-clock rate | **29.35 fps** |
| Converted frame | NV12 1280×720, last sequence 90, mean luma 142.4 |
| Output | `/data/local/tmp/oneios-m3q-camera-wide-720p.png` |
| Cleanup | NDK session reported `session: closed` |
| Command exit code | **0** |

**Verdict: PASS for the original OneOS S24-style NDK Wide capture
configuration, reproduced on the Samsung S26 Ultra.** The 91st
`started` callback is not itself an error; the test exits upon
receiving 90 frames, so an additional capture can be in flight at
teardown. There are no failed capture callbacks or lost buffers.
The measured ~29.35 read fps is close to requested 30. The owner
provided logs, not the resulting PNG; visual image correctness is
still unverified.

Previously passed m3q captures: Wide, Front and Ultrawide at
640×480 / 15 fps / 10 frames each (individual clean exits).

### Next bounded optical-path test — Tele3 only

The m3q enumeration identified camera `6` as a **physical**
`tele3` member of logical camera `0`. The current
`backend_ndk.c` deliberately opens the logical parent, but
creates a **physical capture output** using
`ACaptureSessionPhysicalOutput_create(window, "6", ...)`.
This differs from the proven plain YUV stream path. A physical
camera advertising YUV output sizes does not guarantee this type
of physical-only capture session will be accepted.

After closing all apps actively using camera, perform **one**
`tele3` test at 640×480/15 fps/10 frames, timeout 45 seconds,
using the same verified standalone diagnostic:

```sh
adb shell su -c 'timeout 45 /data/local/tmp/oneios-m3q-camctl \
  --backend ndk --camera tele3 --size 640x480 --fps 15 \
  --frames 10 --out /data/local/tmp/oneios-m3q-camera-tele3.png \
  -v capture'
echo "Exit code: $?"
```

**Stop and report** if configuration fails, image callbacks do not
arrive, the camera service disconnects, or the command times out.
Do **not** automatically fall back to `--zoom 3`, try direct
`--backend hal`, or proceed to Tele5 without reviewing the
independent Tele3 result. A physical-output rejection can be a
camera HAL policy/stream limitation, not a hardware failure.

Even when the host Wide test passes at 720p, **camera after One UI
framework stop and inside XNU remain untested**. The S26 return
Gates A/B/C, USB transport continuity, Bluetooth ownership,
display brightness writes and the original OneOS active audio/HAL
checks also remain unverified.

## Ninth audit — physical Tele3 stream succeeds on SM8850 (2026-11-17)

The owner explicitly ran a **bounded active** Camera2 NDK Tele3 capture
after the S24-reference wide test. This used the previously verified
standalone `camctl` with `--backend ndk --camera tele3
--size 640x480 --fps 15 --frames 10 -v capture` under KernelSU
with One UI's `system_server` running and a 45-second timeout.

| Metric | Actual m3q result |
| --- | --- |
| Requested role | `tele3`, physical camera **ID 6** |
| Camera device opened | Logical parent **ID 0** for physical ID 6 |
| Output configuration | **Physical** `YUV_420_888` / 640×480 / CPU-read |
| Repeating request | Accepted, 15–15 fps, preview template |
| Session | Active, later closed normally |
| Capture callbacks | **10 started, 10 completed, 0 failed** |
| Frame output | **10/10** NV12 frames, 0 unreadable, 0 missed |
| Buffers lost / device errors | **0 / 0** |
| First frame | **562 ms** |
| FPS (sensor / reader) | **13.53 / 13.81** |
| Last PNG | `/data/local/tmp/oneios-m3q-camera-tele3.png`; mean luma **144.5** |
| Exit status | **0** |

**Verdict: PASS** for the physical-camera NDK output path on
the Tele3 sensor. This is stronger than merely enumerating physical
camera 6: the code's `ACaptureSessionPhysicalOutput_create()`
route opened logical camera 0, configured the physical stream,
and delivered actual buffers. The log confirms the session
stopped without lost buffers or device errors.

**Not proven:** PNG image quality or lens exclusivity by a visual
inspection, sustained tele operation, zoom transitions, Tele5,
direct vendor-camera HAL, operation with One UI's framework stopped,
or guest-iOS camera support. No fallback to `--zoom 3` was
required to receive Tele3 buffers in the tested configuration.

### Next bounded optical-path test — physical Tele5 (ID 7)

The metadata inventory identifies **Tele5 ID 7** as another
physical child of logical ID 0, with 113 mm 35-mm-equivalent focal
length. Test it **independently**, using the same conservative
parameters as Tele3: 640×480, fixed 15 fps, 10 frames and a
45-second timeout. Run only while One UI is active and no app
is occupying the camera.

```sh
adb shell su -c 'timeout 45 /data/local/tmp/oneios-m3q-camctl \
  --backend ndk --camera tele5 --size 640x480 --fps 15 \
  --frames 10 --out /data/local/tmp/oneios-m3q-camera-tele5.png \
  -v capture'
echo "Exit code: $?"
```

Any nonzero exit, unsupported physical stream, missing images or
timeout is a **STOP**, not a reason to immediately try `--backend
hal`, `--zoom 5`, another camera or session takeover. Examine
the camera callback logs first. After Tele5, return to the remaining
original OneOS S24 hardware-check matrix (audio, display,
sensors, Bluetooth) rather than treating camera-only successes
as completing the S26 port.

## Tenth audit — physical Tele5 NDK stream succeeds (2026-11-17)

The owner separately ran the already-verified `camctl` on the rooted
SM-S948B with One UI's `system_server` still running. The **active**
test selected `--backend ndk --camera tele5 --size 640x480
--fps 15 --frames 10`, with verbose callbacks and a 45-second
timeout; the PNG was retained privately on the phone.

| Item | Verified |
| --- | --- |
| Capture route | Logical camera **ID 0** opened for physical camera **ID 7** |
| Stream | One **physical** `YUV_420_888` output, CPU-read 640×480, fixed 15–15 fps |
| Camera callbacks | **10 started / 10 completed / 0 failed** |
| Images | **10/10** received, 0 unreadable, 0 reader misses |
| Buffer loss / device errors | **0 / 0** |
| First frame | **314 ms** |
| Sensor/read FPS | **13.50 / 13.65** |
| Last output | NV12 640×480 sequence 10, mean luma 134.1 |
| PNG | `/data/local/tmp/oneios-m3q-camera-tele5.png` |
| Teardown | `session: closed`, exit code **0** |

**Verdict: Tele5 physical NDK stream PASS.** The tested NDK route
opens the logical camera and uses a physical output for ID 7, and
successfully receives buffers; no fallback to wide zoom 5 or direct
HAL was necessary. Lens optical quality and guest operation remain
unverified.

### Combined Camera2 NDK coverage on S26 Ultra

| Camera role | ID | Mode | Frames | Result |
| --- | --- | --- | --- | --- |
| Wide | 0 | 640×480, 15 fps | 10/10 | PASS |
| Front | 1 | 640×480, 15 fps | 10/10 | PASS |
| Ultrawide | 2 | 640×480, 15 fps | 10/10 | PASS |
| Tele3 | 6, physical of 0 | 640×480, 15 fps | 10/10 | PASS |
| Tele5 | 7, physical of 0 | 640×480, 15 fps | 10/10 | PASS |
| Wide — original S24 check | 0 | 1280×720, 30 fps | 90/90 | PASS |

In addition to the five expected lens roles, enumeration
advertised ID 3 (another front-facing `other`) and physical
ID 5 (`other` rear member of 0); **neither was captured**.
Do not conflate seven enumerated IDs with seven tested streams.

**Remaining camera scope:** visual correctness, extended capture
under load, unknown camera IDs 3/5, direct camera HAL enumeration
and capture, simultaneous streams, One UI stopped and iOS guest.
These are separate from the original S24 `camera-list` and
`camera` checks, which now have equivalent host PASS evidence.

### Next original S24 check: speaker-only AAudio

`OneOS:app-android/app/src/full/assets/root/oneios_root.sh`
defines `audio` as `bridgectl audio $R/oneios-audio` (20-second
limit). Unlike camera enumeration, this deliberately plays a quiet
tone. The current `bridgectl` implements a 440 Hz tone for 2 s
then 660 Hz for 0.5 s, with no microphone unless `record` is
supplied. `oneios-audio` may attempt low-latency AAudio MMAP
exclusive output and may temporarily alter audio focus/routing;
avoid running during calls, alarms, media playback, or recording.

Use the **same checksum-verified** local CI runtime artifact to stage
both `bin/bridgectl` and `bin/oneios-audio` as standalone
diagnostic binaries to unique `/data/local/tmp` paths. Check both
phone SHA-256 values before executable use. Run a 25-second bound
and inspect the helper's output, actual listening confirmation and
exit code. Do not include `record` yet, do not start the
disruptive Bluetooth controller test and do not run OneOS
`Run all`. Keep the OneiOS session stage absent and the
SM8850 switch gate unchanged.

## Eleventh audit — original S24 speaker AAudio check (physical SM8850, 2026-11-17)

The owner staged a **matched pair** of `bin/bridgectl` and
`bin/oneios-audio` from the same local-CI runtime package
at commit `78e4e025`. The package SHA-256 check passed.
Both files were transferred as standalone diagnostic executables
under `/data/local/tmp`; owner-side host-vs-device SHA-256
checks succeeded before invocation. The original OneOS
speaker check was run through KernelSU, One UI running:

```sh
timeout 20 /data/local/tmp/oneios-m3q-audio-bridgectl \
  audio /data/local/tmp/oneios-m3q-oneios-audio 2
```

**Outcome:** application exit **0**, speaker backend opened,
PCM submitted, normal helper socket closure. **Not a complete
audio-quality / low-latency PASS.** The owner's audible
confirmation was not provided with the log.

| Observable | Result |
| --- | --- |
| Output configuration | 48000 Hz / 2 channels, low latency accepted |
| AAudio data path | MMAP **exclusive**, burst 96 frames (2 ms), buffer 576 / 6144 frames |
| Scheduling | SCHED_OTHER, configured writer uclamp.min 512; no AAudio data callback |
| Pre-tone probe | **FAIL**: no timestamp during 1.5 s; parent reports `I/O error` |
| 440 Hz periods | **400 / 400** sent (2 s); helper 96000 in / 96000 played |
| 660 Hz segment | Helper 24000 in / 24000 played (0.5 s) |
| Helper's first-run underruns | **2**, second run **0** |
| Dropped frames / overflows | **0 / 0** in reported segments |
| Raw AAudio XRun counter | **389**, unchanged in all three later reports |
| Buffer target and queue | Target **80 ms** / AAudio queued ~**82–86 ms** |
| Estimated output latency | **82–86 ms**; e2e about **83–86 ms** during tone |
| Shutdown | `oneios-audio: socket closed: exit`; exit **0** |

**Interpretation from current source** (`runtime/bridges/audio/aaudio_helper.c`):
1. The log's `389 xruns` comes from the **cumulative current**
   `AAudioStream_getXRunCount()` in `out_report()`, not 389
   additional errors at every reported STOP. Since it remains 389
   for the 440 Hz report, 660 Hz report and final closure, no new
   XRuns are observed *between those snapshots*. The log does not
   expose the counter at the end of probe / first START, so precise
   onset remains unconfirmed.
2. `open_stream()` issues asynchronous
   `AAudioStream_requestStart()` **before** `start_dir()`
   creates the writer and before any explicit output prefill.
   Android's AAudio documentation recommends pre-filling an
   output stream before starting it. This is a concrete
   startup-underrun hazard; it has **not** been isolated as the
   sole cause of the observed XRun count.
3. AAudio's writer increases `target` by **5 ms** for
   each XRun increment until **80 ms**, and the same control
   responds to internal ring underruns. The first PCM START
   reuses the stream opened by `AU_PROBE` and resets statistical
   counters, **not** the raised `target`. Hence initial probe
   underruns can contaminate the real audio segment's latency
   and cause the intended 5-ms MMAP floor to rise to 80 ms.
4. The pre-tone probe requires at least one successful
   `AAudioStream_getTimestamp()` after `getFramesRead() > 0`
   during a 1.5-second window. On timeout, it returns 0; the
   parent `br_audio_probe_latency()` maps that 0 to `-EIO`.
   Thus the printed `I/O error` is a **probe measurement
   failure**, not evidence of audio frame write failure.
   Timestamp availability may depend on asynchronous START
   completion or vendor MMAP behavior; error codes and
   stream state are **not currently logged**.

**Proposed host-only regression before a runtime fix:** fake
AAudio stream that produces XRuns or unavailable timestamps during
`AU_PROBE`, then starts real PCM, checking the target's
initial value, cumulative-vs-delta XRun reporting, asynchronous
START readiness and the accuracy of the probed latency.
Never treat a probe failure as a successful latency result or
silently publish an unmeasured value. Fix and test without changing
the SM8850 switch gates.

### Next controlled A/B on One UI: non-MMAP baseline (speaker only)

Compare with the already staged, checksum-verified pair by
launching a new helper process with
`ONEIOS_AUDIO_MMAP=off ONEIOS_AUDIO_PERF=none`.
These are inherited environment settings of the standalone
helper; `AAudio_setMMapPolicy(NEVER)` applies in its process.
This avoids changes to global `setprop`, audioserver restart,
and vendor ownership. Keep the same 2-second 440 Hz and
0.5-second 660 Hz test; do not enable microphone `record`
or an unattended batch.

```sh
adb shell su -c 'ONEIOS_AUDIO_MMAP=off ONEIOS_AUDIO_PERF=none \
  timeout 20 /data/local/tmp/oneios-m3q-audio-bridgectl \
  audio /data/local/tmp/oneios-m3q-oneios-audio 2'
echo "Exit code: $?"
```

Compare path/mmap, timestamps/probe, XRun count, first segment
underruns, queue/target, endpoint latency, cleanup and whether
the user actually heard two tones. If legacy also fails,
inspect provider state and timestamps before patching.
If legacy is healthy, isolate and test MMAP exclusive
start/prefill before making a production default change.
No iOS guest run or framework stop is authorized by this test.

## Twelfth audit — Legacy AAudio A/B and shared silent-probe failure (2026-11-17)

The owner explicitly repeated the **speaker-only** original OneOS audio
test on SM8850 using the same pair of checksum-verified standalone
`bridgectl` / `oneios-audio` diagnostics, setting process-local
`ONEIOS_AUDIO_MMAP=off ONEIOS_AUDIO_PERF=none`.
No Android audio-system properties were changed and One UI remained up.

| Measure | MMAP exclusive (previous trial) | Legacy mixer (current trial) |
| --- | --- | --- |
| Output | 48 kHz stereo | 48 kHz stereo |
| Performance requested / given | Low latency / low latency | None / none |
| Path | Exclusive, mmap=1 | Shared, mmap=0 |
| Burst | 96 frames, 2 ms | 1920 frames, 40 ms |
| Output buffer after open | 576/6144 frames | 3120/5760 frames |
| Pre-tone probe | **no timestamp, no latency measured** | **no timestamp, no latency measured** |
| 440 Hz periods | 400/400 | 400/400 |
| Helper input accounted for | 96000 frames | 96000 frames |
| Helper underruns | 2 first segment, 0 second | 0 first and second |
| AAudio XRun raw counter | 389 on all 3 reports | 0 on all 3 reports |
| Adaptive target | 80 ms | 20 ms |
| AAudio estimated queued output | 82–86 ms | 184–192 ms |
| Estimated end-to-end during PCM | 83–86 ms | 187–193 ms |
| Cleanup / shell exit | Clean / 0 | Clean / 0 |

Legacy's mixer reports regular pulls of **1920 frames every ~40 ms**.
It reported `slips +0/-900` in the first tone: the helper's
drift-control output resampled a total of 900 fewer output frames
(18.75 ms at 48 kHz), **not** 900 capture or buffer losses. The
helper's `played` count measures ring input consumed before
resampling, so it does not independently demonstrate all 96000
PCM frames reached the physical speaker unchanged. Neither log
is a substitute for the owner's audible confirmation.

**Narrowed conclusion:** the capture/PCM pathways are functional at
the host API level in both configurations. MMAP exclusive was
~105–110 ms lower latency than Legacy in the reported windows but
had serious startup XRun/target inflation; Legacy reported zero
XRun/underruns but much higher output queue latency. **Both** fail
the `AU_PROBE` early timestamp measurement. This is a
shared initial-probe lifecycle problem, not proof of a global
vendor absence of timestamps: `pipeline_frames()` yielded
end-to-end measurements during real PCM playback.

Source analysis: `probe()` skips calling
`AAudioStream_getTimestamp()` whenever
`AAudioStream_getFramesRead() == 0`; when no valid samples
arrive within 1.5 seconds it reports only
`no timestamp` without distinguishing lack of consumption
from timestamp return error or stream START timing.
Android's AAudio NDK documentation specifies
`AAudioStream_requestStart()` is asynchronous, and
timestamps are only valid in STARTED state. The helper
also starts the AAudio stream before explicitly pre-filling
the buffer, a possible startup underrun cause. Neither
has yet been proven to be the sole trigger on m3q.

### Diagnostic-only follow-up, not a playback behavior change

The fork's `runtime/bridges/audio/aaudio_helper.c` now logs
`framesWritten`, `framesRead`,
`AAudioStream_getXRunCount()`, final
`AAudioStream_getTimestamp()` return code and adaptive
target **only when the probe fails**. The test fake AAudio
can simulate a stream that consumes silence but refuses
timestamps, asserting `AU_LATENCY=0` and that real
PCM can start afterward. The additional logging changes
no audio scheduling, buffer sizing, timestamp fallback,
frame transfer or default backend.

**Local validation required:** run the existing
`runtime/bridges/tests/test_audio_helper.c` host suite
and CachyOS local-CI build at this commit before
transferring any new helper onto the phone.
The previously installed phone binaries are unchanged
and still have the earlier limited probe logging. Until
the new probe diagnostics have been tested on the S26,
do not change the production default or claim an audio
latency is certified for the guest.

### Local-CI acceptance and fake-process isolation (2026-11-17)

The user independently ran `JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci`
on CachyOS at commit `3f4dc133`. **PASS**: 20,323 fake-AAudio
checks, 0 failed; 14,076 XNU host checks, 0 failed; runtime,
display, camera, encoder, link, package and remaining tests passed.
The signed-out ARM64 runtime-only package is at
`out/release/oneios-runtime-0.0.0-ci-arm64.tar.zst` with verified
SHA-256 `1b183698b0b0cfeef3c63e063c7fe605beab710a2d0f818e4f31b6076a901a9a`.
No iOS guest session was run.

Review of the new fake-AAudio failure-case log found `iOS is told
15 ms` after an intentionally unmeasured probe. This was a **host
test-harness isolation leak**, not evidence that a fresh production
helper had fabricated a latency: multiple fake helpers share static
`told_frames` in one test process, whereas production starts a new
helper OS process. The test now resets `told_frames` in
`helper_up()` and asserts it remains zero both on failed
`AU_PROBE` and after subsequent normal PCM playback with no
`AU_TOLD`. The production helper and its staged binary are
unchanged by this follow-up; **re-run the host audio test** on the
new commit to accept the test-only correction.

The previous run also demonstrated, in the controlled fake HAL,
`AU_PROBE` returned no measurement when its synthetic timestamp
was unavailable even after 73k+ frames were written/read; subsequent
PCM playback succeeded. This does **not** prove the same root cause
on the Samsung HAL. The new production diagnostic already emits
written/read counters and timestamp status on probe failure, so
the next device A/B test is to run only the updated `oneios-audio`
from the SHA-verified archive, with the same `bridgectl`.

## Thirteenth audit — startup prefill root-cause candidate and local fix (2026-11-17)

The owner's independent local regression at `199362ef` passed
**20,325 checks, zero failed**, and the checksum-verified new
`oneios-audio` diagnostic was run on the physical SM-S948B.
The MMAP exclusive output stream reports burst **96 frames**,
buffer **576 frames**, and this **pre-tone probe**:

```text
written 480, read 0, xruns 0,
timestamp status -895 (AAUDIO_ERROR_INVALID_STATE), target 10 ms
```

With real PCM afterward, the stream works but the raw cumulative
XRun count rises to **390**, the adaptive buffer target reaches
**80 ms**, and tone-time estimated latency is **82–85 ms**.
No iOS session was started. The exact speaker audibility has
not been independently confirmed.

**Evidence-backed diagnosis:** output `requestStart()` was called
**before any silence prefill**. The writer then held only its
target 10 ms (**480 frames**), fewer than the output buffer
size (**576 frames**), so `FramesRead` was still zero at
the end of probe. The last timestamp request returned
`AAUDIO_ERROR_INVALID_STATE`; this does not demonstrate
that SM8850 lacks timestamp support. The legacy path's
advertised buffer is similarly larger than its initial
silence target. Android NDK's AAudio guidance explicitly
recommends filling output buffers with non-blocking writes
**before** `AAudioStream_requestStart()` to avoid underruns.

**New candidate runtime fix:** `open_stream()` pre-fills the
already chosen output stream with digital silence up to its
advertised AAudio buffer size, using a finite number of
`AAudioStream_write(..., timeoutNanos=0)` calls, then invokes
`AAudioStream_requestStart()`. If prefill is incomplete,
the output start is refused rather than silently treating
a blocked output as healthy. Microphone startup and the
SM8850 model/switch/recovery gates are unchanged.

**Added host regression:** a fake HAL that stalls output
until a full buffer has been primed *before* the start
request, for both MMAP exclusive and Legacy. The test
checks the normal AU_PROBE latency answer, actual
`FramesRead` progress, reuse of the same stream when
the guest starts PCM, and clean stop. This fake model
reproduces the mechanism suggested by the SM8850 logs
but is **not proof of Samsung's internal AAudio code**.

**Status:** patch written and reviewed, **not yet accepted**.
Run `make -C runtime/bridges build/host/test_audio_helper`
plus the ASAN host test first, then the CachyOS
`scripts/ci-local.sh all` packaging pipeline before
running a newly built standalone helper on m3q.
Keep the previous on-phone executable untouched for A/B.
Do not authorize live iOS switching or framework stop.

## Fourteenth audit — prefill scope and AAudio queue accounting corrected (2026-11-17)

Owner's first CachyOS ASAN host-test run on `7cf70ce7` returned
**20,423 checks, 3 failed**. The fake MMAP and Legacy `AU_PROBE`
strict-start tests **did** achieve complete prefill (672/672,
2800/2800 frames) and measured latency, but old **non-probe**
Legacy drift tests failed `net` expectations (line 400/401)
and MMAP latency-stage test failed its lower e2e bound
(line 678). The script stopped before local ARM64 packaging
and no `7cf70ce7` binary was deployed to the S26 phone.

Two distinct regressions were found in the code:

1. **Over-broad prefill change:** output `requestStart()`
   prefill was applied to every AU_START, unintentionally
   changing the start threshold, ring level and drift timing
   of existing sound-playback tests. Prefill is now an
   **explicit scoped option for AU_PROBE only**. The
   normal AU_START still uses its previously tested start
   path. The separate strict-start fake MMAP/Legacy tests
   still exercise prefilled AU_PROBE then reuse the stream.
2. **Wrong AAudio frame timeline:** prefill writes silence
   directly to AAudio *before* `start_dir()` reset
   `d->frames=0`. The timestamp position included that
   initial silence while `pipeline_frames()` used only
   subsequent writer frames. This made its queue/latency
   estimate clip to zero; it explains the fake-test
   mismatch where ~11 ms of marker queue existed but
   helper e2e was ~1 ms. The counter now initializes from
   `AAudioStream_getFramesWritten()` after open, so the
   prefill is included in the timestamp coordinate system.

New fake-host assertions verify the normal AU_START is not
prefilled, and that a successfully prefilled probe includes
those frames in `out_dir.frames`. Test diagnostics print
the signed drift-slip total and starting/ending margin
without weakening or deleting any original drift or
latency thresholds.

**Still pending:** a second local ASAN and full CachyOS CI
run of this correction; a successful fake test never proves
Samsung's audio-service implementation. No active phone
test, direct HAL takeover, Android framework stop, iOS
guest start or S26 switch-gate changes are included here.

## Fifteenth audit — accepted local CI for scoped audio-prefill fix (2026-11-17)

The owner checked out exact commit `4dd7242c97a265863b2a523b7832190af08704ee` on CachyOS
and ran an ASAN/UBSAN host audio regression, followed by the full local build
`JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci` **only after the audio test passed**.

- Audio test: **20,432 checks, 0 failed**.
- Legacy drift checks: `+0 ppm net +181`, `-2000 ppm net -663`,
  `+2000 ppm net +1308`; all retained thresholds passed.
- MMAP drift checks: `+0 ppm net 0`, `-2000 ppm net -1149`,
  `+2000 ppm net +1131`; all retained thresholds passed.
- Full local CI: **PASS**, Android ARM64 package built successfully,
  all ELF dependency checks passed with 0 failures.
- Produced runtime-only artifact:
  `out/release/oneios-runtime-0.0.0-ci-arm64.tar.zst`
  (831955 bytes).
- Verified complete archive SHA-256:
  `dc87a3bc16e3249af04ad228b15d6413719a23b90b63027bb656adfa95c956c5`.
- Outer command exit code: **0**.

**Verdict:** scoped AU_PROBE prefill and accounting change has passed fake-AAudio
host regression and the full CachyOS local build, but is **NOT YET validated
on the physical SM8850 audio service**. The previous Samsung MMAP exclusive
trial with the unprefilled `3f4dc13` helper logged `written 480, read 0`,
`AAUDIO_ERROR_INVALID_STATE`, 390 cumulative XRuns and an adaptive target of
80 ms. This baseline must not be overwritten.

**Next step (optical/audio host only):** extract `bin/oneios-audio` from
the SHA-verified new archive, push it to a unique path under
`/data/local/tmp`, verify phone-side SHA-256 matches the extracted binary,
and run one `bridgectl audio <new helper> 2` with a 20-second timeout.
Keep One UI's system_server running and all competing audio apps closed.
Inspect whether the first `speaker prefill: N/N` line precedes
`AU_PROBE`, whether `read` advances and probe succeeds, and whether
MMAP XRun count and adaptive target remain near baseline or improve.
A newly measured probe latency on the phone is stronger evidence than
the fake-HAL acceptance, but is not evidence of guest-iOS audio.
Do not change default audio routing, switch/return gates or framework.

## Sixteenth audit — host audio prefill works; residual XRun/latency inflation (2026-11-17)

A single owner-initiated speaker-only trial on rooted SM-S948B used the
checksum-verified runtime package built from `4dd7242c`,
SHA-256 `dc87a3bc16e3249af04ad228b15d6413719a23b90b63027bb656adfa95c956c5`,
and deployed **only** `bin/oneios-audio` to the distinct path
`/data/local/tmp/oneios-m3q-audio-prefill4dd7242`. The original
standalone `bridgectl` was reused; no iOS guest/framework switch,
microphone or global audio policy change occurred.

| Check | Previous diagnostic (3f4dc13) | Prefill (4dd7242) |
| --- | --- | --- |
| Output | MMAP exclusive, 48 kHz stereo, 96-frame burst, 576-frame buffer | Same |
| Explicit silence before START | No | **576/576 frames** |
| AU_PROBE | **FAIL**: written 480/read 0; timestamp invalid state | **PASS**: 480 frames (10 ms) |
| First 440-Hz segment | 400/400 guest periods | 400/400 |
| Writer ring underruns | 2 | 1 |
| Raw cumulative AAudio XRun count | 390 | **18** |
| Adaptive target at first STOP | 80 ms | **80 ms** |
| PCM-time estimated end-to-end | 83–86 ms | **84–86 ms** |
| Cleanup & shell status | Closed / 0 | Closed / 0 |

**Verdict:** explicit prefill repaired the AU_PROBE measurement and
the initial output-start starvation symptoms in this trial.
The residual output-latency inflation is **not fixed**; 18 raw
XRuns were present at the first 440-Hz STOP, and no new XRuns were
observed between the three STOP snapshots. Exact XRun onset
during AU_PROBE vs the 440-Hz segment cannot be determined from
this log alone. A single trial also cannot prove an across-run
percentage improvement. Audible speaker confirmation remains open.

The successful 10-ms probe is a **pre-tone latency estimate**
derived while the helper's adaptive target was low. It is not
the same measure as the later 84–86-ms guest-tone end-to-end
estimate. On this standalone diagnostic, `bridgectl audio`
prints `oneios-audio-latency=480 in a session` but does
**not call** `br_audio_told()`; therefore the helper reports
`iOS is told not known` as expected. This is not a probe
regression or a guest iOS result.

The current writer has *two* paths to raise target by 5 ms,
capped at 80: observing an increase in cumulative AAudio
`getXRunCount()`, or a ring underflow with the guest
running. In the first case one observed **increase** can
represent multiple raw XRuns; the log only reports snapshots.
The target-decay policy waits 20 seconds of stable operation
per 5-ms decrease (subject to guest-period lateness), much
longer than the 2-second + 0.5-second diagnostic. Do not
interpret 80-ms target as a persistent hardware floor.

### Next change: bounded opt-in startup tracing only

To distinguish when the inflation occurs, the next commit adds
`ONEIOS_AUDIO_TRACE_STARTUP=1`, off by default:
- snapshots after successful AU_PROBE and before the first
  guest `AU_START`, with actual written/read, XRun and target;
- up to **48** in-memory XRun / ring-underrun events captured
  inside the existing writer's lock, including stream-relative
  time, target before/after, guest_on, priming, queue and
  frame counts;
- print these events only on control-thread AU_STOP / teardown,
  not inside the writer's hot loop.

Playback buffer sizing, target logic, latency calculation,
AAudio mode, PCM content and SM8850 safety gates are unchanged.
The fake-AAudio strict-prefill test activates trace output to
exercise the event and snapshot paths. **Do not deploy the new
instrumented binary until a fresh ASAN host test and full
CachyOS local CI pass**. If device trace confirms all residual
XRuns occur in the AU_PROBE-to-first-tone transition,
then isolate with a targeted regression; do not raise the
minimum latency or disable XRun accounting without proof.

## Seventeenth audit — cause of MMAP startup target inflation and coalescing regression (2026-11-17)

The owner ran the exact `9bd0541` host audio test (20,432 checks,
**0 failed**), and the full CachyOS local CI (**PASS**). They
SHA-verified and installed the standalone trace helper on rooted
SM-S948B without stopping One UI, running one bounded speaker-only
`bridgectl audio` session with `ONEIOS_AUDIO_TRACE_STARTUP=1`.
The host trial ended normally with exit code **0**.

**Exact physical-phone observations:**

- MMAP exclusive, 48 kHz stereo, burst 96 frames, 576-frame buffer.
- Full `576/576` silence prefill; `AU_PROBE` successful: **480
  frames (10 ms)**, with **0 XRuns**, 10-ms target, no trace events.
- Immediately before the first guest `AU_START`: written 1056,
  read 576, XRun 0, target 10 ms, `guest_on=0`.
- First tone: 96000/96000 frames input/played, 1 ring underrun,
  **18 cumulative AAudio XRuns**, no dropped frames.
- Exactly **19 recorded events**, **0 trace overflows**.
  The XRun counter rose from 0 to 18 during the approximately
  **0.2–0.5-ms window after guest START**, while target climbed
  **10 -> 80 ms**, followed by a stable 83–85-ms output queue.
  Every reported event had ring=0; the last recorded queue
  value was 96 frames. The original trace did not capture
  total guest PCM received at each event, so it did not
  alone prove whether the first PCM period had arrived.
- The second (660-Hz) tone, 0.5 seconds, delivered 24000/24000
  frames with no additional events, XRuns, underruns or drops;
  target remained at 80 ms (20-second default decay prevents
  recovery during this short test).

**Mechanism:** the current writer adds **5 ms adaptive target for
every observed increase** in the AAudio XRun counter, and another
5 ms for an internal ring underrun. In AOSP's
`AudioStreamInternalPlay.cpp`, the MMAP free-running path can
increment `mXRunCount` on successive `processDataNow()` passes
when its read pointer outruns available written data. A burst of
rapid client iterations does not necessarily represent an equal
number of separate hardware-buffer intervals; the SM8850 log
shows 18 increments in under 1 ms, with a burst nominally 2 ms
long. Samsung's own vendor implementation has not been inspected.

**Bounded candidate fix:** raw XRun and internal-underrun counts
remain fully visible, but both adaptive target-raising paths
use one shared 5-ms (*one guest period*) spacing between target
increases. This permits gradual response to sustained starvation
while preventing one rapid output-start episode from driving
10 -> 80 ms. The host fake test injects **18 synthetic reports plus
one ring underrun within 0.38 ms** and asserts only one 5-ms
target increase; another report at +6 ms must raise it again.
Existing drift, latency, microphone and switch-gate tests remain.

The opt-in trace now includes **received PCM frame count** per
event (to determine whether the guest has sent its first
period), and uses a ring-lock-protected guest START timestamp,
so the displayed time is explicitly `t_guest`, not
stream-open-relative. It logs only on the control thread.

**Not yet accepted:** this policy change requires independent
host regression and full local CI on CachyOS, and the same
one-off device test before recommending a production default.
If device XRun count remains high but playback latency stays
near 10–20 ms, the raw XRun issue still requires investigation:
do not represent a lower buffer target as proof of glitch-free
speaker output. One UI/system_server, recovery gates, direct
HAL and iOS guest are untouched.

## Eighteenth audit — audible S26 speaker PASS, startup coalescing accepted (2026-11-17)

The owner confirmed on the physical rooted Galaxy S26 Ultra SM-S948B that
the standalone audio diagnostic **actually emitted both sounds**:
the long `tiiiiiiiii` 440-Hz tone and the short `títtt`
660-Hz tone. This is direct human confirmation of audible
speaker output, beyond HAL acceptance and PCM accounting.
It does **not** independently establish that there are no pops,
clicks, short glitches or dropouts.

The owner pulled exact branch commit
`c4d9e318fd06e55e3495852342ba0b6c8a8e1670`
and ran ASAN/UBSAN `test_audio_helper`:
**20,422 checks, 0 failures**. The full
`JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci` also passed;
all 6 dynamic ELF dependency checks and ARM64 packaging
passed. Produced artifact: `oneios-runtime-0.0.0-ci-arm64.tar.zst`,
832765 bytes, verified SHA-256
`91e46a70890d3979539837420305dd2f7a516c1885c30340a74f69297d4abc2b`.

The owner staged only checksum-matched
`bin/oneios-audio` at
`/data/local/tmp/oneios-m3q-audio-coalesce-c4d9`,
reusing the existing standalone `bridgectl`, and executed
one 20-second-bounded, **speaker-only** test on One UI.
No mic capture, system_server stop, global audio policy
changes, direct HAL takeover, session stage or iOS guest were
attempted. Exit code **0** and helper socket cleanup normal.

| Observation | Earlier diagnostic 9bd0541 | New c4d9e318 |
| --- | --- | --- |
| Pre-start speaker prefill | 576/576 frames | **576/576 frames** |
| AU_PROBE | 480 frames / 10 ms, PASS | **480 frames / 10 ms, PASS** |
| MMAP exclusive 48 kHz stereo | yes | yes |
| Raw AAudio XRun count | 18 | **18** (unchanged) |
| Internal ring underrun | 1 | **1** (unchanged) |
| Adaptive target after first tone | **80 ms** | **15 ms** |
| Estimated helper end-to-end, first tone | 84 ms | **21 ms** (max 22) |
| Estimated helper end-to-end, second tone | 85 ms | **20 ms** (max 21) |
| Guest PCM 440 Hz | 96000/96000 frames, 0 dropped | 96000/96000 frames, **0 dropped** |
| Guest PCM 660 Hz | 24000/24000 frames, 0 dropped | 24000/24000 frames, **0 dropped** |
| Listening verification | Not yet reported | **YES, both long/short tones audible** |

**Exactly 19 events**, no trace overflow, all within about
**0.1–0.8 ms of first `AU_START`**, and after the first
**240 input frames**: 18 raw AAudio XRuns plus 1 ring
underrun. The first XRun raised target 10 to 15 ms; all
remaining events in the same starvation window kept it at
15 ms. There were no new events during the second tone.
All 3 remaining STOP reports preserved XRun count 18.
This shows the coalescing logic prevents overreaction to a
single startup burst but does not eliminate the underlying
startup XRun / underrun itself.

**Acceptance:** the original OneOS S24 `audio` **speaker
check** is now **host PASS on SM8850**, with the explicit
startup-XRun limitation. The 10-ms `AU_PROBE` is a
pre-tone estimate; 20–21-ms end-to-end is an estimate
from the helper's AAudio clock/timestamps, not an
external acoustic latency measurement. `iOS is told
not known` in standalone `bridgectl` is by design
because it does not send `AU_TOLD`. The audio guest
bridge in an actual iOS session, microphone audio,
repeated-trial glitch rate, latency under load,
return/restore behavior and recovery remain **untested**.

**Safety-next:** do not repeat more speaker-only experiments
simply to chase zero startup XRuns when audible and output
latency have been validated once. A separately authorized
`bridgectl audio <helper> 2 record` can check the
microphone (2-second capture summarized only by count,
peak and RMS, not saved as an audio file); keep the
standalone process bound with timeout and One UI up.
The original OneOS S24 audio checklist tests only
speaker output; mic is an additional audit. Other
open original checks (display overlay, LED/ALS writes,
Bluetooth controller ownership, direct camera HAL)
retain their independent safety gates and must not
be silently invoked by a batch/Run-all action.

## Nineteenth audit — independent SM8850 microphone capture functional PASS (2026-11-17)

The owner ran a separate microphone test with the *already verified*
standalone audio binaries under One UI on rooted Galaxy S26 Ultra
SM-S948B. Only the existing /data/local/tmp diagnostic helper
`oneios-m3q-audio-coalesce-c4d9` and `oneios-m3q-audio-bridgectl`
were invoked; no new binaries installed. One UI `system_server`
availability was checked, the command had a **20-second timeout**,
and the `record` flag explicitly authorized the 2-second
microphone test:

```sh
timeout 20 /data/local/tmp/oneios-m3q-audio-bridgectl \
  audio /data/local/tmp/oneios-m3q-audio-coalesce-c4d9 2 record
```

| Observable | Result |
| --- | --- |
| Speaker prelude | 440-Hz 96000/96000 frames and 660-Hz 24000/24000 frames; cleanup normal |
| Speaker probe | 480 frames / 10 ms, pass |
| Speaker MMAP target/estimate | target 15 ms; output end-to-end approx 20 ms in both tones |
| Speaker initial conditions | 18 cumulative raw XRuns, 1 ring underrun, 0 PCM drops; no growth in second tone |
| Microphone backend | AAudio, 48000 Hz mono, performance NONE, SHARED, non-MMAP |
| Input AAudio device ID | 22 (identifier only; hardware microphone route not independently mapped) |
| Input buffer/burst | 2880/2880 frames, 960-frame burst |
| Parent `bridgectl` read | **94320 frames** in a 2-second wall-clock loop (98.25% of nominal 96000) |
| PCM signal | peak 751, **-32.8 dBFS**; RMS **-47.4 dBFS**, after skipping first 250 ms |
| Helper `oneios-audio` read | **95280 frames**, 397 periods sent, **0 reported send losses**, **0 short reads** |
| Shutdown | `microphone stopped`, `speaker stopped`, `socket closed: exit`, `ok`, shell exit **0** |

**Framing of PASS:** The native AAudio input stream opened, read real
(nonzero) PCM, transferred hundreds of 240-frame packets and closed
without error. The mic path is **functional on the Android host**.
No waveform was saved; only aggregate count, peak and RMS were
printed. This does not establish recognizable voice, capture
quality, device-22 physical mic identity, echo cancellation,
full-duplex audio, sample-perfect continuity or any guest-iOS
audio behavior.

**Accounting gap is understood but not yet diagnosed:** helper
`reader()` logs 397 packets x 240 = **95280 frames** sent with no
socket send failure; `bridgectl audio` consumed 393 packets x 240
= **94320 frames** by the end of its 2-second loop. That is
**four 240-frame packets (960 frames, 20 ms)** between the two
counters; the helper total is itself three packets (720 frames,
15 ms) below the 96000-frame ideal. In source,
`runtime/bridges/tools/bridgectl.c` ends its receiving loop
at the wall-clock 2-second limit and immediately calls
`b->stop(false)`; `runtime/bridges/audio/backend.c`
has no post-stop PCM drain. Thus frames still in transit / queued
at the stop boundary are a plausible explanation; the evidence
does **not** prove internal microphone lost samples. Do not
silently report sample-accurate 96000/96000 or alter recording
behavior for this bounded functional test.

**Milestone:** original OneOS hardware `audio` speaker check PASS
and **additional microphone host input functional PASS**.
Original S24 checks with potential One UI side effects remain
separately gated: display overlay/layer, haptic legacy pattern,
brightness levels/ALS writes, Bluetooth HCI Reset / controller
ownership, and direct vendor Camera HAL. The independent wired
recovery and full SM8850 switch/return acceptance are **not
verified**. Keep original switch guard closed; do not run all
hardware checks as a batch or stop Android framework.

## Twentieth audit — passive ALS / Bluetooth / OTG, first HEVC device failure (2026-11-17)

Owner ran the next standalone hardware checks on the rooted SM-S948B
with One UI active; these are **not** an iOS guest session.

- **USB-C OTG storage:** Android VolumeManager reports
  `disk:8,80` and `public:8,81 mounted 4E21-0000`, alongside
  existing private/emulated volumes. This is PASS for removable
  storage enumeration/mount, **not** USB data-cable ADB,
  adbd continuity or a rescue boot path.
  `sys.usb.config=adb`, `sys.usb.state=adb`,
  controller `a600000.dwc3`, `init.svc.adbd=running`,
  `/sys/class/power_supply/usb/online=0` were observed.
- **ALS:** identified the named `als_rear` at
  `/dev/input/event6` with `enable=1`. An 8-second
  event read produced no sample, so **device discovery PASS,
  live sensing not yet verified**. The multi-line form
  `adb shell su -c '...'` triggered KernelSU
  `Argument to option 'c' missing` at the start of each
  block; some subsequent statements executed as ordinary
  shell commands instead of under su. A single quoted
  remote command (`adb shell "su -c 'timeout 8 getevent
  -lt /dev/input/event6'"`) is needed to repeat the
  bounded read unambiguously. Do not run `brightctl als`:
  that command opens the active backlight/ALS bridge and
  may write panel, touch IC and sensor enable nodes.
- **Bluetooth:** `hwservicemanager=stopped`,
  `/dev/hwbinder` symlinks to binderfs, and
  `service list` registers the modern AIDL service
  `android.hardware.bluetooth.IBluetoothHci/default`,
  plus Bluetooth audio/ranging/vendor and framework
  Bluetooth manager services. `lshal list -i` showed
  `android.hardware.bluetooth@1.0::I*/* (... -qti)` as
  an implementation-library entry, **not a verified live
  HIDL `IBluetoothHci/default` instance**. The current
  production `runtime/bridges/bt/hci_hidl.c` requires
  `android.hardware.bluetooth@1.x::IBluetoothHci/default`
  over HWBinder and so must not be assumed compatible.
  Controller ownership and HCI Reset remain BLOCKED while
  One UI Bluetooth runs. A separate AIDL bridge/preflight
  is needed, not a direct `bridgectl bt` call.
- **HEVC encoder:** the latest SHA-verified local CI
  archive provided `bin/encctl`, deployed via unique
  path and SHA-matched between host/device. On
  `encctl hevc 256 256` the real MediaCodec backend
  opened a session (32-MiB pool, 2 slots) but the command
  returned **0 access units, 0 bytes, keyframe false,
  0 accounted errors, exit 1**. This is an encoder
  **output FAIL**, not proof HEVC hardware is absent.
  H.264 was **not run** because the shell had `set -e`.

**Source review:** `encctl.c` ignored some returned V4L2-IOCTL
statuses (capture/output QBUF, both STREAMON, STOP) and
`media_device.c` ignored the result of the backend's
`drain()`. The NDK implementation may return
`-EAGAIN` when no input buffer is available for the
EOS marker; such a result is not equivalent to successful
end-of-stream. The host test with a stand-in backend
delivers CAPTURE data **before** issuing STOP, unlike
the phone diagnostic, which issues STOP immediately
after input QBUF. This timing difference is a candidate
mechanism, **not a confirmed root cause**.

**Next commit scope:** strictly improve the
phone diagnostic's status checking and event+frame
accounting; log the backend drain acceptance status
without changing drain retry, encoder timing,
format, or codec selection. Do not mask 0 output
with another codec/default or count an opened
MediaCodec session as success. Gate updated ARM64
diagnostic behind fresh local host regression and
full CI. Run HEVC first and only later, separately,
H.264 if independent failure analysis warrants it.

## Twenty-first audit — both HEVC and H.264 stage frame; no coded output (2026-11-17)

The owner ran the hash-checked standalone diagnostic from
`ece3da2dd349d61434ba7620c6ac2b6104ba738e` on
rooted SM-S948B with One UI still running.

- HEVC 256x256: MediaCodec backend opened session 1, 32-MiB pool,
  `drain request accepted (rc 0)`, `frames_in=1`,
  `frames_out=0`, `errors=0`; one OUTPUT `DQBUF`
  index 0, bytes 0, followed by a **5-s event timeout**,
  0 CAPTURE access units and nonzero shell exit.
- H.264 640x480: exactly the same sequence and failure.
  The two codecs were run independently. No output frame
  or EOS event was seen in either.
- This demonstrates that the V4L2 command layer accepted
  input and the NDK backend returned 0 from
  `AMediaCodec_queueInputBuffer()` and
  `AMediaCodec_queueInputBuffer(... EOS)` (via the
  `drain rc 0` path). It **does not** prove either
  hardware codec created or returned encoded output.
- The test's early EOS order differs from the host
  fake test, which obtains the first coded CAPTURE
  buffer before requesting STOP. Whether that is
  causally important to Samsung Codec2 is unknown.
  No MediaCodec vendor error code, chosen component
  name, or repeated output-dequeue count has yet
  been captured.

**Next bounded change:** add opt-in
`ONEIOS_ENCODER_TRACE=1` tracing to the Android
`backend_ndk.c` only, with the chosen codec name,
accepted input format, feed/EOS statuses,
output-format notifications and a poll summary at
1, 1000, 2000 ... calls. The trace does not change
format, input bytes, queue ordering, drain behavior,
worker priority or timeout. Do not deploy until
a fresh host encoder regression and full local
CachyOS CI have passed. If the 5-second test
still shows only `TRY_AGAIN_LATER` output events,
collect bounded Android Codec2/MediaCodec logcat
errors before attempting a format/rate or drain-order
fix. Avoid blaming hardware encoder support on
the current evidence.

**ALS follow-up:** root quoting was corrected and
`id` showed uid 0 (KernelSU context); an 8-second
`getevent -lt /dev/input/event6` completed with
exit **124** and no sensor events. The device
`als_rear` exists and reported `enable=1`,
but active light-sensor reporting on that node
remains **unverified**. Do not write the node's
`enable` property or call active `brightctl als`
while One UI is running. Investigate the Sensors
HAL's front ambient-light sensor separately with
passive sensorservice inventory.

## Twenty-second audit — Qualcomm HEVC no-output trace; live front ALS inventory (2026-11-17)

The owner deployed the SHA-verified `encctl` from the
`ba16b8ca8fb85c58135b23447c5a52b7306ccd2d`
diagnostic package to a new standalone path
`/data/local/tmp/oneios-m3q-encctl-ba16b8` and ran the
bounded `ONEIOS_ENCODER_TRACE=1` HEVC 256x256 test on
rooted SM-S948B, with One UI and `system_server` running.
The pasted output only contains the **HEVC trace**: the
shell's `set -e` stopped the enclosing command after
the failed HEVC test; no new H.264 trace was attached.

- `AMediaCodec_getName` selected **c2.qti.hevc.encoder**
  (status 0), NOT a software encoder.
- `AMediaCodec_configure` and `start` both returned
  0; accepted format was **256x256 NV12 color-format 21**.
  The requested encoder mode was constant quality
  (bitrate-mode CQ = 0), a potential vendor-specific
  compatibility variable that has not yet been tested.
- The first input buffer was dequeued at index 0;
  **98304 NV12 bytes**, PTS **1000000 us**, were queued
  with status 0. Input EOS was queued at index 1 with
  status 0, and bridge `drain request accepted (rc 0)`.
- `dequeueOutputBuffer(..., timeoutUs=0)` reported
  **TRY_AGAIN_LATER** at each observed poll,
  including polls 1, 1000, 2000, 3000 and 4000.
  No `INFO_OUTPUT_FORMAT_CHANGED`, buffer-changed
  notice or output-buffer index was observed;
  `frames_out=0`, `errors=0`.
- One V4L2 **OUTPUT** DQBUF for index 0 occurred;
  this only recycles the submitted input buffer,
  **not** an encoded CAPTURE buffer. The guest
  event loop timed out after five seconds;
  `0 access units, 0 bytes, key=0`. The test failed.
- Cause remains **unresolved**: the result cannot
  establish a hardware encoder defect, because
  both input-queue success and accepted EOS occur
  before Codec2 produces a coded frame. Unlike the
  PC fake-encoder test, the phone harness sends EOS
  immediately after feeding just one frame.
  Further Android-side Codec2 diagnostics are
  needed before changing CQ mode, input packing,
  timing or sequencing. The earlier H.264 no-output
  test at `ece3da2d` remains recorded separately.

**Passive ALS discovery:** `dumpsys sensorservice`
revealed actual front Sensortek **STK33F15** sensors:
standard `android.sensor.light` handle **0x33**
(active, 250 ms sampling) and Samsung automatic-
brightness light sensor handle **0x673** (active,
50 ms sampling, privileged permission). Samsung
vendor extensions for light IR and CCT were listed.
The rear **STK6DAX Rear ALS**, handle **0x01000001**,
is a different sensor of type `bio_alc` requiring
`com.samsung.permission.HRM_EXT`; it is not the
front ambient light input used for One UI display
brightness. The prior `/dev/input/event6`
`als_rear` test produced no events while enabled.
Sensorservice's reported active listeners confirm
framework registration, **not** that fresh numeric
lux values were captured by our bridge. Current
`runtime/bridges/brightness/brightness.c` Treble
path explicitly lacks a Sensors HAL client;
it can only fall back to rear evdev ALS.
Consequently, S26 **front ALS -> OneiOS guest
auto-brightness is NOT implemented or PASS**.

**Safe next evidence:** inspect existing, bounded
`logcat` entries for `CCodec`, `Codec2`,
`qti`, `VIDC` around the HEVC test; do not
clear Android's log buffers. Query the STK33F15
front sensor's recent event values from a bounded
`dumpsys sensorservice` excerpt, without enabling
or disabling sensors. Do not send Bluetooth HCI
reset, write screen brightness, start an iOS
session, or replace the sensor HAL without a
separate host-gated plan.

## Twenty-third audit — front ambient-light numeric samples PASS; unrelated logcat excluded (2026-11-18)

The owner supplied read-only Android `dumpsys sensorservice` output
from rooted SM-S948B with One UI running:

- **Front STK33F15 Light Ambient Light Sensor Non-wakeup**:
  the "last 50 events" history contained timestamped samples
  at 2026-11-18 09:29:17–09:29:20 (local phone time):
  **114.01, 113.00, 111.98, 113.00, 114.01, 115.02,
  114.01, 116.98, 117.99, 116.98, 116.03, 115.02,
  114.01, 100.98, 95.99**. These are *real, variable,
  time-stamped front ALS values* reported to Android
  sensorservice, rather than only device enumeration or
  active listener registration. Mark the **Android host
  front ALS data path PASS**; do not infer that the
  guest OneiOS brightness bridge has a Sensors HAL
  consumer. Its existing Treble path still lacks one.
- The rear `als_rear` / `STK6DAX` at
  `/dev/input/event6` remained silent in the
  previous bounded 8-second evdev test. That is a
  separate sensor and route and is **not PASS**.
- The owner's `logcat -d ... | grep -iE
  'CCodec|Codec2|c2\\.qti|MediaCodec|vidc|venus|venc|encoder'
  | tail -n 180` output contained mostly
  **c2.android.aac.decoder**, an unrelated **audio
  decoder** around 09:29:38. An isolated
  `Codec2-ComponentInterface: We have a failed config`
  line was adjacent to that AAC decoder, not
  causally tied to `c2.qti.hevc.encoder` or
  `c2.qti.avc.encoder`. **Do not attribute**
  the video encoding failure to it.
- The earlier targeted `ba16b8ca` video trace
  confirmed `c2.qti.hevc.encoder` configure,
  start, 98304-byte NV12 input, and input EOS
  succeeded, while output returned
  `TRY_AGAIN_LATER` on >4000 polls with no
  output-format change, CAPTURE frame or output
  EOS. The root cause is still **unknown**.
- Android MediaCodec's public end-of-stream contract
  expressly permits a *separate empty input*
  marked EOS after the last valid frame; its
  timestamp is ignored. Therefore the earlier
  "one input frame then immediate EOS" hypothesis
  is **not sufficient to declare a harness defect**.
  If Qualcomm exhibits a vendor-specific delay,
  it needs direct runtime evidence.

**Next bounded diagnostic:** record a **fresh live
logcat** (do not clear global logs) in parallel with
one `ONEIOS_ENCODER_TRACE=1 encctl hevc 256 256`
run. Preserve logcat with exact timestamps and
filter by `c2.qti.hevc.encoder`, `Codec2`,
`CCodec`, `VIDC`, `VENC`, `OMX`, vendor
codec service name and test process PID/time.
`tail -n 180` of all generic MediaCodec matches
buries the relevant run under background AAC
activity. Keep the test `timeout 30`, keep
`system_server` running, and preserve the
original exit code. No direct HAL takeover,
framework stops or guest start.

## Twenty-fourth audit — live Codec2 log pins native Binder pool gap (2026-11-18)

The owner captured a bounded live `adb logcat` alongside
`ONEIOS_ENCODER_TRACE=1 encctl hevc 256 256`, using
the SHA-verified standalone `encctl` on rooted
SM-S948B with One UI / `system_server` still running.
The 40-MB raw log contains ~290,000 lines, mostly
historical noise; the *relevant run* is 2026-11-18
**09:37:10.364 to 09:37:16.233 local time**. Test
process **PID 5727**, Qualcomm vendor C2 service
**PID 2120**.

Evidence in chronological order:

- At 09:37:10.364, *before* codec creation, **PID
  5727** reported `Binder Thread Pool max thread
  count is 0` for media.player; same for
  media.resource_manager and the AIDL
  `android.hardware.media.c2.IComponentStore/default`.
  `BpBinder: Linking to death ... no threads ...
  listening to incoming transactions` was explicitly
  logged against `IComponent` at 09:37:10.420.
  The standalone `encctl` program does not call
  `ABinderProcess_startThreadPool()`; unlike a
  framework-launched Android app it has no
  pre-existing Binder callback pool.
- At 09:37:10.426, the C2 query reported
  bitrate-mode 3 initially; at 09:37:10.438,
  configured bitrate-mode became **7** inside C2;
  the public MediaCodec output format later showed
  `bitrate-mode = 0` (requested CQ), bitrate
  **262144**. These are *different abstraction-layer
  parameter values*; do not assume they are
  numerically interchangeable. Color-format 21 was
  requested, and CCodec internally logged
  `android._color-format = 2141391876` while
  Qualcomm `QC2Buf` reported
  `unsupported color format` at 09:37:10.486.
- At 09:37:10.492 and 09:37:10.499, Qualcomm
  `QC2PipelinedEntity` reported
  `BufferTracking pipelineid=103 failed to
  queueInputs, err 38` (Linux ENOSYS) for
  `hvcE_612`; its components also logged
  `Few parameters failed to configure`.
  These vendor-side faults occurred **before** the
  test timed out, not only at shutdown.
- At 09:37:10.490, `CCodec` was RUNNING with
  15 initial input buffers; both the 98304-byte
  NV12 feed and empty-EOS queue returned status 0
  from the NDK API. The test made >4000
  nonblocking output polls without any encoded
  frames, output-format change or output EOS,
  then returned **exit 1** after a 5-second event
  timeout.
- At 09:37:16.225–09:37:16.233,
  `Codec2-AIDL-BufferTypes` reported
  `registerSender error 4`, corrupted work item,
  AIDL transaction failed, then
  `unlinkToDeath ... DEAD_OBJECT`. These were
  at/after standalone process shutdown, so
  they may be a **consequence**, not the
  initiating failure. No causal assertion yet.
- Historical crashes in the `-b crash` log
  were from 2026-11-16 and concerned
  `app_process64` / third-party
  `com.aidc.immortal.DaemonEntry`
  `ClassNotFoundException`; they must not be
  conflated with this HEVC trial.

**A/B hypothesis:** absent native Binder threadpool
can leave incoming AIDL callbacks/death handling
unprocessed (AOSP says client processes must
start one if they require callbacks); it is
technically plausible as a cause of no-output.
But the separate Qualcomm `QC2Buf`/BufferTracking
errors also make unsupported NV12 layout,
CQ configuration or vendor behavior plausible.
Do **not** mark root cause as resolved.

**Diagnostic commit scope:** add explicit, opt-in
`ONEIOS_ENCODER_BINDER_POOL=1` handling only to
`runtime/bridges/encoder/encctl.c` main
(entrypoint), link `-lbinder_ndk` only for this
diagnostic executable. This does not modify
production helper `oneios-encoder` or any
codec configuration, input pattern, EOS timing
or worker queue behavior. Compare the same
HEVC testcase with and without the opt-in,
only after passing CachyOS host encoder tests,
full local CI, ARM64 packaging/ELF checks
and SHA-matched device deployment. If still
failing, investigate color/layout and vendor
queueInputs error separately with controlled
one-variable tests.

**Restore/safety gate:** One UI, ADB, system_server
and host recovery must remain intact. No
full iOS guest, switch, Bluetooth HCI ownership,
backlight writes or HAL stop.

## Twenty-fifth audit — correct platform Binder header build failure (2026-11-18)

The owner pulled `614945580ecda63bcd7b9848287e78e136063bfa`
and ran the local CachyOS encoder test + full CI,
without deploying or running any new phone binary.

- `make -C runtime/bridges/encoder test`: **69/69
  host checks PASS**.
- Full `JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci`:
  **FAIL** while compiling the ARM64 `encctl.c`,
  `fatal error: 'android/binder_process.h' file not
  found`. Consequently the encoder Android build,
  `runtime/build.sh`, and `package.sh` also
  failed, and the CI exited **1**. This is a
  *compile/toolchain mismatch introduced by the
  previous diagnostic commit*, not a phone GPU,
  MediaCodec, or Binder failure.
- Confirmed from AOSP source that
  `android/binder_process.h` is located under
  `frameworks/native/libs/binder/ndk/include_platform`
  (a platform implementation header, not NDK r28's
  public API-30 sysroot). Linking it directly via
  `-lbinder_ndk` also risks relying on a
  non-NDK-exported platform symbol.
- **Remedy:** remove the platform header and the
  `-lbinder_ndk` link from `encctl`.
  When and only when
  `ONEIOS_ENCODER_BINDER_POOL=1`, use NDK-public
  `dlopen("libbinder_ndk.so", RTLD_NOW|RTLD_LOCAL)`
  and `dlsym()` to locate the two platform Binder
  process functions. Keep the library handle
  resident while Binder threads run. If loading
  or symbol resolution fails, **fail closed** with
  an explicit `error:` message, not a fake PASS
  or fallback. The default test performs *no*
  Binder library load. Production
  `oneios-encoder`, MediaCodec settings,
  frame/EOS order and worker remain untouched.
- This is an **experimental platform-internal
  diagnostic**, not a public API for a production
  Android application. Verify Android ARM64
  compilation and package ELF/API-30 checks on
  CachyOS **before** deploying; then A/B the same
  HEVC case with and without the opt-in, reporting
  both shell exit codes and logs. The phone
  test remains unverified on this corrected code.

## Twenty-sixth audit — real Qualcomm HEVC A/B PASS with native Binder pool (2026-11-18)

The owner pulled `16f74797e748b940eb54937e5ca0fceef079fd8b`
on CachyOS and reported local `make -C runtime/bridges/encoder
test` **69/69 PASS**, `JOBS=8 ./scripts/ci-local.sh all
0.0.0-ci` **PASS**, SHA-verified runtime artifact and
**0 failures** in 6 dynamic ARM64 ELF checks. The helper
and `encctl` compiled without platform Binder headers.

The exact same SHA-matched standalone `encctl` binary
was then tested twice on rooted SM-S948B with One UI and
`system_server` running. Only
`ONEIOS_ENCODER_BINDER_POOL` differed:

- **OFF = 0 (baseline):** `c2.qti.hevc.encoder`
  configured/started and queued one 98304-byte
  256x256 NV12 frame + EOS (both queue statuses 0);
  **4,000+ output polls returned not-ready**; no
  output-format change, coded CAPTURE or EOS;
  5-s event timeout; **exit 1**.
- **ON = 1 (experimental Binder pool):**
  `ABinderProcess_setThreadPoolMaxThreadCount(2)`
  and `ABinderProcess_startThreadPool()` succeeded;
  same `c2.qti.hevc.encoder` and exact frame size,
  mode (CQ=0), color format 21, EOS sequencing.
  The NDK codec reported **one output-format change**
  with `csd-0`, then:
  **79 bytes** codec config (`flags 0x2`),
  **10454 bytes** keyframe (`flags 0x1`) and
  **0-byte output EOS** (`flags 0x4`).
  The guest virtio-media test saw corresponding
  **CAPTURE 79+10454 bytes**, with NAL 32 (VPS)
  and NAL 20 (IDR) at the beginnings,
  `frames_in=1`, `frames_out=2`,
  `errors=0`, `event type 2` (EOS),
  `10533 bytes` total, and **exit 0**.
- Within this one matched A/B pair, enabling native
  Binder callback threads is a **strongly supported
  causal fix for the no-output symptom**.
  Mark **HEVC encode on Android host PASS** for
  this standalone `encctl` one-frame test only.
  This does NOT establish H.264, real production
  helper operation, guest iOS VideoToolbox,
  HEIC container support or prolonged operation.
- The previous vendor `QC2Buf unsupported color
  format` and `queueInputs err 38` in an OFF run
  did not preclude a full frame with the original
  format in the ON run. Treat their relationship
  to missing callback dispatch as unresolved;
  don't change NV12, CQ, bitrate or EOS based on
  the earlier OFF-only vendor errors.

**Production source follow-up (not device-validated):**
`runtime/bridges/encoder/helper.c` is also a standalone
native executable; it uses `backend_ndk` but did not
bootstrap its own Binder threadpool. Add the **same
bootstrap to the production `oneios-encoder` entrypoint**
before its `ENC_MSG_HELLO`, failing closed if the
Binder process API is unavailable. Keep
`ONEIOS_ENCODER_STUB`/host test paths intact and
provide a passive `oneios-encoder --binder-preflight`
to check the binary on-device without MediaCodec or
switching into iOS. Share the dynamic symbol
bootstrap in `binder_pool.c`, using `dlopen`
and `dlsym` so NDK r28/API30 and package
ELF checks continue to work.

**Gate:** the code change must pass a *fresh* host
regression and full local CI before phone deployment.
A PASS from `--binder-preflight` validates Binder
initialization only; it does not replace a real
production-helper MediaCodec round-trip or iOS test.
An unverified OneiOS switch/return remains blocked.

## Twenty-seventh audit — H.264 host PASS and production Binder preflight PASS (2026-11-18)

The owner pulled `72517d38297e99e760bd6eed65526a10c2249cc1`
on CachyOS and reported the following **physically run** validations
on rooted SM-S948B, One UI still active:

- Host `make -C runtime/bridges/encoder test`:
  **69/69 PASS**.
- Full `JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci`:
  **PASS**. SHA-verified ARM64 package
  `oneios-runtime-0.0.0-ci-arm64.tar.zst`,
  archive sha256
  `75324d3a979d15357331c31732e79a7037ac31921380430259d2bc84f6ef985e`,
  6 dynamic ELF files validated against public
  NDK API 30 libraries, 0 failures.
- The SHA-matched **production**
  `oneios-encoder --binder-preflight` ran on
  S26 as root and printed
  `Binder callback threadpool started` then
  `binder-preflight PASS (no codec opened)`.
  This validates the production helper's
  Binder bootstrap but is **not an encoder
  socket or MediaCodec E2E test**.
- **H.264 device PASS in standalone direct
  `encctl`:** `c2.qti.avc.encoder`
  configure/start/accepted NV12 640x480 all
  succeeded, one 460800-byte NV12 frame and
  input EOS queued with status 0.
  One output-format change, 30-byte codec-config
  SPS (NAL type 7 at start), 11564-byte keyframe
  IDR (NAL type 5), zero-byte EOS; `frames_in=1`,
  `frames_out=2`, `errors=0`; combined
  **11594 bytes**, shell **exit 0**.
- Combined with the previous A/B HEVC device
  success (10533 bytes, keyframe+EOS), **both
  Qualcomm hardware video encoders are now
  verified at the *Android host, direct
  encctl* level**, not at the iOS guest level.
  No proof of iOS VideoToolbox, HEIC container,
  full video stream, or production-helper
  socket round-trip yet.

**Follow-up code, not yet run on phone:** add an
optional `encctl --helper PATH hevc|h264 W H`
mode that uses `br_encoder_backend_helper`
instead of direct NDK backend. It exercises
the production route from the same stand-in
virtio guest over UNIX socket to the
standalone production `oneios-encoder`
process (and real Qualcomm MediaCodec).
The test harness itself **does not** start
a Binder pool in this mode; the helper must
start its own. Tighten the production
backend's socket creation to
`SOCK_STREAM|SOCK_CLOEXEC` to avoid the
child inheriting both ends and holding the
parent endpoint alive. Harden the diagnostic
PASS gate to require **actual Annex-B IDR
NAL type (HEVC 19/20; AVC 5), nonempty
coded bytes, KEYFRAME flag, EOS event and
zero counted backend errors**, because
the older helper/NDK code can flag codec
configuration as a keyframe and the helper
can synthesize EOS on a timeout.
Must pass a fresh local host regression/full
ARM64 CI before phone deployment.

**Known limitation:** the production
`helper.c` currently sends `ENC_MSG_EOS`
even when its drain wait reaches ~2 seconds
without a true NDK EOS. Therefore smoke
test success must require **actual nonempty
coded keyframe data**, not only an EOS event,
and shouldn't be interpreted as proof of
robust, lossless flush semantics or video
streaming. The separate error contract
deserves a follow-up after the first E2E run.

## Twenty-eighth audit — production encoder socket HEVC + H.264 PASS on S26 Ultra (2026-11-18)

After pulling `9cbf548d53c56dc253525fe9fdaff3c972f22528`,
the owner staged an SHA-matched `bin/encctl` and
`bin/oneios-encoder` pair from their local
`oneios-runtime-0.0.0-ci-arm64.tar.zst` on the
rooted SM-S948B (One UI running). The archive's
own SHA256 sidecar passed. The remote files were
verified against the extracted host binaries before
execution. The **first local CI snippet shown for
this commit stops at `Updating 72517d3..9cbf548`**:
neither a new `test_encoder: 69/69` nor a
`ci-local: PASS` line for this **specific commit**
is visible in the supplied output. Do NOT infer
full local CI PASS for 9cbf548 from the earlier
72517d3 PASS or from a self-consistent archive.

**Physically observed E2E:**
- `encctl --helper /data/local/tmp/oneios-m3q-9cbf548d-oneios-encoder hevc 256 256`
  used `mediacodec-helper`, spawned the production
  encoder, which reported
  `Binder callback threadpool started`;
  `frames_in=1`, `frames_out=2`,
  `errors=0`, CAPTURE 79-byte HEVC config
  (NAL 32) and 10454-byte IDR frame (NAL 20),
  followed by CAPTURE 0-byte LAST and
  `EVENT EOS=2`; **10533 bytes total**,
  `IDR+EOS present; ok`, **exit 0**.
- `encctl --helper ... h264 640 480`
  likewise used the production
  `mediacodec-helper` socket path, independently
  started the child's Binder threadpool, returned
  CAPTURE 30-byte H.264 SPS config (NAL 7)
  and 11564-byte IDR frame (NAL 5),
  a 0-byte LAST and EOS event; `frames_in=1`,
  `frames_out=2`, `errors=0`;
  **11594 bytes total**, `IDR+EOS present; ok`,
  **exit 0**; enclosing test **Overall exit code: 0**.
- Because `--helper` selects
  `br_encoder_backend_helper`, these runs test:
  **plain-memory guest → virtio-media →
  backend_helper.c → UNIX socket →
  production oneios-encoder helper → Qualcomm
  MediaCodec → socket → CAPTURE/IDR/EOS**.
  Mark *single-frame hardware encoding through
  the production host path on physical SM-S948B*
  **PASS for HEVC and H.264**, independently of
  the unconfirmed full CI output.
- This is **not** a booted S26 iOS guest, iOS
  VideoToolbox end-to-end test, HEIC container,
  sustained/multi-frame video throughput test,
  or full crash/restore certification.
- Known code-level limitation still remains:
  `helper.c` may synthesize `ENC_MSG_EOS` after
  1000 unsuccessful ~2-ms polls without actual
  codec EOS. It also ignores the return values
  from `backend->feed()` and
  `backend->drain()`; backend_helper.c currently
  does not process `ENC_MSG_ERROR`. The smoke
  test's real coded IDR plus EOS proves the happy
  path, **not** lossless failure propagation or
  timeout correctness. Future work should return
  explicit errors, never fake EOS on a deadline,
  and add tests for malformed/missing output,
  helper failure, cleanup, multi-frame operation.

**Immediate next safe gate:** confirm a fresh
`make -C runtime/bridges/encoder test` and
`JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci`
PASS at **9cbf548d**, and inspect the package's
embedded `runtime.json` git commit to avoid
testing a stale archive. No iOS hot-switch before
independent USB recovery/return verification.

## Twenty-ninth audit — CI verified, encoder error/EOS contract hardening (2026-11-18)

**Owner's final validation of the previously installed production encoder
E2E work:** after pulling `660aa47ac8b6973dc5225b5e939e813e3acd3183`, they
ran `make -C runtime/bridges/encoder test` (**69/69 PASS**) and full local
`JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci` (**PASS**). ARM64 ELF checks:
**zero failures**. Embedded `runtime.json` contained the exact current commit
`660aa47ac8b6973dc5225b5e939e813e3acd3183`. A passive process listing
reported **no leftover oneios-encoder helper process**. These checks close
all host CI/package/lifecycle gates for the previous single-frame HEVC/H.264
production socket-path PASS, but they do not validate the new code below.

**Next proposed implementation (needs fresh CI and device validation):**
- The original production `helper.c` ignored `backend->feed()` and
  `backend->drain()` errors and also accepted `backend->poll()` errors
  as if no data were currently ready. After ~2 seconds without EOS, it
  emitted `ENC_MSG_EOS` anyway, masking failure as completion.
- Reuse existing `ENC_MSG_ERROR=9` with positive errno in header field `a`
  (no new binary framing or link-version change). Send a sticky terminal
  error on feed/drain/poll failure or a real deadline, **not synthetic EOS**.
  Preserve real output buffers before EOS where present; handle EOS on a
  nonempty last coded buffer too.
- `backend_helper.c` records asynchronous errors, returns `-errno` from
  `poll()` once already-queued coded buffers are consumed, and returns
  `-EPIPE` if helper died prematurely. No process should die from
  `SIGPIPE` when the other socket endpoint closes.
- `media_device.c` counts such failures, marks the session failed
  once and issues `MEDIA_EVT_ERROR` with an errno body rather than an
  EOS event. `encctl` distinguishes it and fails promptly.
- New Linux host stub fault modes deliberately inject feed, drain, poll,
  missing EOS and helper crash failures; a dedicated test executable checks
  errno and **absence of fake EOS**. They are compile-time host-only test
  injections, never active in Android production builds.

**Status:** code changes need a fresh local encoder host regression and
full CachyOS ARM64 CI. Do not claim the hardening or multi-frame behavior
is PASS on S26 without subsequent physical tests. Guest iOS and USB recovery
remain blocked independently.
