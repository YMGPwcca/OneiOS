// SPDX-License-Identifier: MIT
#ifndef ONEIOS_KGSL_DRAIN_H
#define ONEIOS_KGSL_DRAIN_H
#include <errno.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>

/* Process-local ledger of accepted GPU_COMMAND timestamps, independent
 * of guest fences. Renderer serializes each queue's submission/destruction. */
struct oneios_kgsl_drain_entry {
   struct oneios_kgsl_drain_entry *next;
   int fd;
   uint32_t ctx, last;
   bool seen, pending, inflight;
};
struct oneios_kgsl_drain {
   pthread_mutex_t lock;
   struct oneios_kgsl_drain_entry *entries;
   uint64_t ticket;
   unsigned active;
   bool closed, fault, verified;
};
#define ONEIOS_KGSL_DRAIN_INITIALIZER { .lock = PTHREAD_MUTEX_INITIALIZER }
typedef int (*oneios_kgsl_wait_fn)(int, uint32_t, uint32_t, void *);

static inline bool oneios_kgsl_drain_closed(const struct oneios_kgsl_drain *d)
{
   return __atomic_load_n(&d->closed, __ATOMIC_ACQUIRE);
}
static inline void oneios_kgsl_drain_fault(struct oneios_kgsl_drain *d)
{
   pthread_mutex_lock(&d->lock);
   d->fault = true; d->verified = false;
   pthread_mutex_unlock(&d->lock);
}
/* Allocation failure loses proof, but does not alter an open-path submit.
 * Return 1 to suppress keepalive; a guest submit while closed is a fault. */
static inline int oneios_kgsl_drain_begin(struct oneios_kgsl_drain *d,
   int fd, uint32_t ctx, bool autonomous, struct oneios_kgsl_drain_entry **out)
{
   *out = NULL;
   pthread_mutex_lock(&d->lock);
   if (oneios_kgsl_drain_closed(d)) {
      if (!autonomous) { d->fault = true; d->verified = false; }
      pthread_mutex_unlock(&d->lock);
      return autonomous ? 1 : -EBUSY;
   }
   struct oneios_kgsl_drain_entry *e = d->entries;
   while (e && (e->fd != fd || e->ctx != ctx)) e = e->next;
   if (!e) {
      e = calloc(1, sizeof *e);
      if (e) {
         e->fd = fd; e->ctx = ctx;
         e->next = d->entries; d->entries = e;
      } else d->fault = true;
   }
   if (e && e->inflight) { d->fault = true; e = NULL; }
   if (e) e->inflight = true;
   d->active++; d->verified = false; *out = e;
   pthread_mutex_unlock(&d->lock);
   return 0;
}
static inline void oneios_kgsl_drain_finish(struct oneios_kgsl_drain *d,
   struct oneios_kgsl_drain_entry *e, bool accepted, uint32_t timestamp)
{
   pthread_mutex_lock(&d->lock);
   if (!accepted || !e || !timestamp) d->fault = true;
   if (e) {
      if (!e->inflight) d->fault = true;
      e->inflight = false;
      if (accepted) {
         uint32_t advance = timestamp - e->last;
         if (e->seen && (!advance || advance >= UINT32_C(0x80000000)))
            d->fault = true;
         e->last = timestamp;
         e->seen = e->pending = true;
      }
   }
   if (!d->active) d->fault = true;
   else d->active--;
   d->verified = false;
   pthread_mutex_unlock(&d->lock);
}
static inline int oneios_kgsl_drain_trylock(struct oneios_kgsl_drain *d)
{
   int r = pthread_mutex_trylock(&d->lock);
   return r == EBUSY ? -EAGAIN : -r;
}
/* Close remains useful even if proof was lost. Fault is sticky. */
static inline int oneios_kgsl_drain_close(struct oneios_kgsl_drain *d, uint64_t *ticket)
{
   if (!ticket) return -EINVAL;
   int r = oneios_kgsl_drain_trylock(d);
   if (r) return r;
   if (oneios_kgsl_drain_closed(d)) r = -EBUSY;
   else if (d->ticket == UINT64_MAX) r = -EOVERFLOW;
   else {
      *ticket = ++d->ticket; d->verified = false;
      __atomic_store_n(&d->closed, true, __ATOMIC_RELEASE);
   }
   pthread_mutex_unlock(&d->lock);
   return r;
}
/* At most 16 timestamp checks per poll. No syscall wall-clock guarantee:
 * the independent caller owns the overall BOOTTIME deadline. */
static inline int oneios_kgsl_drain_poll(struct oneios_kgsl_drain *d,
   uint64_t ticket, oneios_kgsl_wait_fn wait, void *arg)
{
   if (!ticket || !wait) return -EINVAL;
   int r = oneios_kgsl_drain_trylock(d);
   if (r) return r;
   if (!oneios_kgsl_drain_closed(d) || ticket != d->ticket) r = -ESTALE;
   else if (d->fault) r = -EIO;
   else if (d->active) r = -EAGAIN;
   else {
      unsigned polled = 0;
      for (struct oneios_kgsl_drain_entry *e = d->entries; e; e = e->next) {
         if (!e->pending) continue;
         if (polled++ == 16) { r = -EAGAIN; break; }
         r = wait(e->fd, e->ctx, e->last, arg);
         if (!r) e->pending = false;
         else {
            if (r != -EAGAIN) { d->fault = true; r = -EIO; }
            break;
         }
      }
      d->verified = r == 0;
   }
   pthread_mutex_unlock(&d->lock);
   return r;
}
/* Poll before identity disappears. Never assume context/fd destruction
 * or reuse implies retirement. Do not wait/retry in normal teardown. */
static inline void oneios_kgsl_drain_forget(struct oneios_kgsl_drain *d,
   int fd, uint32_t ctx, bool whole_fd, oneios_kgsl_wait_fn wait, void *arg)
{
   pthread_mutex_lock(&d->lock);
   if (oneios_kgsl_drain_closed(d)) { d->fault = true; d->verified = false; }
   for (struct oneios_kgsl_drain_entry **p = &d->entries; *p;) {
      struct oneios_kgsl_drain_entry *e = *p;
      if (e->fd != fd || (!whole_fd && e->ctx != ctx)) { p = &e->next; continue; }
      if (e->inflight) {
         d->fault = true; d->verified = false; p = &e->next; continue;
      }
      if (e->pending && (!wait || wait(e->fd, e->ctx, e->last, arg))) d->fault = true;
      *p = e->next; free(e);
   }
   pthread_mutex_unlock(&d->lock);
}
static inline int oneios_kgsl_drain_resume(struct oneios_kgsl_drain *d, uint64_t ticket)
{
   if (!ticket) return -EINVAL;
   int r = oneios_kgsl_drain_trylock(d);
   if (r) return r;
   if (!oneios_kgsl_drain_closed(d) || ticket != d->ticket) r = -ESTALE;
   else if (d->fault) r = -EIO;
   else if (d->active || !d->verified) r = -EBUSY;
   else {
      d->verified = false;
      __atomic_store_n(&d->closed, false, __ATOMIC_RELEASE);
   }
   pthread_mutex_unlock(&d->lock);
   return r;
}
#endif
