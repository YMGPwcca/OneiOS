# SM8850 recovery acceptance — evidence and outstanding gates

**OneiOS + OneOS · Samsung SM-S948B / m3q / SM8850 · NOT CERTIFIED**

[← Handbook](README.md) · [Physical status](SM8850_LIVE_STATUS_2026-11-20.md) · [OneOS watchdog investigation](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-reboot-smoke/docs/oneios-watchdog-recovery.md) · [Thermal guard](SM8850_THERMAL_GUARD.md)

> [!CAUTION]
> Android `boot_completed=1` and `ro.boot.bootreason=reboot,oneios-sm8850-reboot-return` were observed **after** the guest experiment. Neither proves independently qualified watchdog ownership, exact 600-second return requester or a fully unassisted normal boot. A previous USB-connected Volume Up + Volume Down gesture caused a Download Mode detour. Do **not** use that chord as a recovery test or run a destructive smoke to fill a documentation gap.

## Proof matrix

| Question | Existing evidence | Additional independent acceptance evidence | Status |
| :--- | :--- | :--- | :--- |
| Did Android Framework stop? | OneOS and host Framework-stop markers | Match current boot and exact root-owned run token | **OBSERVED** |
| Did iOS run? | `IOS_GUEST_READY=OBSERVED`, first displayed frame, `xnuhost` report | Preserve authenticated launch and display receipts; do not confuse with responsive 60 FPS | **OBSERVED** |
| Did the guest run ~600 seconds? | **600.6 s from process start** in saved `xnuhost` log | Separate monotonic Framework-stop/deadline timestamps and authenticated deadline event | **Duration OBSERVED; requester NOT VERIFIED** |
| Was a watchdog independently qualified? | Legacy `/dev/watchdog` `a:82` and older feeder observations | Firmware-matched driver, FD owner, kernel mapping, actual timeout, keepalive and release semantics | **NOT VERIFIED** |
| Who requested the final return? | New Android boot with named reboot reason; `EXIT=4` after DirtyFrag root loss | Original `return.outcome`, `return.log`, watcher/feeder records and launch token correlated to host receipts | **NOT VERIFIED** |
| Was normal One UI return unassisted? | New Android boot; broader test history includes Download Mode | Independent no-intervention observation and original session attribution | **NOT VERIFIED** |
| Was a thermal fail-safe active? | Hot physical session with `bench/bridges=0` | Pass the separate [thermal-guard gate](SM8850_THERMAL_GUARD.md) | **BLOCKED** |

## Read-only, local-first procedure

1. After authorized root restoration, preserve the existing root-owned `/data/adb/oneios-m3q-framework` evidence *without* rearming or launching a new guest.
2. Correlate `launches/<token>/switch.log`, `session/xnuhost.log`, `control/display.log`, `return.log`, `return.outcome`, watchdog feeder/watcher records and `logs/session.*` with the host's archived `out/sm8850/takeover/` receipts. Match boot ID, generation/token and monotonic timestamps.
3. Reject missing, stale, partially overwritten or untrusted root-owned records. Keep unprivileged ADB `bootreason` separate from authoritative return evidence.
4. Inspect firmware-matched watchdog metadata, owner FD and source **passively**. Do not open/write/magic-close watchdog devices merely to probe them.
5. Exercise invalid deadline, stale heartbeat, dead watcher, missing guard, consumed APFS Data, and rootless post-return cases using reproducible local fixtures before another physical trial.
6. A new physical recovery qualification requires an independent safety review and separate authorization; **do not** remove the OneOS Android app's SM8850 iOS switch block.

## Standard status labels

```text
GUEST_READY=OBSERVED
IOS_DISPLAY_FIRST_FRAME=OBSERVED
ANDROID_NEW_BOOT=OBSERVED
DEADLINE_REQUESTER=NOT_VERIFIED
WATCHDOG_QUALIFICATION=UNVERIFIED_REBOOT_ONLY
UNASSISTED_RETURN=NOT_VERIFIED
RECOVERY_ACCEPTANCE=BLOCKED
```

These are **evidence categories**, not a new programmatically produced success report. See [the existing physical ledger](SM8850_LIVE_STATUS_2026-11-20.md) and [OneOS's current SM8850 boundary](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-reboot-smoke/docs/oneios.md).

## 2026-11-21 additional 300s-request probe: observed thermal abort, not certified recovery

The earlier matrix's `IOS_GUEST_READY` and ~600s lines refer to the **historical successful full-run experiment**, not the new opt-in 300s-request attempt.

For the latter, operator-provided **pre-reboot** thermal stream records `P0_THERMAL_GUARD=FAIL_CLOSED soft_temperature_abort crossed=cpu cpu_mC=75200 cpu_zone=cpu-0-2-1@10` (internal CPU sensor 75.2 C vs conservative experimental 55 C cutoff). Its switch log reaches watchdog `TRANSFER_PENDING` and `/dev/watchdog` magic-close `EBUSY` **after the source-level `stop_android_framework()` success branch**, but has no complete Framework-stop/300s deadline marker or guest launch receipt. Subsequent host witness records ADB OFFLINE at t=50.567s and a *different healthy normal One UI boot* at t=72.615s. The owner reports the return occurred automatically. No original root-owned `return.outcome`, watchdog feeder completion or exact reboot caller could be recovered postboot.

**Scope-aware acceptance:**
- `P0_CPU_THERMAL_THRESHOLD_FAULT=OBSERVED`, not vendor critical sensor calibration or proof of sustained overtemperature.
- `P0_INDEPENDENT_MONITOR_ARMED=OBSERVED`; initial framework stop path passed by source control-flow; full Framework-stop finalization, +300s deadline write and new iOS guest execution **NOT EVIDENCED**.
- `P0_HOST_NEW_ONEUI_BOOT=OBSERVED`, but `P0_REBOOT_CAUSALITY=NOT_VERIFIED`, `P0_WATCHDOG_QUALIFICATION=UNVERIFIED`, `P0_UNASSISTED_RETURN_CERTIFIED=NO`.
- Retain `P0_FULL_600S_TAKEOVER=BLOCKED`; no repeat physical test just to obtain missing logs. Protect root/private raw evidence; add future live return-path capture only after source review.

Full contemporaneous [OneOS log analysis](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-p0-thermal-reader-sim/docs/SM8850_SHORT_GUARDED_IOS_PROBE.md) and [OneiOS physical status](SM8850_LIVE_STATUS_2026-11-20.md).
