#ifndef XH_QUIESCE_H
#define XH_QUIESCE_H

#include <stdint.h>

/* Offline coordination only. One serialized control worker owns this object
 * for a single session; no provider callback may reenter it. The independent
 * owner must enforce the absolute BOOTTIME deadline even if this worker blocks.
 * guard must independently attest immutable membership/lifetime, helper identity,
 * parked non-GPU shadow producers (including the boot console), prevention of
 * guest/reset mutations and other producer ingress, and resume authorization
 * in RESUME_CHECK/RESUMING. These proofs are NOT supplied by this module.
 * Keep those conditions through completion; never thaw on a fault. */
#define XHQ_MAX_BLOCKS 6u
#define XHQ_MAX_MEMBERS (XHQ_MAX_BLOCKS + 2u)
#define XHQ_GPU 0u
/* Block members are 1..nblocks; display is nblocks+1. */
enum xhq_phase {
  XHQ_IDLE, XHQ_CLOSING, XHQ_DRAINING, XHQ_DISPLAY_CLOSE, XHQ_VERIFY,
  XHQ_PARKED, XHQ_RESUME_CHECK, XHQ_RESUMING, XHQ_DONE, XHQ_FAULT
};
struct xhq_ops {
  int (*now)(void *, uint64_t *); /* CLOCK_BOOTTIME nanoseconds */
  int (*guard)(void *, uint64_t owner, uint64_t cycle, enum xhq_phase);
  int (*close)(void *, unsigned member, uint64_t *ticket);
  int (*poll)(void *, unsigned member, uint64_t ticket);
  int (*resume)(void *, unsigned member, uint64_t ticket);
};
struct xhq {
  struct xhq_ops ops;
  void *ctx;
  uint64_t owner, cycle, deadline, last_ns;
  uint64_t tickets[XHQ_MAX_MEMBERS];
  unsigned nblocks, closed, verified, resume_attempted, reopened;
  enum xhq_phase phase;
  int fault;
};
/* Initialize once, before use. No reset/reinit to recover a failed session. */
int xhq_init(struct xhq *, const struct xhq_ops *, void *, uint64_t owner, unsigned nblocks);
/* One deadline covers park, hold and resume; cannot extend or reuse a cycle. */
int xhq_begin(struct xhq *, uint64_t owner, uint64_t deadline_ns, uint64_t *cycle);
/* 0 = a fresh sequential parked receipt, or completed resume (inspect phase).
 * -EAGAIN = retry; other provider failures latch. Receipt is not atomic device
 * idle, APFS unmount, panel present, or thermal safety. */
int xhq_step(struct xhq *, uint64_t owner, uint64_t cycle);
int xhq_request_resume(struct xhq *, uint64_t owner, uint64_t cycle);

/* Actual runtime binding. Supply every configured block transport in creation
 * order and the 3D GPU; external guard is responsible for membership proof.
 * Neither this binding nor the core registers a live caller. */
struct xh_virtio;
struct xhq_runtime {
  struct xh_virtio *gpu, *blocks[XHQ_MAX_BLOCKS];
  unsigned nblocks;
  int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase);
  void *guard_ctx;
};
int xhq_runtime_init(struct xhq *, struct xhq_runtime *, uint64_t owner,
                     struct xh_virtio *gpu, struct xh_virtio *const *blocks,
                     unsigned nblocks, unsigned configured_ndisk,
                     int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase), void *);
#endif
