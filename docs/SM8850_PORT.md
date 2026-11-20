# SM8850 host validation — Galaxy S26 Ultra

> **2026-11-20 update:** hardware-only early port notes below are historical.
> The separate root-only S26 Ultra Framework experiment now **has**
> physically booted iOS 27.0.1, shown its first frame and executed for
> ~600.6 s; there is real KGSL 3D activity, but serious lag/heat and no
> fully verified unassisted return. **The OneOS app switch for SM8850
> remains blocked.** See
> [live status](SM8850_LIVE_STATUS_2026-11-20.md) and
> [Framework takeover](SM8850_FRAMEWORK_TAKEOVER.md). This does not
> retroactively qualify the 2026-11-16 diagnostics or watchdog.
>


Original S24 Ultra switch/return audit and upstream synchronization plan:
[SM8850_ORIGINAL_AUDIT.md](SM8850_ORIGINAL_AUDIT.md). This passive
probe must be reviewed before any phone session; an absent stage and an
unverified recovery path are BLOCKED, not a switch permission.

Target measured on 2026-11-16: Samsung SM-S948B (m3q), Qualcomm SM8850 (canoe), Android 17 / One UI 9.0, kernel 6.12.69, 4 KiB pages, KernelSU/SELinux Enforcing.

## CPU results

| Host CPUs | capacity | max frequency (kHz) | Current OneiOS relative class |
| --- | ---: | ---: | --- |
| 0–5 | 741 | 3628800 | E |
| 6–7 | 1024 | 4742400 | P |

bridgectl cpu from runtime v0.1.9 reported 8 CPUs and a 6E/2P plan, successful vcpu7 affinity and uclamp.min. The new fixture in runtime/bridges/tests/test_bridges.c captures the observed topology. These relative E/P labels are *not* verified physical efficiency/performance core labels. Do not force an S24 2E/6P configuration without XNU scheduler validation.

## GPU results

Verified SHA-256 of the public OneiOS v0.1.9 release before running diagnostics, as KernelSU root while One UI was running:

- gpuctl nodes: KGSL, udmabuf, DMA heap open. udmabuf limits 64 MiB per buffer, 1024 runs.
- gpuctl routes: memfd-udmabuf, system DMA heap, qcom system heap, and KGSL GPUOBJ_ALLOC all successfully imported, bound and CPU mapped. A 256 GiB VBO starves GPU addresses; 192 GiB works.
- gpuctl probe: chip 0x44050a00, GPU ID 6860, 192 GiB VBO, GMEM 18432 KiB.
- gpuctl submit -v: 16 KiB buffer, CP_NOP command submission, GPU fence retired after 0.72 ms, zero faults and async errors.
- gpuctl large -v: 96 MiB split across 2 udmabufs; 1100 separate pages split across 2 udmabufs; all command buffers and fences succeeded (5.30, 0.16, 0.38 ms), zero faults and async errors.
- KGSL reported that imported buffers retained IO coherence. GPU clocks reported 160–1300 MHz.

These results show basic host GPU execution, **not** guest Metal or graphics output, sustained FPS or reliability.

## Display and input inventory (2026-11-16, non-invasive)

The host shell was Bash on CachyOS. An initial `getevent -lp | Select-String ...` command failed because `Select-String` is PowerShell-only. A subsequent `adb shell su -c 'getevent -pl'` capture provided the following actual evdev capabilities.

- Android display reports an internal 1440 x 3120 panel at 600 dpi and portrait orientation 0, with 120 Hz modes for native (1440 x 3120), FHD+ (1080 x 2340) and HD+ (720 x 1560) resolutions.
- SurfaceFlinger's active panel mode reports 1440 x 3120, peakRefreshRate about 120 Hz and vsyncRate about 240 Hz; Android's 48 Hz `renderFrameRate` is a per-render-rate observation, **not** evidence that the panel's native refresh is 48 Hz.
- The display reports ARR support and intermediate render rates; do not conflate app render-frame pacing with the selected display mode.
- `/dev/dri/card0` and `/dev/dri/renderD128` exist (crw-rw-rw-); `/sys/class/backlight/panel` and `/sys/class/backlight/panel0-backlight` exist. `/sys/class/graphics` is absent on this host; this alone is not a fault.
- `panel0-backlight` resolves through the Qualcomm MDSS MDP backlight class. No brightness values or writable interface were exercised.
- `dumpsys display` exposes the internal cutout and rounded corners; no display bridge has been launched or validated on this phone.
- Touchscreen: `/dev/input/event8` `sec_touchscreen`, `INPUT_PROP_DIRECT`, 10 touch slots, MT X/Y 0..4095. This is eligible for the existing virtio-input bridge.
- Samsung `/dev/input/event9` `sec_touchpad` is a separate MT device, also X/Y 0..4095, without `INPUT_PROP_DIRECT`. It must not be mixed with the direct panel.
- A **connected HUAWEI Band 11-F88** on `/dev/input/event14` exposes `INPUT_PROP_DIRECT` and MT X/Y 0..1079 / 0..2399 (8 slots). Its virtual touchscreen must not be selected instead of Samsung's internal panel if event numbers reorder. The input scanner now first looks for an eligible `sec_touchscreen` and prefers it over other direct touch devices. Without a native Samsung panel, generic direct touch selection is unchanged.
- Physical keys are split across `gpio-keys` event0 (Volume Up), `pmic_resin` event5 (Volume Down), and `pmic_pwrkey` event4 (Power). A paired HUAWEI Band consumer-control device (event13) also advertises volume keys.
- S Pen: `/dev/input/event12` `sec_e-pen` advertises BTN_TOUCH and BTN_STYLUS, ABS_X 0..7330, ABS_Y 0..15881, pressure 0..4095, distance 0..255, and tilt X/Y -63..63. **Correction:** the earlier claim that BTN_TOOL_PEN was absent was incorrect: `getevent` prints `BTN_DIGI` for evdev key code `0x140`, exactly the same numeric value as Linux `BTN_TOOL_PEN`. A full evdev capture confirms `BTN_DIGI DOWN/UP` at the start/end of hover. OneiOS's original strict detection and hover logic is compatible; an unnecessary tool-less Samsung detection exception was reverted.
- Backlight: `/sys/class/backlight/panel` reports max 0, while `panel0-backlight` reports max 12750. The Samsung backend's lookup skips zero maxima and chooses `panel0-backlight`. An earlier reading had brightness/actual_brightness 0 even when Android reported display ON; a later user-controlled slider sweep establishes that the node's **brightness** responds to One UI. `actual_brightness` still reads 0 at all tested levels (not a usable luminance sensor). `bl_power=0` in these observations while the screen is lit (normally Linux unblank).
- **Important brightness side effect:** existing `brightctl info` calls `br_bright_open`, which can write a midrange value if the initial brightness reads 0 (and may enable ALS and touch IC power changes). **Do not run `info`, `levels`, or `als` on SM8850 during discovery.** The SM8850 branch now adds **`brightctl inspect`**, a separate `O_RDONLY`-only path that reports named backlight sysfs values without opening the active bridge, touching ALS or changing the touch IC. The fixture test `runtime/bridges/brightness/test_inspect.sh` covers the exact S26 observation (`panel` max 0, `panel0-backlight` max 12750, both current values 0) and no file content changes. Probe must still be built and tested on the phone before the active brightness route can be evaluated.
- The first multi-line `adb shell su -c '...'` backlight attempt printed KernelSU's `Argument to option 'c' missing` and then output from the remaining shell loop. Treat the displayed sysfs values as a passive shell reading, not a successful root-only command; no writes were made.

**Next safe read-only command from the Linux host (when a fresh snapshot is needed):**

```sh
adb shell getevent -pl | grep -E 'add device|name:|ABS_MT_(POSITION_X|POSITION_Y|SLOT|TRACKING_ID)|ABS_(X|Y|PRESSURE|DISTANCE|TILT_X|TILT_Y)|BTN_(TOOL_PEN|TOUCH|STYLUS|STYLUS2)|KEY_(POWER|VOLUMEUP|VOLUMEDOWN)'
```

Keep any `displayctl` test separate from input inventory: it intentionally creates a transient SurfaceFlinger layer above One UI. No `--takeover`, mode change, hot-switch or kernel patch is justified by the passive display dump.

### One UI manual brightness sweep (read-only, 2026-11-16)

Adaptive brightness was intended to be disabled for repeatability; the user manually selected roughly three different positions on the One UI slider. The percentages label the approximate slider positions, **not calibrated luminance percentages**. No sysfs writes or root-only commands were used for this sweep.

| Slider position | `settings get system screen_brightness` | `panel0-backlight/brightness` | `actual_brightness` | `bl_power` |
| --- | ---: | ---: | ---: | ---: |
| Low (~20%) | 49 | 512 | 0 | 0 |
| Middle (~50%) | 115 | 1228 | 0 | 0 |
| High (~90%) | 222 | 2300 | 0 | 0 |

`settings get system screen_brightness_float` returned `null` at every position. `panel` remained max/brightness/actual=0 and `bl_power=0`; `panel0-backlight/max_brightness` stayed 12750.

**Follow-up at the exact manual slider maximum:** The user moved the One UI brightness slider fully to its end (without an explicit Extra brightness/HBM reading). `adb shell settings get system screen_brightness` returned **255** and `adb shell cat /sys/class/backlight/panel0-backlight/brightness` returned **2300**. The earlier near-high slider at Android value 222 already read 2300, so the **observed normal slider output plateaus** by that point. We have not observed/verified the purpose of the hardware's 12750 upper bound, nor measured HDR/HBM or extra-brightness output.

**SM8850 manual test profile:** Use `ONEIOS_BRIGHT_MAX=2300` as an **explicit opt-in ceiling candidate only in controlled fake-sysfs or future permitted active tests**, never silently change Samsung S24 or generic profiles. The new `test_sm8850_manual_brightness_cap` asserts that `br_bright_open` with `o.ceiling=2300` picks the nonzero-max `panel0-backlight` and maps a full slider to <=2300 in fake sysfs. This is not a physical write validation or a promise that any value up to 2300 is harmless under all panel modes.

**Key safety finding:** The active brightness bridge currently sets its ceiling to `br_bright_ceiling(12750) = 12750` by default; it only halves special max values 510/51000. The measured `panel0-backlight/brightness` at a near-high manual slider setting was **2300**, far lower than 12750. The upper region could be reserved for high-brightness/HDR handling or another extended hardware mode; there is not enough evidence yet to infer its purpose or safe maximum. **Do not run active `brightctl info/levels` or an SM8850 iOS brightness session using the unbounded default ceiling.** Need a passive reading at the slider's normal maximum (without extra-brightness/HBM toggles) and a validated ceiling policy before enabling active writes.

## Physical display helper diagnostic and correction (2026-11-16)

The verified SM8850 CI runtime `oneios-runtime-0.0.0-ci-arm64.tar.zst` was extracted and the display/brightness diagnostic binaries staged under `/data/local/tmp/oneios-m3q-diag` on the phone. This is **not** an iOS session.

- `brightctl inspect`: **PASS**, no writes. `panel` max/brightness/actual=0; `panel0-backlight` max=12750, brightness=645, actual=0, bl_power=0, chosen. Ends `inspect ok (no state changes)`.
- First `displayctl test --seconds 5`: the helper connects to Android's SurfaceFlinger and detects a 1440x3120 internal panel, native 120 Hz, SRGB mode, HDR types 2/3/4, reported panel max luminance 1275 nits (panel capability report, **not** measured actual brightness), and posts a SurfaceControl layer. Buffer type 5 (BGRA_8888), sRGB dataspace 0x08810000, 1:1 native size. On exit the layer was removed, process status 0.
- **Not yet a visual display PASS:** `displayctl` sent **482** test updates over 5.01s but `oneios-display` logged `the first frame waits for /data/local/tmp/displayctl.*/ready`, then `the socket closed after 0 frames`. The command's old `displayctl: ok` only certified transport and cleanup, not actual on-screen presentation.
- **Root cause in diagnostic harness:** `displayctl` launched `oneios-display --session DIR`, which waits for the real XNU `session/ready` file; a standalone color-bar diagnostic has no XNU process and never creates that file. This is distinct from and does not indicate an Android GPU/display driver failure.
- **Code fix:** `displayctl test` now launches `oneios-display --socket DIR/display.sock` so the helper uses its existing no-ready-hold diagnostic path. The production XNU `--session` readiness behavior is unchanged. The test now allowlists forwarded options, rejecting `--takeover`, `--session`, `--socket`, `--lib`, `--wait` and other potential endpoint/takeover overrides. Host test asserts `--socket` plus path, processes the test frame and checks that the temporary directory is removed.
- **Second on-phone diagnostic (2026-11-16, legacy runtime + temporary socket wrapper):** The user used a small `socket-helper.sh` wrapper to translate the old `displayctl`'s `--session DIR` argument into the display helper's existing `--socket DIR/display.sock` mode. The verified old Android binaries otherwise remained unchanged and were *not* replaced with the newly compiled `displayctl` yet. The helper successfully detected the native **1440x3120 at 120 Hz** panel, SRGB color mode, BGRA_8888 buffer format 5, dataspace 0x08810000, and showed a 1:1 geometry. Log sequence: `layer up`, **`first frame posted`**, `the socket closed after 578 frames`, `layer removed`; `displayctl` logged **387 pattern update steps over 5.01 seconds**, `the helper removed its layer and exited 0`, and `displayctl: ok`. These counters measure different events; their difference is not an error. The helper reports `reading xnuhost's socket failed: Connection reset by peer` when the diagnostic ends and its sender closes, then cleans up normally.
- **Acceptance split:** Actual host graphics buffer posting and clean SurfaceFlinger layer teardown are **PASS from logs**. Visual color bars / moving white square **have not been confirmed by the user**, so visible panel output cannot yet be marked PASS. The current fix's host regression CI passed, but the newly packaged `displayctl` binary still needs separate validation; the wrapper demonstrates equivalent no-ready-hold behavior on hardware. An XNU guest, guest Metal rendering, touch-to-iOS routing, and recovery remain **untested**.
- **Next required observation:** Ask the user whether colored bars and a moving white square were visible for the five seconds, with One UI restoring immediately afterward. If yes, mark diagnostic overlay as visually verified; if not, collect SurfaceFlinger/layer state rather than advancing to hot-switch.

## Physical visual acceptance and moving-square flicker (2026-11-16)

The user **visually confirmed** that the color-bar pattern and a moving white square really appeared on the Galaxy S26 Ultra's built-in display during the five-second no-takeover test, and that the motion looked smooth at the panel's 120 Hz setting. The user also observed **noticeable flicker on the moving white square**. This verifies the diagnostic overlay's ability to present visible content and restore One UI; it does **not** prove a measured stable 120 FPS (the log reported 387 pattern steps in 5.01 seconds and 578 helper buffer posts, which are different counters).

The diagnostic's original animation loop called `xhd_send_flush` **twice** per logical movement: once for the old square and once for the new position. With the shared memfd and the helper's partial-damage `ANativeWindow_lock/unlockAndPost` path, these independent packets could cause an intermediate buffer containing only one updated rectangle (especially at the moving edge). This is a plausible, source-backed explanation for the flicker, **not yet confirmed as the only cause**; the shared framebuffer still lacks a producer/consumer write barrier and can race during copying.

**Flicker mitigation implemented in the diagnostic only:** Compose the restored background and new square first, form the union of old and new rectangles using `xhd_rect_union`, then send **one** `XHDF` damage message for each movement. CI's stand-in display helper counts actual received packets and asserts the initial full-frame message plus exactly one partial update per completed movement for both 8-bit BGRX and RGBA16F. No change to real guest XNU frame transport, graphics drivers, brightness controls, root/model gate or return flow.

**On-device acceptance: PASS (2026-11-16).** The user downloaded the **new ARM64 runtime artifact** from GitHub Actions run `43799119719`, verified `oneios-runtime-0.0.0-ci-arm64.tar.zst: OK` with SHA256, and pushed only the newly built `displayctl` to `/data/local/tmp/oneios-m3q-diag/bin/displayctl`. The test ran **without the temporary `socket-helper.sh` wrapper** and completed:
- Panel: 1440x3120, 120 Hz active/native, 1:1 display; SurfaceFlinger layer and 8-bit sRGB/BGRA_8888 buffers created normally.
- `oneios-display: first frame posted (...)`, `the socket closed after 369 frames`, `layer removed`; `displayctl: 377 frames in 5.01 s`, `the helper removed its layer and exited 0`, `displayctl: ok`.
- User visually confirms: **"hết flicker rồi"** (white square no longer flickers), smooth motion, real on-panel display works. The layer and One UI are restored normally as reported by the helper.
- This result validates the **diagnostic's one-union-flush-per-step flicker mitigation on real SM8850 hardware**. Helper posts and diagnostic steps count different things; `377/5.01` steps per second is not a verified sustained 120 application FPS merely because the panel advertises 120 Hz.
- `Connection reset by peer` is logged when the diagnostic client closes its socket on completion; no failure status followed, and teardown succeeded.

### On-device RGBA_FP16 / scRGB-linear acceptance (2026-11-16)

The user ran the already-staged no-takeover command `/data/local/tmp/oneios-m3q-diag/bin/displayctl test --seconds 5 --format rgba16f` on the Galaxy S26 Ultra. Full on-phone diagnostic result:

- Native internal panel **1440x3120, 120 Hz**, 1:1 layer geometry.
- Sender: `pattern in R,G,B,A half float, linear extended sRGB`; frame stride **11520 bytes** (1440 x 8), protocol **format 2**.
- Helper selected Android **buffer format 22 RGBA_FP16**, actual buffer stride **1472 pixels**, and **`scRGB-linear` dataspace `0x18410000`**. This is the actual posted buffer, not merely the desired format. **No BGRA_8888 fallback** was reported.
- Helper log: `layer up`, `first frame posted (1440x3120 buffer, stride 1472, format 22 RGBA_FP16, dataspace 0x18410000 scrgb-linear; ...)`, `the socket closed after 459 frames`, `layer removed`, `displayctl: ok`.
- Diagnostic generated **496 animation steps in 5.00 seconds** (~99.2 steps/s); helper posted 459 buffers (~91.8 posts/s). These are different counts. The panel's refresh capability is 120 Hz, **not** proof of sustained 120 application FPS.
- `Connection reset by peer` preceded normal layer teardown when the diagnostic ended, consistent with previous successful trials.

**Result: PASS for host-to-Android native RGBA_FP16 allocation, frame posting, dataspace tagging and clean overlay teardown on SM8850.** Still **unverified by eye**: actual wide-gamut P3 separation in the patches, full-screen visual stability/flicker in the FP16 mode, extra HDR brightness/headroom, and precise color accuracy. The panel announced SRGB among available modes `NATIVE,SRGB,DISPLAY_P3`; the current active color mode does not alone establish visible P3 reproduction. No destructive `--takeover` was used.

**Next stage:** Passive read-only checks of SM8850 battery and thermal sensors using `batteryctl` and `thermalctl` from the same verified runtime; record which readings are valid and which are missing. Defer haptic playback, audio routing, Bluetooth controller takeover, camera acquisition, brightness writes and especially XNU hot-switch until independently validated, individually reversible tests and recovery checks. This successful FP16 host overlay does **not** establish guest Metal rendering, S Pen routed into iOS, XNU boot or safe recovery.

## On-device battery and thermal bridge inventory (2026-11-16)

The owner staged checksum-verified ARM64 `batteryctl` (448 KiB) and `thermalctl` (485 KiB) from the existing CI runtime under `/data/local/tmp/oneios-m3q-diag/bin/` and ran each **once**, read-only, with One UI running and no XNU session.

### Battery Samsung backend — PASS

`batteryctl` reported `bridges: hw: battery: backend samsung (the default)`, `status "Discharging"` and `batteryctl: ok`. The sample was **90%**, `present=1`, `plugged=0`, `charging=0`, `full=0`, **30.1 C** (`temp=301` tenths), **4327 mV**, **-270 mA**, **5000 mAh** reported both full and design, **28 cycles**, and `minutes=1000` (an instantaneous approximate runtime estimate, not a measured discharge duration). The Samsung default sysfs backend appears functionally compatible; this is a single snapshot rather than longitudinal power validation.

### Thermal Samsung backend — false `trapping` from non-live trip zones

The original `thermalctl` listed **30 thermal zones of interest**, including **`cpu-hw-trip-0` = 105000** and **`cpu-hw-trip-1` = 105000** millidegrees. Other readings at the same moment were real CPU max **37.4 C** (`cpu-0-5-1`), GPU max **35.9 C**, DDR **35.5 C**, AP board **32.2 C**, battery **30.1 C**, `lrp`/case **32.1 C**. `xo-therm` was absent/unknown. The old thermal reader used broad `cpu-*` matching, accidentally included the two `cpu-hw-trip-*` zones and reported **`cpu 105.0 soc 105.0 (cpu-hw-trip-0)`**, **`level trapping (40)`**, despite the hardware being cool. `xnuhost step 0` was unaffected, but the virtual thermal notification to iOS would have been incorrect.

**Fix:** `runtime/bridges/thermal/thermal.c` now narrowly excludes `cpu-hw-trip-*` before treating `cpu-*` as a genuine live CPU sensor. Their value/name strongly suggests a hardware trip threshold pseudo-zone, though the precise Samsung driver implementation is not verified. The regression test adds both 105 C pseudo-zones and checks they do not cause a false critical pressure, while verifying a **genuine** CPU zone at 105.5 C still triggers `TRAPPING`. A second fixture mirrors the user's cool readings and expects nominal pressure and cap 0. No generic temperature ceiling was lowered, no thermal safety mechanisms were disabled, no S24 behavior changed.

**Post-fix on-device acceptance: PASS (2026-11-16).** The owner downloaded runtime artifact from [Actions run 43802356785](https://github.com/YMGPwcca/OneiOS/actions/runs/43802356785), verified `oneios-runtime-0.0.0-ci-arm64.tar.zst: OK` with SHA256, deployed only the updated `thermalctl`, and reran the read-only check with One UI still active:

- `backend: samsung`; **`zones: 28 of interest`**; neither `cpu-hw-trip-0` nor `cpu-hw-trip-1` appears among the accepted live zones.
- `reading (C): cpu 40.5 gpu 37.4 ddr 37.4 soc 40.5 (cpu-0-5-1) xo - ap 33.3 battery 29.6 lrp 32.4; case = 32.4 (lrp)`.
- **`level: nominal (0); case rule 0, SoC rule 0, battery rule 0; xnuhost step 0`**.
- The list printed `cpu-0-5-1` at 40.1 C, while the later aggregated read was 40.5 C. The two readings occur at different times and can naturally change, especially with CPU activity; no inconsistency is established.

**Conclusion:** The narrowly scoped pseudo-zone exclusion works in the actual S26 Ultra thermal sysfs, eliminates the false SoC 105 C / trapping report, and retains actual CPU/GPU/DDR and case/battery temperatures. The existing host regression also preserves real high-temperature alerts; the phone test does not itself establish every high-heat response. This is **thermal sensor classification and nominal pressure PASS**, not XNU boot/guest thermal-policy validation. No sysfs writes, hot-switch or physical thermal load test was performed.

## On-device Wi-Fi status / Supplicant AIDL (2026-11-16)

The owner deployed the existing, checksum-verified `wifictl` ARM64 utility from the CI runtime to `/data/local/tmp/oneios-m3q-diag/bin/wifictl` and ran **`wifictl status` only**, with One UI connected to Wi-Fi. No SSID, passphrase, join/leave, interface ownership change, or network reset was performed.

- **Status probe PASS:** `wlan0` exists; `android.hardware.wifi.supplicant.ISupplicant/default` is available; station interface `wlan0` returned successfully. The interface and supplicant both reported the same MAC address (omitted from this public document).
- Supplicant reported **one configured network** (network ID `0`) and a valid `signal poll`: **-49 dBm**, reported transmit PHY rate **468 Mb/s**, receive PHY rate **526 Mb/s**, frequency **5805 MHz** (5 GHz, channel 161). Utility exited with **`ok`**.
- These are currently reported station/link statistics, **not** a measured IP throughput or proof of guest networking. The AIDL service lookup and read-only status query work on SM8850 under One UI.
- Source review: `wifictl status` uses `br_supplicant_open(ifname, 0, ...)`, `br_supplicant_status`, and close; it does not call `br_wlan_prepare`, remove configured networks or change IP addresses. `wifictl scan [SECONDS [IFACE]]` uses nl80211 **`NL80211_CMD_TRIGGER_SCAN`** and **`GET_SCAN`**; it triggers a real radio scan (possibly causing brief connectivity/latency variation), but does not call the disruptive session `join` path. A single supervised `scan 6 wlan0` is the next candidate check, with returned SSIDs/BSSIDs redacted before sharing.
- **Physical scan acceptance: PASS (2026-11-16).** From the already-staged checksum-verified `wifictl` binary, the owner ran `wifictl scan 6 wlan0` via root while One UI was active. `nl80211` scan/dump returned **46 BSS/network entries** and `ok`, without any error or resource-busy message. Results spanned **2.4 GHz** (2412–2462 MHz) and **5 GHz** (5180–5805 MHz), reporting WPA2 and mixed WPA3/WPA2 security with several hidden-SSID entries and signal readings around -50 to -89 dBm. All SSIDs and BSSIDs were **redacted from the shared log**, and none are stored in this public port report. This confirms the non-join network discovery path on SM8850; it does **not** prove a 6 GHz scan, actual Internet throughput, guest iOS association, DHCP, IP transfer, or long-term reconnection stability. The scan triggers real nl80211 radio work and could transiently affect latency, but this command did not invoke the session's network takeover path.
- **Physical status-after-scan acceptance: PASS (2026-11-16).** A repeat `wifictl status` after the 46-BSS nl80211 scan still returned `ok`, same configured network ID `0`, `android.hardware.wifi.supplicant.ISupplicant/default`, connected `wlan0` station, **-55 dBm**, TX/RX PHY rates **234/433 Mb/s**, **5805 MHz** (5 GHz, channel 161). The MAC matched the prior read (omitted from this public document). Signal and link rates are dynamic; there is no evidence from the two snapshots of a dropped association. One UI's network configuration was not changed.
- **Pending Wi-Fi:** separately plan reversible guest `en0` association, DHCP, IP frames, disconnect and restoration. **Do not run `wifictl join` or `restore`** while still in passive checks; those can change One UI Wi-Fi state. No XNU boot/hot-switch.

## On-device haptic capability inventory (2026-11-16)

The owner ran `adb shell su -c 'getevent -pl'` and filtered **only for haptic/vibrator input devices**, without opening the active OneiOS haptic backend or uploading any effects.

- Samsung `sec_vibrator_inputff` device was found at **`/dev/input/event7`** on this S26 Ultra, exposing `FF_PERIODIC`, `FF_SINE`, `FF_CUSTOM`, `FF_GAIN` and no advertised `FF_RUMBLE`. This **matches the FF_PERIODIC + FF_SINE capabilities required by the Samsung OneiOS haptic backend**, so the capability/device-inventory check is **PASS**.
- The older S24 example documents `/dev/input/event8`. The backend does **not** hardcode event8: `br_haptic_find` enumerates `/dev/input/event*`, checks `EVIOCGBIT(EV_FF)` for periodic/sine and prefers a device named `sec_vibrator_inputff`. So event7 requires **no source change** or Samsung-specific path override.
- **Active vibration is still untested.** `br_haptic_open_backend` sends `FF_GAIN=10000` on opening the Samsung evdev backend; `br_haptic_vib` then uses `EVIOCSFF` followed by an `EV_FF` play event. Normal close queues a stop and closes its descriptor, but the interaction with One UI's own haptic gain/state has not been verified on SM8850.
- **First actual vibration test FAIL (2026-11-16).** The user deployed the checksum-verified CI `bridgectl` from the same runtime and ran `ONEIOS_HW_BACKEND_HAPTICS=samsung bridgectl haptic 80 150` while One UI stayed up. The correct `/dev/input/event7` Samsung driver opened and reported sine effects, period 4..10 ms and level 40..255, but the worker logged **`request (80 ms, intensity 150) failed: Invalid argument`** and **`0 effects played, 1 failed`**. The CLI nevertheless printed **`ok`** because the earlier command ignored worker errors. **Haptic capability PASS; actual haptic playback FAIL.** Do not assume an effect was audible/felt.
- **Mapped request:** `br_haptic_map(150,0)` produces a **6 ms** period and level **72**; the Samsung backend builds an `FF_PERIODIC`/`FF_SINE` effect with 80 ms length. The old error line does not distinguish failed `EVIOCSFF` upload from failed `EV_FF` play, and a failed `FF_GAIN=10000` write is also silently ignored by the original code. The S24 CS40L26A-specific assumptions must **not** be presumed identical on S26 merely because the capability flags match. Driver support for an advertised waveform is not proof that every parameter/format is accepted. Independent Linux implementations exhibit `EINVAL` for device-specific invalid effects; the correct S26 driver source has not yet been verified.
- **Diagnostic-only source fix:** `haptic.c` now reports **`effect upload` versus `effect play`** failures with duration, intensity, period, mapped magnitude and effect id; it also logs gain-setting failure. `bridgectl` now waits for the asynchronous worker and returns nonzero when no effect played or any request failed. New **`bridgectl haptic-inspect`** opens input devices `O_RDONLY` and uses read-only `EVIOCGBIT`, `EVIOCGNAME`, `EVIOCGEFFECTS` ioctls to print the feature bits and maximum effect slots, **without issuing gain, upload, playback, or input grab**. Fake-motor tests cover `-EINVAL` at upload and at play, including the observed `80 ms / 150` mapping. The active waveform/driver behavior is unchanged.
- **Passive diagnostic acceptance: PASS (2026-11-16).** The owner downloaded CI run `43821960082`'s Android ARM64 runtime and verified `oneios-runtime-0.0.0-ci-arm64.tar.zst: OK` with SHA256. After deploying only its updated `bridgectl`, `bridgectl haptic-inspect` returned `/dev/input/event7 "sec_vibrator_inputff" FF_PERIODIC=1 FF_SINE=1 FF_CUSTOM=1 FF_GAIN=1 max_effects=4`, then `haptic-inspect: ok (O_RDONLY; no FF_GAIN, EVIOCSFF, or playback)` and `ok`. Device identity/capability inspection works without changing actuator state. `EVIOCGEFFECTS=4` reports **maximum supported effect slots**, not how many slots are currently free; it does **not** prove the original `EINVAL` resulted from capacity exhaustion or that One UI is not holding any effect slots.
- **Kernel observation:** filtered `dmesg` contained repeated `cs40l26 53-0040` suspend/resume and IRQ enable/disable entries but **no explicit FF upload/play rejection** in the captured tail. This confirms that the active actuator binds to a driver with CS40L26 identity at I2C `53-0040`, but those power-state logs do not explain the earlier `EINVAL`. The `readlink -f /sys/class/input/event7/device` command printed no path; this should be investigated separately rather than interpreted as a confirmed absent device.
- **Reference-source caveat:** Linux input FF documentation defines `EVIOCSFF` as an effect upload, with a separate playback event. Public *non-Samsung* CS40L26 driver code supports `FF_PERIODIC`/`FF_SINE`, but the exact Android 17 Samsung S26 Ultra driver contract has not yet been verified. Source references: `https://android.googlesource.com/kernel/common/+/refs/heads/android-mainline/Documentation/input/ff.rst` and `https://android.googlesource.com/kernel/google-modules/amplifiers/+/aba0cca145df5e55d1c5c4294a90bc382b0d2ec1/cs40l26/cs40l26.c`.
- **Next controlled diagnostic:** Host CI for instrumented haptics succeeded, and a checksum-verified new `bridgectl` is present on the phone. An **optional single identical** `ONEIOS_HW_BACKEND_HAPTICS=samsung bridgectl haptic 80 150` test, while One UI is running and the owner can observe/recover, will now distinguish **`effect upload failed`** vs **`effect play failed`** and return a nonzero shell status on error. Do not raise amplitude, run `haptic-pattern`, change waves to `FF_CUSTOM`, or try Bluetooth/hot-switch. This is an active effect attempt, not a read-only check. The correct fix remains undecided until the failing stage is recorded.



## S26 haptic fault localized to FF upload (2026-11-16)

With the **new instrumented binary**, the user performed exactly one repeat of the **80 ms / intensity 150** Samsung evdev test, while One UI was active. Result:

```
hw: haptics: backend samsung (hw-backend-haptics=samsung)
haptics: on: /dev/input/event7 (sine effects, period 4..10 ms, level 40..255)
error: haptics: effect upload failed: Invalid argument
       (80 ms, intensity 150, period 6 ms, level 72, effect id -1)
bridgectl: haptic failed (effects played=0, failed=1)
haptics: counters: ... 0 effects played, 0 stopped, 1 failed ...
failed
ADB exit status: 1
```

**Definitive failing operation: `ioctl(fd, EVIOCSFF, &ff_effect)` / `FF_PERIODIC` + `FF_SINE` upload returns `-EINVAL`.** Since the effect ID is -1 (allocate new) and the upload returns negative, **no effect ID was created and the `EV_FF` play event was never issued by this test**. The diagnostic tool's changed exit status now correctly reflects the worker failure. The `FF_GAIN=10000` initial write did not generate an error report, but the evdev gain is a state-changing action and its interaction with One UI gain policy is not yet established.

A separate read-only `dmesg` excerpt shows the Samsung kernel's `cs40l26 53-0040` actuator repeatedly accepting **`FF_CUSTOM` waveform uploads of `len=2`**, followed by `cs40l26_playback_effect` effect ID 0 start and stop. Example trigger indices from the Android system were `0x01000032`, `0x01000020`, `0x01000024`. These are *internal firmware trigger indices*, **not** safe arguments to blindly use with `FF_CUSTOM` or an identified mapping of the vendor's waveform bank. This demonstrates that the standard Android haptic path is functioning but does **not** establish why the S26 rejects the OneiOS sine effect. A public Google CS40L26 implementation has an `FF_SINE` path but the S26's exact Samsung build and driver contract have not yet been confirmed. Upstream Linux's `ff-core.c` uses `-ENOSPC` if no effect slot is free; the phone instead returned `EINVAL`, which makes a full four-slot capacity less likely as the sole explanation. The four-slot maximum is not a current usage count.

**No automatic `FF_CUSTOM` fallback or parameter guessing has been added.** Potential explanations that still require vendor-driver evidence include effect format restrictions, an unavailable sine/buzz generator path, unsupported firmware configuration, or Samsung-specific validation in the evdev handler.

**Passive next step:** A new `bridgectl haptic-hal-inspect` command uses the existing stable AIDL client to resolve `android.hardware.vibrator.IVibrator/default`, query its descriptor/version and call **`getCapabilities()` only**, then release the binder handle. Unlike `ONEIOS_HW_BACKEND_HAPTICS=treble bridgectl haptic`, it makes **no `on()`, `off()`, `setAmplitude()`, gain write or evdev effect upload**, and cannot accidentally use the Samsung evdev fallback if the AIDL service is missing. Fake-HAL tests assert no active calls. The existing Samsung and treble **production haptic backends remain unchanged**; choosing whether to use the vendor HAL for the S26 requires physical service inspection and later a separately authorized reversible actuation test.

## On-phone Vibrator HAL AIDL capability probe (2026-11-16)

**Passive AIDL probe PASS on SM8850/Android 17.** The owner checked `service list` and found the registered services:

- `android.frameworks.vibrator.IVibratorControlService/default`
- `android.hardware.vibrator.IVibrator/default`
- `android.hardware.vibrator.IVibratorManager/default`
- `external_vibrator_service` (`android.os.IExternalVibratorService`)
- `vibrator_manager` (`android.os.IVibratorManagerService`)

The owner downloaded Android ARM64 runtime from Actions **43824202427**, verified the archive with `sha256sum -c` (`oneios-runtime-0.0.0-ci-arm64.tar.zst: OK`), staged only `bridgectl`, and ran `bridgectl haptic-hal-inspect` with One UI running. Output:

```
haptic-hal-inspect: android.hardware.vibrator.IVibrator/default version 3 capabilities 0x3c (amplitude=yes)
haptic-hal-inspect: ok (getCapabilities only; no on, off, amplitude or FF events)
ok
```

**Bitmask decoded against AOSP stable vibrator AIDL:**

| Flag | Meaning |
| --- | --- |
| `0x04 CAP_AMPLITUDE_CONTROL` | `setAmplitude` supported in normal mode |
| `0x08 CAP_EXTERNAL_CONTROL` | supports entering external-control mode |
| `0x10 CAP_EXTERNAL_AMPLITUDE_CONTROL` | amplitude support while external control is enabled |
| `0x20 CAP_COMPOSE_EFFECTS` | vibrator effect composition supported |

The flags `CAP_ON_CALLBACK` (0x01), `CAP_PERFORM_CALLBACK` (0x02), and frequency-control/PWLE support are **not** set in the reported mask. Their absence does **not** prevent calling `on(ms, null)`, because the bridge deliberately provides a null callback. HAL version 3 refers to the stable AIDL interface version, **not a guarantee of iOS haptic feature parity**. AOSP source: https://android.googlesource.com/platform/hardware/interfaces/+/refs/heads/master/vibrator/aidl/android/hardware/vibrator/IVibrator.aidl

`haptic-hal-inspect` itself only resolves Binder, checks descriptor/version, calls `getCapabilities()`, and closes its own Binder handle: **no vibration, `on`, `off`, `setAmplitude`, `setExternalControl`, `FF_GAIN`, `EVIOCSFF`, or evdev play**. This gives a viable candidate alternative to the Samsung `FF_SINE` path (which definitively failed at `EVIOCSFF`), but **active HAL playback is not yet validated on device**. `CAP_EXTERNAL_CONTROL` does not mean external control is currently active, and should **not** be enabled for the simple `on(ms)` diagnostic.

**Next on-device test candidate (active, separately reversible):** when the phone is idle and the owner explicitly expects a brief buzz, run exactly one `ONEIOS_HW_BACKEND_HAPTICS=treble ONEIOS_HW_FALLBACK=0 bridgectl haptic 80 150`. Inspect `haptics: on: the vibrator HAL`, `effect 1 played`, `0 failed` and exit code 0, then obtain visual/tactile confirmation. Note that this command calls HAL `on(80)` and `setAmplitude` (if supported), and **`off()` during normal close**, which can interrupt a concurrent One UI vibration. Do not assume a successful `on` result proves perceived amplitude, persistence or guest iOS haptic fidelity. No `FF_CUSTOM` guess, controller takeover, recovery/hot-switch or production-default change is authorized by this passive HAL result.

## S26 active Vibrator HAL playback — PASS, too faint for practical use (2026-11-16)

Following the successful passive AIDL v3 probe, the owner ran exactly one **active, supervised HAL backend** test under One UI:

```text
ONEIOS_HW_BACKEND_HAPTICS=treble ONEIOS_HW_FALLBACK=0 bridgectl haptic 80 150
hw: haptics: backend treble (hw-backend-haptics=treble)
haptics: on: the vibrator HAL android.hardware.vibrator.IVibrator/default (version 3, capabilities 0x3c: amplitude control; level 40..255 as the amplitude)
haptics: effect 1 played on the vibrator HAL: 80 ms, period 6 ms, level 72 (intensity 150, 0 Hz asked)
haptics: counters: 1 requests from the guest (1 vibrate, 0 stop; 0 replaced before they started), 1 effects played, 0 stopped, 0 failed on the vibrator HAL
ok
ADB exit status: 0
```

**Result: physical HAL haptic playback PASS, but tactile strength/calibration remains OPEN.** The owner reported the phone did vibrate, **so faintly that it was nearly imperceptible**. HAL AIDL calls `on(80, null)` and `setAmplitude(72/255)` both succeeded; normal bridge shutdown calls `off()`. This is not a claim that the full iOS/CoreHaptics experience, shape, latency, strength, or frequency mapping has passed.

The requested amplitude value is `72/255 ≈ 0.282`, **not** a measured physical vibration strength. The existing Samsung/S24-derived intensity mapper computes `magnitude = intensity ? 40 + 215*intensity/1000 : 0`, and the HAL translates magnitude to an amplitude fraction. The short **80 ms** pulse and moderate-to-low requested amplitude plausibly explain the faint sensation. Also, HAL `on()` is sent before `setAmplitude()`; the resulting transition delay and system policy have not been measured. The frequency request `0` maps to the software's 6 ms nominal period, but HAL `on()` does **not** accept or use that period; it uses the vendor actuator's own behavior.

**Next safe calibration proposal:** keep `treble` and `ONEIOS_HW_FALLBACK=0`, use **one 200 ms / intensity 400** test (maps to magnitude **126/255 ≈ 0.494**). Run with the phone idle, explicitly expecting an active vibration and possible interference with Android's concurrent haptics; record whether it is clearly perceptible, comfortable, or too strong. An intermediate test should precede any full-scale test; **do not** use `haptic-pattern` or attempt `FF_CUSTOM` trigger indices, change system gains or make `treble` the SM8850 production default before real calibration. For eventual crisp iOS-style taps, AIDL `CAP_COMPOSE_EFFECTS` (bit `0x20`) suggests a possible vendor-native composition path, but its primitive support, waveform repertoire, and fidelity are **not** yet proven.

## S26 HAL vibration calibration follow-up: 200 ms / 400 still weak (2026-11-16)

The owner reported that the follow-up active `ONEIOS_HW_BACKEND_HAPTICS=treble ONEIOS_HW_FALLBACK=0 bridgectl haptic 200 400` pulse was **still very weak**, despite lengthening the command from **80 ms** to **200 ms** and increasing the requested `intensity` from **150** to **400**. No CLI output or exit code from this second test was supplied; do **not** mark that individual call as a verified zero-error transaction. The preceding **80 ms / 150** HAL test already proved 1 play, 0 failures and a barely perceptible actual vibration.

The existing shared `br_haptic_map` produces a magnitude of **126/255 (~49.4% requested HAL amplitude)** for 400/1000 versus 72/255 (~28.2%) for 150/1000. These values are requested normalized amplitudes, not measured actuator acceleration or perceived strength. More duration and requested amplitude failed to provide an adequate tactile sensation. **HAL discovery and basic actuation: PASS; tactile calibration/UX: FAIL/OPEN.**

Relevant implementation caveat: the Treble backend calls `IVibrator.on(timeoutMs, null)` **before** `IVibrator.setAmplitude(float)`, and `br_haptic_close` calls `IVibrator.off()`; the HAL `on()` call ignores `period_ms`. Per the stable AIDL interface, `setAmplitude` changes the motor force but does not specify guaranteed physical linearity, response latency or an onset shape. We have **not verified** whether Samsung applies amplitude promptly, scales continuous vibration differently from its built-in effect primitives, or is impacted by user strength preferences.

**Next before further pulses:** with the device under One UI, capture **read-only** `adb shell dumpsys vibrator` (or `dumpsys vibrator_manager` if needed; redact app identifiers), `settings get system haptic_feedback_enabled` and relevant `settings list system | grep -iE 'vibrat|haptic'` (read only). Compare a normal One UI keyboard/touch feedback sensation to the HAL `on()` pulse (qualitative only), without changing vibration settings. Inspect `IVibrator.getSupportedPrimitives()` and `getPrimitiveDuration()` via a separately validated read-only probe if the vendor HAL supports them, then plan a single deliberate `compose()` trial using supported primitives. **Do not blindly raise amplitude to 100%, modify Samsung driver settings, send `FF_CUSTOM` indices, use `haptic-pattern`, or change production backend defaults**. Do not claim iOS haptic fidelity or proceed to hot-switch.

## Read-only Samsung vibration settings after weak HAL pulse (2026-11-16)

The owner queried current settings (no writes):
- `adb shell su -c 'dumpsys vibrator | ...'` returned `Can't find service: vibrator`. This is **a wrong Android service name**, not a device error: the phone earlier listed the framework service as `vibrator_manager` (`android.os.IVibratorManagerService`). The correct read-only query is `adb shell dumpsys vibrator_manager`; filter output and redact any app identifiers before publication.
- `settings get system haptic_feedback_enabled` returned **1**, and `settings list system` showed `keyboard_vibration_enabled=1`, `dialing_keypad_vibrate=1`, `navigation_gestures_vibrate=1`, `sip_key_feedback_vibration=1`, `SEM_VIBRATION_FORCE_TOUCH_INTENSITY=4`, `SEM_VIBRATION_NOTIFICATION_INTENSITY=5`, and `media_vibration_intensity=5`. These are Android/Samsung user preferences, **not calibrated amplitude fractions, not guaranteed scale maxima, and not proof the actuator reaches a particular acceleration**.
- The subjective **200 ms / intensity 400** HAL pulse was still very weak. Do not infer that the user turned system haptics off; verify the framework state and compare with an actual One UI keypress sensation. No change to Samsung settings or motor driver is justified by this snapshot.

**Next read-only probe added to source:** `bridgectl haptic-hal-primitives`. It calls the registered AIDL v3 `IVibrator/default` `getCapabilities()` then, only if `CAP_COMPOSE_EFFECTS` is advertised, calls `getCompositionDelayMax()`, `getCompositionSizeMax()`, `getSupportedPrimitives()`, `getPrimitiveDuration()` for reported IDs, and `getSupportedEffects()`. These are **pure query methods**: no `on()`, `off()`, `setAmplitude()`, `perform()`, `compose()`, `setExternalControl()`, `FF_GAIN` or `EVIOCSFF`. The fake AIDL service has matching getter responses and mock tests assert no actuation calls. **Await CI and real-phone output before claiming which primitives Samsung actually supports**; an AOSP enum listing alone is not an S26 hardware capability inventory. The `compose()` actuation API also has callback/composition requirements and must not be invoked until those are separately validated.

## S26 VibratorManager and native effect inventory — physical PASS (2026-11-16)

After fixing the `dumpsys` service name, the owner inspected `dumpsys vibrator_manager` on a running One UI system (passive). The relevant non-identifying fields were:

- `vibrateOn=true`; `defaultVibrationAmplitude=255`; the service's single vibrator `id=0` reports loaded `VibratorInfo`, `currentAmplitude=0.0` while idle, capabilities `COMPOSE_EFFECTS`, `AMPLITUDE_CONTROL`, `EXTERNAL_CONTROL` and `EXTERNAL_AMPLITUDE_CONTROL`.
- Android framework's **supported presets:** CLICK, DOUBLE_CLICK, TICK, HEAVY_CLICK.
- Android framework's **supported primitives and durations:** CLICK 20 ms, THUD 300 ms, SPIN 130 ms, QUICK_RISE 150 ms, SLOW_RISE 500 ms, QUICK_FALL 100 ms, TICK 20 ms, LOW_TICK 20 ms.
- Android's ordinary keyboard/touch uses proprietary `SemHaptic` effects through its framework (examples have internal IDs 50025 and 50075). These IDs must **not** be copied into direct FF_CUSTOM or AIDL payloads. The dump has no obvious global suppression or vibrate-disabled state; it does not prove amplitude-force linearity.

The owner also downloaded the CI runtime from Actions **43830452598**, verified `oneios-runtime-0.0.0-ci-arm64.tar.zst: OK` via SHA256, deployed `bridgectl` and ran `haptic-hal-primitives` **read-only** on actual SM8850. Exact meaningful output:

```text
haptic-hal-primitives: AIDL version 3 capabilities 0x3c compose=yes
haptic-hal-primitives: max delay 1000 ms, max composition entries 10
haptic-hal-primitives: 8 supported primitive(s)
  primitive 1 CLICK        duration 20 ms
  primitive 2 THUD         duration 300 ms
  primitive 3 SPIN         duration 130 ms
  primitive 4 QUICK_RISE   duration 150 ms
  primitive 5 SLOW_RISE    duration 500 ms
  primitive 6 QUICK_FALL   duration 100 ms
  primitive 7 LIGHT_TICK   duration 20 ms
  primitive 8 LOW_TICK     duration 20 ms
haptic-hal-primitives: 4 supported preset effect(s): 0 1 2 5
haptic-hal-primitives: ok (read-only AIDL getters; no on, off, compose, perform, amplitude or FF)
ok
```

**Naming distinction:** AOSP's stable `CompositePrimitive` calls primitive ID 7 **LIGHT_TICK**, while Android's framework diagnostic dump renders its corresponding native support as **TICK**. The same underlying 20-ms primitive is meant here; do not conflate `Effect.TICK` (preset ID 2) with `CompositePrimitive.LIGHT_TICK` (primitive ID 7). The 4 standard preset ID mappings from AOSP are **0 CLICK, 1 DOUBLE_CLICK, 2 TICK, 5 HEAVY_CLICK**. These **physical getter results are PASS**. No active native primitive or preset was played as part of this inventory.

**Immediate next stage: one native preset acceptance test.** A new `bridgectl haptic-hal-click` deliberately uses **`IVibrator.perform(Effect.CLICK, EffectStrength.MEDIUM, null)`**; AOSP AIDL declares this method with result `durationMs`. Before performing, the tool requires `ONEIOS_HAPTIC_ACTIVE_TEST=1` and re-queries `getSupportedEffects()` to ensure CLICK is actually advertised. It makes exactly **one** effect request, never automatically retries, stops, changes gain, calls `on()`, `off()`, `setAmplitude()`, `compose()`, enters external control or uses evdev fallback. It waits only for the HAL-returned estimated duration plus a short margin (max 1s duration accepted). It is **an active vibration**: run only once when One UI is idle, not on a call, and compare perceived feedback with Samsung keyboard haptics. On failure record the exact Binder error and exit code; on success obtain tactile confirmation and do not assume full iOS haptic fidelity.

**Why preset before compose:** the current S26 HAL mask `0x3c` lacks `CAP_PERFORM_CALLBACK`, so `perform()` accepts a null callback; `compose()` requires implementing `IVibratorCallback.onComplete()` even though CAP_COMPOSE_EFFECTS is present. Using an existing CLICK preset is a narrower test than introducing callback handling and compound waveform semantics at once. Do not start XNU/guest iOS, hot-switch or take ownership of One UI resources.

## Native AIDL CLICK playback validated on S26; stronger preset trial pending (2026-11-16)

The owner deployed Android ARM64 runtime from **Actions run 43833060687**, verified the archive (`oneios-runtime-0.0.0-ci-arm64.tar.zst: OK`) with SHA256, and ran the previously gated one-shot `ONEIOS_HAPTIC_ACTIVE_TEST=1 bridgectl haptic-hal-click` on the real rooted SM8850 while One UI stayed running.

```text
haptic-hal-click: HAL accepted one CLICK MEDIUM (reported duration 60 ms)
haptic-hal-click: done (one perform; no off, gain, compose or fallback; tactile verification required)
ok
ADB exit status: 0
```

The owner **felt one short, proper haptic-style click** but described the sensation as **still very faint/weak**. **AIDL preset CLICK (MEDIUM) acceptance and physical actuation: PASS; subjective strength: OPEN/WEAK.** The returned 60 ms is the vendor's `perform(CLICK)` estimate, **not** the separate 20 ms `getPrimitiveDuration(CompositePrimitive.CLICK)`. A preset `Effect.CLICK` and a composable `CompositePrimitive.CLICK` are different AIDL APIs and need not share timing, force, or waveform.

There is no evidence of an AIDL/Binder invocation failure or motor failure in this test. Samsung One UI uses proprietary `SemHaptic` patterns which may feel stronger/different than AIDL's standard `on()` or preset. Increasing `on()` intensity earlier to 400/1000 was still weak. This does **not** establish whether stock Samsung keyboard feedback is perceptibly stronger; collect a direct qualitative comparison. Do not infer that the AIDL medium strength means a linear 50% of motor force.

**Next bounded active trial implemented (not yet physically validated):**
- `bridgectl haptic-hal-heavy-click` sends **exactly one** AIDL `perform(Effect.HEAVY_CLICK=5, EffectStrength.STRONG=2, callback=null)`, only when `ONEIOS_HAPTIC_ACTIVE_TEST=1`. The SM8850 HAL previously advertised effect ID 5, and the implementation re-checks `getSupportedEffects()` before issuing the active call. It does not call `on()`, `off()`, `setAmplitude()`, `compose()`, `setExternalControl()`, touch `FF_CUSTOM`/evdev or automatically retry. It caps accepted HAL-reported duration to 1000 ms and waits for the bounded one-shot effect to end.
- AOSP stable AIDL defines `HEAVY_CLICK` as a stronger crisp click and `EffectStrength.STRONG` as strength value 2. S26 does not advertise `CAP_PERFORM_CALLBACK`, so the null callback used for the earlier successful CLICK is retained.
- Mock HAL regression tests cover no active call when opt-in is absent, exactly one `perform 5 2`, and fail-closed behavior when the vendor removes the HEAVY_CLICK capability. The existing CLICK/MEDIUM test remains.
- Gate real phone use on **current-head CI success**, checksum-verified new ARM64 artifact and an idle phone (no call or concurrent vibration). Run **once** and report whether clearly tactile or still too faint. If strong HEAVY_CLICK remains unsatisfactory, stop standard HAL intensity escalation and investigate Samsung's framework-controlled native `SemHaptic` path before proposing an iOS haptic map. Never use unverified vendor trigger indices or modify system vibration policy. No XNU boot or hot-switch.

## Native impacts: experimental guest-to-HAL integration (source staged; no guest boot)

**Physical foundation:** the Galaxy S26 Ultra (SM8850) returned `ok`, exit code 0 and a **single distinctly stronger tactile tick** for `IVibrator.perform(HEAVY_CLICK, STRONG)` (reported duration **110 ms**). `perform(CLICK, MEDIUM)` reported 60 ms and was physically felt but weak. An earlier `on(ms)+setAmplitude` path was too weak; direct Samsung `FF_SINE` upload failed `EVIOCSFF/EINVAL`. Only the strong preset has been subjectively accepted.

**The integration is explicit, disabled by default, and not a claim that guest Core Haptics works end-to-end:**

- The guest's `Actuator` has two distinct roles: a short isolated audio burst (candidate impact) and a sustained 48-kHz waveform (continuous `VIB/STOP` traffic). Mapping **every** 20/50 ms `VIB` segment to a native preset would turn a single long buzz into dozens of hard ticks; this is explicitly prohibited.
- New source mode `oneios_native_impacts=1` (guest boot argument) holds the beginning of a new Actuator run for **up to 30 ms**. A short burst under 30 ms followed by at least **10 ms silence** becomes **one** `OB_HAPTIC_IMPACT` packet; sustained runs preserve the original `OB_HAPTIC_VIB/STOP` semantics after this optional initial classification delay. The existing behavior is unchanged without the boot arg.
- Native impact capability is negotiated by a length-extended v1 HELLO (original v1 8-byte HELLO remains valid, extended HELLO is 12 bytes with feature bit `OB_FEAT_HAPTIC_IMPACT`). Older host/kernel combinations remain compatible and never misinterpret missing features as impact support.
- Host requires all three **independent opt-ins/gates**: selection of `hw-backend-haptics=treble` (not changing the global default), `ONEIOS_HAPTIC_NATIVE_IMPACTS=1`, and an actual AIDL `getSupportedEffects()` response including TICK/CLICK/HEAVY_CLICK. A HAL without these effects publishes no native-impact feature; there is **no automatic fallback** to Samsung evdev, no attempt to write `FF_CUSTOM` data and no guess about vendor trigger indices.
- Experimental amplitude classification of a confirmed isolated audio burst: up to **250/1000 → `perform(TICK, LIGHT)`**; 251..800 → `perform(CLICK, MEDIUM)`; over 800 → **`perform(HEAVY_CLICK, STRONG)`**. Only the heavy classification is physically calibrated for a clear tactile tick; light/medium are provisional. Continuous pulses, legacy FigVibrator patterns and active button haptic stubs retain their original paths.
- Host serializes impact, VIB, STOP on **one worker**. A STOP within the HAL-reported preset duration cancels that active effect; after the duration expires, STOP/close does **not** send a late `off()` that might interrupt a new Android/One UI vibration. The legacy non-native HAL shutdown behavior is preserved.

**Validation gates:** host fake motor + fake AIDL/virtuo bridge tests cover opt-in rejection, extended/legacy HELLO compatibility, supported-effects preflight, invalid impact packets, one effect per tap, long-run VIB/STOP unchanged, immediate cancellation and no late off. Source-level/CI success is needed; real guest playback, onset latency, light/medium quality, App-level iOS haptic fidelity and shutdown behavior remain **UNVERIFIED** until a separately authorized guest session. No XNU boot, display takeover, Wi-Fi takeover or thermal stress has been performed for this change.

## Safe production Haptics preflight before guest boot (2026-11-16)

The new native-impact code has passed SM8850 host regression **4/4 jobs** (run 43838772950), and Android ARM64 runtime packaging **SUCCESS** with artifact `oneios-runtime` (run 43838772788). The host CI environment has **no binderfs**: its `test_hal_binder` **compiled but skipped**; pure host fake-motor/VirtIO queue tests passed (346 checks). No native-impact guest session has been booted.

To close the hardware integration gap **without vibrating the phone**, `bridgectl haptic-native-inspect` opens the actual production Treble `br_haptic_open_as` backend, queries the AIDL `getCapabilities()` and `getSupportedEffects()` presets, checks TICK/CLICK/HEAVY_CLICK, and closes unused. It is opt-in (`ONEIOS_HAPTIC_NATIVE_IMPACTS=1`), refuses `ONEIOS_HW_FALLBACK=1`, and never emits HAL `on`, `off`, `setAmplitude`, `perform`, external control or any evdev writes. A related close fix suppresses **late off()** when native mode was requested but the HAL did not advertise all presets and no continuous haptic was started; legacy non-native mode still stops its motor on close. Fake-HAL phone tests assert no state-changing HAL calls for enabled, blocked and failed-preflight cases.

On real S26, after the **latest matching** checksum-verified ARM64 runtime was staged (not an older `bridgectl`):

```sh
adb shell su -c 'ONEIOS_HAPTIC_NATIVE_IMPACTS=1 ONEIOS_HW_FALLBACK=0 /data/local/tmp/oneios-m3q-diag/bin/bridgectl haptic-native-inspect'
```

Expected: `haptics: native impacts enabled ...`, followed by `haptic-native-inspect: ready (native impact preflight PASS; no on, off, gain, perform or evdev)`, `ok`, ADB exit 0. **No physical actuation is required for this acceptance**. It will verify the production HAL open/preflight, but not a guest-produced impact, stream waveform fidelity, reset under real guest or audio-to-tick latency. Do not enable XNU boot/hot-switch, display takeover or Wi-Fi takeover for this test.

## Captured S Pen evdev trace (2026-11-16)

The user provided 11,126 `getevent -lt /dev/input/event12` log lines across 17.82 s, containing 3,507 SYN_REPORT frames, 2 complete hover/contact/out-of-range cycles and a third, still-in-hover cycle truncated by the recording timeout. No `BTN_STYLUS` press/release appeared in this capture (the side button capability exists but remains untested dynamically).

| Event | evdev time (s) | Meaning |
| --- | ---: | --- |
| BTN_DIGI DOWN (key 0x140) | 868.741952 | First hover begins; positions/distance/tilt arrive; distance 77 |
| BTN_TOUCH DOWN | 870.919734 | Tip contacts screen; pressure subsequently rises up to 156 |
| BTN_TOUCH UP | 873.328402 | Tip lifts; BTN_DIGI stays down and hover continues |
| BTN_DIGI UP | 874.744644 | First hover ends; no contact remains |
| BTN_DIGI DOWN | 881.791380 | Second hover begins |
| BTN_TOUCH DOWN | 882.681687 | Second contact; max observed pressure 272 |
| BTN_TOUCH UP | 883.357822 | Second tip lifts; hover continues |
| BTN_DIGI UP | 884.031229 | Second hover ends |
| BTN_DIGI DOWN | 886.161176 | Third hover begins; timeout ends mid-hover |

The approximately 2 ms spacing of many frames demonstrates the input report cadence *in this capture*, not a guaranteed constant 500 Hz device polling rate. The observed pen coordinate range during the trace was X 0..6728, Y 0..12545; kernel-advertised full ranges remain X 0..7330 and Y 0..15881. The tool uses the existing evdev BTN_TOOL_PEN_ constant `0x140`; in-range is properly derived from this key, independently of tip contact. Regression tests now cover the strict code-0x140 lookup and captured hover-contact-lift-leave sampling using the measured axis bounds.

Input compatibility is covered by `runtime/xnuhost/tests/test_xnuhost.c` and the `xnuhost-input` SM8850 CI job. These are host tests of simulated events, **not** real guest iOS pen rendering, pressure, handwriting or side-button usability.

## Scope and boundaries of the SM8850 development branch

- Added CPU topology regression fixture from measured SM8850 sysfs and companion OneOS submodule fork/branch wiring.
- Preserved the original strict S Pen detection: the `BTN_DIGI` label in Android `getevent` and `BTN_TOOL_PEN` in OneiOS both mean Linux key `0x140`. Added regression tests grounded in the live hover/contact/lift trace; reverted the unnecessary tool-less lookup exception.
- Added a change to xnuhost's touchscreen selection to prefer a genuine direct `sec_touchscreen` over direct virtual touch devices from connected wearables, with dedicated tests and a SM8850 CI job.
- Display and backlight findings are **documented**, with a new passive `brightctl inspect` tool and host fixture tests. The on-phone display driver, brightness output and touch-power writes have **not** been tested. `displayctl test` now explicitly refuses the session-only `--takeover` flag, so visual tests can overlay a temporary pattern without changing display modes or invoking hot-switch.
- No modifications to XNU, kernel patches, GPU driver behavior or the Android kernel. OneOS still blocks hot-switch on SM8850 until independent recovery verification. A green host CI suite is not proof of real-phone pen, touch, graphics, iOS boot, or safe recovery.

Companion: https://github.com/YMGPwcca/OneOS/tree/feat/oneios-sm8850-m3q