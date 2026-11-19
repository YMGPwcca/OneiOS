# SM8850 iOS 27.0.1 GUI crash

## Confirmed failing operation

The four saved `backboardd` aborts on iPhone18,2 build 24A446 resolve
to the same QuartzCore call chain. The saved 2D and auto runs use
different cache slides. Subtracting each slide and using the call
instruction preceding the saved return address gives:

| Unslid address | Operation |
| --- | --- |
| `0x1845652bc` | `CA::OGL::AsynchronousNode::retain_surface` calls the context's IOSurface import. |
| `0x1845652dc` | The non-null wrapper returned by import is passed to `Context::push_surface`. |
| `0x1844640d8`–`0x184464104` | `push_surface` selects a context-local tracking list and looks for the exact wrapper pointer. |
| `0x1844642a8` | The pointer is absent. QuartzCore calls its assertion handler for `found != slist->end ()`, `ogl-context.cpp:1309`. |

The software vtable's import slot resolves to
`SWContext::create_surface_from_iosurface` at `0x1846c8718`. It wraps and
retains the IOSurface for finalization without inserting the wrapper in
the calling context's tracking list. The ordinary software allocator
calls `Context::track_surface`. The IOSurface retain and context
registration are separate ownership operations. The failing lookup is
for the QuartzCore wrapper pointer. The captures contain no numeric
IOSurface or virtio resource ID for that particular wrapper.

In the 2D run, `backboardd[52]` aborts at 4165.800 s and the new
`backboardd[257]` takes over the framebuffer. `SpringBoard[30]` exits
with SIGKILL and a backboardd-respawn reason. The same assertion recurs
at 4264.332 s in generation 257. The auto run shows the same pair of
QuartzCore frames in `backboardd[52]` and `backboardd[233]`. An earlier
`chronod` SIGABRT in the 2D capture has a different call stack.
[xnuhost 2D log](../out/sm8850/ios27-touch-2d-xnuhost.log) ·
[xnuhost auto log](../out/sm8850/ios27-touch-xnuhost.log)

## Renderer boundaries

| Capture | Host GPU | Guest addon | Saved evidence |
| --- | --- | --- | --- |
| Addon-off control | 2D | `sheng-gpu-addon=0` | Unrun. Confirm the explicit addon-off marker and absence of an addon mount or plug-in load. |
| Touch, 2D | 2D | Enabled | The saved log reports display only and an addon mount. |
| Touch, auto | Auto | Enabled | The saved log negotiates the DRM-native renderer. The plug-in loads, then backboardd reports no Vulkan device (`-3`). Successful 3D rendering remains unverified. |

The 2D capture reports display-only capabilities and has no recorded
Turnip device initialization failure. It reaches the same software
wrapper assertion. The addon-off case is unrun. The saved host runs
terminate on the bench timeout.

## Vulkan initialization

The auto capture records host DRM capability negotiation at line 188
of `ios27-touch-xnuhost.log`. The effective boot arguments at line 35
omit `vgpu-3d=1`. Lines 704–709 show the Turnip dylib passing library
validation, followed by the open of the virtio client (`0x4149`) and
the failed opens of the legacy NativeAdreno client (`0x4147`,
`0xe00002d5` or `kIOReturnBusy`). The plug-in reports `-3` at line
716. The earlier Metal capture contains the same sequence.

NativeAdrenoMetal passes the bundle's `libvulkan_freedreno.dylib` path
to metal2vulkan. Ash loads Turnip's Darwin `vkGetInstanceProcAddr`
export directly. There is no manifest-based ICD selection on this path.
Turnip's `vkCreateInstance` installs the physical-device enumerator.
The first `vkEnumeratePhysicalDevices` call, which requests the device
count, runs this chain:

```text
vk_common_EnumeratePhysicalDevices
  → tu_enumerate_devices → tu_knl_darwin_load → dw_open_connection
  → dwv_board_default → GETPARAM(DEFAULT_3D)
  → IOServiceOpen(IOAcceleratorES, 0x4147)
  ← 0xe00002d5 → VK_ERROR_INITIALIZATION_FAILED (-3)
```

The staged guest source initializes the `DEFAULT_3D` reply to zero
when the boot argument is absent, independently of advertised virtio
features. Turnip then selects legacy NativeAdreno. Its
`dw_open_connection` maps the observed IOKit status to `-3` and Mesa
propagates it through enumeration. This source chain and a local replay
of the captured IOKit results identify the failing Vulkan operation.
The old capture has no direct Vulkan API trace. The failed enumeration
left this attempt without a selected Vulkan physical device or a
`vkCreateDevice` request. The saved host probe identified Adreno 840
chip `0x44050a00`, GPU ID `6860`, DRM capset 6, wire format 2 and MSM
1.12. The patched Turnip device table contains that exact chip ID.
The standalone host submission retired a fence with zero GPU faults or
async errors. It bypassed guest backend selection, Vulkan enumeration and
Turnip's logical device creation.

xnuhost now supplies `vgpu-3d=1` after it opens the host DRM-native
renderer when the effective boot arguments omit that switch. The
regression covers custom arguments, exact-token matching, explicit
`vgpu-3d=0`, repeat application, insufficient room and display-only
selection. The Turnip replay reaches the DRM-native open with the fixed
arguments and stops at that boundary.

For an instrumented build, guest boot argument `oneios-vk-init=1`
enables process-tagged stderr and Mesa diagnostics. They record the
Vulkan entry path, instance creation, enumeration, physical device
properties, device extension and feature selection, logical device
creation and the stages of DRM context initialization. Collect the
guest process diagnostics alongside the xnuhost log. The build applies
the diagnostics to local staged sources.

## Surface lifecycle replay

OneiOS's virtio resource IDs identify device resources and scanouts.
NativeAdrenoMetal's retained imports keep the referenced IOSurface
alive while its Metal wrapper or in-flight work still uses it.
Neither table owns QuartzCore's context-local software wrapper list.
The saved traces cannot correlate the failing wrapper to a host blob,
a virtio resource ID, or an Android SurfaceControl transaction.

Guest boot argument `oneios-surface-trace=1` logs NativeMetal's
IOSurface imports, cache ownership and texture release with process ID,
IOSurface ID and NativeMetal object identity. Host environment variable
`ONEIOS_GPU_TRACE=1` records virtio resource lifetimes, context and
owner IDs, queue generations, descriptor heads, and fence completions
and discards. Each new host resource lifetime receives a fresh trace
serial, including reuse of the same resource ID. The trace adds no
references to imported buffers or textures.

In the local native replay, context 6 attached and detached resource 11
owned by context 5. The attach and detach named the same resource
generation. Ring 1's fenced descriptors stayed pending until the
recording backend reported retirement. A reset during a capset command
discarded the old descriptor. Context 5 and resource 7 reappeared in
queue generation 2 with a new resource trace serial and completed on
the new queue.

The evidence establishes a OneiOS backend-selection bug (A) for GPU
initialization and a QuartzCore software registration failure in both
saved renderer configurations. A Vulkan failure can put the auto run
on the software path (B). The 2D capture establishes that an observed
Vulkan failure is unnecessary for the assertion. The missing
registration is consistent with a QuartzCore compatibility issue (C).
The private wrapper list remains invisible to both traces. An
addon-off capture and an accelerated guest capture are required to
determine what triggers the software import and whether acceleration
bypasses it during GUI use.

## Queue reset fix from `7227956`

A separate host reset race was reproduced with a recording backend.
A reset during a backend command could reinitialize the queue before
the GPU worker cleared the old tables. Reusing a context or resource
ID in that window could see the old ID and fail, or have the reset
tear down a newly created entry.

`runtime/xnuhost/src/virtio_gpu.c` now reconciles the state generation
under the command lock before either lane classifies or executes work.
Old queued work cannot update the new generation. The regression in
`runtime/xnuhost/tests/test_xnuhost.c` reuses the same IDs while a
command overlaps reset and checks that the old completion stays off
the new queue. This is a host-side fix with a local reproducer. The
saved guest assertion is still unresolved under the source-only
constraint.

## Local validation

- `JOBS=8 scripts/ci-local.sh test` passed. The native xnuhost suite
  passed 14,088 checks, including the queue reset and boot argument
  regressions. The Android ARM64 runtime ran its synthetic test kernel
  under QEMU.
- `ASAN_OPTIONS=detect_leaks=1 CYCLES=128 runtime/xnuhost/build/host/test_gpu_leaks`
  passed 4,022 checks with no LeakSanitizer findings. The KGSL calls
  ran against the test backend.
- Patched metal2vulkan initialized a logical Vulkan device on the
  Linux RADV host and logged the instance, enumeration, extensions,
  feature selection and device result. A missing loader path returned
  `LoaderNotFound`. An enumeration-only failure injection reported
  `vkCreateInstance=0` followed by `vkEnumeratePhysicalDevices=-3`
  and returned the same Vulkan error to the caller.
- The native trace replay used the test transport and renderer. The
  macOS IOSurface frontend tests require Apple's frameworks and the
  Linux host cannot run them.
- The arm64e iOS 27 Turnip dylib, Rust bridge and NativeAdrenoMetal
  plug-in cross-built locally. The shader smoke test, PAC branch
  rewrite and Mach-O checks against the target stubs passed. The
  instrumented bundle and addon are in
  `out/sm8850/gui-crash/local-validation/metal/`.

## APFS restore verification

A disposable sparse copy of the 8 GiB `data.img` and
`unique-chip-id` passed the saved SHA-256 manifest. It was verified
offline with read-only input and a read-only FUSE mount. Block 0 still
points to xid 2898, whose object-map block was subsequently reused.
The checkpoint-aware OneiOS reader opened Data at xid 3172 (container
superblock block 20) and checked 3,320 volume tree nodes. Xids 3163
through 3172 passed the container and volume checks. `apfsutil`
independently located Data, and OneiOS and apfs-fuse returned identical
bytes for `/.oneios-seed`.

The file read pass traversed 28,358 directories and read 12,453 files
totaling 2,142,878,991 bytes. Fourteen `.atx` files returned `EIO` from
apfs-fuse. Their inodes carry `com.apple.decmpfs` methods `0x0f` and
`0x10` (six inline and eight with resource forks). The independent
OneiOS file lookup did not recover those entries by path. An earlier
bulk extraction to NTFS stopped at a literal asterisk in a filename,
which is a scratch destination restriction. The container and recent
checkpoints are readable. Full restore readiness remains unverified
pending a reader that can decode those entries and a restore check on
compatible APFS tooling. The guest boot gate remains closed.

## Preservation

The experimental assembly and incomplete matrix-test draft were
archived under `out/sm8850/gui-crash/preserved-experiment.ObMlkH` and
are outside build inputs. Neither was applied. The previous read-only
cache mount was released.

The captured phone Data and saved backup were used only as provenance.
All current filesystem checks ran on the offline copy. Any later phone
matrix requires a verified restore, an independent working Data store
and the original bench admission checks.
