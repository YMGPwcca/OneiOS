// SPDX-License-Identifier: MIT
// Pure host regression, no guest, Android, DRM, or KGSL required.
#include <stdio.h>
#include <stdint.h>
#include "gpu_fence_perf.h"

static int checks, failures;
#define CHECK(x) do { checks++; if (!(x)) { failures++; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

int main(void)
{
  struct xh_fence_perf p = { 0 };
  CHECK(xh_fence_perf_quantile_le_us(&p.fast, 95) == 0);
  CHECK(xh_fence_perf_quantile_le_us(NULL, 95) == 0);
  CHECK(xh_fence_bound_us(0) == 250);
  CHECK(xh_fence_bound_us(XH_FENCE_BUCKETS - 1) == UINT64_MAX);

  // One merged callback completes each prior fence on the matching ctx/ring:
  // accounting is per pending command, not per callback.
  xh_fence_perf_record(&p, XH_FENCE_COMPLETED, true, 1000000000, 1001000000);
  xh_fence_perf_record(&p, XH_FENCE_COMPLETED, true, 2000000000, 2002000000);
  xh_fence_perf_record(&p, XH_FENCE_COMPLETED, true, 3000000000, 3061656000);
  CHECK(p.fast.count == 3 && p.fast.sum_us == 64656 && p.fast.max_us == 61656);
  CHECK(xh_fence_perf_quantile_le_us(&p.fast, 50) == 2000);
  CHECK(xh_fence_perf_quantile_le_us(&p.fast, 95) == 100000);
  CHECK(xh_fence_perf_quantile_le_us(&p.fast, 100) == 100000);
  CHECK(p.fast.bins[2] == 1 && p.fast.bins[3] == 1 && p.fast.bins[9] == 1);

  xh_fence_perf_record(&p, XH_FENCE_COMPLETED, false, 1000000000, 1000500000);
  CHECK(p.other.count == 1 && p.other.sum_us == 500 && p.other.max_us == 500);
  CHECK(xh_fence_perf_quantile_le_us(&p.other, 50) == 500);

  // Context destruction and refused backend fences are not GPU completions.
  xh_fence_perf_record(&p, XH_FENCE_CANCELED, true, 100, 0);
  xh_fence_perf_record(&p, XH_FENCE_REJECTED, false, 100, 0);
  CHECK(p.canceled == 1 && p.rejected == 1);
  CHECK(p.fast.count == 3 && p.other.count == 1);

  // Stale/invalid clocks produce an explicit invalid result, never underflow.
  xh_fence_perf_record(&p, XH_FENCE_COMPLETED, true, 0, 0);
  xh_fence_perf_record(&p, XH_FENCE_COMPLETED, true, 2000, 1000);
  CHECK(p.invalid_time == 2 && p.fast.count == 3);
  CHECK(xh_fence_perf_quantile_le_us(&p.fast, 0) == 0);
  CHECK(xh_fence_perf_quantile_le_us(&p.fast, 101) == 0);

  // A span above all normal ceilings uses the actual maximum.
  xh_fence_perf_record(&p, XH_FENCE_COMPLETED, false, 1000000000, 2300000000);
  CHECK(xh_fence_perf_quantile_le_us(&p.other, 100) == 1300000);
  CHECK(p.other.bins[XH_FENCE_BUCKETS - 1] == 1);
  xh_fence_perf_record(NULL, XH_FENCE_COMPLETED, true, 1, 2);
  struct xh_fence_hist stage = { 0 };
  CHECK(!xh_fence_hist_span(&stage, 0, 1));
  CHECK(!xh_fence_hist_span(&stage, 9, 8));
  CHECK(xh_fence_hist_span(&stage, 1000, 1000));
  CHECK(xh_fence_hist_span(&stage, 1000, 17001000));
  CHECK(stage.count == 2 && stage.sum_us == 17000 && stage.max_us == 17000);
  CHECK(xh_fence_perf_quantile_le_us(&stage, 95) == 33000);
  printf("gpu fence perf: %d checks, %d failures\n", checks, failures);
  return failures ? 1 : 0;
}
