// SPDX-License-Identifier: MIT
// Keep process-lifetime timing totals off a single shared cache line.
#ifndef XNUHOST_TASK_TIMING_TOTALS_H
#define XNUHOST_TASK_TIMING_TOTALS_H

#include "task_profile.h"

// Separate writers by logical vCPU, not the host CPU they happen to run on.
// A distinct host bucket handles callers outside vCPU threads. The 128-byte
// alignment also separates neighboring shards on hosts with wider cache lines.
typedef struct {
  _Alignas(128) xh_task_timing_profile timing;
} xh_tt_shard;

typedef struct {
  xh_tt_shard bucket[XH_TP_BUCKETS];
} xh_task_timing_totals;

_Static_assert(_Alignof(xh_tt_shard) >= 128, "timing shard alignment");
_Static_assert(sizeof(xh_tt_shard) % 128 == 0, "timing shard stride");

static inline void xh_tt_total_record(xh_task_timing_totals *p, unsigned cpu,
                                     enum xh_tt_stage stage, bool acknowledged,
                                     uint64_t ns)
{
  if (!p) return;
  if (cpu >= XH_MAX_CPUS) cpu = XH_TP_HOST_BUCKET;
  // Keep relaxed atomics for reporting and multiple non-vCPU writers.
  xh_tt_record(&p->bucket[cpu].timing, stage, acknowledged, ns);
}

// Merge cumulative shard snapshots. Sums/counts add, maxima do not. Like
// xh_tt_snapshot this is approximate during concurrent writes, exact after
// quiescence. No task-slot lifetime dependency, reset, or report-side lock.
static inline void xh_tt_total_snapshot(xh_task_timing_profile *out,
                                        const xh_task_timing_totals *in)
{
  *out = (xh_task_timing_profile){ 0 };
  for (unsigned cpu = 0; cpu < XH_TP_BUCKETS; ++cpu) {
    xh_task_timing_profile sample;
    xh_tt_snapshot(&sample, &in->bucket[cpu].timing);
    for (unsigned stage = 0; stage < XH_TT_STAGES; ++stage) {
      xh_task_timing_hist *dst = &out->stage[stage];
      const xh_task_timing_hist *src = &sample.stage[stage];
      for (unsigned bin = 0; bin < XH_TT_BINS; ++bin)
        dst->bins[bin] += src->bins[bin];
      dst->sum_ns += src->sum_ns;
      dst->aborted += src->aborted;
      if (src->max_ns > dst->max_ns) dst->max_ns = src->max_ns;
    }
  }
}

#endif
