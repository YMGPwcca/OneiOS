# OneiOS to-do

## SM8850 first full guest: current P0–P3 gate (2026-11-20)

**Real iOS 27.0.1 guest boot and first frame observed for ~600.6 s**, but
severe lag/heat, unresolved precise reboot-return provenance and an inactive
OneiOS thermal bridge in the `bench/bridges=0` profile block long-session
acceptance. Do not mark “full takeover PASS” or “60 FPS” based on boot markers.

- [ ] **P0:** read-only thermal telemetry and independently scoped thermal
  guard/fail-safe for the root-only touch-exclusive path; preserve kernel
  and vendor protection, no broad `bridges=1` or thermal override.
- [ ] **P0:** restore root only for **read-only** archived return/watcher
  evidence and verify the exact deadline requester / unassisted boot path.
- [ ] **P0:** truthful host receipts across ephemeral-root loss and durable
  CPU/GPU/display/thermal logs with per-session provenance.
- [ ] **P1:** isolate Spotlight cold-index load, task traps/futex/map/TLB
  overhead and any isolated 8-vCPU affinity improvement.
- [ ] **P2:** trace guest scanout/fences versus SurfaceFlinger post gaps,
  GPU imports/resources and frame copy expense; do not equate posts with FPS.
- [ ] **P3:** hugepage/page-table investigation and matched short-session
  benchmarks with local-first CachyOS CI before new hardware tests.

Full evidence, measured values and acceptance criteria:
[SM8850_LIVE_STATUS_2026-11-20.md](SM8850_LIVE_STATUS_2026-11-20.md).



Work that is known and wanted but not on the critical path to a first phone boot. The boot itself and its
blockers live in the board, [agents.md](agents.md), and the status in [../README.md](../README.md). Keep this list
short: an item here has a one-line what and why, and points at the file or doc that describes it.

## Bridges: follow Project Treble / GSI standards where a HAL is reachable

OneiOS runs as a Treble/GSI-style container: the switch stops the Android framework (zygote, system_server, apps)
but leaves the vendor HALs and `surfaceflinger`/`audioserver`/`cameraserver` running, and iOS's bridges become
their clients ([hardware.md](hardware.md)). Today the bridges are a mix:

- **Through the vendor HAL (Treble-standard), keep as is:** Bluetooth (HIDL `android.hardware.bluetooth@1.1`
  over hwbinder), camera (provider HAL + Camera2 NDK), GPU (KGSL), display (surfaceflinger).
- **Direct to a kernel node (below the HAL), because the owning HAL lives in the dead framework:** haptics (evdev
  FF), backlight (`/sys/class/backlight`), light sensor (evdev `als_rear`), touch/buttons (evdev), network
  (`/dev/tun`).

**To do:** audit each direct-node bridge and move it onto a vendor HAL that stays up in a session where one exists,
so the path is Treble-correct and portable to other devices. Known concrete case first:

- [ ] **Light sensor through the sensors HAL.** `als_rear` read by evdev returns 0 lux on the S24 (the rear ALS
  data goes through the sensor hub / SSC, not that evdev node; the front ALS is hub-only). The correct path is a
  direct client of the vendor sensors HAL (AIDL `android.hardware.sensors`), which keeps running when
  system_server is gone. See [hardware.md](hardware.md) section 7a and the `als_rear` facts. This is also what
  auto-brightness needs to reach CoreBrightness.
- [ ] Audit haptics, backlight, touch and network the same way: is there a vendor HAL that stays up in a session,
  and is the HAL or the kernel node the right surface for each? Record the verdict per bridge in `hardware.md`.
- [ ] Where a bridge must stay on a kernel node (no HAL survives the framework), note why in `hardware.md`, so the
      choice is deliberate and documented, not accidental.

**Why:** a HAL is the device-independent, vendor-maintained surface; a raw `/dev`/`/sys` node is device-specific
and can be fed by a different subsystem on another SoC (the ALS-vs-sensor-hub case). Using the HAL where one is
reachable makes OneiOS correct here and portable later.

## Make the iOS image on the phone, and user docs to build and change it for their own phones

The owner's request (2026-11-15). Today the image set and `kernel.kc` are made on a PC or a Mac and staged over USB.
Apple's files can never be in a release (CLAUDE.md), so each user must make them from Apple's own IPSW. The tools
that make them are already Rust (`oneios-tool`), so the OneOS app can run them on the phone. Do this when the kernel
stops changing every day.

- [ ] **`oneios-tool` for Android arm64.** Cross-build it with the NDK (the parts the phone needs: `remotezip`,
  `image`, `prelink`, `package`'s Apple-file check), ship it in the runtime release, and run it as root from the app.
  Check that its speed and memory fit on the phone (the Mac's prelink took 4 s).
  **State 2026-11-15:** it cross-builds (14.7 MB stripped); `oneios-tool serve` is merged (#52: one root process per
  flow, JSON lines, all cores at nice 10-19, the thermal stop). Shipping it in the runtime package is PR #49 (open,
  conflicts with main). Not run on the phone yet. `docs/newtodo.md` "Stopped 2026-11-15" has the detail.
- [ ] **Build the kernel on the phone too.** The default is to download our released `xnu.macho` (`kernel/publish.sh`,
  `kernel/release-kernel.txt`; open-source XNU and our patches, no Apple binaries). The phone must also build it
  itself, fast: port the Linux build (`kernel/build-linux.sh`: clang, lld, the XNU build system, MIG) to arm64
  Android (the NDK's or a bundled clang and lld), all 8 cores, ccache and incremental builds so that one patch
  rebuilds in minutes. Guess: a full build about 10-20 min on the S24 Ultra (the 4-CPU PC took 800 s, the Mac 186 s);
  measure it. Keep the phone cool: nice 19, never realtime, stop on the thermal line.
- [ ] **Build the iOS-side plug-ins on the phone (Metal, camera).** Today they need Xcode. On the phone: clang for
  arm64-apple-ios, `ld64.lld`, and the SDK's stubs made from the user's own IPSW (the dyld cache's exports as
  `.tbd` files, the headers we write or the open-source ones). Apple's SDK is never shipped. Not proven: check
  first that the plug-ins link and load this way on a PC.
- [ ] **The app's "Make iOS image" step,** in the same flow as the Android systems' screens (fork #5):
  **State 2026-11-15:** the app side is OneOS #10 (open, half done); the tool does steps 1, 2 and 4 (`download`,
  `fetch`/`zip-get`, `apfs-copy`, `prelink`) but not the root tweaks (Python, `not-ported`), `build.sh`'s order and
  checks (`make-image`) or the AEA decryption, so the step only shows those refusals today.
  1. download the runtime and `xnu.macho` from the OneiOS release (SHA-256 checked);
  2. fetch only the needed parts of the iOS 27 IPSW from Apple's server for the user (`remotezip`, no full 10 GB),
     or take an IPSW that the user gives;
  3. unpack the volumes (`image apfs-copy`), apply the root tweaks and write `xnuhost.conf` for the phone;
  4. prelink `kernel.kc` (`prelink`, then the audit and `stubs-check`);
  5. stage as today, with the same checks.
  Show the step, the space it needs, the time left and the reason when a step is refused. Keep the work and its
  temporary files in the stage, and remove them on a cancel or a failure.
- [ ] **Nothing has to stay on a PC or a Mac** (the owner, 2026-11-15): every step above runs on the phone itself,
  and fast. A PC or a Mac stays an option for developers, never a need.
- [ ] **User docs: build it and change it for your phone.** A short guide in plain steps, separate from the
  developer docs:
  - install the APK, download the runtime, make the iOS image in the app, switch, return;
  - the same steps on a PC or a Mac for those who want to (`docs/building.md` shortened);
  - change it for another phone: the hardware backends (`hw-backend=samsung|treble`, `docs/hardware.md` 7e), the
    device profile (what a new phone needs: SoC, GPU, kernel features, the side keys, the touch screen), the
    `xnuhost.conf` settings (RAM, the display, the S Pen), and how to report a session's logs (`oneios-tool phone
    log`, `cycle --only collect`);
  - what is safe to change and what must not change (the way back to One UI, CLAUDE.md's rules).
