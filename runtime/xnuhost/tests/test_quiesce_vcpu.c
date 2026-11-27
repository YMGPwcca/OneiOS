#define _GNU_SOURCE
#include "quiesce_vcpu.h"
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
static unsigned allow, entered, paused, exits[8], done, bad_errno;
static void *cpu(void *arg)
{
  unsigned i = (unsigned)(uintptr_t)arg, bit = 1u << i;
  xhqv_register(i);
  __atomic_fetch_or(&entered, bit, __ATOMIC_RELEASE);
  while (!__atomic_load_n(&done, __ATOMIC_ACQUIRE)) {
    if (__atomic_load_n(&allow, __ATOMIC_ACQUIRE) & bit) {
      __atomic_fetch_and(&paused, ~bit, __ATOMIC_RELEASE);
      errno = EDOM;
      xhqv_checkpoint(i);
      if (errno != EDOM) __atomic_store_n(&bad_errno, 1, __ATOMIC_RELEASE);
      __atomic_add_fetch(&exits[i], 1u, __ATOMIC_RELAXED);
    } else __atomic_fetch_or(&paused, bit, __ATOMIC_RELEASE);
    struct timespec t = {0, 100000}; nanosleep(&t, NULL);
  }
  return NULL;
}
static void wait_mask(unsigned *p, unsigned mask)
{
  for (unsigned i = 0; i < 5000; i++) {
    if (__atomic_load_n(p, __ATOMIC_ACQUIRE) == mask) return;
    usleep(1000);
  }
  CHECK(0);
}
static void wait_park(uint64_t t)
{
  for (unsigned i = 0; i < 5000; i++) {
    int r = xhqv_poll(t);
    if (!r) return;
    if (r != -EAGAIN) break;
    usleep(1000);
  }
  CHECK(0);
}
static void cycles(int fault)
{
  pthread_t th[8]; uint64_t t = 0, previous = 0;
  CHECK(xhqv_configure(8) == 0 && xhqv_configure(8) == -EBUSY);
  for (unsigned i = 0; i < 7; i++) CHECK(pthread_create(&th[i], NULL, cpu, (void *)(uintptr_t)i) == 0);
  wait_mask(&entered, 127);
  CHECK(xhqv_close(&t) == -EAGAIN && !t);
  CHECK(pthread_create(&th[7], NULL, cpu, (void *)(uintptr_t)7) == 0);
  wait_mask(&entered, 255);
  for (unsigned cycle = 0; cycle < 6; cycle++) {
    __atomic_store_n(&allow, 0, __ATOMIC_RELEASE);
    wait_mask(&paused, 255);
    CHECK(xhqv_close(&t) == 0 && t > previous);
    CHECK(xhqv_close(&previous) == -EBUSY);
    CHECK(xhqv_poll(t+1) == -ESTALE && xhqv_resume(t+1) == -ESTALE);
    __atomic_store_n(&allow, 127, __ATOMIC_RELEASE);
    // CPU 7 is intentionally denied a checkpoint. No receipt even when others arrive.
    for (unsigned i = 0; i < 5000 && ((__atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE) >> 8) & 127u) != 127; i++) usleep(1000);
    CHECK(((__atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE) >> 8) & 127u) == 127);
    CHECK(xhqv_poll(t) == -EAGAIN && xhqv_resume(t) == -EAGAIN);
    __atomic_store_n(&allow, 255, __ATOMIC_RELEASE);
    for (unsigned i = 0; i < 5000 && ((__atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE) >> 8) & 255u) != 255; i++) usleep(1000);
    CHECK(((__atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE) >> 8) & 255u) == 255);
    CHECK(xhqv_resume(t) == -EBUSY); // all arrived, but no verified receipt yet
    wait_park(t);
    unsigned count[8]; for (unsigned i = 0; i < 8; i++) count[i] = __atomic_load_n(&exits[i], __ATOMIC_RELAXED);
    usleep(3000);
    for (unsigned i = 0; i < 8; i++) CHECK(count[i] == __atomic_load_n(&exits[i], __ATOMIC_RELAXED));
    if (fault && cycle == 5) {
      if (fault == 1) xhqv_invalidate_if_closed(); else if (fault == 2) xhqv_register(7); else xhqv_invalidate();
      CHECK(xhqv_poll(t) == -ESTALE && xhqv_resume(t) == -ESTALE && xhqv_close(&previous) == -ESTALE);
      usleep(3000);
      for (unsigned i = 0; i < 8; i++) CHECK(count[i] == __atomic_load_n(&exits[i], __ATOMIC_RELAXED));
      return; // process exits without thaw; fixture deliberately leaves parked threads
    }
    CHECK(xhqv_resume(t) == 0 && xhqv_poll(t) == -ESTALE);
    previous = t;
    for (unsigned i = 0; i < 8; i++) {
      for (unsigned n = 0; n < 5000 && count[i] == __atomic_load_n(&exits[i], __ATOMIC_RELAXED); n++) usleep(1000);
      CHECK(count[i] != __atomic_load_n(&exits[i], __ATOMIC_RELAXED));
    }
  }
  CHECK(!__atomic_load_n(&bad_errno, __ATOMIC_ACQUIRE));
  __atomic_store_n(&done, 1, __ATOMIC_RELEASE);
  for (unsigned i = 0; i < 8; i++) CHECK(pthread_join(th[i], NULL) == 0);
}
static void invalid(void)
{
  uint64_t t = 0;
  CHECK(xhqv_close(&t) == -ENOTSUP && xhqv_configure(0) == -EINVAL && xhqv_configure(9) == -EINVAL);
  CHECK(xhqv_configure(1) == 0);
  xhqv_invalidate_if_closed();
  CHECK(xhqv_close(&t) == -EAGAIN);
  xhqv_register(0);
  CHECK(xhqv_close(&t) == 0);
  CHECK(xhqv_poll(0) == -ESTALE && xhqv_poll(t) == -EAGAIN);
  xhqv_invalidate(); CHECK(xhqv_poll(t) == -ESTALE && xhqv_resume(t) == -ESTALE);
}
int main(void)
{
  alarm(30);
  for (int i = 0; i < 5; i++) {
    int p[2]; CHECK(pipe(p) == 0);
    pid_t pid = fork(); CHECK(pid >= 0);
    if (!pid) {
      close(p[0]); checks = 0;
      if (i == 4) invalid(); else cycles(i);
      if (write(p[1], &checks, sizeof checks) != sizeof checks) _exit(2);
      _exit(0);
    }
    close(p[1]); unsigned n = 0;
    CHECK(read(p[0], &n, sizeof n) == sizeof n); close(p[0]);
    int status; CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && !WEXITSTATUS(status));
    checks += n;
  }
  printf("vCPU rendezvous: %u checks, 0 failed\n", checks);
  return 0;
}
