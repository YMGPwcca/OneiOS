# SM8850 GPU bench: isolated Data snapshot (no guest run)

**OneiOS · Galaxy S26 Ultra / SM8850 · One-shot APFS Data and snapshot policy**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!NOTE]
> This page is earlier device evidence or an experimental design record. Compare with the [latest physical status](SM8850_LIVE_STATUS_2026-11-20.md); do not infer current safety or performance from a historical PASS.

The standalone physical Adreno acceptance is `HOST_ADRENO=PASS`. The remaining iOS
Turnip and QuartzCore results are unverified. The phone's benchmark
`xnuhost-gui-bench` binary does **not** match the current source-built
`runtime/xnuhost/build/android/xnuhost`; the phone's GPU addon matches the
older `out/userland/NativeAdrenoMetal.gpuaddon`, not the instrumented
`out/sm8850/gui-crash/local-validation/metal/NativeAdrenoMetal.gpuaddon`.
Those artifacts and their owner-trust CDHashes must be qualified separately.

This stage snapshots the **current existing** 8 GiB APFS Data image plus its 8-byte
chip ID into a new root-owned private directory with the verified sparse-copy
helper. It never boots a guest, remounts the image, invokes a switcher, or
operates a watchdog. The original Data file is opened for reading only. The
script validates preflight, sizes, single-link inode identities, SHA-256 before
and after copying, identical destination hashes, and the remaining 30 GiB plus
64 MiB storage reserve. It never deletes a partial snapshot; an interrupted
copy is quarantined by virtue of its fresh path and never marked ready.

## First: read-only plan

Connect the authorized S26 Ultra through USB while One UI is running:

```sh
cd ~/projects/OneiOS
export PATH="$HOME/Android/Sdk/platform-tools:$PATH"
python3 scripts/phone/test-sm8850-gpu-data-snapshot.py -v
python3 scripts/phone/sm8850-gpu-data-snapshot.py plan
```

The plan reports `COPY_ADMISSION=PASS` only when the same strict phone and asset
gates pass. This step writes only a local JSON report in
`out/sm8850/gpu-acceptance/`.

## Then: create an independent, disposable candidate

Only if the plan passes and the latest verified backup remains safely held
**off-device**, deliberately run:

```sh
python3 scripts/phone/sm8850-gpu-data-snapshot.py snapshot
```

To additionally pin the currently deployed source to **independent** hashes
obtained from the off-device verified backup manifest, provide both
`--expected-data-sha256` and `--expected-chip-sha256`. Never guess the hashes.
Without these arguments, the script still verifies a byte-identical snapshot
of the **current** Data source but does **not** certify that this source
matches the earlier off-device recovery backup.

The script compiles the existing `scripts/phone/framework-image-copy.c` with
Android NDK 28.2, pushes only the new helper to a nonce-specific temporary path,
then runs a bounded sparse copy into
`/data/adb/oneios-m3q-gpu-snapshot-<nonce>/data/`. The private directory is
root-owned, mode 0700, with Data files mode 0600. The source's original
permissions and bytes are untouched. The tool removes only the helper upload;
it **preserves** the private snapshot, its hashes and any partial stage for
forensic or recovery review. No automatic deletion of snapshots is provided.

`DATA_CLONE_READY=PASS` means this separate **copy** is hash-identical. It is
**not** evidence that boot-time APFS writes are safely isolated by every
possible launcher, that `owner-trust.json` accepts an updated addon, or that
an independent device return is available. The tool reports
`GUEST_RUN_READY=BLOCKED` regardless of clone success.

## Further mandatory gates

A future guest runner must use this candidate Data path exclusively, not the
world-writable old bench Data; it must preserve the original external backup,
select a source-built `xnuhost` incorporating `vgpu-3d=1`, construct a separate
image view containing the instrumented addon **and** matching owner-trust
CDHashes/trustcache/manifest, hold an exclusive session lock, enforce a device-
side hard deadline, verify recovery and never switch Android Framework.
The previously proposed no-copy/FUSE adapter is not enabled.
