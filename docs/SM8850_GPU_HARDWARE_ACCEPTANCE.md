# SM8850 GPU hardware acceptance (no guest boot)

> **Historical hardware-only GPU gate (2026-11-16), updated 2026-11-20:**
> the separate SM8850 root-only Framework experiment subsequently did boot
> hosted iOS 27.0.1 with a displayed first frame, live KGSL GPU traffic
> and ~600.6 s of host execution. Do **not** read the earlier statements
> "no guest boot" or "Framework takeover stays blocked" below as the
> current physical result. Full Vulkan API conformance, interactive FPS,
> heat safety and independent return remain unverified. See
> [current evidence](SM8850_LIVE_STATUS_2026-11-20.md).


This is a **bounded, non-takeover diagnostic** for the Samsung SM-S948B / m3q / SM8850 with pinned firmware `S948BXXS4BZIG`. It runs `gpuctl` through the real `drm2kgsl` / KGSL / Adreno driver, and audits saved iOS 27 logs. It does **not** run the iOS guest, switch Android Framework, open a watchdog, change kernel settings, or write an APFS image.

The source fix for `vgpu-3d=1` was already tested offline. The correct iOS Turnip hardware path, `vkEnumeratePhysicalDevices`, `vkCreateDevice`, GUI performance and QuartzCore's `push_surface` remain separate **unverified** milestones.

## CachyOS commands

Run from `~/projects/OneiOS` after pulling the SM8850 feature branch; keep Android One UI running and attach exactly one authorized device via **USB**:

```sh
python3 scripts/phone/test-sm8850-gpu-acceptance.py
python3 scripts/phone/sm8850-gpu-acceptance.py preflight
make -C runtime/xnuhost -j8 build/android/gpuctl
python3 scripts/phone/sm8850-gpu-acceptance.py host-submit
```

Use `--serial SERIAL` for multiple USB devices. The output report is saved under `out/sm8850/gpu-acceptance/`. A failed gate returns exit code 2. `preflight` only reads device metadata and current state. `host-submit` additionally uploads one tool to a nonce-specific path, copies it into a root-owned mode-0700 directory, checks the SHA-256, performs **nodes → probe → submit** with 20-second device-side timeouts, then attempts to remove its own staged files. A host USB disconnect may leave that nonce-specific staging directory; inspect the report's `cleanup_warning` before removing it manually. No generic cleanup or other guest files are deleted.

Strict admission: `SM-S948B:m3q:SM8850`, the recorded firmware, root, USB ADB, boot-completed One UI with `system_server`, enforcing SELinux, no existing guest/takeover, at least 30 GiB plus 64 MiB free, battery at least 30%, battery temperature no greater than 44°C, and a usable device-side `timeout`.

## If preflight reports BLOCKED: space

The admission gate requires exactly **31,522,816 KiB** free on the filesystem holding
`/data/local/tmp`: 30 GiB reserve plus 64 MiB temporary probe headroom. The JSON
report now contains `storage.free_kib`, `storage.required_kib` and `storage.deficit_kib`
even when preflight is blocked, and the error message prints the precise shortfall.
No allocation or cleanup is attempted.

Read the latest report on CachyOS:

```sh
python3 - <<'PY'
import glob, json
paths = sorted(glob.glob("out/sm8850/gpu-acceptance/*-preflight.json"))
if not paths:
    raise SystemExit("No preflight report yet")
r = json.load(open(paths[-1]))
print("failures:", r.get("failures"))
print("storage:", json.dumps(r.get("storage"), indent=2))
PY
```

Inspect actual filesystem capacity on the device **without deleting anything**:

```sh
adb shell -T 'df -Pk /data/local/tmp'
adb shell -T 'su -c "du -sk /data/local/tmp/oneios-m3q-ios27-bench /data/adb/oneios-m3q-framework 2>/dev/null || true"'
```

Reclaim space only after identifying dispensable files through a separate review.
Never remove or shrink the protected APFS Data, chip-ID pair, iOS image assets,
evidence/backup copies or rollback artifacts to satisfy this gate. A successful
offline filesystem restore is not permission to delete the device's original.

## Offline iOS evidence parser

Use an existing **instrumented** xnuhost log; do not run a guest just to populate the parser:

```sh
python3 scripts/phone/sm8850-gpu-acceptance.py analyze \
  --log out/sm8850/ios27-metal-xnuhost.log
```

`IOS_VULKAN=PASS` is intentionally strict. The log must prove **all** of: host DRM native, an effective `vgpu-3d=1` boot argument, Turnip DRM-native selection and successful `IOServiceOpen(0x4149)`, `vkEnumeratePhysicalDevices` with at least one physical device, `vkCreateDevice` returning zero, and actual nonzero `backboardd` GPU fence retirement. A Vulkan initialization failure overrides all other markers. A plugin load, `AGXDeviceUserClient` open, a contentful frame, or standalone host fence does not count.

`GUI_STABLE=NOT_EVALUATED` means the parser did not see the crash, **not** that SpringBoard is stable. An observed `backboardd` SIGABRT / QuartzCore `push_surface` assertion yields `GUI_STABLE=FAIL`. Software-rendering compatibility is still open.

## Remaining gate for an iOS hardware GUI run

Do not reuse the original 8 GiB APFS Data file as a writable guest store. Offline `RESTORE_READY=PASS` established file recovery, but no safe on-phone copy-on-write adapter has been accepted. The no-copy design in `SM8850_NO_COPY_IMAGE_ADAPTER.md` is **not implemented**. A new guest run requires an independently verified writable Data clone/overlay, capacity beyond the required 30 GiB reserve, provenance of the instrumented Metal bundle and sidecars, bounded device-side termination, and reliable recovery. Until those are demonstrably present, a standalone GPU diagnostic and offline log analysis are the permitted steps; Framework takeover stays blocked.


## Next: passive iOS GPU bench inventory after HOST_ADRENO=PASS

The standalone Adreno test does not certify the guest runner. Before any new
iOS boot, compare the current phone's bench image, effective disk configuration,
GPU addon and xnuhost binary with the locally built artifacts. The existing
bench binary may predate the corrected vgpu-3d default, and the existing addon
may predate the new Vulkan initialization tracing.

The dedicated inventory **only reads** the device; it never boots a guest,
copies or writes Data, starts Framework takeover or changes a sysctl.

```sh
python3 scripts/phone/test-sm8850-ios-gpu-readiness.py -v
python3 scripts/phone/sm8850-ios-gpu-readiness.py
```

The JSON report under `out/sm8850/gpu-acceptance/*-ios-readiness.json`
records the pinned phone assets, sizes, inode identities, hashes of the
staged addon and bench binary, image config excerpts, and local build hashes.
It separately tests whether there is enough free space for an 8 GiB
independent Data clone plus 2 GiB operating headroom **above** the 30 GiB
reserve. It reports `SOURCE_ASSETS=PASS` only when that inventory
is complete; it deliberately reports `GUEST_RUN_READY=BLOCKED` until the
isolated writable Data store, effective disk paths, updated host binary,
instrumented GPU addon, bounded termination and rollback are qualified.

Do not treat the offline Data restore rehearsal, a matching hash for the old
bench image, or `SOURCE_ASSETS=PASS` as permission to launch a
guest against the original Data image.
