// SPDX-License-Identifier: MIT
// Opt-in, bounded task-process counters for XNUHost's guest task Linux processes.
// Each event updates one atomic u64. There is no allocation or per-event logging.
// The final bucket represents calls made outside vCPU threads (map/service host calls).
#ifndef XNUHOST_TASK_PROFILE_H
#define XNUHOST_TASK_PROFILE_H

#include <stdint.h>
#include <stdbool.h>
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

// Map/unmap queue observations occur only when perf-task=1.
// Bins: [1], [2-3], [4-7], ..., [128-255], [256+].  Each drain
// is counted once, so joined mappings do not masquerade as kernel calls.
enum { XH_TQ_DEPTH_BUCKETS = 9 };
enum xh_tq_reason {
  XH_TQ_MAP_QUEUE_FULL, XH_TQ_UNMAP_QUEUE_FULL,
  XH_TQ_UNMAP_TASK_RUNNING, XH_TQ_REASONS
};
typedef struct {
  uint64_t batches[2];                  // 0: carried by thread release; 1: service order
  uint64_t queued_ops[2];               // actual xs_op entries in the drained queue
  uint64_t queued_unmap_requests[2];    // logical unmap calls, before queue coalescing
  uint64_t depth_bins[2][XH_TQ_DEPTH_BUCKETS];
  uint64_t fallbacks[XH_TQ_REASONS];
} xh_task_queue_profile;

typedef struct {
  uint64_t events[XH_TP_BUCKETS][XH_TP_EVENTS];
  xh_task_queue_profile queue;
} xh_task_profile;

static inline unsigned xh_tq_depth_bucket(unsigned n)
{
  if (!n) return 0;
  unsigned b = 0;
  while (n > 1 && b + 1 < XH_TQ_DEPTH_BUCKETS) { n >>= 1; ++b; }
  return b;
}

static inline void xh_tq_record_batch(xh_task_queue_profile *p, bool service_order,
                                      unsigned queued_ops, unsigned unmap_requests)
{
  if (!p || !queued_ops) return;
  const unsigned side = service_order ? 1u : 0u;
  __atomic_fetch_add(&p->batches[side], 1, __ATOMIC_RELAXED);
  __atomic_fetch_add(&p->queued_ops[side], queued_ops, __ATOMIC_RELAXED);
  __atomic_fetch_add(&p->queued_unmap_requests[side], unmap_requests, __ATOMIC_RELAXED);
  __atomic_fetch_add(&p->depth_bins[side][xh_tq_depth_bucket(queued_ops)], 1, __ATOMIC_RELAXED);
}

static inline void xh_tq_record_fallback(xh_task_queue_profile *p, enum xh_tq_reason reason)
{
  if (p && (unsigned)reason < XH_TQ_REASONS)
    __atomic_fetch_add(&p->fallbacks[reason], 1, __ATOMIC_RELAXED);
}

static inline uint64_t xh_tq_read(const uint64_t *counter)
{
  return __atomic_load_n(counter, __ATOMIC_RELAXED);
}

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
