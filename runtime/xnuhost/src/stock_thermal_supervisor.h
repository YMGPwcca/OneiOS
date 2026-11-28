/* SPDX-License-Identifier: MIT */
#ifndef XH_STOCK_THERMAL_SUPERVISOR_H
#define XH_STOCK_THERMAL_SUPERVISOR_H
#include "quiesce_supervisor.h"
#include "sm8850_thermal_controller.h"

/* External root-side owner only; never run in the guest-owned groups.
 * The production launcher must independently authenticate the endpoint,
 * pin exact session membership (including the display helper), supervise
 * source reads, and prove the outer producer gates. A supervisor ACK
 * covers GPU/block/display, not all board providers or stock services.
 * Never treat a guessed/constant verify callback as a production proof.
 * The caller owns the peer and groups; this adapter never closes them. */
struct xh_stock_supervisor {
  struct xhqs_owner *peer;
  struct oneios_owned_groups *groups;
  struct oneios_thermal_identity id;
  uint64_t session_deadline;
  int (*session_verify)(void *, const struct oneios_thermal_identity *);
  int (*outer_verify)(void *, bool parked);
  void *ctx;
};
int xh_stock_supervisor_bind(struct xh_stock_supervisor *,
    struct xhqs_owner *, struct oneios_owned_groups *,
    const struct oneios_thermal_identity *, uint64_t session_deadline,
    int (*session_verify)(void *, const struct oneios_thermal_identity *),
    int (*outer_verify)(void *, bool parked), void *ctx,
    struct oneios_thermal_ops *out);
#endif
