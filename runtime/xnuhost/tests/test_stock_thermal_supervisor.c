/* Host-only: actual independent IPC + actual stock policy/controller.
 * Fake board/owned-group operations are intentionally NOT hardware proof. */
#define _GNU_SOURCE
#include "stock_thermal_supervisor.h"
#include <errno.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); exit(1); } } while (0)
static const struct oneios_thermal_identity id = {
  "51ca8a7b-7fe0-4075-be5f-6a9029b8d392",
  "51ca8a7b-7fe0-4075-be5f-6a9029b8d392.123.456",
  "ee7c626acb814d92901a8672dc8169ef"
};
struct fixture { struct xhqs_owner peer; struct oneios_owned_groups g; bool owned, outer_bad; };
static struct fixture *active;
static int verify(void *ctx,const struct oneios_thermal_identity *key)
{
  struct fixture *f=ctx;
  return f->owned && !strcmp(key->token,id.token) ? 0 : -EPERM;
}
static int outer(void *ctx,bool p)
{
  struct fixture *f=ctx;
  if (f->outer_bad) return -EPERM;
  return p ? (f->peer.phase==XHQ_PARKED ? 0 : -EPERM) :
    (f->peer.phase==XHQ_IDLE || f->peer.phase==XHQ_DONE ? 0 : -EPERM);
}
int oneios_owned_groups_verify(struct oneios_owned_groups *g,bool frozen)
{ return g==&active->g && !g->fault && g->freeze_confirmed==frozen ? 0 : -1; }
int oneios_owned_cpu_set(struct oneios_owned_groups *g,unsigned p)
{ CHECK(g==&active->g && active->owned); g->cpu_pct=p; return 0; }
int oneios_owned_freeze(struct oneios_owned_groups *g,unsigned ms)
{
  CHECK(g==&active->g && active->owned && ms<=2000);
  g->freeze_confirmed=true; return 0;
}
int oneios_owned_thaw(struct oneios_owned_groups *g,unsigned ms)
{
  CHECK(g==&active->g && active->owned && ms<=2000 && active->peer.phase==XHQ_PARKED);
  g->freeze_confirmed=false; return 0;
}
static int clock_ns(void *ctx,uint64_t *ns) { (void)ctx; return xhqs_now(ns); }
static int guard(void *ctx,uint64_t owner,uint64_t cycle,enum xhq_phase phase)
{ (void)ctx;(void)phase;return owner==17 && cycle ? 0 : -EPERM; }
static int close_gate(void *ctx,unsigned member,uint64_t *t)
{ (void)ctx; *t=member+1; return 0; }
static int poll_gate(void *ctx,unsigned member,uint64_t t)
{ (void)ctx; return t==member+1 ? 0 : -EINVAL; }
static const struct xhq_ops worker_ops={clock_ns,guard,close_gate,poll_gate,poll_gate};
static pid_t launch(struct fixture *f)
{
  memset(f,0,sizeof *f); f->owned=true; f->g.cpu_pct=70;
  snprintf(f->g.name,sizeof f->g.name,"oneios_guest.%s",id.token);
  active=f;
  int fd[2]; CHECK(!xhqs_pair(fd));
  pid_t owner=getpid(),pid=fork(); CHECK(pid>=0);
  if (!pid) {
    close(fd[0]);
    struct xhq q; struct xhqs_worker w;
    CHECK(!xhq_init(&q,&worker_ops,NULL,17,1));
    CHECK(!xhqs_worker_init(&w,fd[1],owner,getuid(),getgid(),&q));
    for (;;) {
      struct pollfd p={.fd=w.peer.fd,.events=POLLIN};
      CHECK(poll(&p,1,15000)==1);
      if (p.revents & (POLLHUP|POLLERR|POLLNVAL)) break;
      int r=xhqs_worker_once(&w);
      if (r && r!=-EAGAIN) break;
    }
    xhqs_worker_close(&w); _exit(0);
  }
  close(fd[1]); CHECK(!xhqs_owner_init(&f->peer,fd[0],pid,getuid(),getgid(),17,1));
  return pid;
}
static void finish(struct fixture *f,pid_t pid)
{
  xhqs_owner_close(&f->peer);
  int status; CHECK(waitpid(pid,&status,0)==pid && WIFEXITED(status) && !WEXITSTATUS(status));
}
static enum oneios_thermal_result tick(struct oneios_thermal_controller *c,unsigned seq,int temp)
{
  uint64_t n; CHECK(!xhqs_now(&n));
  struct oneios_thermal_sample s={.id=id,.seq=seq,.ms=n/1000000u,
    .cpu_mc=temp,.gpu_mc=40000,.ddr_mc=40000,.battery_dc=300,.lrp_dc=300,.board_ap_dc=400};
  struct oneios_thermal_native_sample h={.id=id,.seq=seq,.ms=s.ms,.severity=0};
  return oneios_thermal_controller_tick_stock(c,&s,&h);
}
int main(void)
{
  alarm(60);
  struct fixture f; pid_t pid=launch(&f);
  struct xh_stock_supervisor b; struct oneios_thermal_ops ops;
  uint64_t now; CHECK(!xhqs_now(&now));
  CHECK(!xh_stock_supervisor_bind(&b,&f.peer,&f.g,&id,now+30000000000ull,verify,outer,&f,&ops));
  CHECK(!ops.frequency_set && !ops.frequency_verify);
  struct oneios_thermal_controller c;
  CHECK(!oneios_thermal_controller_init_stock(&c,&f.g,&id,&ops,&b));
  CHECK(tick(&c,1,45000)==ONEIOS_THERMAL_RUNNING);
  CHECK(tick(&c,2,104800)==ONEIOS_THERMAL_PAUSED);
  CHECK(f.g.freeze_confirmed && f.g.cpu_pct==10 && f.peer.phase==XHQ_PARKED);
  uint64_t seq=f.peer.seq;
  CHECK(!ops.gpu_verify(&b,true) && f.peer.seq==seq); /* no IPC while frozen */
  /* Five cool samples + >5s hold. Real CLOCK_BOOTTIME; no fake clock. */
  for (unsigned i=3;i<7;i++)
    CHECK(tick(&c,i,45000)==ONEIOS_THERMAL_PAUSED);
  sleep(6);
  CHECK(tick(&c,7,45000)==ONEIOS_THERMAL_RUNNING);
  CHECK(!f.g.freeze_confirmed && f.peer.phase==XHQ_DONE && f.g.cpu_pct==10);
  CHECK(!c.freq_applied);
  CHECK(tick(&c,8,104800)==ONEIOS_THERMAL_PAUSED && f.peer.cycle==2);
  f.outer_bad=true;
  CHECK(tick(&c,9,45000)==ONEIOS_THERMAL_FAULT_UNCONFIRMED);
  CHECK(f.g.freeze_confirmed && c.fault);
  CHECK(tick(&c,10,45000)==ONEIOS_THERMAL_FAULT_UNCONFIRMED);
  finish(&f,pid);
  printf("STOCK_THERMAL_SUPERVISOR=PASS checks=%u DEVICE_ACCESS=NONE\n",checks);
  return 0;
}
