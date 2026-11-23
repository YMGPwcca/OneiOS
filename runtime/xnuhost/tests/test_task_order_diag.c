// SPDX-License-Identifier: MIT
// Regression for order(t, NULL, 0) timeout / slow-report diagnostics.
// Pure host test: never launches a guest or accesses a phone.
#include <errno.h>
#include <stdio.h>
#include "../stub/stub_abi.h"
#include "../src/task_order_diag.h"

static unsigned checks, failures;
#define CHECK(expr) do { checks++; if (!(expr)) { failures++; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #expr); } } while (0)

int main(void)
{
  const struct xs_op pending[] = {
    { .op = XS_OP_MAP, .va = 0x1000, .size = 0x1000 },
    { .op = XS_OP_UNMAP, .va = 0x2000, .size = 0x1000 }
  };
  const struct xs_op requested[] = { { .op = XS_OP_PROTECT, .va = 0x3000, .size = 0x1000 } };
  xh_task_order_diag d;

  // Normal successful flush is silent; success on the 999ms boundary is silent.
  d = xh_task_order_diag_make(NULL, 0, pending, 2, 0, 0);
  CHECK(!d.report && d.op == NULL);
  d = xh_task_order_diag_make(NULL, 0, pending, 2, 0, 999);
  CHECK(!d.report && d.op == NULL);

  // The previously crashing path: zero requested ops, NULL requested pointer.
  d = xh_task_order_diag_make(NULL, 0, pending, 2, -ETIMEDOUT, 10);
  CHECK(d.report && d.op == pending && d.deferred_count == 2 && d.requested_count == 0);
  CHECK(d.op && d.op->op == XS_OP_MAP && d.op->va == 0x1000);
  d = xh_task_order_diag_make(NULL, 0, pending, 2, 0, 1000);
  CHECK(d.report && d.op == pending && d.deferred_count == 2 && d.requested_count == 0);

  // A requested operation takes precedence over queued maps in diagnostics.
  d = xh_task_order_diag_make(requested, 1, pending, 2, -ESRCH, 1);
  CHECK(d.report && d.op == requested && d.deferred_count == 2 && d.requested_count == 1);
  CHECK(d.op->op == XS_OP_PROTECT);

  // No queued or direct ops: still report the timeout without dereferencing NULL.
  d = xh_task_order_diag_make(NULL, 0, NULL, 0, -ETIMEDOUT, 10);
  CHECK(d.report && d.op == NULL && d.deferred_count == 0 && d.requested_count == 0);
  d = xh_task_order_diag_make(NULL, 0, NULL, 0, 0, 1000);
  CHECK(d.report && d.op == NULL);
  d = xh_task_order_diag_make(NULL, 0, NULL, 0, 0, 999);
  CHECK(!d.report && d.op == NULL);

  // Defensive fallback when callers provide a count but no requested buffer.
  d = xh_task_order_diag_make(NULL, 1, pending, 2, -ETIMEDOUT, 10);
  CHECK(d.report && d.op == pending && d.requested_count == 1);

  if (failures) fprintf(stderr, "test_task_order_diag: %u/%u checks FAILED\n", failures, checks);
  else printf("test_task_order_diag: %u checks passed\n", checks);
  return failures ? 1 : 0;
}
