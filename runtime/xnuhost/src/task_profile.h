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

// Bounded elapsed-wall-time histograms. The existing per-vCPU perf.c
// histograms remain unchanged. Updates are relaxed atomics; concurrent
// readers take an approximate, non-transactional snapshot, not a lock.
enum xh_tt_stage {
  XH_TT_ORDER_LOCK, XH_TT_ORDER_DEFERRED_ACK, XH_TT_ORDER_DIRECT_ACK,
  XH_TT_RELEASE_LOCK, XH_TT_RELEASE_ACK, XH_TT_STAGES
};
enum { XH_TT_BINS = 16 };
typedef struct {
  uint64_t bins[XH_TT_BINS], sum_ns, max_ns, aborted;
} xh_task_timing_hist;
typedef struct {
  xh_task_timing_hist stage[XH_TT_STAGES];
} xh_task_timing_profile;

static inline uint64_t xh_tt_ceiling_ns(unsigned bin)
{
  static const uint64_t ceilings[XH_TT_BINS] = {
    1000, 2000, 4000, 8000, 16000, 32000, 64000, 128000,
    256000, 512000, 1000000, 4000000, 16000000, 64000000,
    1000000000, UINT64_MAX
  };
  return ceilings[bin < XH_TT_BINS ? bin : XH_TT_BINS - 1];
}

static inline void xh_tt_record(xh_task_timing_profile *p, enum xh_tt_stage stage,
                                bool acknowledged, uint64_t ns)
{
  if (!p || (unsigned)stage >= XH_TT_STAGES) return;
  xh_task_timing_hist *h = &p->stage[stage];
  if (!acknowledged) {
    __atomic_fetch_add(&h->aborted, 1, __ATOMIC_RELAXED);
    return;
  }
  unsigned bin = 0;
  while (bin + 1 < XH_TT_BINS && ns > xh_tt_ceiling_ns(bin)) bin++;
  __atomic_fetch_add(&h->sum_ns, ns, __ATOMIC_RELAXED);
  uint64_t old = __atomic_load_n(&h->max_ns, __ATOMIC_RELAXED);
  while (ns > old && !__atomic_compare_exchange_n(&h->max_ns, &old, ns,
                    true, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
  __atomic_fetch_add(&h->bins[bin], 1, __ATOMIC_RELAXED);
}

static inline void xh_tt_snapshot(xh_task_timing_profile *out,
                                  const xh_task_timing_profile *in)
{
  for (unsigned stage = 0; stage < XH_TT_STAGES; stage++) {
    xh_task_timing_hist *dst = &out->stage[stage];
    const xh_task_timing_hist *src = &in->stage[stage];
    for (unsigned bin = 0; bin < XH_TT_BINS; bin++)
      dst->bins[bin] = __atomic_load_n(&src->bins[bin], __ATOMIC_RELAXED);
    dst->sum_ns = __atomic_load_n(&src->sum_ns, __ATOMIC_RELAXED);
    dst->max_ns = __atomic_load_n(&src->max_ns, __ATOMIC_RELAXED);
    dst->aborted = __atomic_load_n(&src->aborted, __ATOMIC_RELAXED);
  }
}

// These helpers read a detached snapshot, not the live atomic histogram.
static inline uint64_t xh_tt_count(const xh_task_timing_hist *h)
{
  uint64_t n = 0;
  for (unsigned i = 0; i < XH_TT_BINS; i++) n += h->bins[i];
  return n;
}
static inline uint64_t xh_tt_quantile_ns(const xh_task_timing_hist *h, unsigned pct)
{
  uint64_t n = xh_tt_count(h);
  if (!n || !pct || pct > 100) return 0;
  const uint64_t target = (n / 100) * pct + ((n % 100) * pct + 99) / 100;
  uint64_t seen = 0;
  for (unsigned i = 0; i < XH_TT_BINS; i++) {
    seen += h->bins[i];
    if (seen >= target) return i == XH_TT_BINS - 1 ? h->max_ns : xh_tt_ceiling_ns(i);
  }
  return 0;
}

typedef struct {
  uint64_t events[XH_TP_BUCKETS][XH_TP_EVENTS];
  xh_task_queue_profile queue;
  xh_task_timing_profile timing;
  uint64_t trap_class[XH_DC_COUNT];
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
