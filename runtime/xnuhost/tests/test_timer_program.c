// SPDX-License-Identifier: MIT
#define _POSIX_C_SOURCE 200809L
#include "timer_program.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
static void check_zero(timer_t t)
{
  struct itimerspec got;
  CHECK(timer_gettime(t, &got) == 0);
  CHECK(!got.it_value.tv_sec && !got.it_value.tv_nsec && !got.it_interval.tv_sec && !got.it_interval.tv_nsec);
}
int main(void)
{
  timer_t t;
  sigset_t mask; sigemptyset(&mask); sigaddset(&mask, SIGUSR1);
  CHECK(sigprocmask(SIG_BLOCK, &mask, NULL) == 0);
  struct sigevent event = { .sigev_notify = SIGEV_SIGNAL, .sigev_signo = SIGUSR1 };
  struct itimerspec zero = {0}, future = { .it_value = { .tv_sec = 60 } }, invalid = { .it_value = { .tv_nsec = 1000000000L } };
  uint64_t calls = 0;
  bool skipped;
  unsigned state = XH_TIMER_UNKNOWN;
  CHECK(timer_create(CLOCK_MONOTONIC, &event, &t) == 0);
  check_zero(t);
  // Unknown state must actually program the kernel, even for zero.
  CHECK(xh_timer_apply(&state,t,&zero,&calls,&skipped) == 0 && !skipped && calls == 1 && state == XH_TIMER_ZERO);
  for (unsigned i = 0; i < 10000; i++) {
    CHECK(xh_timer_apply(&state,t,&zero,&calls,&skipped) == 0 && skipped && calls == 1);
  }
  check_zero(t);
  CHECK(!xh_timer_future_programmed(state));
  CHECK(xh_timer_apply(&state,t,&future,&calls,&skipped) == 0 && !skipped && calls == 2 && xh_timer_future_programmed(state));
  struct itimerspec got;
  CHECK(timer_gettime(t,&got) == 0 && got.it_value.tv_sec > 0);
  // Failure must not manufacture a disarm or make a future request reusable.
  CHECK(xh_timer_apply(&state,t,&invalid,&calls,&skipped) == -1 && errno == EINVAL && !skipped && calls == 3 && state == XH_TIMER_UNKNOWN);
  CHECK(!xh_timer_future_programmed(state));
  CHECK(timer_gettime(t,&got) == 0 && got.it_value.tv_sec > 0);
  CHECK(xh_timer_apply(&state,t,&zero,&calls,&skipped) == 0 && !skipped && calls == 4 && state == XH_TIMER_ZERO);
  check_zero(t);
  // Compare new calls with the old always-program rule for a fixed sequence.
  uint64_t before = calls;
  for (unsigned i = 0; i < 1000; i++) {
    CHECK(xh_timer_apply(&state,t,&future,&calls,&skipped) == 0 && !skipped && xh_timer_future_programmed(state));
    CHECK(xh_timer_apply(&state,t,&zero,&calls,&skipped) == 0 && !skipped && state == XH_TIMER_ZERO);
    CHECK(xh_timer_apply(&state,t,&zero,&calls,&skipped) == 0 && skipped);
    CHECK(xh_timer_apply(&state,t,&zero,&calls,&skipped) == 0 && skipped);
  }
  uint64_t sequence_calls = calls-before;
  CHECK(sequence_calls == 2000);
  check_zero(t);
  // Actual signal delivery after a cached disarm; expiry must not
  // create an inferred ZERO state or suppress programming the next arm.
  struct itimerspec soon = { .it_value = { .tv_nsec = 1000000 } };
  struct timespec timeout = { .tv_sec = 2 };
  CHECK(xh_timer_apply(&state,t,&soon,&calls,&skipped) == 0 && !skipped);
  CHECK(sigtimedwait(&mask,NULL,&timeout) == SIGUSR1);
  check_zero(t);
  CHECK(xh_timer_apply(&state,t,&zero,&calls,&skipped) == 0 && !skipped);
  CHECK(xh_timer_apply(&state,t,&zero,&calls,&skipped) == 0 && skipped);
  CHECK(xh_timer_apply(&state,t,&soon,&calls,&skipped) == 0 && !skipped);
  CHECK(sigtimedwait(&mask,NULL,&timeout) == SIGUSR1);
  CHECK(timer_delete(t) == 0);
  printf("host timer programming: %u checks, 0 failed; synthetic transition sequence: 4000 -> %llu host calls\n", checks, (unsigned long long)sequence_calls);
  return 0;
}
