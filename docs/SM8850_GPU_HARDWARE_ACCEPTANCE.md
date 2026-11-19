# SM8850 GPU hardware acceptance (no guest boot)

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
