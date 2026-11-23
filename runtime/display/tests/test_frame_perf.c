// SPDX-License-Identifier: MIT
#include "frame_perf.h"
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
  printf("frame_perf tests: %d checks, %d failed\n",checks,failed);
  return failed?1:0;
}
