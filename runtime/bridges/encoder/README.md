# runtime/bridges/encoder: the host video encoder

Owner: the encoder agent. The iOS/guest side: `kernel/patches/oneios-hosted/codec`. The whole path and the route:
`docs/hardware.md` section 7g ("Video encoder"). This is the host end of iOS's paravirtualized VideoToolbox
encoder, so CMPhoto writes HEIC: chronod's widget snapshots, screenshots, the photo library (then video later).

**State (2026-11-18):** host fake-encoder transport proved on PC (69 checks). On the S26 Ultra SM-S948B,
the SHA-verified, standalone `encctl` successfully encoded **one HEVC 256x256 keyframe+EOS** with
`c2.qti.hevc.encoder` (10533 bytes total) and **one H.264 640x480 keyframe+EOS** with
`c2.qti.avc.encoder` (11594 bytes) only after starting a native Binder callback threadpool.
The production `oneios-encoder --binder-preflight` passed. The production **UNIX socket round-trip**
has now also passed on the physical S26 for both codecs: `encctl --helper` reported 10533 B HEVC
(VPS + IDR 20 + EOS) and 11594 B H.264 (SPS + IDR 5 + EOS), both exit 0.
No iOS guest VideoToolbox, HEIC container or sustained multi-frame test has been verified on the S26.
The latest commit's full local CI status was not visible in the owner's abbreviated log.

```sh
make test          # host test: the device + socket + helper + stand-in, over the real transport (ASan, UBSan)
make               # build/android/{oneios-encoder, encctl, liboneencoder.a}   (NDK r28c)
```

## The parts

| File | What |
|---|---|
| `media_proto.h` | the wire layout of the `droidvm,virtio-media` device: the commandq (OPEN/CLOSE/IOCTL/MMAP), the eventq (DQBUF/EVENT), and the V4L2 structs (`v4l2_buffer`, `v4l2_format`) as UniXNU-droidvm's `DroidVMVirtioMedia.c`/`DroidVMVTHost.cpp` read them |
| `media_device.c` | xnuhost's stateful V4L2 **encoder** device on `xh_virtio_*`: OUTPUT = tightly packed NV12, CAPTURE = HEVC/H.264 Annex-B. Each guest session gets a slice of the media pool (`media-host-pool`); a worker thread turns coded access units into CAPTURE DQBUF events. `liboneencoder.a` (static, into xnuhost) |
| `encoder.h` | the backend interface (`open`/`feed`/`drain`/`poll`/`close`) and `br_encoder_create` |
| `backend_helper.c` | the device-side backend that runs the real encoder in the **oneios-encoder helper process** (xnuhost is static; MediaCodec is a shared library, as for the camera and audio helpers). Spawns the helper, multiplexes sessions over a UNIX socket (`encoder_link.h`), buffers coded AUs for `poll()` |
| `helper.c` → `oneios-encoder` | the helper: reads the device's messages, runs the backend, streams the bitstream back. Dynamic |
| `backend_ndk.c` | the real backend: the NDK's `AMediaCodec` (`video/hevc` → Codec2 `c2.qti.hevc.encoder`, `video/avc`), NV12 ByteBuffer input, Annex-B output. Still-image settings: one keyframe, constant quality. Both the `samsung` and `treble` hardware backends use this same path |
| `backend_stub.c` | the PC stand-in: the box has no MediaCodec, so it emits a structurally valid HEVC/H.264 Annex-B access unit (VPS/SPS/PPS + IDR) sized to the frame, the IDR body carrying the frame's dims and an NV12 checksum. It checks the path, it does not compress |
| `encctl.c` → `encctl` | standalone phone test: direct MediaCodec or `--helper PATH` through the full production socket backend, with a plain-memory virtio guest and no iOS session |
| `tests/test_encoder.c` | the host test (above) |

## Into xnuhost

`liboneencoder.a` links into xnuhost (static). `main.c` carves the media pool (after the GPU pool, inside the 64 MiB
the hosted kernel lets a task map, `0024-gpu-pool.patch`), creates the device over `br_encoder_backend_helper`, and
publishes `/arm-io/virtio-media-0` with `media-host-pool`. Ship `build/android/oneios-encoder` as `bin/oneios-encoder`
(0755) in the runtime package. Off by default: `encoder=auto` turns it on (and adds `droidvm-vt-paravirt=1` to the
guest), once the guest codec archive is in `kernel.kc`.

## CLAUDE.md's bridge rules

- **One replaceable lookup, read-only to the system:** the device touches only its own media pool and the socket to
  the helper; the helper opens Android's MediaCodec and nothing of One UI's `/data`.
- **No realtime threads:** the device's worker is an ordinary `SCHED_OTHER` thread; the helper is a plain process.
- **Closed at the return:** the device's `reset` closes every encoder session; closing the socket ends the helper (it
  exits when its `read` returns 0), and MediaCodec is released per session. Nothing is grabbed, nothing persists.

## On the phone

On the **S26 Ultra**, keep One UI and `system_server` running. Stage SHA-matched `encctl` and
`oneios-encoder` binaries from the same locally verified runtime archive and invoke using
**absolute device paths** (KernelSU multiline `su -c` quoting has previously failed):

```sh
# Direct path already verified: client executable itself owns the Binder threadpool.
adb shell "su -c 'ONEIOS_ENCODER_BINDER_POOL=1 timeout 20 /data/local/tmp/encctl hevc 256 256'"

# New production end-to-end path: only the child oneios-encoder starts Binder.
adb shell "su -c 'timeout 25 /data/local/tmp/encctl --helper /data/local/tmp/oneios-encoder hevc 256 256'"
adb shell "su -c 'timeout 25 /data/local/tmp/encctl --helper /data/local/tmp/oneios-encoder h264 640 480'"
```

`encctl --helper` drives the real V4L2-shaped virtio-media device, opens its
`backend_helper.c` UNIX socket, spawns the real production `oneios-encoder`
(which starts its own Binder callback pool), feeds NV12, and verifies that coded
CAPTURE NAL bytes and EOS return through both boundaries. A 5-second event timeout,
missing coded bytes, keyframe or EOS is **FAIL**, not a PASS.
The backend helper socket uses `SOCK_CLOEXEC` so the child cannot keep the
parent endpoint alive after the parent exits. Test only after local CI PASS;
the iOS guest switch/return path remains blocked until independent recovery proof.

`encctl` encodes one NV12 test pattern and prints, on a pass: each access unit's size and first NAL type, and
`encctl: hevc 256x256: N access unit(s), M bytes, keyframe present; ok`. `error:` lines say which step failed
(`S_FMT`, `no output buffer`, or `N access units, ... key 0`: MediaCodec refused NV12 ByteBuffer input — then try
`encctl` with a larger size, since `c2.qti` encoders have a 96x96 minimum). It is harmless beside One UI (it opens
its own MediaCodec instance; it touches nothing of One UI's). The device library and the helper have not been run on
the phone yet.

## Failure-path hardening (2026-11-18)

The production helper must never send a fake `ENC_MSG_EOS` after a drain deadline.
It sends the existing `ENC_MSG_ERROR` with a positive errno in message field `a`
for backend feed, drain, poll and bounded drain-timeout failures, and treats a
failed session as terminal. The device-side socket backend converts that into
`-errno`, and the virtio-media worker emits exactly one `MEDIA_EVT_ERROR` instead
of EOS. `MSG_NOSIGNAL` prevents a dead helper from killing xnuhost with SIGPIPE.
An independent host fault-injection regression checks feed/drain/poll/timeout and
unexpected helper exit. This patch makes failures explicit; **multi-frame video
and true output EOS robustness remain unverified until device tests**.
