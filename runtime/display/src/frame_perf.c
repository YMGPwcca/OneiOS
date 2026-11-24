// SPDX-License-Identifier: MIT
#define _POSIX_C_SOURCE 200809L
#include "frame_perf.h"
#include "xhd.h"
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
    uint64_t gap_ns = post_time_ns - p->last_post_ns;
    uint64_t gap_us = gap_ns / 1000;
    observe(&p->gap, gap_us);
    if (gap_ns <= XHD_PERF_ACTIVE_GAP_US * 1000u) {
      p->active_gap_count++;
      p->active_gap_sum_us += gap_us;
      observe(&p->active_gap, gap_us);
      // Rounded-up nominal budgets; not display present or actual jank.
      if (gap_ns > UINT64_C(16666667)) p->active_over_60++;
      if (gap_ns > UINT64_C(8333334)) p->active_over_120++;
    } else p->idle_gaps++;
  }
  p->last_post_ns = post_time_ns;
  p->posts++;
  p->copied_pixels += copied_pixels;
  if (full_copy) p->full_copies++;
  observe(&p->lock, lock_ns / 1000);
  observe(&p->copy, copy_ns / 1000);
  observe(&p->post, post_ns / 1000);
}

void xhd_perf_record_trace(struct xhd_frame_perf *p, const struct xhd_trace_pending *batch, uint64_t post_done_ns)
{
  if (!batch) return;
  p->traced_bad += batch->bad;
  p->traced_legacy += batch->legacy;
  p->traced_gaps += batch->seq_gaps;
  if (!batch->traced) return;
  p->traced_posts++;
  p->traced_flushes += batch->traced;
  p->traced_coalesced += batch->traced - 1;
  if (batch->provenance_packets != batch->traced || batch->legacy || batch->bad || batch->seq_gaps) {
    p->source_unknown_posts++;
  } else if (batch->provenance_mixed) {
    p->source_mixed_posts++;
  } else {
    p->source_unique_posts++;
    // Group by (queue gen, resource gen, resource ID, owner) so ID reuse,
    // process resets, and coalescing cannot silently fabricate ownership.
    unsigned slot = 0;
    while (slot < XHD_PERF_SOURCES && p->sources[slot].posts &&
           (p->sources[slot].queue_generation != batch->provenance_queue_gen ||
            p->sources[slot].resource_generation != batch->provenance_resource_gen ||
            p->sources[slot].resource_id != batch->provenance_resource_id ||
            p->sources[slot].owner_ctx != batch->provenance_owner_ctx)) slot++;
    if (slot < XHD_PERF_SOURCES) {
      struct xhd_source_stat *src = &p->sources[slot];
      if (!src->posts) {
        src->queue_generation = batch->provenance_queue_gen;
        src->resource_generation = batch->provenance_resource_gen;
        src->resource_id = batch->provenance_resource_id;
        src->owner_ctx = batch->provenance_owner_ctx;
      }
      src->posts++;
      src->last_seq = batch->last_seq;
    } else p->source_overflow_posts++;
  }
  p->scanout_packets += batch->scanout_packets;
  p->scanout_blob += batch->scanout_blob;
  p->scanout_2d += batch->scanout_2d;
  p->scanout_copy_sum_ns += batch->scanout_copy_sum_ns;
  if (batch->scanout_copy_max_ns > p->scanout_copy_max_ns)
    p->scanout_copy_max_ns = batch->scanout_copy_max_ns;
  if (batch->scanout_packets) {
    observe(&p->scanout_copy_max_per_post, batch->scanout_copy_max_ns / 1000);
    if (batch->oldest_scanout_start_ns && post_done_ns >= batch->oldest_scanout_start_ns)
      observe(&p->scanout_start_to_post_oldest, (post_done_ns - batch->oldest_scanout_start_ns) / 1000);
  }
  if (batch->oldest_flush_ns && post_done_ns >= batch->oldest_flush_ns)
    observe(&p->flush_to_post_oldest, (post_done_ns - batch->oldest_flush_ns) / 1000);
  if (batch->newest_flush_ns && post_done_ns >= batch->newest_flush_ns)
    observe(&p->flush_to_post_latest, (post_done_ns - batch->newest_flush_ns) / 1000);
  if (batch->newest_flush_ns && batch->newest_recv_ns >= batch->newest_flush_ns)
    observe(&p->flush_to_helper, (batch->newest_recv_ns - batch->newest_flush_ns) / 1000);
}

bool xhd_perf_finish_attempt(struct xhd_frame_perf *p, int post_rc, bool copy_ok,
                             uint64_t post_done_ns, uint64_t lock_ns, uint64_t copy_ns,
                             uint64_t post_ns, uint64_t copied_pixels, bool full_copy,
                             const struct xhd_trace_pending *batch)
{
  p->post_attempts++;
  if (post_rc) p->post_errors++;
  if (!copy_ok || !copied_pixels) p->copy_errors++;
  if (post_rc || !copy_ok || !copied_pixels) return false;
  xhd_perf_record(p, post_done_ns, lock_ns, copy_ns, post_ns, copied_pixels, full_copy);
  xhd_perf_record_trace(p, batch, post_done_ns);
  return true;
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
