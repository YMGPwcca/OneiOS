# Phase 4B image and host boot readiness

> **Historical 2026-11 readiness phase:** staging later advanced to a
> successful isolated F2FS/BusyBox mount probe and verified one-shot
> APFS Data rearm. A separate root-only full experiment physically
> booted the iOS 27.0.1 guest and posted its first frame for ~600.6 s.
> The earlier "stage untouched / boot blocked" reports remain valid
> *at the time they were made*, not current. Thermal, watchdog and
> unassisted return qualification are still open.
> [Live status](SM8850_LIVE_STATUS_2026-11-20.md).


This validation targets iOS 27.0.1 build `24A446`, iPhone18,2 / v54ap /
T8150 / arm64e. OneOS uses image format 1 and session ABI 1. The checks run
on CachyOS x86_64. S26 switch authorization stays disabled.

## Validation checklist

1. Verify the local member inventory against the profile and cached Apple
   BuildManifest erase identity. Check the two decrypted images against their
   local recorded hashes and sizes.
2. Decode the kernelcache and device tree into a new output directory. Match
   the decoded kernelcache to the kernel profile's independent SHA-256 pin.
3. Build a hosted XNU and RELEASE reference from source. Prelink with the
   pinned Apple cache and run the binding audit.
4. Build the format 1 set, verify the APFS metadata and chunk hashes, then
   pack and verify the same manifest in the archive.
5. Pair the image with the source-built ABI 1 runtime. Check the runtime
   assets, fileset and independent build record before attempting a local boot.
6. Observe Data seed verification, launchd, backboardd and the guest-ready
   marker under QEMU user mode. Keep this result scoped to the tested host
   pair. Track phone staging and physical recovery as separate blockers.

## Results

| Step | Status | Evidence |
| --- | --- | --- |
| Fetch inputs | PASS | Local 24A446 cache covers the pinned members. The cached BuildManifest names iPhone18,2 and v54ap's Customer Erase identity with chip `0x8150` and board `0x0e`. The 11 available unencrypted members match the profile's size and digest pins. The original full IPSW is absent and was unnecessary. |
| Decrypt | PASS for cached outputs | The two raw APFS images match the recorded plain sizes and SHA-256 values. A new AEA key-service request and decryption were unnecessary. AEA BuildManifest digests are component metadata and are not whole-file SHA-384 values. |
| Kernel inputs | PASS | Independent decode produced the 78,135,296-byte pinned kernelcache and a 363,936-byte device tree. The decoded kernelcache SHA-256 is `349c4692a6a85df0d396681f28d2d48dc04b95c6d60df0f94d84501e3d0c57e3`. |
| Hosted XNU | PASS | A separate `HOSTED_OUT=phase4b` source build produced the native kernel and RELEASE reference. The native kernel with its hosted fixups is 24,790,920 bytes. |
| Prelink and `kernel.kc` | PASS | The fresh native build produced a 96,059,392-byte arm64e `MH_FILESET` with 135 entries. The audit reported 2,711 paired targets, 93 listed stubs, nine unpaired data targets and zero audit failures. Host boot is the separate runtime qualification. |
| Image build and verify | PASS | The fresh set has 21 files and 17,862,597,913 logical bytes. It includes three APFS disks, the Data seed, the hashed collection, all three trustcaches, and all three root hashes. A separate strict pass pairs the unpacked set with the runtime and the archive by digest. |
| Stage | BLOCKED on the phone | Offline importer tests use synthetic fixtures. The real archive stays local. The S26 stage and activation gates were untouched. |
| Boot | PASS for the host bench path | The fresh pair reached the verified Data seed at 176.279 s, launchd's early-boot completion at 195.306 s, backboardd's framebuffer open at 285.832 s, and a contentful first frame at 321.951 s. The host stopped the benchmark after readiness. Host execution does not qualify device-specific display, watchdog ownership or Gates A/B/C. |

The existing kernel could also be independently re-prelinked. That run
reproduced the previous 96,043,008-byte collection byte-for-byte and
booted to a contentful first frame under QEMU. The fresh source build
produced a different collection. `out/phase4b/readiness.json` records the
fresh pair and archive digests, the boot milestones and the remaining
physical blockers. `out/phase4b/fresh-boot/boot.log` is the corresponding
console log. The host boot uses the normal image hook with optional Metal,
camera and guest helper bundles excluded.

## Reproduce the local build

Run from the parent repository with an unused output name. Keep the IPSW,
decrypted files, kernel collections and archives under ignored directories.
The profile requires 30 GiB free during a full member fetch and decryption.
The additional archive uses about 11 GiB, plus scratch and guest Data.
Keeping inputs and output on the same filesystem lets the builder hard-link
the raw images.

```sh
profile='profiles/ios-27.0.1-iPhone18,2.toml'
work="$PWD/out/phase4b-repro"
mkdir -p "$work"
export CARGO_NET_OFFLINE=true

# Offline checks. A populated Rust cache is needed for --offline.
cargo test --offline --locked --manifest-path tools/oneios-tool/Cargo.toml --workspace
scripts/image/tests/run.sh
JOBS=4 scripts/ci-local.sh all 0.0.0-phase4b-repro

# A cached 24A446 input directory avoids all bulk downloads.
(cd inputs/24A446 && sha256sum -c SHA256SUMS)
OUT="$work/kernel-inputs" scripts/image/kernel-inputs.sh "$profile"

HOSTED_OUT=phase4b-repro XNU_FILESET_REFERENCE=1 JOBS=4 kernel/build-hosted.sh
X18=1 OUT="$work/prelink" \
  KERNEL="$PWD/out/kernel/current-hosted-phase4b-repro/xnu.macho" \
  REFERENCE="$PWD/out/kernel/current-hosted-phase4b-repro/reference.macho" \
  KERNELCACHE="$work/kernel-inputs/kernelcache.macho" \
  kernel/prelink/build.sh

OUT="$work/image" \
  ONEIOS_HELPERS="$work/no-helpers" ONEIOS_METAL_PLUGIN="$work/no-metal" \
  ONEIOS_CAMERA_PLUGIN="$work/no-camera" \
  scripts/image/build.sh "$profile" --kernel "$work/prelink/kernel.kc"

(cd out/release && sha256sum -c oneios-runtime-0.0.0-phase4b-repro-arm64.tar.zst.sha256)
mkdir "$work/runtime"
zstd -dc out/release/oneios-runtime-0.0.0-phase4b-repro-arm64.tar.zst |
  tar -xf - -C "$work/runtime"

archive="$work/image/OneiOS_iOS27.0.1_24A446_iPhone18-2.tar.zst"
python3 scripts/image/verify-boot.py "$work/image/24A446" --runtime "$work/runtime" \
  --kernel-record "$work/prelink/kernel.kc.build.json" \
  --inputs-record inputs/24A446/inputs.json --archive "$archive" > "$work/compatibility.json"
```

If inputs are missing, run `scripts/fetch/fetch.sh --list "$profile"` to
check the pinned Apple URL, ZIP directory and BuildManifest before spending
bandwidth. Verify free space with `df -h inputs`. Then use
`scripts/fetch/fetch.sh "$profile"` to fetch only the profile's named
members and decrypt the two AEA volumes. The complete IPSW is unnecessary.
The kernel-only decode can fetch just the kernelcache, device tree and
BuildManifest when needed. See [building](building.md) for the pinned tools
and [format 1](image-format.md) for the on-disk contract.

## Reproduce the local guest boot

Use the verified unpacked pair and a new writable Data directory. Linux
Bubblewrap supplies a minimal `/dev`, an isolated network and PID namespace,
read-only image and runtime binds, and a writable local run directory.

```sh
mkdir "$work/boot"
mkdir "$work/boot/data" "$work/boot/session"
ulimit -c 0
bwrap --unshare-all --die-with-parent --clearenv --setenv PATH /usr/bin \
  --ro-bind /usr /usr --symlink usr/bin /bin \
  --symlink usr/lib /lib --symlink usr/lib /lib64 \
  --dev /dev --proc /proc --tmpfs /tmp \
  --ro-bind "$work/image/24A446" /image --ro-bind "$work/runtime" /runtime \
  --bind "$work/boot" /run --chdir /run \
  /usr/bin/timeout -s TERM -k 8 900 /usr/bin/qemu-aarch64 -cpu cortex-a710 \
  /runtime/bin/xnuhost --session-abi 1 --mode bench --runtime /runtime \
  --image /image --data /run/data --session /run/session \
  --cpus 8 --ram 4G --display none --no-input --set clusters=EEPPPPPP \
  --boot-args 'debug=0x14e serial=3 -v kt_fixed_zones=120 -no_slto_panic ml-timeout-lock-panic-scale=40 tlto_us=0 armcpu-self-ipi=1 armcpu-spi-ipi=1 use_contiguous_hint=0 interrupt-masked-debug-mode=0 sched_preemption_disable_debug_mode=0 wdt=-1 sheng-smp=1 oneios-data-wait=3000' \
  > "$work/boot/boot.log" 2>&1
```

Inspect `boot.log` for the Data seed verification, launchd's early-boot
completion, backboardd opening its framebuffer, and `guest ready: first
frame (it has content)`. A timed stop after guest readiness is a host test boundary.
A build exit, a successful Mach-O load or the synthetic test kernel by
itself does not establish iOS userspace execution.
