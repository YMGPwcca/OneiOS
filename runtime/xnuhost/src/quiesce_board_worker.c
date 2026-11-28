/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include "quiesce_board_worker.h"
#include "quiesce_vcpu.h"
#include "quiesce_input.h"
#include "xnuhost.h"
#include "bridges/devices.h"
#include <errno.h>
#include <poll.h>
#include <time.h>

enum gate { INPUT, CPU, CONSOLE, BRIDGE, SOUND, GATES };
enum operation { CLOSE, VERIFY, RELEASE };
static uint64_t *ticket(struct xhqb_binding *b, enum gate g)
{
  switch (g) {
  case INPUT: return &b->input_ticket;
  case CPU: return &b->vcpu_ticket;
  case CONSOLE: return &b->console_ticket;
  case BRIDGE: return &b->bridge_ticket;
  case SOUND: return &b->sound_ticket;
  default: return NULL;
  }
}
static bool present(const struct xhqb_binding *b, enum gate g)
{
  return g == BRIDGE ? b->bridge != NULL : g == SOUND ? b->sound != NULL : true;
}
static int outer_call(struct xhqb_binding *b, enum gate g, enum operation op)
{
  uint64_t *t = ticket(b, g);
  if (!t) return -EINVAL;
  if (!present(b, g)) return *t ? -EPROTO : 0;
  if (op == CLOSE && *t) return -EPROTO;
  if (op != CLOSE && !*t) return -EPROTO;
  switch (g) {
  case INPUT:
    return op == CLOSE ? xhqi_close(t) : op == VERIFY ? xhqi_poll(*t) : xhqi_resume(*t);
  case CPU:
    return op == CLOSE ? xhqv_close(t) : op == VERIFY ? xh_tasks_quiesce_check(*t) : xhqv_resume(*t);
  case CONSOLE:
    return op == CLOSE ? xhqb_console_close(t) : op == VERIFY ? xhqb_console_poll(*t) : xhqb_console_resume(*t);
  case BRIDGE:
    return op == CLOSE ? br_bridge_quiesce_close(b->bridge,t) :
           op == VERIFY ? br_bridge_quiesce_poll(b->bridge,*t,NULL) :
                          br_bridge_quiesce_resume(b->bridge,*t);
  case SOUND:
    return op == CLOSE ? br_snd_quiesce_close(b->sound,t) :
           op == VERIFY ? br_snd_quiesce_poll(b->sound,*t) :
                          br_snd_quiesce_resume(b->sound,*t);
  default: return -EINVAL;
  }
}
static int boundary(struct xhqb_worker *w, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  if (!w->ready || owner != w->q.owner || cycle != w->q.cycle) return -ESTALE;
  int r = xhqs_worker_check(&w->ipc, w->q.deadline);
  if (!r) r = w->binding.guard(w->binding.ctx, owner, cycle, phase);
  if (!r) r = xhqs_worker_check(&w->ipc, w->q.deadline);
  return r;
}
static int retry(struct xhqb_worker *w, enum gate g, enum operation op,
                 uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  if (!present(&w->binding, g)) return 0;
  for (;;) {
    int r = boundary(w,owner,cycle,phase);
    if (r) return r;
    r = outer_call(&w->binding,g,op);
    uint64_t *t = ticket(&w->binding,g);
    // Never retry a close that returned a ticket with an error. Never
    // retry a successful release, even if the boundary subsequently fails.
    if (op == CLOSE && ((!r && !*t) || (r && *t))) return -EPROTO;
    if (op == RELEASE && !r) w->released |= 1u << g;
    int c = boundary(w,owner,cycle,phase);
    if (c) return c;
    if (r != -EAGAIN) return r;
    nanosleep(&(struct timespec){.tv_nsec=1000000L},NULL);
  }
}
static int verify_all(struct xhqb_worker *w, uint64_t owner, uint64_t cycle,
                      enum xhq_phase phase)
{
  for (;;) {
    int r = boundary(w,owner,cycle,phase);
    if (r) return r;
    r = xhqb_binding_verify(&w->binding);
    int c = boundary(w,owner,cycle,phase);
    if (c) return c;
    if (r != -EAGAIN) return r;
    nanosleep(&(struct timespec){.tv_nsec=1000000L},NULL);
  }
}
static int worker_guard(void *ctx,uint64_t owner,uint64_t cycle,enum xhq_phase phase)
{
  struct xhqb_worker *w=ctx;
  int r=boundary(w,owner,cycle,phase);
  if (r) return r;
  if (w->prepared_cycle != cycle) {
    if (phase != XHQ_CLOSING || w->prepared_cycle || w->released ||
        w->binding.input_ticket || w->binding.vcpu_ticket ||
        w->binding.console_ticket || w->binding.bridge_ticket || w->binding.sound_ticket)
      return -ESTALE;
    // Input first: a live script refuses before other gates change.
    // Park guest execution before asking device producers to drain.
    // Actual board classification was checked before accepting the channel.
    for (enum gate g=INPUT; g<GATES; g++) {
      if ((r=retry(w,g,CLOSE,owner,cycle,phase)) ||
          (r=retry(w,g,VERIFY,owner,cycle,phase))) return r;
    }
    w->prepared_cycle=cycle;
  }
  return verify_all(w,owner,cycle,phase);
}
static int finish_resume(void *ctx,uint64_t owner,uint64_t cycle)
{
  struct xhqb_worker *w=ctx;
  if (w->q.phase != XHQ_DONE || w->prepared_cycle != cycle || w->released)
    return -ESTALE;
  // All GPU/block/display reopen ACKs precede outer release. Keep the
  // vCPU rendezvous closed until all other producers were released.
  int r=verify_all(w,owner,cycle,XHQ_RESUMING);
  if (r) return r;
  static const enum gate order[]={SOUND,BRIDGE,CONSOLE,INPUT,CPU};
  for (unsigned i=0;i<sizeof order/sizeof order[0];i++)
    if ((r=retry(w,order[i],RELEASE,owner,cycle,XHQ_RESUMING))) return r;
  for (enum gate g=INPUT;g<GATES;g++) {
    if (present(&w->binding,g) && !(w->released & (1u<<g))) return -EPROTO;
    *ticket(&w->binding,g)=0;
  }
  w->prepared_cycle=0; w->released=0;
  return 0;
}
static int runtime_ready(void *ctx)
{
  struct xhqb_worker *w=ctx;
  if (!w->ready || w->q.phase!=XHQ_IDLE || w->q.cycle) return -ESTALE;
  int r=xhqb_match(&w->binding.board);
  if (!r) r=xh_display_quiesce_verify_helper();
  if (!r) r=xhqi_ready();
  if (!r) r=xhqv_ready();
  if (!r) r=w->binding.guard(w->binding.ctx,w->q.owner,0,XHQ_IDLE);
  if (!r) r=xhqb_match(&w->binding.board);
  return r;
}
int xhqb_worker_init(struct xhqb_worker *w,int fd,pid_t pid,uid_t uid,gid_t gid,
    uint64_t owner,int helper_pidfd,uid_t helper_uid,gid_t helper_gid,
    int (*guard)(void *,uint64_t,uint64_t,enum xhq_phase),void *ctx)
{
  if (!w || w->attempted || !guard || !owner || fd<0 || helper_pidfd<0)
    return -EINVAL;
  w->attempted=true;
  w->binding.guard=guard; w->binding.ctx=ctx;
  int r=xhqb_binding_snapshot(&w->binding);
  if (!r) r=xh_display_quiesce_bind_helper(helper_pidfd,helper_uid,helper_gid);
  if (!r) r=xh_display_quiesce_verify_helper();
  if (!r) r=xhq_runtime_init(&w->q,&w->binding.runtime,owner,w->binding.board.gpu,
      w->binding.board.blocks,w->binding.board.nblocks,w->binding.board.nblocks,
      worker_guard,w);
  if (!r) r=xhqs_worker_init(&w->ipc,fd,pid,uid,gid,&w->q);
  if (r) return r; // no rebind on the same process after a partial init
  w->ipc.finish_resume=finish_resume; w->ipc.finish_ctx=w;
  w->ipc.ready_check=runtime_ready; w->ipc.ready_ctx=w;
  w->ready=true;
  return 0;
}
int xhqb_worker_run(struct xhqb_worker *w)
{
  if (!w || !w->ready) return -EINVAL;
  for (;;) {
    struct pollfd f[]={{.fd=w->ipc.peer.fd,.events=POLLIN},
                       {.fd=w->ipc.peer.pidfd,.events=POLLIN}};
    int n=poll(f,2,-1);
    if (n<0) { if (errno==EINTR) continue; return -errno; }
    if (f[1].revents) return -ESRCH;
    if (f[0].revents & (POLLHUP|POLLERR|POLLNVAL)) return -ENOTCONN;
    if (!(f[0].revents & POLLIN)) continue;
    int r=xhqs_worker_once(&w->ipc);
    if (w->ipc.fault) return w->ipc.fault;
    if (r && r!=-EAGAIN) return r;
  }
}
void xhqb_worker_close(struct xhqb_worker *w)
{
  if (w && w->ready) {
    w->ready=false;
    xhqs_worker_close(&w->ipc);
  }
}
