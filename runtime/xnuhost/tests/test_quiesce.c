#include "quiesce.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
enum { CLOSE, POLL, RESUME };
struct fake {
  uint64_t now;
  unsigned closed, drained, reopened, nblocks;
  unsigned calls[3][XHQ_MAX_MEMBERS], order[XHQ_MAX_MEMBERS], nresume;
  int op, member, result, guard_error;
  unsigned delay, bad_ticket, deny_resume;
};
static int guard(void *ctx, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  struct fake *f = ctx;
  CHECK(owner == 17 && cycle != 0);
  if (f->deny_resume && (phase == XHQ_RESUME_CHECK || phase == XHQ_RESUMING)) return -EPERM;
  return f->guard_error;
}
static int now(void *ctx, uint64_t *n) { *n = ((struct fake *)ctx)->now; return 0; }
static int fault(struct fake *f, int op, unsigned m)
{
  f->calls[op][m]++;
  if (op == f->op && (int)m == f->member) { f->now += f->delay; return f->result; }
  return 0;
}
static int close_gate(void *ctx, unsigned m, uint64_t *ticket)
{
  struct fake *f = ctx;
  CHECK(!(f->closed & (1u << m)));
  if (m == f->nblocks + 1u) CHECK(f->drained == (1u << m) - 1u);
  int r = fault(f, CLOSE, m);
  if (r) return r;
  f->closed |= 1u << m;
  *ticket = f->bad_ticket ? 0 : 100u + m;
  return 0;
}
static int poll_gate(void *ctx, unsigned m, uint64_t ticket)
{
  struct fake *f = ctx;
  CHECK(ticket == 100u + m && (f->closed & (1u << m)) && !(f->reopened & (1u << m)));
  int r = fault(f, POLL, m);
  if (!r) f->drained |= 1u << m;
  return r;
}
static int resume_gate(void *ctx, unsigned m, uint64_t ticket)
{
  struct fake *f = ctx;
  CHECK(ticket == 100u + m && (f->drained & (1u << m)) && !(f->reopened & (1u << m)));
  int r = fault(f, RESUME, m);
  if (r) return r;
  f->order[f->nresume++] = m;
  f->reopened |= 1u << m;
  return 0;
}
static const struct xhq_ops ops = { now, guard, close_gate, poll_gate, resume_gate };
static void fresh(struct fake *f, struct xhq *q, uint64_t *c)
{
  *f = (struct fake){ .now = 1, .nblocks = 2, .op = -1 };
  CHECK(xhq_init(q, &ops, f, 17, 2) == 0);
  CHECK(xhq_begin(q, 17, 100, c) == 0 && *c == 1);
}
static int drive(struct xhq *q, uint64_t c)
{
  int r = -EAGAIN;
  for (unsigned i = 0; i < 16 && r == -EAGAIN; i++) r = xhq_step(q, 17, c);
  return r;
}
static void park(struct xhq *q, uint64_t c) { CHECK(drive(q, c) == 0 && q->phase == XHQ_PARKED); }
/* Stub the actual ABI to test the runtime adapter's dispatch and membership.
 * Real device providers retain their own G24.8/G24.9 regression suites. */
struct xh_virtio { unsigned member; };
static struct fake *binding;
int xh_virtio_gpu_quiesce_close(struct xh_virtio *d, uint64_t *t) { CHECK(d->member == 0); return close_gate(binding, d->member, t); }
int xh_virtio_gpu_quiesce_poll(struct xh_virtio *d, uint64_t t) { CHECK(d->member == 0); return poll_gate(binding, d->member, t); }
int xh_virtio_gpu_quiesce_resume(struct xh_virtio *d, uint64_t t) { CHECK(d->member == 0); return resume_gate(binding, d->member, t); }
int xh_virtio_blk_quiesce_close(struct xh_virtio *d, uint64_t *t) { CHECK(d->member > 0); return close_gate(binding, d->member, t); }
int xh_virtio_blk_quiesce_poll(struct xh_virtio *d, uint64_t t) { CHECK(d->member > 0); return poll_gate(binding, d->member, t); }
int xh_virtio_blk_quiesce_resume(struct xh_virtio *d, uint64_t t) { CHECK(d->member > 0); return resume_gate(binding, d->member, t); }
int xh_display_quiesce_close(uint64_t *t) { return close_gate(binding, binding->nblocks+1, t); }
int xh_display_quiesce_poll(uint64_t t) { return poll_gate(binding, binding->nblocks+1, t); }
int xh_display_quiesce_resume(uint64_t t) { return resume_gate(binding, binding->nblocks+1, t); }
int main(void)
{
  struct xhq q;
  struct fake f;
  uint64_t c, other;
  fresh(&f, &q, &c);
  CHECK(xhq_step(&q, 18, c) == -ESTALE && xhq_step(&q, 17, c+1) == -ESTALE);
  CHECK(xhq_begin(&q, 17, 200, &other) == -EBUSY && xhq_request_resume(&q, 17, c) == -EBUSY);
  f.op = CLOSE; f.member = 2; f.result = -EAGAIN;
  CHECK(xhq_step(&q, 17, c) == -EAGAIN && q.closed == 3 && !f.calls[CLOSE][3]);
  f.op = POLL; f.member = 0;
  CHECK(xhq_step(&q, 17, c) == -EAGAIN && q.closed == 7);
  CHECK(xhq_step(&q, 17, c) == -EAGAIN && !f.calls[CLOSE][3]);
  f.op = -1; park(&q, c);
  CHECK(q.closed == 15 && q.verified == 15 && f.calls[CLOSE][0] == 1);
  f.op = POLL; f.member = 3; f.result = -EAGAIN;
  CHECK(xhq_step(&q, 17, c) == -EAGAIN && q.phase == XHQ_VERIFY && xhq_request_resume(&q, 17, c) == -EBUSY);
  f.op = -1; park(&q, c);
  CHECK(xhq_request_resume(&q, 17, c) == 0 && xhq_step(&q, 17, c) == -EAGAIN);
  f.op = RESUME; f.member = 3; f.result = -EAGAIN;
  CHECK(xhq_step(&q, 17, c) == -EAGAIN && q.resume_attempted == 8 && !q.reopened);
  f.op = RESUME; f.member = 2;
  CHECK(xhq_step(&q, 17, c) == -EAGAIN && q.reopened == 10 && !f.calls[RESUME][0]);
  f.op = -1; CHECK(drive(&q, c) == 0 && q.phase == XHQ_DONE && q.reopened == 15);
  CHECK(f.nresume == 4 && f.order[0] == 3 && f.order[1] == 1 && f.order[2] == 2 && f.order[3] == 0);
  f = (struct fake){ .now = 2, .nblocks = 2, .op = -1 };
  CHECK(xhq_begin(&q, 17, 100, &other) == 0 && other == 2 && xhq_step(&q, 17, c) == -ESTALE);
  park(&q, other);

  fresh(&f, &q, &c); f.now = 100;
  CHECK(drive(&q, c) == -ETIMEDOUT && q.phase == XHQ_FAULT && !q.closed);
  fresh(&f, &q, &c); f.op = CLOSE; f.member = 0; f.delay = 100;
  CHECK(drive(&q, c) == -ETIMEDOUT && q.closed == 1 && !f.calls[CLOSE][1]);
  fresh(&f, &q, &c); f.op = POLL; f.member = 1; f.delay = 100;
  CHECK(drive(&q, c) == -ETIMEDOUT && q.closed == 7 && !f.calls[CLOSE][3]);
  fresh(&f, &q, &c); f.bad_ticket = 1;
  CHECK(drive(&q, c) == -EPROTO && q.phase == XHQ_FAULT);
  fresh(&f, &q, &c); f.guard_error = -ESTALE;
  CHECK(drive(&q, c) == -ESTALE && q.phase == XHQ_FAULT && !q.closed);
  fresh(&f, &q, &c); park(&q, c); f.op = POLL; f.member = 3; f.result = -ENOTCONN;
  CHECK(drive(&q, c) == -ENOTCONN && q.phase == XHQ_FAULT && xhq_request_resume(&q, 17, c) == -ENOTCONN);
  fresh(&f, &q, &c); park(&q, c); f.deny_resume = 1;
  CHECK(xhq_request_resume(&q, 17, c) == -EPERM && q.phase == XHQ_FAULT && !q.resume_attempted);
  fresh(&f, &q, &c); park(&q, c);
  CHECK(xhq_request_resume(&q, 17, c) == 0); f.op = POLL; f.member = 1; f.result = -ESTALE;
  CHECK(drive(&q, c) == -ESTALE && !q.resume_attempted);
  fresh(&f, &q, &c); park(&q, c);
  CHECK(xhq_request_resume(&q, 17, c) == 0); f.op = RESUME; f.member = 2; f.result = -EIO;
  CHECK(drive(&q, c) == -EIO && q.phase == XHQ_FAULT && q.reopened == 10 && q.resume_attempted == 14);
  CHECK(drive(&q, c) == -EIO && !f.calls[RESUME][0] && xhq_begin(&q, 17, 200, &other) == -EIO);
  fresh(&f, &q, &c); park(&q, c);
  CHECK(xhq_request_resume(&q, 17, c) == 0); f.op = RESUME; f.member = 3; f.delay = 100;
  CHECK(drive(&q, c) == -ETIMEDOUT && q.reopened == 8 && q.resume_attempted == 8);
  fresh(&f, &q, &c); f.now = 0;
  CHECK(drive(&q, c) == -ESTALE && !q.closed);

  struct xhq_runtime b;
  struct xh_virtio dev[XHQ_MAX_BLOCKS+1];
  struct xh_virtio *blocks[XHQ_MAX_BLOCKS];
  for (unsigned i = 0; i <= XHQ_MAX_BLOCKS; i++) { dev[i].member = i; if (i) blocks[i-1] = &dev[i]; }
  f = (struct fake){ .nblocks = XHQ_MAX_BLOCKS, .op = -1 }; binding = &f;
  CHECK(xhq_runtime_init(&q, &b, 17, &dev[0], blocks, 1, 2, guard, &f) == -EINVAL);
  blocks[1] = blocks[0];
  CHECK(xhq_runtime_init(&q, &b, 17, &dev[0], blocks, 2, 2, guard, &f) == -EINVAL);
  blocks[1] = &dev[2];
  CHECK(xhq_runtime_init(&q, &b, 17, &dev[0], blocks, XHQ_MAX_BLOCKS, XHQ_MAX_BLOCKS, guard, &f) == 0);
#ifdef CLOCK_BOOTTIME
  CHECK(xhq_begin(&q, 17, UINT64_MAX, &c) == 0); park(&q, c);
  CHECK(q.closed == 255 && q.verified == 255 && xhq_request_resume(&q, 17, c) == 0);
  CHECK(drive(&q, c) == 0 && q.reopened == 255 && f.nresume == 8 && f.order[0] == 7 && f.order[7] == 0);
#else
  CHECK(xhq_begin(&q, 17, UINT64_MAX, &c) == -ENOTSUP);
#endif
  printf("quiesce coordinator: %u checks, 0 failed\n", checks);
  return 0;
}
