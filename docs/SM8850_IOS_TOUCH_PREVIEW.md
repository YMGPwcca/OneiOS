# SM8850: interactive iOS lock-screen touch preview, no Framework takeover

The previous 2026-11-19 visual run physically displayed an iOS lock screen
and Liquid Glass clock on S26 Ultra, with 291 posted SurfaceFlinger frames
and 34 retired backboardd fences. It launched the guest with `--no-input`,
so touches could not affect iOS.

## New bench-only physical touchscreen mode

`sm8850-ios-gpu-visual.py run --touch` starts the same bounded GPU-auto,
SurfaceFlinger SHM preview, with a **fresh independent APFS Data snapshot** and
a rebuilt `xnuhost`. It replaces `--no-input` with
`--set touch-exclusive=1`.

The native host opt-in is accepted **only** for `mode=bench`,
`display=shm`, `input=1`, `bridges=0`. Unlike takeover, Android Framework
remains alive. The host selects exactly the physical Samsung
`sec_touchscreen` with `INPUT_PROP_DIRECT`, never a wearable or
`sec_touchpad`, and calls `EVIOCGRAB` on that touchscreen fd.
If a touchscreen is missing or the grab is denied, guest boot fails closed.
Side keys (power/volume) are never grabbed; existing key support stays.
On normal shutdown the host explicitly ungrabs then closes its fd. On
unexpected process exit or timeout's SIGKILL the kernel closes the fd and
releases the evdev grab (the input reader starts after the task factory).

The visible display helper receives the SHM framebuffer just as before.
It is **not** a touch target. The separately grabbed evdev device feeds the
existing virtio-input filter, so finger taps/swipes are delivered to the
iOS HID driver rather than dispatched to Android underneath.

**This is physical phone touchscreen input, not scrcpy clicks.** scrcpy's
ADB/Android injection bypasses the raw `sec_touchscreen` evdev source and
does not control this iOS preview.

## Run on the CachyOS host

Keep the USB/ADB connection stable, battery charged and the physical phone
visible. Android One UI must be running before the test.

```sh
cd ~/projects/OneiOS
export PATH="$HOME/Android/Sdk/platform-tools:$PATH"

python3 scripts/phone/test-sm8850-ios-gpu-visual.py -v
make -C runtime/xnuhost -j8 build/host/test_xnuhost
# This test opens ../../kernel/... and include/... relative to its cwd.
# Its test fixture intentionally leaves mock devices allocated; match Makefile's ASAN policy.
( cd runtime/xnuhost && ASAN_OPTIONS=detect_leaks=0 ./build/host/test_xnuhost )

python3 scripts/phone/sm8850-ios-gpu-visual.py run --touch \
  --duration 240 --ram-mib 4096
```

The native test must report `xnuhost tests: N checks, 0 failed` before
running the phone command. If it fails, stop before any guest attempt.
`ASAN_OPTIONS=detect_leaks=0` only disables leak checking for this legacy
fixture test; ASan and UBSan instrumentation remain active. This is the
same setting used by `runtime/xnuhost/Makefile`.

**Do not touch the phone until both** `LIVE_TOUCH_GRABBED=YES` and
`LIVE_DISPLAY_FIRST_FRAME=POSTED` are printed. Then interact with the
actual phone screen: swipe upward on the iOS lock screen, tap and swipe
using one or more fingers. The display is an Android SurfaceFlinger layer
but the raw touchscreen is exclusively routed to iOS for this run.
Unexpected touches during the preview no longer operate One UI underneath.

Results:
- `TOUCH_EXCLUSIVE_GRABBED=True` proves the host acquired the real
  touchscreen evdev grab.
- `TOUCH_GESTURES_LOGGED=N` counts completed raw gestures delivered through
  the host input path; the response seen on iOS is the end-to-end test.
- `DISPLAY_FRAMES_POSTED`, `GPU_FENCES_REPORTED_TOTAL` and
  `GUEST_GPU_PATH` separately report actual frames and GPU operations.
- `TOUCH_RELEASE_LOGGED=True` requires graceful input shutdown; when killed,
  the OS releases the fd even if this message is absent.
- `IOS_VULKAN=UNVERIFIED` remains correct without vkCreateDevice tracing.

The guest has an on-device `timeout -s TERM -k 15 240` and the display
helper a separate timeout. The script never stops Android's zygote,
`system_server`, SurfaceFlinger or watchdog; it does not take over
the Android Framework and does not reuse an already-booted Data clone.

## Emergency release

In a **separate terminal** on the CachyOS host, while the guest is running,
stop only the preview's `xnuhost-gpu` process:

```sh
adb shell -n -T "su -c 'pkill -TERM -x xnuhost-gpu'"
```

The SurfaceFlinger layer should disappear when its guest socket closes.
If the process ignores TERM, the guest's own bounded timeout sends KILL.
A killed process cannot retain an evdev grab after its fd is closed.
Do not stop `system_server`, `surfaceflinger` or the whole input service.
A lost SSH/USB connection does not cancel the device-side guest timeout.

### Known limitations

Native touch exclusivity has host tests and source review but is **not
yet proven on the real S26 Ultra**. If Samsung SELinux or driver policy
rejects `EVIOCGRAB`, report the logged error and do not remove the
exclusive guard to force boot. There remains a global `vm.max_map_count`
change from the first GPU session; the visual runner requires that it is
already at least 1,048,576 and refuses to raise it. The iOS Data copy
is one-shot and remains preserved as evidence when the run ends.
