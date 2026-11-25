// SPDX-License-Identifier: MIT
#ifndef XNUHOST_STUB_EVENT_H
#define XNUHOST_STUB_EVENT_H
#include <stdint.h>

// One writer (the non-nesting stub handler), reset by its owning vCPU
// before release. TRAPPED subsumes MAP_ACK: all queued operations finish
// before the handler resumes guest code, which can then trap again.
enum xs_host_event {
  XS_HOST_PENDING = 0,
  XS_HOST_TRAPPED = 1,
  XS_HOST_MAP_ACK = 2,
};

static inline uint32_t xs_host_event_read(const uint32_t *word)
{
  return __atomic_load_n(word, __ATOMIC_ACQUIRE);
}

static inline int xs_host_event_has_ack(uint32_t event)
{
  return event == XS_HOST_MAP_ACK || event == XS_HOST_TRAPPED;
}

// Publish both the payload and the event on the actual futex word. The
// caller wakes a sleeper; FUTEX_WAIT must compare its original snapshot,
// not a reloaded word, so publication before enqueue cannot be lost.
static inline int xs_host_event_publish(uint32_t *word, uint32_t event, const uint32_t *sleeping)
{
  __atomic_store_n(word, event, __ATOMIC_RELEASE);
  __atomic_thread_fence(__ATOMIC_SEQ_CST);
  return __atomic_load_n(sleeping, __ATOMIC_RELAXED) != 0;
}
#endif
