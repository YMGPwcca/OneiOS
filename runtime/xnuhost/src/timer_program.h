// SPDX-License-Identifier: MIT
#ifndef XH_TIMER_PROGRAM_H
#define XH_TIMER_PROGRAM_H
#include <stdbool.h>
#include <stdint.h>
#include <time.h>

// The vCPU owner is the sole programmer of its one-shot POSIX timer.
// This records successful requests, not the guest virtual timer line.
// Expiry alone does not update the cache; a failed syscall invalidates it.
enum xh_timer_program { XH_TIMER_UNKNOWN, XH_TIMER_ZERO, XH_TIMER_NONZERO };
static inline bool xh_timer_future_programmed(unsigned state)
{
  return state == XH_TIMER_NONZERO;
}
static inline int xh_timer_apply(unsigned *state, timer_t timer, const struct itimerspec *spec,
                                 uint64_t *calls, bool *skipped)
{
  bool zero = !spec->it_value.tv_sec && !spec->it_value.tv_nsec &&
              !spec->it_interval.tv_sec && !spec->it_interval.tv_nsec;
  *skipped = zero && *state == XH_TIMER_ZERO;
  if (*skipped) return 0;
  ++*calls;
  int rc = timer_settime(timer, 0, spec, NULL);
  *state = rc ? XH_TIMER_UNKNOWN : zero ? XH_TIMER_ZERO : XH_TIMER_NONZERO;
  return rc;
}
#endif
