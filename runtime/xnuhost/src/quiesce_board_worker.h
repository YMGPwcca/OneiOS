/* SPDX-License-Identifier: MIT */
#ifndef XH_QUIESCE_BOARD_WORKER_H
#define XH_QUIESCE_BOARD_WORKER_H
#include "quiesce_board.h"
#include "quiesce_supervisor.h"

/* Real provider assembly for a sealed, supported XNUHost board.
 * Initialize with {0} once at a stable address. The trusted launcher
 * must pin the supervisor and actual display helper, prove full process
 * membership and lifetime, exclude unsupported non-VirtIO producers,
 * and independently authorize resume. No launcher/admission here.
 * The guard checks that external ownership, including through partial
 * release; it must not pretend a provider has parked. This worker
 * checks its own real tickets separately. Any failure is terminal;
 * do not start another worker or automatically release gates. */
struct xhqb_worker {
  struct xhq q;
  struct xhqb_binding binding;
  struct xhqs_worker ipc;
  uint64_t prepared_cycle;
  unsigned released;
  bool attempted, ready;
};
int xhqb_worker_init(struct xhqb_worker *, int control_fd, pid_t owner_pid,
    uid_t owner_uid, gid_t owner_gid, uint64_t owner,
    int helper_pidfd, uid_t helper_uid, gid_t helper_gid,
    int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase), void *);
/* Sole dedicated control thread. No per-frame activity. Returns only
 * on terminal failure/disconnect; no implicit thaw, kill or reboot.
 * A stopped/frozen worker needs an independently supervised owner. */
int xhqb_worker_run(struct xhqb_worker *);
void xhqb_worker_close(struct xhqb_worker *);
#endif
