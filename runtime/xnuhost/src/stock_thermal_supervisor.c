/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include "stock_thermal_supervisor.h"
#include <errno.h>
#include <string.h>
#include <time.h>

static int now_ms(void *ctx, uint64_t *ms)
{
  (void)ctx;
  uint64_t ns;
  int r = xhqs_now(&ns);
  if (!r) *ms = ns / 1000000u;
  return r;
}
static int owner_valid(struct xh_stock_supervisor *b)
{
  uint64_t ns;
  if (!b || !b->peer || !b->groups || !b->session_verify || !b->outer_verify)
    return -EINVAL;
  int r = xhqs_now(&ns);
  if (r) return r;
  if (ns >= b->session_deadline) return -ETIMEDOUT;
  return b->session_verify(b->ctx, &b->id);
}
static int session_verify(void *ctx, const struct oneios_thermal_identity *id)
{
  struct xh_stock_supervisor *b = ctx;
  if (!b || !id ||
      memcmp(id->boot, b->id.boot, sizeof id->boot) ||
      memcmp(id->generation, b->id.generation, sizeof id->generation) ||
      memcmp(id->token, b->id.token, sizeof id->token)) return -ESTALE;
  return owner_valid(b);
}
static int limit_for(struct xh_stock_supervisor *b, unsigned ms, uint64_t *end)
{
  if (!ms || ms > ONEIOS_THERMAL_ACK_MS) return -EINVAL;
  int r = owner_valid(b);
  uint64_t now;
  if (r || (r = xhqs_now(&now))) return r;
  uint64_t budget = (uint64_t)ms * 1000000u;
  if (now >= b->session_deadline) return -ETIMEDOUT;
  *end = b->session_deadline - now < budget ? b->session_deadline : now + budget;
  return 0;
}
static bool parked(const struct xhqs_owner *o)
{
  return o->phase == XHQ_PARKED && o->members &&
    o->closed == o->members && o->verified == o->members &&
    !o->attempted && !o->reopened;
}
static bool opened(const struct xhqs_owner *o)
{
  return o->phase == XHQ_IDLE ||
    (o->phase == XHQ_DONE && o->reopened == o->members &&
     o->attempted == o->members);
}
/* No per-event polling in the normal render path. Wait only on a park
 * transition; each IPC is bounded by the SAME absolute operation limit. */
static int drive(struct xh_stock_supervisor *b, uint64_t limit, bool want_park)
{
  for (;;) {
    int r = owner_valid(b);
    if (r) return r;
    r = xhqs_owner_step_until(b->peer, limit);
    if (r != -EAGAIN) {
      if (r) return r;
      return (want_park ? parked(b->peer) : opened(b->peer)) ? 0 : -EPROTO;
    }
    (void)nanosleep(&(struct timespec){.tv_nsec=1000000L}, NULL);
  }
}
static int gpu_verify(void *ctx, bool pause)
{
  struct xh_stock_supervisor *b = ctx;
  int r = owner_valid(b);
  if (r || (r = xhqs_owner_check(b->peer))) return r;
  if (!pause) {
    if (b->groups->freeze_confirmed || !opened(b->peer)) return -EPERM;
  } else {
    if (!parked(b->peer)) return -EPERM;
    if (b->groups->freeze_confirmed) {
      /* Worker is frozen: never ask it to produce another ACK. Retain
       * the exact receipt only while independently verified freeze,
       * endpoint liveness and outer producer ownership hold. */
      if (oneios_owned_groups_verify(b->groups, true)) return -EPERM;
    } else {
      /* Before freeze or after thaw obtain a fresh actual worker receipt. */
      uint64_t end;
      if ((r = limit_for(b, ONEIOS_THERMAL_ACK_MS, &end)) ||
          (r = drive(b, end, true))) return r;
    }
  }
  if ((r = b->outer_verify(b->ctx, pause))) return r;
  if ((r = owner_valid(b))) return r;
  return xhqs_owner_check(b->peer);
}
static int gpu_quiesce(void *ctx, unsigned ms)
{
  struct xh_stock_supervisor *b = ctx;
  uint64_t end;
  int r = limit_for(b, ms, &end);
  if (r) return r;
  if (b->groups->freeze_confirmed) return -EPERM;
  if (!parked(b->peer)) {
    if (!opened(b->peer)) return -EPERM;
    r = xhqs_owner_begin_until(b->peer, b->session_deadline, end);
    if (r) return r;
  }
  if ((r = drive(b, end, true))) return r;
  if ((r = b->outer_verify(b->ctx, true)) || (r = owner_valid(b))) return r;
  uint64_t now;
  if ((r = xhqs_now(&now))) return r;
  return now < end ? xhqs_owner_check(b->peer) : -ETIMEDOUT;
}
static int gpu_resume(void *ctx, unsigned ms)
{
  struct xh_stock_supervisor *b = ctx;
  uint64_t end;
  int r = limit_for(b, ms, &end);
  if (r) return r;
  if (b->groups->freeze_confirmed || !parked(b->peer) ||
      oneios_owned_groups_verify(b->groups, false)) return -EPERM;
  if ((r = b->outer_verify(b->ctx, true)) || (r = owner_valid(b))) return r;
  if ((r = xhqs_owner_resume_until(b->peer, end)) || (r = drive(b, end, false))) return r;
  if ((r = b->outer_verify(b->ctx, false)) || (r = owner_valid(b))) return r;
  uint64_t now;
  if ((r = xhqs_now(&now))) return r;
  return now < end ? xhqs_owner_check(b->peer) : -ETIMEDOUT;
}
int xh_stock_supervisor_bind(struct xh_stock_supervisor *b,
    struct xhqs_owner *peer, struct oneios_owned_groups *groups,
    const struct oneios_thermal_identity *id, uint64_t session_deadline,
    int (*verify)(void *, const struct oneios_thermal_identity *),
    int (*outer)(void *, bool), void *ctx, struct oneios_thermal_ops *out)
{
  if (!b || !peer || !groups || !id || !verify || !outer || !out ||
      peer->phase != XHQ_IDLE || !peer->owner || !peer->members)
    return -EINVAL;
  *b = (struct xh_stock_supervisor){ .peer=peer, .groups=groups, .id=*id,
    .session_deadline=session_deadline, .session_verify=verify, .outer_verify=outer, .ctx=ctx };
  int r = gpu_verify(b, false);
  if (r) { memset(b, 0, sizeof *b); return r; }
  *out = (struct oneios_thermal_ops){
    .now_ms=now_ms, .session_verify=session_verify,
    .gpu_quiesce=gpu_quiesce, .gpu_verify=gpu_verify, .gpu_resume=gpu_resume
  };
  return 0;
}
