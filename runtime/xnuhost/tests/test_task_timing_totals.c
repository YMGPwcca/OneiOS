// SPDX-License-Identifier: MIT
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include "task_timing_totals.h"

enum { WORKERS = XH_MAX_CPUS + 2, LOOPS = 20000 };
static xh_task_timing_totals totals;

static unsigned bucket(unsigned id)
{
  return id < XH_MAX_CPUS ? id : XH_TP_HOST_BUCKET;
}

static enum xh_tt_stage stage_of(unsigned i)
{
  return (enum xh_tt_stage)(i % XH_TT_STAGES);
}

static uint64_t ns_of(unsigned id, unsigned i)
{
  return i % 37 == 0 ? UINT64_C(2000000000) + id : (uint64_t)(i % 23 + 1) * 1000 + id;
}

static void *record_worker(void *arg)
{
  const unsigned id = *(const unsigned *)arg;
  // Exercise both exact vCPU buckets and the out-of-range host fallback.
  const unsigned cpu = id < XH_MAX_CPUS ? id : XH_MAX_CPUS + id;
  for (unsigned i = 0; i < LOOPS; ++i)
    xh_tt_total_record(&totals, cpu, stage_of(i), i % 7 != 0, ns_of(id, i));
  return NULL;
}

static void same(const xh_task_timing_profile *a, const xh_task_timing_profile *b)
{
  for (unsigned stage = 0; stage < XH_TT_STAGES; ++stage) {
    const xh_task_timing_hist *x = &a->stage[stage], *y = &b->stage[stage];
    for (unsigned bin = 0; bin < XH_TT_BINS; ++bin) assert(x->bins[bin] == y->bins[bin]);
    assert(x->sum_ns == y->sum_ns && x->aborted == y->aborted && x->max_ns == y->max_ns);
  }
}

int main(void)
{
  pthread_t threads[WORKERS];
  unsigned ids[WORKERS];
  xh_task_timing_profile expected = { 0 }, merged, observed;
  xh_task_timing_profile reference[XH_TP_BUCKETS] = { 0 };
  xh_tt_total_record(NULL, 0, XH_TT_RELEASE_ACK, true, 1);
  xh_tt_total_record(&totals, 0, (enum xh_tt_stage)XH_TT_STAGES, true, 1);
  xh_tt_total_snapshot(&merged, &totals);
  same(&merged, &expected);
  for (unsigned id = 0; id < WORKERS; ++id) {
    ids[id] = id;
    assert(pthread_create(&threads[id], NULL, record_worker, &ids[id]) == 0);
  }
  // Exercise the read path while writers may still be active; no assertion
  // of a transactionally consistent intermediate snapshot.
  xh_tt_total_snapshot(&observed, &totals);
  for (unsigned id = 0; id < WORKERS; ++id) {
    assert(pthread_join(threads[id], NULL) == 0);
    for (unsigned i = 0; i < LOOPS; ++i) {
      xh_tt_record(&expected, stage_of(i), i % 7 != 0, ns_of(id, i));
      xh_tt_record(&reference[bucket(id)], stage_of(i), i % 7 != 0, ns_of(id, i));
    }
  }
  xh_tt_total_snapshot(&merged, &totals);
  same(&merged, &expected);
  for (unsigned cpu = 0; cpu < XH_TP_BUCKETS; ++cpu) {
    xh_task_timing_profile sample;
    xh_tt_snapshot(&sample, &totals.bucket[cpu].timing);
    same(&sample, &reference[cpu]);
  }
  for (unsigned stage = 0; stage < XH_TT_STAGES; ++stage) {
    const xh_task_timing_hist *x = &observed.stage[stage], *y = &merged.stage[stage];
    for (unsigned bin = 0; bin < XH_TT_BINS; ++bin) assert(x->bins[bin] <= y->bins[bin]);
    assert(x->sum_ns <= y->sum_ns && x->aborted <= y->aborted && x->max_ns <= y->max_ns);
  }
  printf("TASK_TIMING_TOTALS=PASS workers=%u samples=%u shards=%u bytes=%zu\n",
         (unsigned)WORKERS, (unsigned)(WORKERS * LOOPS), (unsigned)XH_TP_BUCKETS, sizeof totals);
  return 0;
}
