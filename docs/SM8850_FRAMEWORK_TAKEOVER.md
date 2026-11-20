# SM8850 Framework takeover — physical status (2026-11-20)

> **Status: guest boot/first frame observed; performance and independent recovery NOT accepted.** This page supersedes the pretrial 240-second/2D/in-place-return proposal that previously occupied this file. The live SM8850 path has changed substantially: it is a **600-second, GPU-auto/3D, 8-vCPU, 4-GiB RAM** root-only experiment with **mandatory reboot**, not an ordinary OneOS app switch.

See the authoritative [2026-11-20 evidence ledger](SM8850_LIVE_STATUS_2026-11-20.md),
the [full-run/staging procedure](SM8850_FULL_IOS_10MIN.md), and OneOS's
[separate SM8850 port](https://github.com/YMGPwcca/OneOS/blob/feat/sm8850-reboot-smoke/docs/SM8850_PORT.md).

## Scope and trust boundary

- **Exact device only:** SM-S948B / m3q / SM8850, build `S948BXXS4BZIG`, Android 17 / One UI 9, Linux `6.12.69-android16-6-pb4d3caf-abogkiS948BXXS4BZIG-4k`, SELinux Enforcing, ephemeral DirtyFrag/KernelSU root.
- **Root-only experiment:** `scripts/phone/sm8850-full-takeover.sh` uses `scripts/phone/sm8850-takeover.py` and a root-owned stage under `/data/adb/oneios-m3q-framework` with explicit risk consent. **The OneOS app/model/job switch remains disabled for SM8850.**
- **Watchdog:** legacy `/dev/watchdog` `a:82` path, `WATCHDOG_QUALIFICATION=UNVERIFIED_REBOOT_ONLY`. Driver, hardware timeout and independent first-ping handback are not qualified. The protective device-side deadline and watcher are distinct from confirmed watchdog-core behavior.
- **Return:** after this Framework-only switch, OneOS requests `reboot,oneios-sm8850-reboot-return`. **No in-place One UI handback is promised for SM8850.** Volume Up + Volume Down with Samsung USB connected can enter Download Mode; do not use that chord during a run.

The original [Gate 0 readiness plan](SM8850_TAKEOVER_RETURN_GATE0.md)
records an earlier, intentionally more conservative pretrial gate; it must
not be read as a current assertion that Framework Takeover has never happened.

## Executed physical sequence

1. **Framework smoke (historical):** verified Framework stop and a device-side deadline *reboot request*; subsequent Android boot reason contained `oneios-sm8850-reboot-return`. The 20-second smoke did not independently qualify the watchdog or an entirely unassisted boot.
2. **First full-run attempt:** reached Framework stop, then failed early at BusyBox single-operand self-file bind remount (`/data/oneios_switch.sh`), before `xnuhost` started. `switch-failed` reboot was intentional recovery; not a GPU failure.
3. **Corrective stage + rearm:** bind-mount **directory** Data/session writable islands, remount staged `/data` read-only using explicit BusyBox SOURCE and TARGET operands. The **on-phone isolated mount namespace probe passed**. A fresh one-shot APFS Data clone was hash-verified; the consumed clone preserved under `.retired-data/`. Archive-based original smoke proof and passive full-run admission passed with no Framework stop.
4. **Second full run:** the host observed `FRAMEWORK_TAKEOVER=CONFIRMED`, `IOS_GUEST_READY=OBSERVED`, `IOS_DISPLAY_FIRST_FRAME=OBSERVED` and `IOS_HOST_CPU_MASK=0-7`. Saved `xnuhost` telemetry reports **600.6 s since start**; real KGSL 3D traffic and the first guest frame were present.
5. **Post-run Android:** after reboot, ADB reported `sys.boot_completed=1` and reason `reboot,oneios-sm8850-reboot-return`; ephemeral root disappeared and the host reported `EXIT=4`. **This is not failure to boot the guest.** The exact 600s deadline requester, root-owned `return.outcome` and uninterrupted unassisted return have not been independently verified.

The last physically executed revisions were OneiOS `21b88f7372cf5a03bd94f9d2a29056f55997655c` and OneOS `349c0293b0083449067f6e849c172277b0c8aabf`. New commits describing that result are **not new live acceptance**.

## Current performance and safety blockers

- The filtered saved excerpt covers ~200.758 s of display telemetry, **2,135 SurfaceFlinger posts** in 40 windows, **11 zero-post windows**, about **10.63 posted buffers/s weighted**. This is **not iOS animation FPS**, and an idle static screen can have zero posts.
- The 600.6-second `xnuhost` report shows 21.54 million guest/host traps (**35.86k/s**), long tail syscall/interrupt stalls, repeated Spotlight ~one guest vCPU, about 1.4 GiB GPU blob memory in one sampled interval, **4 GiB prefaulted/locked** and **0 MiB guest swapped**.
- Real `drm2kgsl`/KGSL traffic was seen; `gpu=auto` still allows 2D fallback in a *different* run. Do not claim Vulkan conformance or stable 60 Hz from readiness markers.
- `--mode bench --set bridges=0` is the exclusive-touch safety configuration. It **does not start the OneiOS thermal bridge or normal CPU topology/affinity bridge**. Linux kernel, Qualcomm and Samsung firmware thermal limits still apply, but **temperature and throttling were not measured during this full-run excerpt**. The phone became extremely hot, and the owner reported severe UI lag.
- An 8-CPU accessible mask is **not** eight independently pinned vCPUs. Do not boost/disable thermals or change global governor/sysctl to obtain a prettier FPS number.

## Safe investigations next — do not launch another long takeover yet

Use read-only archived logs and local CI before new guest runs. Once root is available again, root-owned `launches/<token>/switch.log`, `session/xnuhost.log`, `control/display.log`, `return.log`, `return.outcome` and previous `logs/session.*` archives may be inspected. **Do not collect by rerunning takeover**. Unprivileged ADB boot metadata is a separate lower-trust source.

1. **P0:** stand-alone, read-only thermal monitor/guard and evidence-preserving recovery, without enabling `bridges=1` in the touch-exclusive runtime.
2. **P0:** verify actual return cause/elapsed time and independent watchdog behavior by root-owned logs plus physically observed no-intervention return; continue to distinguish partial observed boot from certified recovery.
3. **P1:** profile host handoff, page faults/syscalls and Spotlight/cold-start load; test distinct-host-core placement only with controlled local A/B and no system-wide frequency writes.
4. **P2:** correlate UI interaction, guest GPU fence, guest scanout and SurfaceFlinger post; optimize frame copying only when a measured bottleneck is present.
5. **P3:** retain one-shot APFS snapshots and local-first regression + complete benchmark capture before any longer qualification.

### Current non-disruptive commands (CachyOS)

```sh
cd ~/projects/OneiOS
python3 scripts/phone/test-sm8850-takeover.py -v
python3 scripts/phone/test-sm8850-full-takeover.py -v
make -C runtime/xnuhost test
# Optional read-only post-boot state, no root:
adb -s R5GL64LZ9HA shell -T 'getprop ro.boot.bootreason; getprop sys.boot_completed'
```

The separately risk-acknowledged destructive `run` command remains documented in
[SM8850_FULL_IOS_10MIN.md](SM8850_FULL_IOS_10MIN.md) **for reference, not as a current recommendation**.
Do not reuse a consumed APFS Data clone, loosen the OneOS app gate, alter watchdog nodes or boot partitions, or force another 600-second trial until P0 is addressed.
