// SPDX-License-Identifier: MIT
#define _POSIX_C_SOURCE 200809L
#include "frame_perf.h"
#include <string.h>
#include <time.h>

static const uint64_t ceilings_us[XHD_PERF_BUCKETS] = {
  250, 500, 1000, 2000, 4000, 8000, 16000, 33000,
  50000, 100000, 250000, 500000, 1000000, UINT64_MAX
};

uint64_t xhd_perf_clock_ns(void)
{
  struct timespec ts;
  if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
  return (uint64_t)ts.tv_sec * UINT64_C(1000000000) + (uint64_t)ts.tv_nsec;
}

static void observe(struct xhd_perf_hist *h, uint64_t microseconds)
{
  h->count++;
  h->sum_us += microseconds;
  if (microseconds > h->max_us) h->max_us = microseconds;
  for (unsigned i = 0; i < XHD_PERF_BUCKETS; ++i)
    if (microseconds <= ceilings_us[i]) { h->bins[i]++; break; }
}

void xhd_perf_begin(struct xhd_frame_perf *p, uint64_t start_ns)
{
  memset(p, 0, sizeof *p);
  p->window_start_ns = start_ns;
}

void xhd_perf_record(struct xhd_frame_perf *p, uint64_t post_time_ns,
                     uint64_t lock_ns, uint64_t copy_ns, uint64_t post_ns,
                     uint64_t copied_pixels, bool full_copy)
{
  if (p->last_post_ns && post_time_ns > p->last_post_ns) {
    uint64_t gap_us = (post_time_ns - p->last_post_ns) / 1000;
    observe(&p->gap, gap_us);
    if (gap_us > 0 && gap_us <= XHD_PERF_ACTIVE_GAP_US) {
      p->active_gap_count++;
      p->active_gap_sum_us += gap_us;
    }
  }
  p->last_post_ns = post_time_ns;
  p->posts++;
  p->copied_pixels += copied_pixels;
  if (full_copy) p->full_copies++;
  observe(&p->lock, lock_ns / 1000);
  observe(&p->copy, copy_ns / 1000);
  observe(&p->post, post_ns / 1000);
}

bool xhd_perf_due(const struct xhd_frame_perf *p, uint64_t now_ns)
{
  return now_ns >= p->window_start_ns &&
         now_ns - p->window_start_ns >= XHD_PERF_WINDOW_NS;
}

void xhd_perf_next_window(struct xhd_frame_perf *p, uint64_t now_ns)
{
  uint64_t last_post = p->last_post_ns;
  xhd_perf_begin(p, now_ns);
  p->last_post_ns = last_post;  // A long idle gap must not masquerade as 60 FPS.
}

uint64_t xhd_perf_quantile_bound_us(const struct xhd_perf_hist *h, unsigned percentile)
{
  if (!h->count || percentile < 1 || percentile > 100) return 0;
  uint64_t target = (h->count * percentile + 99) / 100;
  uint64_t sum = 0;
  for (unsigned i = 0; i < XHD_PERF_BUCKETS; ++i) {
    sum += h->bins[i];
    if (sum >= target) return ceilings_us[i] == UINT64_MAX ? h->max_us : ceilings_us[i];
  }
  return h->max_us;
}

double xhd_perf_active_cadence(const struct xhd_frame_perf *p)
{
  if (p->active_gap_count < 3 || !p->active_gap_sum_us) return 0.0;
  return 1000000.0 * (double)p->active_gap_count / (double)p->active_gap_sum_us;
}

double xhd_perf_post_rate(const struct xhd_frame_perf *p, uint64_t now_ns)
{
  if (now_ns <= p->window_start_ns) return 0.0;
  return (double)p->posts * 1e9 / (double)(now_ns - p->window_start_ns);
}
