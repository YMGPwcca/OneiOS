# SM8850 GPU bench: first preboot block and exact-error retry

The first hardware guest runner (`eaeb9c3`) could report `blocked:2` before starting
`xnuhost`: it incorrectly required `image/kernel.kc.trustcache`. But xnuhost's
`sidecar("trustcache")` is optional. When no sidecar is present and the
verified image set lists `trust/static.trustcache`, `xh_imageset_trustcaches`
constructs the guest's trust modules from the image, including the signed
owner module in `overlay/userland/owner-trust.json`. This is the actual host
source behavior; absence of the sidecar alone is not a fatal image error.

The corrected runner accepts either trust source. It **does not** update the
GPU addon, trust files, Apple binaries, Android Framework or protected Data.

## Inspect the original attempt (read-only)

```sh
cd ~/projects/OneiOS
export PATH="$HOME/Android/Sdk/platform-tools:$PATH"
python3 scripts/phone/sm8850-ios-gpu-bench.py inspect \
  --stage /data/adb/oneios-m3q-gpu-snapshot-6e89899ca4039fed
```

This prints the existing `gpu-bench/{state,run.log,device-run.log,xnuhost.log}`
(tails), the `attempted` marker, and the trust paths. **Do not infer the
blocker from `blocked:2` alone.** Read the original `ERROR=...` first.

## Retry only the proven false trustcache-sidecar block

If and only if the previous run state is **exactly** `blocked:2`, its original
`run.log` contains **exactly** `ERROR=trusted_addon_missing`, there is no
`gpu-bench/attempted` marker and no nonempty `gpu-bench/xnuhost.log`, this
command is allowed:

```sh
python3 scripts/phone/sm8850-ios-gpu-bench.py retry-preboot \
  --stage /data/adb/oneios-m3q-gpu-snapshot-6e89899ca4039fed \
  --duration 240 --ram-mib 4096
```

These conditions are independently enforced **on the phone**; they cannot be
overridden by an argument. If any condition fails, the tool refuses to run a
guest or reuse the snapshot. The original diagnostic files are never moved or
deleted. Only if the exact gate passes does the tool place a distinct copy of
the fixed xnuhost at `bin/xnuhost-gpu-retry`, generate the separate
`gpu-bench/retry-preboot/{run.log,xnuhost.log,state,device-run.log}` and start
the same bounded, non-takeover bench using the original independent Data copy.
The shared `gpu-bench/attempted` marker is written **before any writable guest
open**: no second guest attempt can silently reuse mutated APFS Data.

The runner now prints `DEVICE_RUN_LOG_BEGIN/END` including `ERROR=...` and
`TRUST_SOURCE=...` on completion, so a future failure no longer loses the
reason inside the local JSON report. It still may report `IOS_VULKAN=UNVERIFIED`
when the signed addon lacks Vulkan API-level instrumentation.

**Safety:** No Framework takeover, watchdog operations, kernel/firmware changes,
original Data writes or sysctl changes. A real 4-GiB iOS guest still consumes
phone RAM, CPU and GPU resources, and has a 240-second device-side limit plus
a 15-second TERM-to-KILL backstop. This is not a GUI stability test or a
recovery-handback acceptance test.
