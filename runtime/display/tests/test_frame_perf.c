// SPDX-License-Identifier: MIT
#include "frame_perf.h"
#include "xhd.h"
#include <stdio.h>
#include <stdint.h>
#include <math.h>

static int failed, checks;
#define CHECK(x) do { checks++; if (!(x)) { failed++; fprintf(stderr,"FAIL %s:%d: %s\n",__FILE__,__LINE__,#x); } } while (0)

int main(void)
{
  struct xhd_frame_perf p;
  const uint64_t t0 = UINT64_C(10000000000);
  xhd_perf_begin(&p, t0);
  CHECK(!xhd_perf_due(&p,t0+UINT64_C(4999999999)));
  CHECK(xhd_perf_due(&p,t0+XHD_PERF_WINDOW_NS));
  CHECK(xhd_perf_quantile_bound_us(&p.post,95) == 0);
  CHECK(xhd_perf_active_cadence(&p) == 0.0);
  // Four 16 ms intervals give actual animation-cadence sampling.
  for(unsigned i=0;i<5;i++)
    xhd_perf_record(&p,t0+UINT64_C(100000000)+UINT64_C(16000000)*i,
                    1500000,2000000,1100000,1080*2340,i<4);
  CHECK(p.posts==5 && p.full_copies==4 && p.copied_pixels==5u*1080*2340);
  CHECK(p.active_gap_count==4 && p.active_gap_sum_us==64000);
  CHECK(fabs(xhd_perf_active_cadence(&p)-62.5)<0.001);
  CHECK(xhd_perf_quantile_bound_us(&p.lock,95)==2000);
  CHECK(xhd_perf_quantile_bound_us(&p.copy,50)==2000);
  CHECK(p.gap.count==4 && p.gap.max_us==16000);
  CHECK(xhd_perf_post_rate(&p,t0+UINT64_C(5000000000))==1.0);
  xhd_perf_next_window(&p,t0+XHD_PERF_WINDOW_NS);
  CHECK(p.posts==0 && p.last_post_ns==t0+UINT64_C(164000000));
  xhd_perf_record(&p,t0+UINT64_C(7000000000),50000000,100000,100000,2,false);
  CHECK(p.active_gap_count==0); // idle gap is deliberately excluded
  CHECK(xhd_perf_active_cadence(&p)==0.0);
  CHECK(p.gap.count==1 && p.gap.max_us>1000000);
  CHECK(xhd_perf_quantile_bound_us(&p.lock,95)==50000);
  CHECK(xhd_perf_quantile_bound_us(&p.post,95)==250);
  CHECK(xhd_perf_quantile_bound_us(&p.gap,0)==0);
  // A single post may include three guest flushes; it is still ONE post.
  struct xhd_trace_pending traced = {
    .traced = 3, .seq_gaps = 1, .oldest_flush_ns = t0,
    .newest_flush_ns = t0 + UINT64_C(2000000),
    .newest_recv_ns = t0 + UINT64_C(2500000)
  };
  xhd_perf_record_trace(&p, &traced, t0 + UINT64_C(11000000));
  CHECK(p.traced_posts == 1 && p.traced_flushes == 3 && p.traced_coalesced == 2 && p.traced_gaps == 1);
  CHECK(p.flush_to_post_oldest.count == 1 && p.flush_to_post_oldest.max_us == 11000);
  CHECK(p.flush_to_post_latest.count == 1 && p.flush_to_post_latest.max_us == 9000);
  CHECK(p.flush_to_helper.count == 1 && p.flush_to_helper.max_us == 500);
  // Bad timing never underflows, and an untraced post must not fabricate FPS.
  traced = (struct xhd_trace_pending){ .bad = 2, .legacy = 1, .traced = 1,
             .oldest_flush_ns = t0 + UINT64_C(30000000),
             .newest_flush_ns = t0 + UINT64_C(30000000),
             .newest_recv_ns = t0 + UINT64_C(32000000) };
  xhd_perf_record_trace(&p, &traced, t0 + UINT64_C(10000000));
  CHECK(p.traced_bad == 2 && p.traced_legacy == 1 && p.traced_posts == 2);
  CHECK(p.flush_to_post_latest.count == 1 && p.flush_to_post_oldest.count == 1);
  xhd_perf_next_window(&p, t0 + UINT64_C(12000000000));
  CHECK(p.traced_posts == 0 && p.traced_flushes == 0 && p.flush_to_post_latest.count == 0);
  const uint64_t t1 = t0 + UINT64_C(13000000000);
  struct xhd_trace_pending scanout = {
    .traced = 2, .scanout_packets = 2, .scanout_blob = 1, .scanout_2d = 1,
    .scanout_copy_sum_ns = UINT64_C(2500000), .scanout_copy_max_ns = UINT64_C(2000000),
    .oldest_scanout_start_ns = t1
  };
  xhd_perf_record_trace(&p, &scanout, t1 + UINT64_C(11000000));
  CHECK(p.scanout_packets == 2 && p.scanout_blob == 1 && p.scanout_2d == 1);
  CHECK(p.scanout_copy_sum_ns == UINT64_C(2500000) && p.scanout_copy_max_ns == UINT64_C(2000000));
  CHECK(p.scanout_copy_max_per_post.count == 1 && p.scanout_copy_max_per_post.max_us == 2000);
  CHECK(p.scanout_start_to_post_oldest.count == 1 && p.scanout_start_to_post_oldest.max_us == 11000);
  CHECK(xhd_perf_quantile_bound_us(&p.scanout_copy_max_per_post, 95) == 2000);
  xhd_perf_next_window(&p, t1 + XHD_PERF_WINDOW_NS);
  CHECK(p.scanout_packets == 0 && p.scanout_copy_max_per_post.count == 0);

  // Two flushes from the same v3 source in one batch are ONE attributed post.
  struct xhd_trace_pending source = {
    .traced = 2, .provenance_packets = 2, .provenance_queue_gen = 0,
    .provenance_resource_gen = 10, .provenance_resource_id = 4,
    .provenance_owner_ctx = 0, .last_seq = 8
  };
  xhd_perf_record_trace(&p, &source, t1 + XHD_PERF_WINDOW_NS);
  CHECK(p.source_unique_posts == 1 && p.sources[0].posts == 1 &&
        p.sources[0].resource_generation == 10 && p.sources[0].last_seq == 8);
  // The same numeric resource ID reused with a new serial is another key.
  source = (struct xhd_trace_pending){ .traced = 1, .provenance_packets = 1,
       .provenance_queue_gen = 0, .provenance_resource_gen = 11,
       .provenance_resource_id = 4, .last_seq = 9 };
  xhd_perf_record_trace(&p, &source, t1 + XHD_PERF_WINDOW_NS);
  CHECK(p.source_unique_posts == 2 && p.sources[1].posts == 1 &&
        p.sources[1].resource_generation == 11);
  // A reset generation separates keys even when the allocation serial is identical.
  source.provenance_queue_gen = 1;
  xhd_perf_record_trace(&p, &source, t1 + XHD_PERF_WINDOW_NS);
  CHECK(p.sources[2].posts == 1 && p.sources[2].queue_generation == 1);
  source.provenance_mixed = true; source.traced = 2; source.provenance_packets = 2;
  xhd_perf_record_trace(&p, &source, t1 + XHD_PERF_WINDOW_NS);
  CHECK(p.source_mixed_posts == 1 && p.source_unique_posts == 3);
  source.provenance_mixed = false; source.legacy = 1;
  xhd_perf_record_trace(&p, &source, t1 + XHD_PERF_WINDOW_NS);
  source.legacy = 0; source.provenance_packets = 1;
  xhd_perf_record_trace(&p, &source, t1 + XHD_PERF_WINDOW_NS);
  CHECK(p.source_unknown_posts == 2 && p.source_unique_posts == 3);

  // Fixed eight-source capacity; additional identities count as overflow,
  // they never replace an earlier source or fabricate a matched fence.
  for (uint64_t gen = 20; gen < 27; gen++) {
    source = (struct xhd_trace_pending){ .traced = 1, .provenance_packets = 1,
      .provenance_queue_gen = 1, .provenance_resource_gen = gen,
      .provenance_resource_id = 4, .last_seq = 100 + gen };
    xhd_perf_record_trace(&p, &source, t1 + XHD_PERF_WINDOW_NS);
  }
  CHECK(p.source_unique_posts == 10 && p.source_overflow_posts == 2);
  CHECK(p.sources[0].resource_generation == 10 && p.sources[7].resource_generation == 24);
  xhd_perf_next_window(&p, t1 + 2 * XHD_PERF_WINDOW_NS);
  CHECK(p.source_unique_posts == 0 && p.source_mixed_posts == 0 &&
        p.source_unknown_posts == 0 && p.source_overflow_posts == 0 &&
        p.sources[0].posts == 0);

  printf("frame_perf tests: %d checks, %d failed\n",checks,failed);
  return failed?1:0;
}
