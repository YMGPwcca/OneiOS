// SPDX-License-Identifier: MIT
// Pure host regression: bounded vCPU/host buckets, atomic counters, no device needed.
#include <stdio.h>
#include <string.h>
#include <pthread.h>
#include "task_profile.h"

enum { THREADS = 4, LOOPS = 25000 };
static void *count_concurrently(void *arg)
{
  xh_task_profile *p = arg;
  for (unsigned i = 0; i < LOOPS; i++) {
    xh_task_profile_add(p, 2, XH_TP_TRAP_OTHER);
    xh_tq_record_batch(&p->queue, false, 1, 0);
    if (!(i % 5)) xh_tq_record_fallback(&p->queue, XH_TQ_UNMAP_TASK_RUNNING);
    xh_tt_record(&p->timing, XH_TT_RELEASE_ACK, true, 4000);
    if (!(i % 5)) xh_tt_record(&p->timing, XH_TT_ORDER_DIRECT_ACK, false, 0);
  }
  return NULL;
}

static unsigned checks, failed;
#define CHECK(x) do { checks++; if (!(x)) { failed++; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); } } while (0)

int main(void)
{
  xh_task_profile p = { 0 };
  CHECK(XH_TP_BUCKETS == XH_MAX_CPUS + 1);
  CHECK(XH_TP_HOST_BUCKET == XH_MAX_CPUS);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_TRAP_FAULT) == 0);
  CHECK(xh_task_profile_read(NULL, 0, XH_TP_TRAP_FAULT) == 0);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_EVENTS) == 0);

  // Independently count task traps by vCPU and operation, including the last vCPU.
  xh_task_profile_add(&p, 0, XH_TP_TRAP_SYSCALL);
  xh_task_profile_add(&p, 0, XH_TP_TRAP_SYSCALL);
  xh_task_profile_add(&p, XH_MAX_CPUS - 1, XH_TP_TRAP_FAULT);
  xh_task_profile_add(&p, 0, XH_TP_MAP_DEFERRED);
  xh_task_profile_add(&p, 0, XH_TP_UNMAP_ORDERED);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_TRAP_SYSCALL) == 2);
  CHECK(xh_task_profile_read(&p, XH_MAX_CPUS - 1, XH_TP_TRAP_FAULT) == 1);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_MAP_DEFERRED) == 1);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_UNMAP_ORDERED) == 1);
  CHECK(xh_task_profile_read(&p, 1, XH_TP_TRAP_SYSCALL) == 0);

  // Calls without an active vCPU are accounted to one distinct host bucket.
  xh_task_profile_add(&p, XH_MAX_CPUS, XH_TP_MAP_ORDERED);
  xh_task_profile_add(&p, XH_MAX_CPUS + 100, XH_TP_MAP_ORDERED);
  CHECK(xh_task_profile_read(&p, XH_TP_HOST_BUCKET, XH_TP_MAP_ORDERED) == 2);
  CHECK(xh_task_profile_read(&p, XH_MAX_CPUS + 1, XH_TP_MAP_ORDERED) == 2);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_MAP_ORDERED) == 0);

  // Invalid event and NULL pointers must be benign.
  xh_task_profile_add(&p, 0, XH_TP_EVENTS);
  xh_task_profile_add(NULL, 0, XH_TP_HOST_FUTEX_WAIT);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_HOST_FUTEX_WAIT) == 0);
  xh_task_profile_add(&p, 0, XH_TP_HOST_FUTEX_WAIT);
  xh_task_profile_add(&p, 0, XH_TP_TASK_FUTEX_SLEEP);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_HOST_FUTEX_WAIT) == 1);
  CHECK(xh_task_profile_read(&p, 0, XH_TP_TASK_FUTEX_SLEEP) == 1);

  // Copy after all updates: future read-only report snapshots must be complete.
  xh_task_profile snapshot;
  memcpy(&snapshot, &p, sizeof p);
  CHECK(xh_task_profile_read(&snapshot, 0, XH_TP_TRAP_SYSCALL) == 2);
  CHECK(xh_task_profile_read(&snapshot, XH_TP_HOST_BUCKET, XH_TP_MAP_ORDERED) == 2);

  // Shared task counters are atomic even when multiple host/vCPU threads update.
  pthread_t workers[THREADS];
  unsigned started = 0;
  for (; started < THREADS; started++)
    if (pthread_create(&workers[started], NULL, count_concurrently, &p)) break;
  for (unsigned i = 0; i < started; i++) pthread_join(workers[i], NULL);
  CHECK(started == THREADS);
  CHECK(xh_task_profile_read(&p, 2, XH_TP_TRAP_OTHER) == (uint64_t)THREADS * LOOPS);
  CHECK(xh_tq_read(&p.queue.batches[0]) == (uint64_t)THREADS * LOOPS);
  CHECK(xh_tq_read(&p.queue.queued_ops[0]) == (uint64_t)THREADS * LOOPS);
  CHECK(xh_tq_read(&p.queue.depth_bins[0][0]) == (uint64_t)THREADS * LOOPS);
  CHECK(xh_tq_read(&p.queue.fallbacks[XH_TQ_UNMAP_TASK_RUNNING]) ==
        (uint64_t)THREADS * (LOOPS / 5));

  // Explicit queue depths, release vs ordered drains, and logical unmap
  // requests (which may exceed entries after a queue join).
  xh_task_queue_profile q = { 0 };
  CHECK(xh_tq_depth_bucket(0) == 0 && xh_tq_depth_bucket(1) == 0);
  CHECK(xh_tq_depth_bucket(2) == 1 && xh_tq_depth_bucket(3) == 1);
  CHECK(xh_tq_depth_bucket(4) == 2 && xh_tq_depth_bucket(31) == 4);
  CHECK(xh_tq_depth_bucket(32) == 5 && xh_tq_depth_bucket(255) == 7);
  CHECK(xh_tq_depth_bucket(256) == 8 && xh_tq_depth_bucket(1024) == 8);
  xh_tq_record_batch(&q, false, 0, 0);  // empty queue is not a drain
  xh_tq_record_batch(&q, false, 1, 0);
  xh_tq_record_batch(&q, false, 3, 4);
  xh_tq_record_batch(&q, true, 256, 300);
  CHECK(q.batches[0] == 2 && q.batches[1] == 1);
  CHECK(q.queued_ops[0] == 4 && q.queued_ops[1] == 256);
  CHECK(q.queued_unmap_requests[0] == 4 && q.queued_unmap_requests[1] == 300);
  CHECK(q.depth_bins[0][0] == 1 && q.depth_bins[0][1] == 1 && q.depth_bins[1][8] == 1);
  xh_tq_record_fallback(&q, XH_TQ_MAP_QUEUE_FULL);
  xh_tq_record_fallback(&q, XH_TQ_UNMAP_QUEUE_FULL);
  xh_tq_record_fallback(&q, XH_TQ_UNMAP_TASK_RUNNING);
  xh_tq_record_fallback(&q, (enum xh_tq_reason)XH_TQ_REASONS);
  xh_tq_record_fallback(NULL, XH_TQ_MAP_QUEUE_FULL);
  xh_tq_record_batch(NULL, true, 10, 1);
  CHECK(q.fallbacks[0] == 1 && q.fallbacks[1] == 1 && q.fallbacks[2] == 1);
  CHECK(xh_tq_read(&q.batches[1]) == 1);

  // Concurrent updates use atomic bins and sums, not lost increments.
  xh_task_timing_profile timing_snapshot;
  xh_tt_snapshot(&timing_snapshot, &p.timing);
  const xh_task_timing_hist *h = &timing_snapshot.stage[XH_TT_RELEASE_ACK];
  CHECK(xh_tt_count(h) == (uint64_t)THREADS * LOOPS);
  CHECK(h->sum_ns == (uint64_t)THREADS * LOOPS * 4000);
  CHECK(h->max_ns == 4000 && h->bins[2] == (uint64_t)THREADS * LOOPS);
  CHECK(xh_tt_quantile_ns(h, 99) == 4000);
  CHECK(timing_snapshot.stage[XH_TT_ORDER_DIRECT_ACK].aborted ==
        (uint64_t)THREADS * (LOOPS / 5));

  xh_task_timing_profile timing = { 0 };
  xh_tt_record(&timing, XH_TT_ORDER_DEFERRED_ACK, true, 1000);
  xh_tt_record(&timing, XH_TT_ORDER_DEFERRED_ACK, true, 1001);
  xh_tt_record(&timing, XH_TT_ORDER_DEFERRED_ACK, true, 16000001);
  xh_tt_record(&timing, XH_TT_ORDER_DEFERRED_ACK, true, UINT64_C(2000000000));
  xh_tt_record(&timing, XH_TT_ORDER_DEFERRED_ACK, false, 0);
  xh_tt_record(&timing, XH_TT_ORDER_DIRECT_ACK, true, 0);
  xh_tt_record(&timing, (enum xh_tt_stage)XH_TT_STAGES, true, 123);
  xh_tt_record(NULL, XH_TT_RELEASE_ACK, true, 123);
  xh_tt_snapshot(&timing_snapshot, &timing);
  h = &timing_snapshot.stage[XH_TT_ORDER_DEFERRED_ACK];
  CHECK(xh_tt_count(h) == 4 && h->aborted == 1);
  CHECK(h->sum_ns == UINT64_C(2016002002) && h->max_ns == UINT64_C(2000000000));
  CHECK(h->bins[0] == 1 && h->bins[1] == 1 && h->bins[13] == 1 && h->bins[15] == 1);
  CHECK(xh_tt_quantile_ns(h, 50) == 2000);
  CHECK(xh_tt_quantile_ns(h, 75) == 64000000);
  CHECK(xh_tt_quantile_ns(h, 99) == UINT64_C(2000000000));
  CHECK(xh_tt_quantile_ns(h, 0) == 0 && xh_tt_quantile_ns(h, 101) == 0);
  CHECK(xh_tt_count(&timing_snapshot.stage[XH_TT_ORDER_DIRECT_ACK]) == 1);
  CHECK(xh_tt_count(&timing_snapshot.stage[XH_TT_RELEASE_ACK]) == 0);
  CHECK(xh_tt_quantile_ns(&timing_snapshot.stage[XH_TT_RELEASE_ACK], 95) == 0);

  CHECK(xh_detail_classify(XH_TRAP_SYSCALL, 0, 0) == XH_DC_BSD_INDIRECT);
  CHECK(xh_detail_classify(XH_TRAP_SYSCALL, 0, 4) == XH_DC_BSD_DIRECT);
  CHECK(xh_detail_classify(XH_TRAP_SYSCALL, 0, UINT64_MAX) == XH_DC_MACH);
  CHECK(xh_detail_classify(XH_TRAP_SYSCALL, 0, UINT64_C(0x80000000)) == XH_DC_PLATFORM);
  CHECK(xh_detail_classify(XH_TRAP_FAULT, XH_PROT_READ, 0) == XH_DC_FAULT_READ);
  CHECK(xh_detail_classify(XH_TRAP_FAULT, XH_PROT_WRITE, 0) == XH_DC_FAULT_WRITE);
  CHECK(xh_detail_classify(XH_TRAP_FAULT, XH_PROT_EXEC, 0) == XH_DC_FAULT_EXEC);
  CHECK(xh_detail_classify(XH_TRAP_FAULT, 0, 0) == XH_DC_FAULT_UNKNOWN);
  CHECK(xh_detail_classify(XH_TRAP_INTERRUPT, 0, 0) == XH_DC_COUNT);
  xh_detail_profile detail = { 0 };
  xh_detail_interval(&detail, XH_DC_MACH, UINT64_C(16666666));
  xh_detail_interval(&detail, XH_DC_MACH, UINT64_C(16666667));
  xh_detail_interval(&detail, XH_DC_COUNT, UINT64_MAX);
  CHECK(detail.intervals[XH_DC_MACH] == 2 && detail.over_budget[XH_DC_MACH] == 1);
  xh_detail_timer_result(&detail, XH_DT_CANCEL_DISARMED, 0);
  xh_detail_timer_result(&detail, XH_DT_ARM, -1);
  CHECK(detail.timer[XH_DT_CANCEL_DISARMED] == 1 && detail.timer[XH_DT_ARM] == 1 && detail.timer[XH_DT_ERRORS] == 1);
  xh_detail_futex(&detail, false, 0, EAGAIN);
  xh_detail_futex(&detail, false, -1, EAGAIN);
  xh_detail_futex(&detail, false, -1, EINTR);
  xh_detail_futex(&detail, true, -1, ETIMEDOUT);
  xh_detail_futex(&detail, true, -1, EINVAL);
  CHECK(detail.futex[0][XH_DW_RETURNED] == 1 && detail.futex[0][XH_DW_CHANGED] == 1 && detail.futex[0][XH_DW_SIGNAL] == 1);
  CHECK(detail.futex[1][XH_DW_TIMEOUT] == 1 && detail.futex[1][XH_DW_OTHER] == 1);
  char mask[32] = "unknown";
  CHECK(xh_detail_allowed_list("Cpus_allowed_list:\t0-3,6-7\n", mask, sizeof mask) && !strcmp(mask, "0-3,6-7"));
  CHECK(!xh_detail_allowed_list("Cpus_allowed_list:\t0-3", mask, sizeof mask));
  CHECK(!xh_detail_allowed_list("Cpus_allowed:\tff\n", mask, sizeof mask));
  CHECK(!xh_detail_allowed_list("Cpus_allowed_list:\t0-3,6-7\n", mask, 3));
  printf("task profile: %u checks, %u failed\n", checks, failed);
  return failed != 0;
}
