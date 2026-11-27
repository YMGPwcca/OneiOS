#ifndef XH_QUIESCE_BOARD_H
#define XH_QUIESCE_BOARD_H
#include "quiesce.h"
#include <stdbool.h>

/* The real VirtIO creation path records every mapped transport, not just
 * those with drain providers. One boot, one immutable membership; no rearm.
 * Other MMIO, non-VirtIO bridge work and guest execution are NOT covered. */
#define XHQB_MAX_DEVICES 32u
struct xhqb_member {
  struct xh_virtio *dev;
  uint64_t base;
  unsigned spi, type;
};
struct xhqb_snapshot {
  struct xhqb_member members[XHQB_MAX_DEVICES];
  unsigned count, nblocks;
  struct xh_virtio *gpu, *blocks[XHQ_MAX_BLOCKS];
};
int xhqb_begin(uint64_t first_base, uint64_t stride, unsigned first_spi, unsigned ndisk);
/* map() is the synchronous, non-reentrant MMIO registration callback.
 * Failed maps are not members. With no board begun, legacy mapping works.
 * Late mapped device creation is refused before mapping and latches fault. */
int xhqb_map(struct xh_virtio *, uint64_t base, unsigned spi, unsigned type,
             int (*map)(void *), void *);
int xhqb_seal(unsigned board_ndev);
int xhqb_snapshot(struct xhqb_snapshot *);
int xhqb_match(const struct xhqb_snapshot *);

/* Single boot-console writer holds the gate across compare, pixel writes
 * and flush notification. A closed gate defers the console update, not
 * guest input or GPU work. Control calls try-lock; no writer is killed.
 * One control owner; enter/leave must be paired in the same thread. */
bool xhqb_console_enter(void);
void xhqb_console_leave(void);
int xhqb_console_close(uint64_t *ticket);
int xhqb_console_poll(uint64_t ticket);
/* Only the external lifecycle owner may release after complete authorized
 * resume. Do not reopen on a partial receipt, owner loss or fault. */
int xhqb_console_resume(uint64_t ticket);

/* Binding uses the sealed actual board and an already parked console.
 * Caller must still independently verify helper identity, guest/reset,
 * remaining device/bridge/input producers, lifetime and authorization.
 * No production caller or thaw mechanism is installed. */
struct xhqb_binding {
  struct xhq_runtime runtime;
  struct xhqb_snapshot board;
  uint64_t console_ticket;
  int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase);
  void *ctx;
};
int xhqb_runtime_init(struct xhq *, struct xhqb_binding *, uint64_t owner,
                      uint64_t console_ticket,
                      int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase), void *);
#endif
