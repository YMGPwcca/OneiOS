// SPDX-License-Identifier: MIT
// Opt-in, bounded task-process counters for XNUHost's guest task Linux processes.
// Each event updates one atomic u64. There is no allocation or per-event logging.
// The final bucket represents calls made outside vCPU threads (map/service host calls).
#ifndef XNUHOST_TASK_PROFILE_H
#define XNUHOST_TASK_PROFILE_H

#include <stdint.h>
#include "xnuhost.h"

enum {
  XH_TP_TRAP_SYSCALL,
  XH_TP_TRAP_FAULT,
  XH_TP_TRAP_INTERRUPT,
  XH_TP_TRAP_OTHER,
  XH_TP_MAP_DEFERRED,
  XH_TP_MAP_ORDERED,
  XH_TP_UNMAP_DEFERRED,
  XH_TP_UNMAP_ORDERED,
  XH_TP_HOST_FUTEX_WAIT,
  XH_TP_TASK_FUTEX_SLEEP,
  XH_TP_EVENTS
};
enum { XH_TP_BUCKETS = XH_MAX_CPUS + 1, XH_TP_HOST_BUCKET = XH_MAX_CPUS };

typedef struct {
  uint64_t events[XH_TP_BUCKETS][XH_TP_EVENTS];
} xh_task_profile;

static inline void xh_task_profile_add(xh_task_profile *profile, unsigned cpu, unsigned event)
{
  if (!profile || event >= XH_TP_EVENTS) return;
  if (cpu >= XH_MAX_CPUS) cpu = XH_TP_HOST_BUCKET;
  __atomic_fetch_add(&profile->events[cpu][event], 1, __ATOMIC_RELAXED);
}

static inline uint64_t xh_task_profile_read(const xh_task_profile *profile, unsigned cpu, unsigned event)
{
  if (!profile || event >= XH_TP_EVENTS) return 0;
  if (cpu >= XH_MAX_CPUS) cpu = XH_TP_HOST_BUCKET;
  return __atomic_load_n(&profile->events[cpu][event], __ATOMIC_RELAXED);
}

#endif
