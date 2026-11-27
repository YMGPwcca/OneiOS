// SPDX-License-Identifier: MIT
#include "task_order_fast.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>

static pthread_mutex_t order_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t queue_lock = PTHREAD_MUTEX_INITIALIZER;
static unsigned pending, unmaps;
static bool unmaps_out;
static uint32_t request, done;
static void *drain(void *unused)
{
  (void)unused;
  pthread_mutex_lock(&order_lock);
  pthread_mutex_lock(&queue_lock);
  assert(pending == 1 && unmaps == 1);
  pending = unmaps = 0;
  unmaps_out = true;
  pthread_mutex_unlock(&queue_lock);
  __atomic_store_n(&request, 1, __ATOMIC_RELEASE);
  __atomic_store_n(&done, 0, __ATOMIC_RELEASE);
  assert(!xh_task_flush_can_skip(0, pending, unmaps, unmaps_out, &request, &done));
  __atomic_store_n(&request, 0, __ATOMIC_RELEASE);
  assert(!xh_task_flush_can_skip(0, pending, unmaps, false, &request, &done));
  __atomic_store_n(&done, 1, __ATOMIC_RELEASE);
  unmaps_out = false;
  pthread_mutex_unlock(&order_lock);
  return NULL;
}
int main(void)
{
  unsigned checks = 0;
  for (unsigned a = 0; a < 3; ++a)
    for (unsigned b = 0; b < 3; ++b)
      for (unsigned c = 0; c < 3; ++c)
        for (unsigned d = 0; d < 2; ++d)
          for (uint32_t e = 0; e < 3; ++e)
            for (uint32_t f = 0; f < 3; ++f) {
              assert(xh_task_flush_can_skip(a,b,c,d,&e,&f) == (!a && !b && !c && !d && !e && f == 1));
              ++checks;
            }
  // A stale pending observation, followed by another worker's complete
  // drain, then the flush caller acquiring both serialization locks.
  for (unsigned i = 0; i < 100; ++i) {
    pending = unmaps = 1; unmaps_out = false; request = 0; done = 1;
    assert(pending != 0);
    pthread_t worker;
    assert(!pthread_create(&worker, NULL, drain, NULL));
    assert(!pthread_join(worker, NULL));
    pthread_mutex_lock(&order_lock);
    pthread_mutex_lock(&queue_lock);
    assert(xh_task_flush_can_skip(0,pending,unmaps,unmaps_out,&request,&done));
    // Newly queued work or an explicit ordered operation still needs IPC.
    pending = 1;
    assert(!xh_task_flush_can_skip(0,pending,unmaps,unmaps_out,&request,&done));
    pending = 0;
    assert(!xh_task_flush_can_skip(1,pending,unmaps,unmaps_out,&request,&done));
    pthread_mutex_unlock(&queue_lock);
    pthread_mutex_unlock(&order_lock);
    checks += 6;
  }
  printf("task empty order: %u checks, 0 failed\n", checks);
  return 0;
}
