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

| Case | Host GPU | Guest addon | Saved evidence |
| --- | --- | --- | --- |
| A | 2D | `sheng-gpu-addon=0` | Unrun. Require the explicit addon-off marker and no successful addon mount or plug-in load. |
| B | 2D | Enabled | The saved log reports display only and an addon mount. It offers no guest 3D accelerator. |
| C | Auto | Enabled | The saved log negotiates the DRM-native renderer. The plug-in loads, then backboardd reports no Vulkan device (`-3`). Successful 3D rendering remains unverified. |

The 2D capture establishes that the assertion occurs without a working
3D device. It does not establish whether the addon-off case reaches the
same path. The saved host runs terminate on the bench timeout and
contain no host SIGABRT corresponding to the guest assertion.

OneiOS's virtio resource IDs identify device resources and scanouts.
NativeAdrenoMetal's retained imports keep the referenced IOSurface
alive while its Metal wrapper or in-flight work still uses it.
Neither table owns QuartzCore's context-local software wrapper list.
The saved traces cannot correlate the failing wrapper to a host blob,
a virtio resource ID, or an Android SurfaceControl transaction.

## Source-level change

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

## Preservation and validation limits

The experimental assembly and incomplete matrix-test draft were
archived under `out/sm8850/gui-crash/preserved-experiment.ObMlkH` and
are outside build inputs. Neither was applied. The previous read-only
cache mount was released.

The off-device copy of the 8 GiB APFS Data file and its chip ID matches
the phone's SHA-256 and file identity records from both sides of the
transfer. Offline APFS readers could not open a usable volume from
that copy, so its restore path is unverified. The results do not clear
guest staging. No phone guest was launched during this investigation.

For a future local investigation, correlate each new renderer
generation's context and resource events during trace replay, and
keep case A's addon evidence separate from the host's 2D report.
Any later phone matrix requires a verified restore, an independent
working Data store, and the original bench admission checks.
