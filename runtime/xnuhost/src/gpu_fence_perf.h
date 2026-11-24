// SPDX-License-Identifier: MIT
// Portable, bounded histogram for VirtIO GPU fenced-command wait times.
// This measures from VirtIO's submit_fence invocation to the backend callback,
// NOT Metal->KGSL execution, nor framebuffer scanout/presentation.
// The caller serializes updates with gpu_state.pl; no per-event allocations.
#ifndef XNUHOST_GPU_FENCE_PERF_H
#define XNUHOST_GPU_FENCE_PERF_H

#include <stdbool.h>
#include <stdint.h>
#include <limits.h>

enum { XH_FENCE_BUCKETS = 14 };
enum xh_fence_outcome { XH_FENCE_COMPLETED, XH_FENCE_REJECTED, XH_FENCE_CANCELED };

struct xh_fence_hist {
  uint64_t bins[XH_FENCE_BUCKETS], count, sum_us, max_us;
};
struct xh_fence_perf {
  struct xh_fence_hist fast, other;  // fast = xnu:backboardd context at enqueue
  uint64_t rejected, canceled, invalid_time;
  // Per callback batch, not per fence. Host used-index publication and IRQ
  // request are observable; guest IRQ handling / fence wakeup are not.
  struct xh_fence_hist publish;
  uint64_t published_chains, unpublished_chains, invalid_publish_time;
};

static inline uint64_t xh_fence_bound_us(unsigned i)
{
  static const uint64_t ceilings[XH_FENCE_BUCKETS] = {
    250, 500, 1000, 2000, 4000, 8000, 16000, 33000,
    50000, 100000, 250000, 500000, 1000000, UINT64_MAX
  };
  return ceilings[i < XH_FENCE_BUCKETS ? i : XH_FENCE_BUCKETS - 1];
}

// Also used for the distinct host queue/service stages. The caller owns
// synchronization and the clock domain; invalid spans are never sampled.
static inline bool xh_fence_hist_span(struct xh_fence_hist *h, uint64_t start, uint64_t end)
{
  if (!h || !start || !end || end < start) return false;
  uint64_t us = (end - start) / 1000u;
  h->count++;
  h->sum_us += us;
  if (us > h->max_us) h->max_us = us;
  for (unsigned i = 0; i < XH_FENCE_BUCKETS; i++)
    if (us <= xh_fence_bound_us(i)) { h->bins[i]++; break; }
  return true;
}

static inline void xh_fence_perf_record(struct xh_fence_perf *p,
                                        enum xh_fence_outcome outcome, bool fast,
                                        uint64_t enqueued_ns, uint64_t retired_ns)
{
  if (!p) return;
  if (outcome == XH_FENCE_CANCELED) { p->canceled++; return; }
  if (outcome == XH_FENCE_REJECTED) { p->rejected++; return; }
  if (!xh_fence_hist_span(fast ? &p->fast : &p->other, enqueued_ns, retired_ns))
    p->invalid_time++;
}

static inline void xh_fence_perf_record_publish(struct xh_fence_perf *p,
                                                unsigned matched, unsigned published,
                                                uint64_t callback_ns, uint64_t end_ns)
{
  if (!p || published > matched) return;
  p->published_chains += published;
  p->unpublished_chains += matched - published;
  if (published && !xh_fence_hist_span(&p->publish, callback_ns, end_ns))
    p->invalid_publish_time++;
}

static inline uint64_t xh_fence_perf_quantile_le_us(const struct xh_fence_hist *h, unsigned percentile)
{
  if (!h || !h->count || percentile < 1 || percentile > 100) return 0;
  uint64_t target = (h->count * percentile + 99u) / 100u;
  uint64_t n = 0;
  for (unsigned i = 0; i < XH_FENCE_BUCKETS; i++) {
    n += h->bins[i];
    if (n >= target) {
      uint64_t ceiling = xh_fence_bound_us(i);
      return ceiling == UINT64_MAX ? h->max_us : ceiling;
    }
  }
  return h->max_us;
}
#endif
