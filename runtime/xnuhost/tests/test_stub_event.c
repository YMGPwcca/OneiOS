// SPDX-License-Identifier: MIT
// Exercise the exact event helpers with real, process-shared Linux futexes.
#define _GNU_SOURCE
#include "stub_event.h"
#include <assert.h>
#include <errno.h>
#include <linux/futex.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static long wait_for(uint32_t *word, uint32_t expected)
{
  const struct timespec step = { 5, 0 };
  return syscall(SYS_futex, word, FUTEX_WAIT, expected, &step, NULL, 0);
}

static void wake(uint32_t *word)
{
  assert(syscall(SYS_futex, word, FUTEX_WAKE, 1, NULL, NULL, 0) >= 0);
}

static void post(uint32_t *word, uint32_t value, const uint32_t *sleeping)
{
  if (xs_host_event_publish(word, value, sleeping)) wake(word);
}

static void stale_wait(uint32_t *word, uint32_t expected)
{
  errno = 0;
  assert(wait_for(word, expected) == -1 && errno == EAGAIN);
}

struct shared {
  uint32_t event, sleeping, release, map_result, trap_result;
};

int main(void)
{
  alarm(60);
  struct shared *s = mmap(NULL, sizeof *s, PROT_READ | PROT_WRITE,
                          MAP_SHARED | MAP_ANONYMOUS, -1, 0);
  assert(s != MAP_FAILED);
  // Deterministically cover the notification-before-enqueue race, both
  // transitions, and an ACK followed by a trap before the host observes it.
  uint32_t expected = xs_host_event_read(&s->event);
  assert(expected == XS_HOST_PENDING && !xs_host_event_has_ack(expected));
  s->map_result = 17;
  post(&s->event, XS_HOST_MAP_ACK, &s->sleeping);
  stale_wait(&s->event, expected);
  expected = xs_host_event_read(&s->event);
  assert(expected == XS_HOST_MAP_ACK && xs_host_event_has_ack(expected));
  assert(s->map_result == 17);
  post(&s->event, XS_HOST_TRAPPED, &s->sleeping);
  stale_wait(&s->event, expected);
  assert(xs_host_event_read(&s->event) == XS_HOST_TRAPPED);
  assert(xs_host_event_has_ack(XS_HOST_TRAPPED));
  stale_wait(&s->event, XS_HOST_PENDING);
  __atomic_store_n(&s->event, XS_HOST_PENDING, __ATOMIC_RELEASE);

  enum { ROUNDS = 20000 };
  pid_t child = fork();
  assert(child >= 0);
  if (!child) {
    for (uint32_t i = 1; i <= ROUNDS; ++i) {
      uint32_t seq;
      while ((seq = __atomic_load_n(&s->release, __ATOMIC_ACQUIRE)) != i) {
        long rc = wait_for(&s->release, seq);
        assert(rc == 0 || (rc == -1 && (errno == EAGAIN || errno == EINTR)));
      }
      if (i & 1) { // queued map release
        s->map_result = i;
        post(&s->event, XS_HOST_MAP_ACK, &s->sleeping);
        if (i & 2) sched_yield();
      }
      s->trap_result = i;
      post(&s->event, XS_HOST_TRAPPED, &s->sleeping);
    }
    _exit(0);
  }
  for (uint32_t i = 1; i <= ROUNDS; ++i) {
    int draining = i & 1;
    __atomic_store_n(&s->event, XS_HOST_PENDING, __ATOMIC_RELEASE);
    __atomic_store_n(&s->release, i, __ATOMIC_RELEASE);
    wake(&s->release);
    __atomic_store_n(&s->sleeping, 1, __ATOMIC_RELAXED);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    for (;;) {
      const uint32_t event = xs_host_event_read(&s->event);
      if (draining && xs_host_event_has_ack(event)) {
        assert(s->map_result == i);
        draining = 0;
      }
      if (!draining && event == XS_HOST_TRAPPED) {
        assert(s->trap_result == i);
        break;
      }
      long rc = wait_for(&s->event, event);
      assert(rc == 0 || (rc == -1 && (errno == EAGAIN || errno == EINTR)));
    }
    __atomic_store_n(&s->sleeping, 0, __ATOMIC_RELAXED);
  }
  int status;
  assert(waitpid(child, &status, 0) == child && WIFEXITED(status) && WEXITSTATUS(status) == 0);
  assert(munmap(s, sizeof *s) == 0);
  puts("STUB_HOST_EVENT=PASS stale-wait ACK/trap, coalesced event, 20000 cross-process releases");
  return 0;
}
