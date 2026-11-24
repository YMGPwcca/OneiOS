// SPDX-License-Identifier: MIT
// Bounded, allocation-free display frame timing statistics. Portable host unit tests
// exercise this code; no Android/guest headers or shared-memory writes are needed.
#ifndef ONEIOS_FRAME_PERF_H
#define ONEIOS_FRAME_PERF_H
#include <stdbool.h>
#include <stdint.h>

#define XHD_PERF_WINDOW_NS UINT64_C(5000000000)
#define XHD_PERF_ACTIVE_GAP_US UINT64_C(250000)
#define XHD_PERF_BUCKETS 14
#define XHD_PERF_SOURCES 8  // bounded resource identities per five-second window; overflow counted

struct xhd_perf_hist {
  uint64_t count, sum_us, max_us;
  uint64_t bins[XHD_PERF_BUCKETS];
};

struct xhd_trace_pending;
struct xhd_source_stat {
  uint64_t queue_generation, resource_generation, posts, last_seq;
  uint32_t resource_id, owner_ctx;
};
struct xhd_frame_perf {
  uint64_t window_start_ns, last_post_ns;
  uint64_t posts, full_copies, copied_pixels;
  uint64_t post_attempts, post_errors, copy_errors;
  uint64_t active_gap_count, active_gap_sum_us, idle_gaps;
  uint64_t active_over_60, active_over_120;
  struct xhd_perf_hist gap, active_gap, lock, copy, post;
  uint64_t traced_posts, traced_flushes, traced_coalesced, traced_gaps, traced_bad, traced_legacy;
  uint64_t scanout_packets, scanout_blob, scanout_2d, scanout_copy_sum_ns, scanout_copy_max_ns;
  struct xhd_perf_hist flush_to_post_oldest, flush_to_post_latest, flush_to_helper;
  struct xhd_perf_hist scanout_copy_max_per_post, scanout_start_to_post_oldest;
  // Count source identity per posted *batch*, not per GPU flush. This does NOT
  // assert a relationship to renderer submission or fence completion.
  uint64_t source_unique_posts, source_mixed_posts, source_unknown_posts, source_overflow_posts;
  struct xhd_source_stat sources[XHD_PERF_SOURCES];
};

uint64_t xhd_perf_clock_ns(void);
void xhd_perf_begin(struct xhd_frame_perf *p, uint64_t start_ns);
void xhd_perf_record(struct xhd_frame_perf *p, uint64_t post_time_ns,
                     uint64_t lock_ns, uint64_t copy_ns, uint64_t post_ns,
                     uint64_t copied_pixels, bool full_copy);
// One display post may coalesce many flushes; these timestamps end at
// ANativeWindow_unlockAndPost completion, not physical panel presentation.
void xhd_perf_record_trace(struct xhd_frame_perf *p, const struct xhd_trace_pending *batch, uint64_t post_done_ns);
// Record only a successfully posted, valid-content guest buffer in cadence and
// trace histograms. Failure counters are independent and may overlap.
bool xhd_perf_finish_attempt(struct xhd_frame_perf *p, int post_rc, bool copy_ok,
                             uint64_t post_done_ns, uint64_t lock_ns, uint64_t copy_ns,
                             uint64_t post_ns, uint64_t copied_pixels, bool full_copy,
                             const struct xhd_trace_pending *batch);
bool xhd_perf_due(const struct xhd_frame_perf *p, uint64_t now_ns);
void xhd_perf_next_window(struct xhd_frame_perf *p, uint64_t now_ns);
uint64_t xhd_perf_quantile_bound_us(const struct xhd_perf_hist *h, unsigned percentile);
// The "active" cadence excludes idle gaps (>250ms) and must not be reported
// as actual animation FPS if fewer than 3 active gaps were observed.
double xhd_perf_active_cadence(const struct xhd_frame_perf *p);
double xhd_perf_post_rate(const struct xhd_frame_perf *p, uint64_t now_ns);
#endif
