# Design for a no-copy SM8850 bench image adapter

**OneiOS · Galaxy S26 Ultra / SM8850 · Historical no-copy design exploration**

[← Handbook](README.md) · [Current status](SM8850_LIVE_STATUS_2026-11-20.md) · [Roadmap](TODO.md)

> [!NOTE]
> **Historical source or earlier experimental procedure.** The latest S26 Ultra full guest ran ~600.6 s with a displayed frame, but serious heat and unverified recovery remain open. Use the [physical ledger](SM8850_LIVE_STATUS_2026-11-20.md) for current decisions.

This design is separate from watchdog qualification and from the
implemented sparse/reflink staging path. It has no live enable flag.
Its goal is to reuse the existing verified iOS 27 benchmark files
without allocating another full image or opening the original APFS
Data file for writing.

## Admission and ownership

1. Quiesce the old bench and verify the original Data store and chip ID
   at stable file identities. Acquire a root-owned per-store session
   lock **before** certifying any backup or source bytes. All supported
   launchers must participate and must refuse a conflict. Inventory
   existing file descriptors and writable mappings. A cooperating
   advisory lock alone does not cover legacy launches and direct
   filesystem writers.
2. Require an off-device, restorable backup of `data.img` and
   `unique-chip-id`. Record the source logical sizes and whole-file
   SHA-256 values under exclusive access, including the sparse file's
   logical zero regions. Verify them against the read-back backup.
   Restore the backup to isolated scratch and verify the hashes again.
   Before each session, require the current original to match the
   backed-up generation. Retain the backup independently of either
   the experimental stage or the phone.
3. Enforce exclusion of alternative access to the Data store for the
   session. The candidate uses the per-store lock for authorized
   consumers and a kernel read lease on the original to prevent
   conflicting write opens and truncates through any name. Validate
   lease behavior and the question of preexisting Android mappings
   on the target. Require a verified kernel open-permission gate
   if alternate readers or noncooperating launchers can otherwise
   open the store, and pin the original path identity against rename
   so it cannot be swapped for a second store. On a host Btrfs fixture,
   a read lease blocked a writer through a hardlink and still allowed
   rename. [Host lease probe](../out/sm8850/watchdog-supervisor/storage-lease-host-probe.log)
   A lease break must trip the independent return and make the
   adapter stop serving Data before the kernel's forced
   break deadline. If timing, mandatory exclusion or SELinux cannot
   be established, refuse the adapter. Keep the original mode and
   ownership. A private read-only bind alone cannot exclude a writer
   through the original path.

## Private view

- Open and hash the exact approved base files once under the ownership
  checks. Pin their open descriptors. In the existing private mount
  namespace expose only the approved read-only ISO/APFS assets,
  kernel, trustcache, GPU addon and other sidecars. Reuse the checks
  and expected hashes from the 44-file benchmark manifest. Preserve
  the existing root-owned runtime and executable requirements. Small
  root-owned executable and manifest files can be staged separately.
  Protect all reused large sources against outside mutation with the
  same verified writer-exclusion mechanism or a verified immutable
  source. Compare hashes on the exact views the runtime consumes.
- Serve a fixed-size `data.img` regular-file view in a private FUSE
  mount. The read-only base FD always addresses the bench original.
  The only writable backing is a separate root-owned sparse overlay.
  Unwritten blocks read from the base. A partial update first reads
  the complete validated base block and commits the replacement in
  the overlay. Bind the overlay and its journal to the verified
  base hash and persist flush ordering. The approved chunk data is
  hashed before use, including the Data blocks used for partial
  writes. Keep the chip ID in the session's private Data folder.
  The current runtime requires the presented size from `fstat` and
  uses positional I/O and flush operations. It can therefore retain
  its existing Data-path contract when the mount implements those
  operations correctly. Test the actual validated bench binary too.
  [Runtime block I/O](../runtime/xnuhost/src/blk.c)
- Install the read-only mounts and the overlay only in the guest's
  private namespace, and ensure stage mount propagation is private.
  Verify no path in that namespace leads to a writable base, Android
  user data, or writable recovery controls. Never expose a writable
  hardlink or writable bind to the original.
- Retain at least 30 GiB free after staging the adapter. Before guest
  start require enough additional headroom for the overlay's
  separately budgeted maximum allocation, index and journal. Use a
  hard allocation ceiling and the existing runtime pressure monitor.
  If the ceiling or reserve would be crossed, reject further writes,
  retain the overlay and trigger device-side return. Do not weaken the
  existing copy path's reservations.

## Return and qualification

On return, stop new guest requests, terminate the guest, flush and
seal the overlay, then stop the adapter and verify private namespace
and mount cleanup. Release the backing-file exclusion only after
checking that the guest and adapter have gone. Preserve the overlay,
journal, hashes, and logs for review. Never merge it into the original
bench Data store automatically. A failed flush or a forced stop leaves
a partial overlay for inspection and an unchanged bench base.

Local acceptance must inject competing bench starts, direct writes
and renames through an alias, stale backup, symlink substitution,
partial blocks, flush and adapter failure, disk exhaustion, and
disconnection. The target must separately prove lease and private
mount behavior under enforcing SELinux, safe failure of attempted
outside writes, original Data hash stability and the 30 GiB reserve.
Lack of any of those proofs keeps the no-copy path disabled.
