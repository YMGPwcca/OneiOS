/* SPDX-License-Identifier: MIT */
#include "stock_session_runner.h"
#include <errno.h>
#include <string.h>
#include <unistd.h>

static bool same(const struct oneios_thermal_identity *a,const struct oneios_thermal_identity *b)
{
  return !memcmp(a->boot,b->boot,sizeof a->boot)&&
    !memcmp(a->generation,b->generation,sizeof a->generation)&&
    !memcmp(a->token,b->token,sizeof a->token);
}
static int verify_session(void *ctx,const struct oneios_thermal_identity *id)
{
  struct xh_stock_runner *r=ctx;
  if(!r||!same(id,&r->session->id)||r->launch->owner_pid!=getpid()||
     r->launch->groups!=&r->session->groups||r->launch->phase!=ONEIOS_LAUNCH_RELEASED||
     r->peer->peer.pid!=r->launch->root[ONEIOS_GUEST_XNUHOST].pid)return -ESTALE;
  // Cross-hierarchy snapshots can race ordinary guest task creation.
  // Retry a few times without modifying membership or treating drift
  // as a successful verification. The external owner still proves
  // descendants that might have escaped BOTH groups.
  for(unsigned i=0;i<3;i++){
    if(!oneios_guest_launch_check_roots(r->launch))return r->verify(r->ctx,id);
    if(errno!=EAGAIN)return -EPERM;
  }
  return -EPERM;
}
static int outer_verify(void *ctx,bool parked)
{
  struct xh_stock_runner *r=ctx;
  return r->outer(r->ctx,parked);
}
static bool reader_ok(const struct xh_stock_reader *a,const struct oneios_thermal_identity *id,
    enum xh_stock_sample_kind kind)
{
  return a&&a->ready&&!a->fault&&!a->pending&&a->owner==getpid()&&
    a->kind==kind&&same(&a->id,id);
}
int xh_stock_runner_bind(struct xh_stock_runner *r,struct oneios_stock_session *s,
    struct oneios_guest_launch *l,struct xhqs_owner *p,struct xh_stock_reader *raw,
    struct xh_stock_reader *native,uint64_t deadline,
    int (*verify)(void *,const struct oneios_thermal_identity *),
    int (*outer)(void *,bool),void *ctx)
{
  if(!r||r->attempted||!s||s->phase!=ONEIOS_STOCK_PREPARED||!s->groups_owned||
     !l||!p||!p->runtime_ready||!verify||!outer||
     !reader_ok(raw,&s->id,XH_STOCK_RAW)||
     (native&&!reader_ok(native,&s->id,XH_STOCK_NATIVE)))return -EINVAL;
  *r=(struct xh_stock_runner){.session=s,.launch=l,.peer=p,.raw=raw,.native=native,
    .deadline=deadline,.verify=verify,.outer=outer,.ctx=ctx,.attempted=true,
    .last=ONEIOS_THERMAL_REFUSED};
  int rc=xh_stock_supervisor_bind(&r->adapter,p,&s->groups,&s->id,deadline,
                                  verify_session,outer_verify,r,&r->ops);
  if(rc)return rc;
  r->bound=true;return 0;
}
enum oneios_thermal_result xh_stock_runner_tick(struct xh_stock_runner *r)
{
  if(!r||!r->bound)return ONEIOS_THERMAL_REFUSED;
  if(r->activated&&r->last!=ONEIOS_THERMAL_RUNNING&&r->last!=ONEIOS_THERMAL_PAUSED)return r->last;
  uint64_t now,limit;
  struct xh_stock_reading raw,native;
  const struct oneios_thermal_sample *s=NULL;
  const struct oneios_thermal_native_sample *n=NULL;
  if(!xhqs_now(&now)&&now<r->deadline){
    uint64_t budget=(uint64_t)ONEIOS_THERMAL_MAX_SAMPLE_AGE_MS*1000000u;
    limit=r->deadline-now<budget?r->deadline:now+budget;
    if(r->native&&!r->native->pending&&!r->native->fault)
      (void)xh_stock_reader_request(r->native,limit);
    if(!xh_stock_reader_request(r->raw,limit)&&!xh_stock_reader_take(r->raw,true,&raw))
      s=&raw.raw;
    if(r->native&&r->native->pending&&!xh_stock_reader_take(r->native,false,&native))
      n=&native.native;
  }
  if(!r->activated){
    r->activated=true;
    r->last=oneios_stock_session_activate_sample(r->session,&r->ops,&r->adapter,s,n);
  }else r->last=oneios_stock_session_tick_sample(r->session,s,n);
  return r->last;
}
