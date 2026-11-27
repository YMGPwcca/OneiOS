// SPDX-License-Identifier: MIT
#ifndef XNUHOST_TASK_ORDER_FAST_H
#define XNUHOST_TASK_ORDER_FAST_H
#include <stdbool.h>
#include <stdint.h>

// Caller owns both task order and queue locks and has verified the task
// is alive. Only a previously completed, now idle service can skip an
// empty flush; an unacknowledged order must take the existing slow path.
static inline bool xh_task_flush_can_skip(unsigned requested, unsigned pending,
                                         unsigned unmaps, bool unmaps_out,
                                         const uint32_t *request, const uint32_t *done)
{
  return !requested && !pending && !unmaps && !unmaps_out &&
         __atomic_load_n(done, __ATOMIC_ACQUIRE) == 1 &&
         __atomic_load_n(request, __ATOMIC_ACQUIRE) == 0;
}
#endif
