// SPDX-License-Identifier: MIT
#include "quiesce_input.h"
#include <errno.h>
#include <pthread.h>

unsigned xhqi_flags;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static unsigned registered, active;
static bool sealed, fault, parked, verified;
static uint64_t generation;

static unsigned flag(void) { return __atomic_load_n(&xhqi_flags, __ATOMIC_ACQUIRE); }
static void set_flag(unsigned f) { __atomic_store_n(&xhqi_flags, f, __ATOMIC_RELEASE); }
static int try_lock(void)
{
  int r = pthread_mutex_trylock(&lock);
  return r == EBUSY ? -EAGAIN : -r;
}
static bool source_valid(enum xhqi_source source) { return source == XHQI_READER || source == XHQI_SCRIPT; }
int xhqi_start(enum xhqi_source source)
{
  if (!source_valid(source)) return -EINVAL;
  unsigned bit = 1u << source;
  pthread_mutex_lock(&lock);
  int r = 0;
  if (sealed || (registered & bit)) { fault = true; r = -EPERM; }
  else { registered |= bit; active |= bit; }
  pthread_mutex_unlock(&lock);
  return r;
}
void xhqi_finish(enum xhqi_source source, bool failed)
{
  pthread_mutex_lock(&lock);
  if (!source_valid(source)) fault = true;
  else {
    unsigned bit = 1u << source;
    if (!(active & bit) || failed || (flag() & XHQI_CLOSED)) fault = true;
    active &= ~bit;
  }
  pthread_mutex_unlock(&lock);
}
int xhqi_seal(void)
{
  pthread_mutex_lock(&lock);
  int r = sealed ? -EBUSY : fault ? -ESTALE : 0;
  sealed = true;
  pthread_mutex_unlock(&lock);
  return r;
}
bool xhqi_reader_wait(void)
{
  pthread_mutex_lock(&lock);
  unsigned f;
  while (((f = flag()) & XHQI_CLOSED) && !(f & XHQI_STOP)) {
    if (!(active & (1u << XHQI_READER))) fault = true;
    else parked = true;
    // No input operation, device lock or callback is held here.
    pthread_cond_wait(&changed, &lock);
  }
  pthread_mutex_unlock(&lock);
  return !(f & XHQI_STOP);
}
void xhqi_reader_stop(void)
{
  pthread_mutex_lock(&lock);
  fault = true;
  set_flag(flag() | XHQI_STOP);
  pthread_cond_broadcast(&changed);
  pthread_mutex_unlock(&lock);
}
int xhqi_close(uint64_t *ticket)
{
  if (!ticket) return -EINVAL;
  int r = try_lock();
  if (r) return r;
  if (!sealed) r = -EBUSY;
  else if (fault) r = -ESTALE;
  else if ((flag() & XHQI_CLOSED) || (active & (1u << XHQI_SCRIPT))) r = -EBUSY;
  else if (generation == UINT64_MAX) r = -EOVERFLOW;
  else {
    parked = verified = false;
    set_flag(flag() | XHQI_CLOSED);
    *ticket = ++generation;
  }
  pthread_mutex_unlock(&lock);
  return r;
}
static int check(uint64_t ticket)
{
  if (!ticket || ticket != generation || !(flag() & XHQI_CLOSED) || fault) return -ESTALE;
  if (active & (1u << XHQI_SCRIPT)) return -ESTALE;
  return (active & (1u << XHQI_READER)) && !parked ? -EAGAIN : 0;
}
int xhqi_poll(uint64_t ticket)
{
  int r = try_lock();
  if (r) return r;
  r = check(ticket);
  if (!r) verified = true;
  pthread_mutex_unlock(&lock);
  return r;
}
int xhqi_resume(uint64_t ticket)
{
  int r = try_lock();
  if (r) return r;
  r = check(ticket);
  if (!r && !verified) r = -EBUSY;
  if (!r) {
    parked = verified = false;
    set_flag(flag() & ~XHQI_CLOSED);
    pthread_cond_broadcast(&changed);
  }
  pthread_mutex_unlock(&lock);
  return r;
}
