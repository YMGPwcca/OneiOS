// SPDX-License-Identifier: MIT
// Portable, allocation-free selection of a task service order's diagnostic source.
// The deferred-only flush calls order(t, NULL, 0), so a slow/error report must
// never assume requested[0] exists. This helper is intentionally not on the
// successful order hot path.
#ifndef XNUHOST_TASK_ORDER_DIAG_H
#define XNUHOST_TASK_ORDER_DIAG_H

#include <stdbool.h>

struct xs_op;

typedef struct {
  const struct xs_op *op;       // requested op, or first deferred op, or NULL
  unsigned deferred_count;
  unsigned requested_count;
  bool report;
} xh_task_order_diag;

static inline xh_task_order_diag xh_task_order_diag_make(
    const struct xs_op *requested, unsigned requested_count,
    const struct xs_op *service_ops, unsigned deferred_count,
    int wait_rc, long took_ms)
{
  xh_task_order_diag d = { 0 };
  if (!wait_rc && took_ms < 1000) return d;
  d.report = true;
  d.deferred_count = deferred_count;
  d.requested_count = requested_count;
  if (requested_count && requested) d.op = requested;
  else if (deferred_count && service_ops) d.op = service_ops;
  return d;
}

#endif
