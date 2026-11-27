#include "quiesce.h"
#include <errno.h>
#include <string.h>

static int fail(struct xhq *q, int r)
{
  q->fault = r < 0 ? r : -EPROTO;
  q->phase = XHQ_FAULT;
  return q->fault;
}
static int clock_check(struct xhq *q)
{
  uint64_t now = 0;
  int r = q->ops.now(q->ctx, &now);
  if (r) return fail(q, r);
  if (now < q->last_ns) return fail(q, -ESTALE);
  q->last_ns = now;
  if (now >= q->deadline) return fail(q, -ETIMEDOUT);
  return 0;
}
static int check(struct xhq *q)
{
  int r = clock_check(q);
  if (r) return r;
  r = q->ops.guard(q->ctx, q->owner, q->cycle, q->phase);
  if (r) return fail(q, r == -EAGAIN ? -EPERM : r);
  return clock_check(q);
}
static int match(const struct xhq *q, uint64_t owner, uint64_t cycle)
{
  if (!q || !owner || !cycle || q->owner != owner || q->cycle != cycle) return -ESTALE;
  return q->phase == XHQ_FAULT ? q->fault : 0;
}
int xhq_init(struct xhq *q, const struct xhq_ops *ops, void *ctx, uint64_t owner, unsigned nblocks)
{
  if (!q || !ops || !ops->now || !ops->guard || !ops->close || !ops->poll || !ops->resume ||
      !owner || !nblocks || nblocks > XHQ_MAX_BLOCKS) return -EINVAL;
  *q = (struct xhq){ .ops = *ops, .ctx = ctx, .owner = owner, .nblocks = nblocks };
  return 0;
}
int xhq_begin(struct xhq *q, uint64_t owner, uint64_t deadline_ns, uint64_t *cycle)
{
  if (!q || !owner || owner != q->owner) return -ESTALE;
  if (!cycle || !deadline_ns) return -EINVAL;
  if (q->phase == XHQ_FAULT) return q->fault;
  if (q->phase != XHQ_IDLE && q->phase != XHQ_DONE) return -EBUSY;
  if (q->cycle == UINT64_MAX) return fail(q, -EOVERFLOW);
  q->cycle++;
  q->deadline = deadline_ns;
  q->closed = q->verified = q->resume_attempted = q->reopened = 0;
  memset(q->tickets, 0, sizeof q->tickets);
  q->phase = XHQ_CLOSING;
  int r = check(q);
  if (!r) *cycle = q->cycle;
  return r;
}
/* Record side effects BEFORE checking the clock/guard again. A provider can
 * return after the deadline or fail after starting a resume handshake. */
static int close_member(struct xhq *q, unsigned m)
{
  int r = check(q);
  if (r) return r;
  uint64_t t = 0;
  r = q->ops.close(q->ctx, m, &t);
  if (t) { q->tickets[m] = t; q->closed |= 1u << m; }
  if ((!r && !t) || (r && t)) return fail(q, -EPROTO);
  int c = check(q);
  if (c) return c;
  return r == -EAGAIN || !r ? r : fail(q, r);
}
static int verify(struct xhq *q, unsigned last)
{
  q->verified = 0;
  for (unsigned m = 0; m <= last; m++) {
    int r = check(q);
    if (r) return r;
    if (!(q->closed & (1u << m))) return fail(q, -EPROTO);
    r = q->ops.poll(q->ctx, m, q->tickets[m]);
    if (!r) q->verified |= 1u << m;
    int c = check(q);
    if (c) return c;
    if (r) return r == -EAGAIN ? r : fail(q, r);
  }
  return 0;
}
static int reopen(struct xhq *q, unsigned m)
{
  int r = check(q);
  if (r) return r;
  q->resume_attempted |= 1u << m;
  r = q->ops.resume(q->ctx, m, q->tickets[m]);
  if (!r) q->reopened |= 1u << m;
  int c = check(q);
  if (c) return c;
  return r == -EAGAIN || !r ? r : fail(q, r);
}
int xhq_step(struct xhq *q, uint64_t owner, uint64_t cycle)
{
  int r = match(q, owner, cycle);
  if (r) return r;
  unsigned display = q->nblocks + 1u;
  switch (q->phase) {
  case XHQ_CLOSING:
    for (unsigned m = 0; m < display; m++) {
      if (q->closed & (1u << m)) continue;
      r = close_member(q, m);
      if (r) return r;
    }
    q->phase = XHQ_DRAINING;
    return -EAGAIN;
  case XHQ_DRAINING:
    r = verify(q, display - 1u);
    if (r) return r;
    q->phase = XHQ_DISPLAY_CLOSE;
    return -EAGAIN;
  case XHQ_DISPLAY_CLOSE:
    /* Refresh GPU/block receipts before closing the helper; no GPU shadow
     * write may follow. The external guard covers other shadow producers. */
    r = verify(q, display - 1u);
    if (r) return r;
    r = close_member(q, display);
    if (r) return r;
    q->phase = XHQ_VERIFY;
    return -EAGAIN;
  case XHQ_VERIFY:
  case XHQ_PARKED:
    r = verify(q, display);
    if (r) { if (r == -EAGAIN) q->phase = XHQ_VERIFY; return r; }
    q->phase = XHQ_PARKED;
    return 0;
  case XHQ_RESUME_CHECK:
    r = verify(q, display);
    if (r) return r;
    q->phase = XHQ_RESUMING;
    return -EAGAIN;
  case XHQ_RESUMING:
    /* Helper first, then blocks, then GPU. Other producers remain parked.
     * Reopen is not atomic: on failure retain attempted/successful masks,
     * never retry a successful reopen or claim a rollback. */
    if (!(q->reopened & (1u << display))) {
      r = reopen(q, display);
      if (r) return r;
    }
    for (unsigned m = 1; m < display; m++) {
      if (q->reopened & (1u << m)) continue;
      r = reopen(q, m);
      if (r) return r;
    }
    r = reopen(q, XHQ_GPU);
    if (r) return r;
    q->phase = XHQ_DONE;
    return 0;
  case XHQ_DONE: return 0;
  default: return -EINVAL;
  }
}
int xhq_request_resume(struct xhq *q, uint64_t owner, uint64_t cycle)
{
  int r = match(q, owner, cycle);
  if (r) return r;
  if (q->phase != XHQ_PARKED) return -EBUSY;
  q->phase = XHQ_RESUME_CHECK;
  return check(q);
}
