# SM8850: 2026-11-23 detached thermal-mode handoff rejection

## Physical result (same-boot proof)

User-selected mode: 180-second full bridges=1, GPU3D, 8 vCPU,
**software thermal guard OFF** with best-effort 28% CPU limit.
Host's admission completed; the root detached live session did **not** use
that mode, despite the host's summary saying it did.

Evidence from preserved launch
`a0e6b35a369b4f3b95e79ab62429f0f0`:

```text
APFS_DATA_CLONE=CONSUMED_ONE_SHOT_BEFORE_FRAMEWORK_STOP
=== [2/5] Arming the way back ===
THERMAL_GUARD=ARMED_ROOT_BEFORE_FRAMEWORK_STOP
CPU_THROTTLE=PREARMED_READ_ONLY_NO_SYSFS_WRITES_BEFORE_FRAMEWORK_STOP
FRAMEWORK_PANEL_WAKE=BLOCKED_BEFORE_FRAMEWORK_STOP
REASON=switch-panel-wake-refused: CPU floor or thermal sample unsettled
CPU0_MIN=3628800 CPU6_MIN=4185600 CPU_MC=61500 elapsed=20s
!!! The way back to One UI could not be armed
```

Host exit 4, device switch exit 4; return outcome `inplace ... One UI was
never stopped`. `control/framework.takeover-confirmed` and
`control/framework.deadline` were absent. Same boot
`da117511-8c60-45ae-b81e-7421c268beaa`, Android
`BOOT_COMPLETED=1`, `system_server=24414`.
No current guest boot, KGSL work or frame trace should be inferred.
The pre-stop abort protected the still-running One UI. The APFS Data clone is
**consumed** even though the guest never started.

The observed mechanism is a host-to-detached-session thermal-mode **mismatch**.
Exact point where the command-scoped environment was lost was not independently
traced; the original live launcher relied on an environment-only mode selector.

## Code correction

OneOS `switcher/assets/oneios_switch.sh` now:

- Allows an exact 4th argument for `--framework-check run 180`
  and an exact 7th argument for
  `--framework-session run ACK TOKEN RISK 180`.
- Accepts only `I_ACCEPT_SOFT_GUARD_OFF_180S` for explicit no-guard mode.
  Legacy env-only selection stays available for non-destructive preflight.
  A detached session with a no-guard env but **no explicit token fails closed**.
- Emits `SM8850_LIVE_THERMAL_PROFILE=NO_SOFT_GUARD_EXPLICIT_180S`
  (or `ROOT_GUARD_DEFAULT`) before one-shot APFS consumption.
- Preserves guarded-mode behavior by default, all root recovery branches and
  kernel/firmware thermal protection. No thermal-limit bypass was added.

OneiOS `sm8850-takeover.py` sends the exact token separately to the
read-only preflight and to the nested `setsid sh -c` live session.
It rejects any preflight response that does not agree with the host-selected
thermal mode **before launching a detached process**.
Bounded passive telemetry preflight also verifies the effective mode.

## Local validation and next experiment gates

Run entirely on CachyOS before physical test:

```sh
git submodule update --init --checkout app
sh -n app/switcher/assets/oneios_switch.sh
python3 app/tests/test_sm8850_guarded_full.py -v
python3 scripts/phone/test-sm8850-takeover.py -v
python3 scripts/phone/test-sm8850-full-takeover.py -v
python3 scripts/phone/test-sm8850-guarded-duration.py -v
JOBS=8 SM8850_BUILD_ARM64=1 bash scripts/phone/sm8850-full-bridges-local-ci.sh
JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci
```

No local/physical PASS claimed by this commit. After CI, stage the updated
OneOS scripts, rearm a **new** one-shot Data clone and use read-only preflight
to verify `SM8850_SOFT_THERMAL_GUARD=OFF_NOT_SPAWNED`.
An actual live session must show
`SM8850_LIVE_THERMAL_PROFILE=NO_SOFT_GUARD_EXPLICIT_180S`
before any framework stop. This does **not** qualify thermal safety:
earlier full experiments reported CPU temperatures >100°C, CPU cap 28%
was best effort, and the legacy watchdog's independent reboot outcome
remains unverified.

## Subsequent experimental 180-second unguarded/uncapped profile

The operator-requested exact 180s no-root-thermal-guard mode also disables the
OneOS best-effort 28% root CPU-frequency cap worker. Read-only host/device
preflight must agree on `SM8850_CPU_CAP=DISABLED_NO_ROOT_WORKER` **before**
consuming one-shot APFS Data, and the root switch emits
`CPU_THROTTLE=OFF_NO_ROOT_CAP_WORKER` after Framework stop.

These are source/profile contract markers, **not** evidence that a real guest
ran, the device maintained safe temperatures, or the recovery watchdog
worked. Kernel/vendor/firmware thermal policy and the guest thermal bridge
remain unchanged. The root thermal guard and root CPU cap are intentionally
OFF in this experimental branch. Historical CPU readings exceeded 100°C.
No new physical safety or return certification is claimed.


## 2026-11-24 follow-up — exact uncapped profile verified, followed by a physical live run

This section is **later** than the earlier mismatch and source-only fix above. Executed source: OneiOS `f244b5cdfdedd592cc68bcbbb0770762def9e140` with OneOS `f5c1b4a44fc45d78987694a230f7ffabb213e99c`. Separate read-only preflight confirmed `SM8850_SOFT_THERMAL_GUARD=OFF_NOT_SPAWNED`, `SM8850_CPU_CAP=DISABLED_NO_ROOT_WORKER` and `NO_USERSPACE_THERMAL_180S_PREFLIGHT=PASS_NO_FRAMEWORK_STOP_NO_DATA_CONSUMPTION`. The clone was rearmed before this check; the check did not rearm or stop Framework again.

The **later live** 180s full-bridges experiment physically reached iOS ready, a first displayed frame, live KGSL 3D and a working brightness path. Its exactly matched archived token was `7434ae27f8e84b76806f7a4b506e90c9`. No `GPU_COMMAND EPROTO` or `backboardd`/`SpringBoard` exit was logged in **this** run, unlike the prior separately capped run. The current run also showed intermittent display/touch latency, and the host's passive CPU-zone telemetry was previously summarized as **104.8°C** peak.

**Profile handoff correctness is supported by the explicit admission receipts and current guest launch, but runtime thermal safety and independently unassisted reboot return are STILL NOT VERIFIED.** A new normal One UI boot and matching boot reason were observed, not an authenticated original root requester. Do **not** repeat no-guard/no-cap live takeover. [Detailed current session](SM8850_180S_UNCAPPED_SESSION_FINDINGS_2026_11_24.md) · [11 source issues](SM8850_180S_UNCAPPED_ENGINEERING_TRACKER_2026_11_24.md) · [OneOS P0 recovery/thermal tasks](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-no-root-cpu-cap-180s/docs/SM8850_180S_UNCAPPED_ROOT_TRACKER_2026_11_24.md).
