# GPU

**OneiOS · Galaxy S26 Ultra / SM8850 · Implementation reference**

[← Handbook](../../docs/README.md) · [Current evidence](../../docs/SM8850_LIVE_STATUS_2026-11-20.md)

Not owned by the bridges agent. The kernel side is UniXNU-droidvm's virtio-gpu 3D transport and NativeAdreno's user
client (unchanged); the host side is the 3D half of booter's `runtime/xnuhost/src/virtio_gpu.c` with virglrenderer's
`drm2kgsl` on `/dev/kgsl-3d0` (`docs/references.md` section 1, `docs/hardware.md` section 2).
