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

struct xhd_perf_hist {
  uint64_t count, sum_us, max_us;
  uint64_t bins[XHD_PERF_BUCKETS];
};

struct xhd_frame_perf {
  uint64_t window_start_ns, last_post_ns;
  uint64_t posts, full_copies, copied_pixels;
  uint64_t active_gap_count, active_gap_sum_us;
  struct xhd_perf_hist gap, lock, copy, post;
};

uint64_t xhd_perf_clock_ns(void);
void xhd_perf_begin(struct xhd_frame_perf *p, uint64_t start_ns);
void xhd_perf_record(struct xhd_frame_perf *p, uint64_t post_time_ns,
                     uint64_t lock_ns, uint64_t copy_ns, uint64_t post_ns,
                     uint64_t copied_pixels, bool full_copy);
bool xhd_perf_due(const struct xhd_frame_perf *p, uint64_t now_ns);
void xhd_perf_next_window(struct xhd_frame_perf *p, uint64_t now_ns);
uint64_t xhd_perf_quantile_bound_us(const struct xhd_perf_hist *h, unsigned percentile);
// The "active" cadence excludes idle gaps (>250ms) and must not be reported
// as actual animation FPS if fewer than 3 active gaps were observed.
double xhd_perf_active_cadence(const struct xhd_frame_perf *p);
double xhd_perf_post_rate(const struct xhd_frame_perf *p, uint64_t now_ns);
#endif
