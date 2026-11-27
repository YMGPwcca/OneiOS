#define _GNU_SOURCE
#include "quiesce_vcpu.h"
#include <errno.h>
#include <limits.h>
#include <linux/futex.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#define READY UINT32_C(0xff)
#define PARKED (READY << 8)
#define FAULT (UINT32_C(1) << 17)
_Static_assert(__atomic_always_lock_free(sizeof(uint32_t), 0), "signal-context gate requires lock-free atomics");
uint32_t xhqv_state;
static uint32_t expected;
static uint64_t generation;
static bool verified;

int xhqv_configure(unsigned ncpu)
{
  if (!ncpu || ncpu > XHQV_MAX_CPUS) return -EINVAL;
  uint32_t zero = 0, mask = (1u << ncpu) - 1u;
  return __atomic_compare_exchange_n(&expected, &zero, mask, false, __ATOMIC_RELEASE, __ATOMIC_RELAXED) ? 0 : -EBUSY;
}
void xhqv_invalidate(void) { __atomic_fetch_or(&xhqv_state, FAULT, __ATOMIC_ACQ_REL); }
void xhqv_invalidate_if_closed(void)
{
  uint32_t s = __atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE);
  while ((s & XHQV_CLOSED) && !(s & FAULT))
    if (__atomic_compare_exchange_n(&xhqv_state, &s, s | FAULT, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return;
}
void xhqv_register(unsigned index)
{
  if (index >= XHQV_MAX_CPUS || !(__atomic_load_n(&expected, __ATOMIC_ACQUIRE) & (1u << index))) {
    xhqv_invalidate(); return;
  }
  uint32_t bit = 1u << index;
  uint32_t s = __atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE);
  do {
    if (s & (bit | XHQV_CLOSED)) { xhqv_invalidate(); return; }
  } while (!__atomic_compare_exchange_n(&xhqv_state, &s, s | bit, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE));
}
void xhqv_park(unsigned index)
{
  int saved = errno;
  uint32_t s = __atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE);
  while (s & XHQV_CLOSED) {
    if (index >= XHQV_MAX_CPUS || !(s & (1u << index))) { xhqv_invalidate(); break; }
    uint32_t bit = 1u << (8u + index);
    if (!(s & bit)) {
      if (!__atomic_compare_exchange_n(&xhqv_state, &s, s | bit, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) continue;
      s |= bit;
    }
    // Signal-context WFI can reach here: no allocation or pthread lock.
    // Timeout also covers an unexpected failed wake; no unpark on timeout.
    struct timespec step = {0, 100000000};
    long r = syscall(SYS_futex, &xhqv_state, FUTEX_WAIT_PRIVATE, s, &step, 0, 0);
    if (r < 0 && errno != EAGAIN && errno != EINTR && errno != ETIMEDOUT) {
      xhqv_invalidate();
      nanosleep(&step, NULL);
    }
    s = __atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE);
  }
  errno = saved;
}
int xhqv_close(uint64_t *ticket)
{
  if (!ticket) return -EINVAL;
  uint32_t mask = __atomic_load_n(&expected, __ATOMIC_ACQUIRE);
  if (!mask) return -ENOTSUP;
  uint32_t s = __atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE);
  if (s & FAULT) return -ESTALE;
  if (s & XHQV_CLOSED) return -EBUSY;
  if ((s & READY) != mask) return -EAGAIN;
  if (generation == UINT64_MAX) return -EOVERFLOW;
  if (!__atomic_compare_exchange_n(&xhqv_state, &s, s | XHQV_CLOSED, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return -EAGAIN;
  verified = false;
  *ticket = ++generation;
  return 0;
}
static int check(uint64_t ticket, uint32_t s)
{
  if (!ticket || ticket != generation || !(s & XHQV_CLOSED) || (s & FAULT)) return -ESTALE;
  uint32_t mask = __atomic_load_n(&expected, __ATOMIC_ACQUIRE);
  if ((s & READY) != mask) return -ESTALE;
  return ((s & PARKED) >> 8) == mask ? 0 : -EAGAIN;
}
int xhqv_poll(uint64_t ticket)
{
  int r = check(ticket, __atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE));
  if (!r) verified = true;
  return r;
}
int xhqv_resume(uint64_t ticket)
{
  uint32_t s = __atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE);
  int r = check(ticket, s);
  if (r) return r;
  if (!verified) return -EBUSY;
  if (!__atomic_compare_exchange_n(&xhqv_state, &s, s & READY, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) return -ESTALE;
  verified = false;
  // Release linearizes above. If wake fails, a timed waiter can still
  // observe the open word; report failure, never claim rollback.
  if (syscall(SYS_futex, &xhqv_state, FUTEX_WAKE_PRIVATE, INT_MAX, 0, 0, 0) < 0) {
    r = -errno; xhqv_invalidate(); return r;
  }
  return 0;
}
