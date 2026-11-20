# Documentation style

**OneiOS · Galaxy S26 Ultra · editorial and evidence conventions**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!NOTE]
> GitHub-flavored Markdown is the canonical output. Pages should render cleanly on both desktop and mobile, without custom fonts, embedded scripts or screenshots required to understand the core facts.

## Visual hierarchy

| Element | House style |
| :--- | :--- |
| **H1** | One descriptive title; no device history in the heading |
| **Lead** | One or two sentences stating scope, version and what the reader learns |
| **Navigation** | Compact link row back to the docs hub, current evidence and roadmap |
| **Status** | Short, clearly scoped GitHub admonition for risk or obsolete evidence |
| **H2** | Purposeful sections: Summary, Evidence, Mechanics, Safety, Verification, Next steps |
| **Tables** | Brief columns and facts; avoid a wall of prose inside one cell |
| **Commands** | Fenced blocks with `bash`, `sh`, `text`, `json` language labels |
| **Related links** | One short footer with the next document and source of truth |

## Acceptance vocabulary

- **OBSERVED** means logs or direct physical behavior were seen; it does not certify adjacent subsystems.
- **PASS** requires a named, repeatable check and a declared scope (host, fake phone, or real device).
- **NOT VERIFIED** means insufficient evidence; never silently equate it with FAIL or PASS.
- **BLOCKED** means a safety or functional prerequisite is missing.
- **HISTORICAL** marks a snapshot whose procedures are no longer current. Preserve relevant evidence without marketing old milestones as the present state.

## Device and documentation scope

- The active project documentation covers **Samsung SM-S948B / m3q / SM8850** with build **S948BXXS4BZIG** and iOS **27.0.1 / 24A446**.
- Older test-device anecdotes belong in Git history, not the project's landing page or the current roadmap. Never migrate their SoC clocks, GPU identifiers, screen parameters or return behavior into the S26 Ultra facts table.
- Preserve source-code paths, ABI names, citations and exact prior test evidence when the technical detail is still needed to understand a function; explicitly mark historical/other-device data as not a current measurement.
- The OneOS general Android guest compatibility matrix describes many devices and is **not** the OneiOS SM8850 app allowlist.
- **Do not silently delete unique technical evidence when shortening documentation.** For an editorial rewrite affecting old logs, record the original commit, link an [engineering evidence index](HISTORICAL_ENGINEERING_EVIDENCE.md), and explicitly migrate S26-relevant findings before considering the cleanup complete. Do not copy prior-device timings or paths into SM8850 acceptance.

## Safety boundary

> [!CAUTION]
> Do not turn an observed first frame or 600-second process lifetime into a production-release declaration. This project has unresolved thermal, independent watchdog and unassisted return gates.

Before discussing another device run, verify the one-shot Data clone policy, preflight, safety acknowledgment, cooling, and planned rootless evidence capture. Prefer read-only diagnostics. Never propose bypassing SELinux, Samsung thermal protections or watchdog refusal checks to gain speed.

## Contributing

1. Read [the current evidence ledger](SM8850_LIVE_STATUS_2026-11-20.md) and state which acceptance gate the change affects.
2. Change code and its owning documentation together.
3. Run native and Python regressions locally on CachyOS before remote CI or any hardware experiment.
4. Record exact revision, command, logs and what remains unverified.
5. Avoid stale links, duplicated device histories and unsupported performance claims.

---

[Browse all documents](README.md) · [Project home](../README.md)
