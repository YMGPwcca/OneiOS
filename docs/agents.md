# Engineering & contributor guide

**Working agreement · OneiOS on SM8850**

[← Handbook](README.md) · [Roadmap](TODO.md) · [Architecture](architecture.md) · [Local build](building.md)

> [!IMPORTANT]
> This is the **current contributor guide**. Earlier parallel-agent chat transcripts, ad hoc task queues and pretrial device-specific instructions have been superseded. Source history is retained in Git; new contributors should start with the physical evidence, not old claims.

## The project in one minute

- **Device:** Galaxy S26 Ultra SM-S948B / m3q / SM8850, firmware S948BXXS4BZIG.
- **Guest:** iOS 27.0.1 / 24A446 running through source-built hosted XNU.
- **Known working:** full Framework takeover, guest ready, first displayed frame, ~600.6 seconds of host runtime and real KGSL traffic.
- **Known incomplete:** safe thermal handling for `bridges=0`, precise unattended reboot/legacy watchdog proof, user-facing smoothness and Vulkan conformance.
- **Safety:** the OneOS normal app switch is still blocked; the root-only profile is restricted and risk-acknowledged.

## Source ownership

| Area | Code and docs |
| :--- | :--- |
| Hosted XNU / vCPUs / syscall costs | `runtime/xnuhost/`, [booter](booter.md), [performance](SM8850_IOS_INTERACTIVE_PERF_TRIAGE.md) |
| GPU and display | `runtime/xnuhost/src/gpu3d*.c`, `runtime/display/`, [GPU guide](gpu.md) |
| Kernel and iOS userland | `kernel/`, `userland/`, [image format](image-format.md), [userland guide](userland.md) |
| Hardware adapters | `runtime/bridges/`, `drivers/`, [hardware](hardware.md) |
| Stage and host CLI | `scripts/phone/`, [full-run log](SM8850_FULL_IOS_10MIN.md) |
| Device takeover / return | OneOS submodule `app/switcher/assets/`, [OneOS status](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-reboot-smoke/docs/SM8850_ONEIOS_FULL_RUN_STATUS.md) |
| Acceptance documentation | [Live ledger](SM8850_LIVE_STATUS_2026-11-20.md), [roadmap](TODO.md) |

## Workflow

1. **Identify the gate.** State whether work is P0 thermal/recovery, P1 CPU, P2 graphics or P3 quality.
2. **Inspect evidence.** Distinguish physical observation, offline fixture, hypothesis and unavailable proof.
3. **Change narrowly.** Preserve device/firmware allowlist, watchdog/reboot behavior, read-only mount isolation and APFS Data one-shot semantics.
4. **Test on CachyOS first.** Native checks and Python regressions before final remote/PR validation.
5. **Write the docs in the same change.** A README PASS badge must never claim a safety condition that was not measured.
6. **Never loop destructive experiments.** A phone trial must be bounded, risk-reviewed and manually approved after safety criteria are satisfied.

## Local verification

```bash
cd ~/projects/OneiOS
git submodule update --init app
python3 scripts/phone/test-sm8850-takeover.py -v
python3 scripts/phone/test-sm8850-full-takeover.py -v
make -C runtime/xnuhost test
JOBS=8 ./scripts/ci-local.sh all 0.0.0-ci
```

Keep command output, exact Git commit, branch, firmware, input hashes and failure markers. A local PASS is **not** a physical phone PASS.

## Unsafe shortcuts

> [!CAUTION]
> Do not bypass SELinux, disable Samsung thermal limits, raise global governor ceilings, open watchdog nodes as a casual inventory probe, reuse a consumed APFS Data clone, enable all bridges in a touch-exclusive bench, or interpret `boot_reason` as independent return certification.

## Evidence language

| Label | Meaning |
| :--- | :--- |
| **OBSERVED** | Device log or physical behavior; narrow to the specific run |
| **PASS** | Reproducible named test completed under stated scope |
| **NOT VERIFIED** | Need additional evidence; neither implicit success nor failure |
| **BLOCKED** | A hard safety or functional prerequisite has not been satisfied |

**Next:** [P0–P3 task board](TODO.md) · [Documentation design](STYLE_GUIDE.md)
