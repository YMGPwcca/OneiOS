# SM8850 watchdog attribution and recovery acceptance


**OneiOS · Galaxy S26 Ultra / SM8850 · Watchdog provenance research**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!NOTE]
> **Historical research.** This document records earlier source/diagnostic decisions, not current SM8850 runtime admission. Live guest boot, performance and safety conclusions belong to the [physical status ledger](SM8850_LIVE_STATUS_2026-11-20.md).

> **2026-11-20 status reconciliation:** the "no handoff was attempted" and
> blocked entries below are historical Phase 4A passive findings. The
> *separate*, explicitly risk-acknowledged root-only SM8850 profile has
> since run Framework stop, guest iOS 27.0.1 ~600.6 s and named
> reboot-return. **These events still do not qualify** the actual driver,
> timeout, watchdog transfer or entirely unassisted One UI recovery.
> Current evidence: [SM8850_LIVE_STATUS_2026-11-20.md](SM8850_LIVE_STATUS_2026-11-20.md).


## Phase 4A.1 and 4A.2 checklist

- [x] Verify the parent checkout and the clean OneOS `21b8e53` pin.
- [x] Search for the exact Samsung kernel source and collect passive runtime evidence.
- [x] Review the pinned feeder, return guard, and Gates A/B/C. Run fault injection locally.
- [x] Record the remaining unknowns and define the Phase 4A.3 acceptance criteria.
- [ ] Obtain matching source and establish the held endpoint's exact callback and timing semantics.
- [ ] Execute independently authorized hardware acceptance. SM8850 switching stays disabled.

## Physical evidence

The USB snapshot matched SM-S948B / m3q / SM8850, Android 17, firmware
`S948BXXS4BZIG`, and kernel
`6.12.69-android16-6-pb4d3caf-abogkiS948BXXS4BZIG-4k`.
The running kernel's GNU build ID is
`870eb3204575d36a0088e2428134f9f8dc34c3b3`.
Samsung's firmware notice confirms the Android release and firmware.
[Samsung release notes](https://doc.samsungmobile.com/SM-S948B/037187260310/eng.html)

| Check | Result | Evidence and confidence |
| --- | --- | --- |
| Existing holder and device identity | **PASS**, high | A stable `system_server` held FD 121 to `/dev/watchdog` at `10:130`. Both descriptor metadata and the live node agreed. The numbered node was `242:0`. The observer used stat, readlink and fdinfo, leaving the existing FD in place. |
| Legacy to numbered mapping | **BLOCKED** | `10:130` resolves to `/sys/devices/virtual/misc/watchdog` and `242:0` to `/sys/devices/virtual/watchdog/watchdog0`. Neither exposes a driver or module link. The pattern fits watchdog-core's legacy alias but does not establish that both names resolve to the same registered watchdog on this kernel. |
| Linux software watchdog | **PASS** for presence, high | Loaded `softdog` exports visible symbols `softdog_dev`, `softdog_ping`, `softdog_stop` and `softdog_fire`. Its build ID is `f709c40344a9fad7acd5b846af27b619da59b479`. Runtime evidence does not tie those operations to FD 121. |
| Qualcomm SoC watchdog | **PASS** for activity, high | Loaded `qcom_soc_wdt`, `qcom_wdt_core` and `sec_qc_qcom_wdt_core`, the `qcom_soc_wdt_probe` symbol and `msm_watchdog_data` pet lines near 9.472 s. This is the observed interval between pets, with no evidence that it is the FD's expiration period. The on-disk `sec_qc_qcom_wdt_core.ko` SHA-256 and ELF GNU build ID matched the live snapshot. |
| MAX77775 charger timer | **PASS** for implementation, high. Activity **BLOCKED** | `max77775_chg_set_wdtmr_kick` and `max77775_chg_get_wdtmr_status` belong to `max77775_charger`, a separate loaded module. The current log buffer had no matching charger kick. Matching MFD and PDIC ELF notes establish those binaries' provenance only. |
| Kernel policy metadata | **PASS** for observed values | The running config has watchdog core built in, `CONFIG_WATCHDOG_SYSFS` unset, default nowayout unset, and `CONFIG_WATCHDOG_OPEN_TIMEOUT=0`. The boot args include `softdog.soft_panic=1` and `watchdog.stop_on_reboot=0`. The exposed watchdog parameters confirm `stop_on_reboot=0` and `open_timeout=0`. The boot argument alone does not prove the active softdog parameter, and build defaults do not prove an endpoint's runtime nowayout bit. |
| Endpoint identity and operations | **BLOCKED** | `identity`, `state`, `timeout`, `pretimeout` and `nowayout` are unavailable. Effective timeout, the initial and post-close deadlines, ping behavior, exclusive-open scope, stop/reboot semantics and time to the framework's first successful keepalive all remain unknown for the held endpoint. |
| Hardware handoff and Gates A/B/C | **BLOCKED** | No handoff was attempted. The verified physical chord and USB observations are independent of the Phase 4B host boot. See [recovery dry-run](SM8850_RECOVERY_DRY_RUN.md) and [image readiness](SM8850_IMAGE_READINESS.md). |

The passive collector never opens a watchdog node or dereferences an FD for
content. It checks the exact target before sending a fixed metadata script
through existing USB ADB and root authorization. The script reads only procfs,
selected sysfs metadata, the filtered kernel ring buffer, and named regular
module files under system module paths. Full output, including software IDs
and hashes, stays in ignored local evidence. A missing field or an ambiguous
or changing owner can block the relevant check.

```sh
mkdir -p out/recovery/phase4a
python3 scripts/phone/s26-watchdog-attribution.py --serial YOUR_S26_USB_SERIAL \
  --output out/recovery/phase4a/watchdog-new.json
```

The command's exit status describes collection. Use the individual JSON
checks for attribution and acceptance. For a path reported under
`module_sha256`, compare the SHA-256 of the regular ELF and the GNU note
from `readelf -n` with the passive JSON. The three comparisons in this
phase used read-only copies of the reported, named `/vendor_dlkm/lib/modules`
files and discarded the temporary host bytes.

## Exact source acquisition remains blocked

The official source center returned HTTP 403 on model and build searches.
Public repository searches for the build and Samsung m3q/SM8850 kernel tree
did not yield a matching source release. The firmware catalogs confirm binary
firmware provenance only. There was no exact source archive in the local
inventory. Generic Linux, Qualcomm trees and the earlier reference SoC reference explain
possible semantics without establishing this firmware's implementation.
[Samsung source search by build](https://opensource.samsung.com/uploadSearch?searchValue=S948BXXS4BZIG) ·
[Prior source and implementation review](../app/docs/oneios-watchdog-recovery.md)

1. In Samsung's Open Source Release Center, search both `SM-S948B` and
   `S948BXXS4BZIG`. Record the exact archive title, official URL, release
   date and SHA-256. If the exact release is missing or access is unavailable,
   use the center's **Inquiry** menu to request the corresponding source
   for the full release string and GNU build ID above. Request the GKI
   base, Samsung and Qualcomm vendor watchdog trees, module build manifest,
   Kconfig fragments, DTS/DTBO sources and toolchain.
2. Keep the source archive and matching stock boot/vendor boot and module
   artifacts local. Run `sha256sum "$SOURCE_ARCHIVE"` and
   `bsdtar -tf "$SOURCE_ARCHIVE"` before unpacking into an isolated folder.
   Compare build records and `readelf -n` of the stock ELFs against the
   captured kernel and loaded module IDs. Match the resolved config and
   registration order to the exact firmware. A source archive may require
   a documented source-to-binary mapping even if its rebuild is not bitwise
   identical.
3. Trace the registration of the legacy misc node and numbered node to
   their actual operations. Determine the owners and failure semantics of
   `.open`, `.write`, `.release`, `.ping`, `.stop` and the reboot/panic
   hooks. Check the matching One UI userspace feeder's open and retry timing
   from firmware artifacts where available. If multiple registrations remain
   possible, require attributable runtime registration evidence from that
   build before approving a handoff.

## Phase 4A.2 baseline OneOS review

The review below describes baseline commit `21b8e53`. Phase 4A.2b addresses
the software stall-detection gap while leaving physical acceptance blocked.

- The feeder is S24-profile scoped and requires identity, state and timeout
  metadata. Its legacy-alias inference and ordinary nonempty write are
  premised on the S24 software-watchdog implementation. The S26 policy
  refuses that path.
- The stop lock serializes the framework stop with return. The switch
  waits up to 10 s in its stop loop and checks feeder readiness over a
  further nominal 2 s. Readiness follows one successful write.
  The watcher detects feeder failure and disappearance, but the stuck-PID
  fixture shows it cannot detect loss of keepalive progress while the
  expected process still exists. A bounded heartbeat freshness check and
  independent deadline are prerequisites for an S26 design. The automatic
  stall-detection criterion is **FAIL** for the pinned implementation in
  the simulated stuck-PID case.
- The return keeps feeding through Gates A and B. It requests feeder exit
  before any zygote-capable restart, waits about 3 s before escalating and
  refuses a holder surviving the nominal 4 s release loop. Process
  identity is used as a proxy for release. A future physical path needs
  evidence of actual last FD closure, including inherited descriptors.
- Gate C waits up to 60 s for `system_server`, up to 180 s for unlock
  after it starts, and 20 s of stability. The final watchdog probe verifies
  reacquisition by metadata, not the first successful framework ping.
  The return guard's step budgets are 90/45/75/45/290 s with a 600 s
  overall guard. These are application bounds. A hardware deadline may
  expire before any of them, and a watchdog panic can preempt the software
  reboot fallback.
- In the offline failure fixture, a missing first ping, `EBUSY`, write
  failure, a surviving owner, or failed reacquisition must avoid in-place
  success. A successful software reboot request in a fixture is evidence
  of the branch taken, not evidence of physical recovery. Preserve earlier
  fail reasons even if multiple guards request fallback.

Reproduce the fault matrix against the pinned scripts under Bash and mksh.
The recovery CI entry point also tests observer shell syntax and the offline
ADB transport. The OneOS JUnit tests exercise the existing watchdog cases.

```sh
ONEOS_TEST_MKSH=/path/to/mksh \
ONEIOS_RECOVERY_REPORT=out/recovery/phase4a/fault-injection.json \
scripts/ci-local.sh recovery

cd app/app-android
JAVA_HOME=/usr/lib/jvm/java-21-openjdk ANDROID_HOME="$HOME/Android/Sdk" \
ONEOS_TEST_MKSH=/path/to/mksh ./gradlew --offline --console=plain \
  :core:root:testDebugUnitTest --tests '*OneiosScriptTest.watchdog*'
```

## Phase 4A.2b heartbeat

The same production watcher now requests recovery when an alive feeder
has no recent successful keepalive. The fake-clock regression failed in
Bash and mksh against `21b8e53` and passed with the heartbeat.
A second fixture blocks the mock write itself and verifies that the
heartbeat stays at the last successful ping. A late completion cannot
reannounce readiness. The return guard watches the active feeder after
the session watcher yields, and supervision ends at the deliberate close
before framework restart. Fault reporting preserves the first fault
and any request that already exists.

The 3 s first-ping and 5 s freshness thresholds are for the existing
S24 software watchdog supervision, using whole seconds of boot uptime.
Polling and scheduling add latency. An SM8850 handoff still requires
matched driver semantics, measured hardware timing, proof of actual
descriptor closure and first framework keepalive, and a separately
validated recovery channel. No Phase 4A.3 entry criterion has been waived.

## Phase 4A.3 entry and acceptance checklist

This checklist is a plan for a separately authorized exercise. Every entry
criterion must pass before disturbing the framework. Keep the product switch
gate disabled, and design the exercise independently of guest iOS startup.

1. **Source and identity.** Record exact firmware, kernel and module build
   IDs, source receipt and hashes, current SELinux state, boot identity,
   the verified endpoint and its aliases. Reject a missing or ambiguous
   mapping or any change since the approved plan.
2. **Independent recovery.** Choose an owner-present, backed-up lab unit,
   a verified stock recovery path for the same model and bootloader
   revision, and power and access independent of One UI, USB ADB,
   `system_server`, and the feeder under test. Rehearse the out-of-band
   recovery under separate authorization before any watchdog transfer.
   Loss of the same ADB transport under test must never strand the unit.
3. **Budget each interval.** Obtain conservative lower bounds for the time
   remaining from the last successful ping, after close, and after any
   documented timeout changes, using matched semantics and validated
   measurements. Timestamp the last owner ping, release, exclusive open,
   first feeder ping, last feeder ping, last descriptor closure, framework
   open and first successful framework ping on a monotonic timeline.
   For each interval require
   `worst elapsed + detection + independent recovery + safety margin < minimum remaining timeout`.
   Set concrete stop, first-ping, heartbeat, release, reopen and abort
   limits from those measurements. Leave the approval blocked while any
   term is unknown. The 9.472 s SoC pet cadence and S24's 100 s window
   are not values for this formula.
4. **Prove fail-safe readiness.** Qualify the canary's heartbeat and
   fail-closed branches offline for early cancellation, unexpected or
   duplicate FD ownership, `EBUSY`, `ENODEV`/write failure, stalled I/O,
   feeder or watcher death, inherited FD leakage, missing cgroup kill,
   framework restart loops and failed first ping after reacquisition.
   Bind recovery to independently witnessed progress and deadlines.
   Approve the fault order, controller, one-run limit and stop criteria
   in writing. Do not begin with a live failure injection.
5. **Gate A.** On the first separately authorized successful-path canary,
   record the unchanged boot identity, original SELinux status and core
   daemon PIDs, restored shmem, and an empty session cgroup, namespace
   and stage-holder inventory. Verify PID cleanup if cgroup kill is
   unavailable. Any surviving task disqualifies in-place recovery.
6. **Gate B.** Record that the stop loop is gone before framework start,
   composer and SurfaceFlinger were restarted and registered, required
   audio and other services are registered, and the pre-stop USB baseline
   and physical transport are recovered as specified. Record the
   exclusive FD release boundary before the framework can reopen.
7. **Gate C.** Require a new stable `system_server`, user 0 unlock and
   20 s of stability, confirmed same-endpoint reacquisition, independently
   evidenced successful framework pings within the handback budget, and
   no watchdog pretimeout, panic, unexpected reset or second holder.
   Confirm input, UI responsiveness and sustained watchdog service for
   the agreed observation period. A forced recovery is a canary failure
   even if the phone is recoverable.
8. **Evidence and decision.** Archive timestamped owner/FD and ping
   evidence, transport and service timelines, guard reasons, pre/post
   boot IDs and release hashes, and authorized out-of-band recovery
   observations. Preserve the first failure if later fallbacks also fire.
   Advance only with independent review of all gates. Keep a separate
   decision for any future live guest switching.
