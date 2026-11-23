# Engineering evidence index — before the SM8850 handbook rewrite

**OneiOS · traceability index, not an operational runbook**

[← Handbook](README.md) · [Current S26 status](SM8850_LIVE_STATUS_2026-11-20.md) · [Documentation policy](STYLE_GUIDE.md) · [Hardware](hardware.md)

> [!IMPORTANT]
> On 2026-11-20 the editorial rewrite made the handbook easier to read but removed **thousands of lines of engineering records**. Those lines were **not permanently deleted**: their original blobs and commit history remain available at the exact parent revision `19820844368766aa6e8f8c90cf8021241c802123`. The legacy content mixes earlier-device measurements, experimental approaches, discarded hypotheses and some reusable interface discoveries. **Do not interpret any old-device sensor, GPIO, watchdog or GPU numbers as a measurement of SM8850.**

## Recoverable full-length records

| Original page before the rewrite | Approximate former size | What the full historical version contains | Status |
| :--- | ---: | :--- | :--- |
| [Engineering agent/bring-up log](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/agents.md) | 2,094 lines | Kernel/prelink/hostcall decisions, debugger/launchd failures, per-agent handoffs, GPU/import/fence findings, USB/audio investigations, local build observations and safety incident reports | **ARCHIVED IN GIT**; the current `agents.md` is a contributor guide |
| [Hardware bridge technical record](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/hardware.md) | 2,849 lines | Per-bridge Wi‑Fi, Bluetooth, haptics, audio, thermal, brightness, camera, HID, battery, S Pen, encoder and Samsung/Treble implementation notes, plus date-stamped physical/host test results | **ARCHIVED IN GIT**; `hardware.md` now covers SM8850 |
| [Paused work / PR handover](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/newtodo.md) | 722 lines | Former PR/branch mapping, fixes versus drafts, cold-start and widget/audio/network hypotheses, scripts and reasons for prioritization | **ARCHIVED IN GIT**; `newtodo.md` redirects to the current TODO |

## Findings that must remain accessible

| Theme | Original source | Current treatment |
| :--- | :--- | :--- |
| Native haptic SM8850 regression from 2026-11-16 | [Hardware guide final sections](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/hardware.md#L2803-L2849) | **Recovered** in [SM8850 haptic evidence](SM8850_HAPTIC_EVIDENCE_2026-11-16.md), distinguishing phone HAL and host-fixture tests from unverified guest tactile acceptance |
| Safe Android kernel sensor inspection | [Previous bring-up safety incident](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/agents.md) | The old incident occurred on a **different device**. Apply the general precaution: **never recursively walk sysfs/proc/debugfs/configfs on a rooted phone**; inspect named, firmware-reviewed nodes only. It is a precaution, not proof the SM8850 firmware has the same fault |
| Historical thermal, CPU and GPU diagnostics | [Hardware and agent logs](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/hardware.md) | **Do not reuse** old thermal thresholds, clock limits or display-size assumptions; use [SM8850 measured baseline](SM8850_PERFORMANCE_BASELINE.md) instead |
| Historical PR statuses and experiment commands | [2026-11-15 handover](https://github.com/YMGPwcca/OneiOS/blob/19820844368766aa6e8f8c90cf8021241c802123/docs/newtodo.md) | Retained for archaeology; **not** a current CI instruction or permission to run old takeover scripts |
| Current safety and roadmap | [Live 2026-11-20 ledger](SM8850_LIVE_STATUS_2026-11-20.md) | The authoritative version for S26 Ultra current device state |

## How to review the old pages without changing branches

Use the links above to read their exact historical content. Alternatively, in a trusted local checkout:

```bash
# Read only; no checkout, build, rearm or phone access.
git show 19820844368766aa6e8f8c90cf8021241c802123:docs/agents.md | less
git show 19820844368766aa6e8f8c90cf8021241c802123:docs/hardware.md | less
git show 19820844368766aa6e8f8c90cf8021241c802123:docs/newtodo.md | less

# Compare current handbook to the former records.
git diff 19820844368766aa6e8f8c90cf8021241c802123..HEAD -- docs/agents.md docs/hardware.md docs/newtodo.md
```

Do **not** `git checkout` an old device profile or `git reset` the S26 feature branch simply to recover history. Any substantive migration to the new device guide must be scoped, source-backed and reviewed for model/firmware assumptions.

## Editorial completeness rule

Before replacing a long technical file with a shorter overview, record where its **unique debugging facts, verified results, protocol contracts, failure mechanisms and safety warnings** remain accessible. If they are still relevant to SM8850, create a clearly scoped page rather than deleting them silently. Keep historical snapshots out of the active runbook, but never imply that shrinking a Markdown file is a completed technical migration.

**No physical phone validation or new code safety acceptance is produced by this index.**
