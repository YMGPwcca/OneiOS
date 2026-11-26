# SM8850 independent thermal guard — design and acceptance

> **SUPERSEDED HISTORICAL DESIGN (2026-11-26):** the return-on-temperature
> state machine below is not the current operator requirement or a new
> launch instruction. See [AGENTS.md](../AGENTS.md) and
> [the adaptive redesign](../app/docs/SM8850_ADAPTIVE_THERMAL.md): 45–70 C,
> soft throttle at 70 C, hard at 80 C latched until <=70 C, no fixed
> 40% frequency ceiling and no temperature-triggered return/reboot.
> The legacy full-run admission is blocked; the replacement actuator
> and non-reboot quiesce remain unimplemented. Preserve stock safeguards
> and historical evidence. Do not rerun recovery/watchdog tests for this
> userspace task.

**OneiOS 27.0.1 · Samsung Galaxy S26 Ultra (SM-S948B / m3q / SM8850) · proposed safety design, NOT IMPLEMENTED**

[← Handbook](README.md) · [Current evidence](SM8850_LIVE_STATUS_2026-11-20.md) · [Recovery gate](SM8850_RECOVERY_ACCEPTANCE.md) · [Roadmap](TODO.md)

> [!CAUTION]
> This is a **design and acceptance contract**, not evidence that a guard exists. The physical 2026-11-20 full run used `--mode bench --set bridges=0`, so OneiOS's ordinary thermal bridge did **not** run. The phone was reported very hot, but no synchronized SoC/skin/battery temperature trace was captured. **Do not repeat a long takeover merely to obtain one.**

## Purpose and ownership

A standalone, fail-closed, bounded thermal monitor must continue to work when `xnuhost` is unresponsive or not yet launched. **OneOS** owns the independent root-side monitor, its lifecycle, reboot-return request and deadline coordination; **OneiOS** owns guest CPU/GPU/display telemetry. Neither should enable other device bridges just to access temperatures. Kernel, vendor and firmware thermal limits must remain intact.

## Proposed state machine

```text
DISARMED --(trusted stage + exact boot/run + healthy sensor reader)--> MONITORING
MONITORING --(sustained warning)--> WARNING
WARNING --(below hysteresis for a bounded dwell)--> MONITORING
MONITORING/WARNING --(critical value)--> RETURN_REQUESTED
MONITORING/WARNING --(stale, malformed, missing sensor or monitor death)--> FAIL_CLOSED
RETURN_REQUESTED/FAIL_CLOSED --(root-side watcher)--> MANDATORY_REBOOT_RETURN
```

The firmware-specific sensor nodes, units, trustworthy thermal zones, sample cadence, stale interval, warning/critical thresholds, hysteresis and maximum return-request latency are **not yet qualified**. Never invent a generic hardcoded temperature threshold. Absent sensors cannot be treated as safe or as zero degrees.

## Safety invariants

- Exact SM-S948B/m3q/SM8850 firmware `S948BXXS4BZIG`, SELinux Enforcing and current boot/run generation; refuse mismatched or stale stage/heartbeat data.
- The independent guard cannot rely on guest progress, GPU fences, `bridges=1`, a network connection or a live ADB session.
- Read actual kernel/vendor thermal sensors **without writing** thermal trip points, CPU/GPU governors, sysctl/hugepage policy or SELinux. Do not open a second watchdog descriptor.
- Use the already existing OneOS **mandatory reboot-return** path; do not invent or promise an SM8850 in-place handback.
- Sensor/guard failure is fail-closed with a bounded recovery request, not an infinite wait. Keep the 600-second device deadline and its existing supervisor safety gates.
- Persist a session-bound timeline of raw values, converted units, sensor health, guard transitions, requester and reboot outcome; a new Android boot property alone is not a validated guard PASS.

## Open implementation and verification checklist

- [ ] Passively identify **specific, firmware-reviewed** thermal-zone and battery/SoC/skin paths, units, cadence and range **from source or a known trusted inventory**. Never recursively traverse sysfs, proc, debugfs or configfs as root: a historical vendor show-callback panic makes bulk reads an unacceptable approach. That event was on a different device, **not** proof of the same fault on SM8850.
- [ ] Build isolated reader and supervisor tied to boot ID and exact session token, outside guest namespace/cgroup.
- [ ] Specify documented firmware-specific warning/critical thresholds and hysteresis from measured/device evidence.
- [ ] Test stale/malformed/missing readings, sudden rise, monitor crash, watcher crash, stale token, repeat run and deadline races in local simulated tests.
- [ ] Validate return-request path, no extra watchdog FD, no system-wide governor changes and log persistence across ephemeral root loss.
- [ ] Require separate authorization for a *short, cool and monitored* real device test after P0 offline checks. A new 600-second full run is not authorized by this design.

## Current evidence

A prior real guest session reached first frame, ~600.6 seconds host execution and KGSL imports but exhibited severe lag and heat. **No sensor threshold crossing can be inferred from that observation.** See [the physical ledger](SM8850_LIVE_STATUS_2026-11-20.md) and [measured performance baseline](SM8850_PERFORMANCE_BASELINE.md).
