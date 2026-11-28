/* Host fixture: actual sealed board, console, input, vCPU rendezvous,
 * coordinator and independent IPC. GPU/IO/bridge/helper are mock devices. */
#define _GNU_SOURCE
#include "quiesce_board_worker.h"
#include "quiesce_vcpu.h"
#include "quiesce_input.h"
#include "bridges/devices.h"
#include "oneios_bridge_proto.h"
#include <errno.h>
#include <pthread.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); exit(1); } } while (0)
struct xh_virtio { unsigned member; };
static struct xh_virtio dev[5];
static int kind;
static unsigned inner, external, last_release, helper_binds, task_polls;
static bool stop_thread;
static int map_ok(void *ctx) { (void)ctx; return 0; }
static void map(unsigned i,unsigned type)
{
  CHECK(!xhqb_map(&dev[i],0x10000u+0x1000u*i,32+i,type,map_ok,NULL));
}
static void make_board(int k)
{
  CHECK(!xhqb_begin(0x10000,0x1000,32,1));
  dev[0].member=1; map(0,2); dev[1].member=0; map(1,16);
  map(2,18); map(3,OB_VIRTIO_DEVICE_ID); map(4,k==2?1:25);
  CHECK(!xhqb_seal(5) && !xhqi_seal());
}
static void *vcpu(void *arg)
{
  unsigned i=(unsigned)(uintptr_t)arg;
  xhqv_register(i);
  while (!__atomic_load_n(&stop_thread,__ATOMIC_ACQUIRE)) {
    xhqv_checkpoint(i);
    usleep(500);
  }
  return NULL;
}
int xh_tasks_quiesce_check(uint64_t t)
{
  int r=xhqv_poll(t);
  if (!r) task_polls++;
  return r;
}
int xh_display_quiesce_bind_helper(int pidfd,uid_t uid,gid_t gid)
{ (void)uid;(void)gid; CHECK(pidfd==99 && !helper_binds); ++helper_binds; return 0; }
int xh_display_quiesce_verify_helper(void) { return helper_binds==1?0:-EPERM; }
static int close_inner(unsigned m,uint64_t *t)
{
  CHECK(!(inner&(1u<<m)) && external==3 && task_polls);
  CHECK(__atomic_load_n(&xhqv_state,__ATOMIC_ACQUIRE)&XHQV_CLOSED);
  CHECK(__atomic_load_n(&xhqi_flags,__ATOMIC_ACQUIRE)&XHQI_CLOSED);
  CHECK(!xhqb_console_enter());
  inner|=1u<<m; *t=m+1; return 0;
}
static int poll_inner(unsigned m,uint64_t t)
{ return t==m+1 && (inner&(1u<<m))?0:-ESTALE; }
static int resume_inner(unsigned m,uint64_t t)
{
  CHECK(!poll_inner(m,t) && external==3);
  CHECK(__atomic_load_n(&xhqv_state,__ATOMIC_ACQUIRE)&XHQV_CLOSED);
  inner &= ~(1u<<m); return 0;
}
int xh_virtio_gpu_quiesce_close(struct xh_virtio *d,uint64_t *t) { CHECK(d==&dev[1]);return close_inner(0,t); }
int xh_virtio_gpu_quiesce_poll(struct xh_virtio *d,uint64_t t) { CHECK(d==&dev[1]);return poll_inner(0,t); }
int xh_virtio_gpu_quiesce_resume(struct xh_virtio *d,uint64_t t) { CHECK(d==&dev[1]);return resume_inner(0,t); }
int xh_virtio_blk_quiesce_close(struct xh_virtio *d,uint64_t *t) { CHECK(d==&dev[0]);return close_inner(1,t); }
int xh_virtio_blk_quiesce_poll(struct xh_virtio *d,uint64_t t) { CHECK(d==&dev[0]);return poll_inner(1,t); }
int xh_virtio_blk_quiesce_resume(struct xh_virtio *d,uint64_t t) { CHECK(d==&dev[0]);return resume_inner(1,t); }
int xh_display_quiesce_close(uint64_t *t) { CHECK(inner==3);return close_inner(2,t); }
int xh_display_quiesce_poll(uint64_t t) { return poll_inner(2,t); }
int xh_display_quiesce_resume(uint64_t t) { return resume_inner(2,t); }
int br_bridge_quiesce_close(xh_virtio *d,uint64_t *t)
{ CHECK(d==&dev[3]&&!external&&!inner);external|=1;*t=31;return 0; }
int br_bridge_quiesce_poll(xh_virtio *d,uint64_t t,unsigned *m)
{ (void)m;return d==&dev[3]&&t==31&&(external&1)?0:-ESTALE; }
int br_bridge_quiesce_resume(xh_virtio *d,uint64_t t)
{
  CHECK(!br_bridge_quiesce_poll(d,t,NULL)&&!inner&&external==1&&last_release==2);
  CHECK(__atomic_load_n(&xhqv_state,__ATOMIC_ACQUIRE)&XHQV_CLOSED);
  if(kind==1)return -EIO;
  last_release=0;external=0;return 0;
}
int br_snd_quiesce_close(xh_virtio *d,uint64_t *t)
{ CHECK(d==&dev[4]&&external==1&&!inner);external|=2;*t=37;return 0; }
int br_snd_quiesce_poll(xh_virtio *d,uint64_t t)
{ return d==&dev[4]&&t==37&&(external&2)?0:-ESTALE; }
int br_snd_quiesce_resume(xh_virtio *d,uint64_t t)
{ CHECK(!br_snd_quiesce_poll(d,t)&&external==3&&!inner);external=1;last_release=2;return 0; }
static int guard(void *ctx,uint64_t owner,uint64_t cycle,enum xhq_phase p)
{ (void)ctx;CHECK(owner==17&&(cycle||p==XHQ_IDLE)&&p!=XHQ_FAULT);return 0; }
static uint64_t end(void)
{ uint64_t n;CHECK(!xhqs_now(&n));return n+5000000000ull; }
static int drive(struct xhqs_owner *o)
{ int r=-EAGAIN;for(unsigned i=0;i<32&&r==-EAGAIN;i++)r=xhqs_owner_step(o);return r; }
static void scenario(int k)
{
  int fd[2];CHECK(!xhqs_pair(fd));
  pid_t parent=getpid(),pid=fork();CHECK(pid>=0);
  if(!pid){
    close(fd[0]);kind=k;make_board(k);
    struct xhqb_worker w={0};
    if(k==2){
      CHECK(xhqb_worker_init(&w,fd[1],parent,getuid(),getgid(),17,99,getuid(),getgid(),guard,NULL)==-ENOTSUP);
      CHECK(!helper_binds&&!w.ready);
      close(fd[1]);_exit(0);
    }
    CHECK(!xhqv_configure(2));
    pthread_t th[2];
    for(unsigned i=0;i<2;i++)CHECK(!pthread_create(&th[i],NULL,vcpu,(void *)(uintptr_t)i));
    CHECK(!xhqb_worker_init(&w,fd[1],parent,getuid(),getgid(),17,99,getuid(),getgid(),guard,NULL));
    int r=xhqb_worker_run(&w);
    if(k==1){
      CHECK(r==-EIO&&w.q.phase==XHQ_FAULT&&w.released==(1u<<4));
      CHECK(!inner&&external==1&&(__atomic_load_n(&xhqv_state,__ATOMIC_ACQUIRE)&XHQV_CLOSED));
      CHECK(!xhqb_console_enter());
      // Keep the process/socket alive until the owner consumes the negative
      // ACK and shuts down; otherwise peer death could win the ACK race.
      struct pollfd p={.fd=w.ipc.peer.fd,.events=POLLIN};
      CHECK(poll(&p,1,5000)==1 && (p.revents & (POLLIN|POLLHUP|POLLERR)));
      // Deliberate terminal fixture exit, never release failed gates.
    }else{
      CHECK(r==-ENOTCONN||r==-ESRCH);
      CHECK(w.q.phase==XHQ_DONE&&!inner&&!external&&!w.prepared_cycle&&!w.released);
      CHECK(!(__atomic_load_n(&xhqv_state,__ATOMIC_ACQUIRE)&XHQV_CLOSED));
      CHECK(!(__atomic_load_n(&xhqi_flags,__ATOMIC_ACQUIRE)&XHQI_CLOSED));
      CHECK(xhqb_console_enter());xhqb_console_leave();
      __atomic_store_n(&stop_thread,true,__ATOMIC_RELEASE);
      for(unsigned i=0;i<2;i++)CHECK(!pthread_join(th[i],NULL));
    }
    xhqb_worker_close(&w);_exit(0);
  }
  close(fd[1]);
  if(k!=2){
    struct xhqs_owner o;CHECK(!xhqs_owner_init(&o,fd[0],pid,getuid(),getgid(),17,1));
    int ready;
    uint64_t limit=end();
    do {ready=xhqs_owner_ready_until(&o,limit);if(ready==-EAGAIN)usleep(1000);}while(ready==-EAGAIN);
    CHECK(!ready&&o.runtime_ready);
    for(unsigned i=0;i<(k==1?1u:2u);i++){
      CHECK(!xhqs_owner_begin(&o,end()));
      CHECK(!drive(&o)&&o.phase==XHQ_PARKED&&o.verified==7);
      CHECK(!xhqs_owner_resume(&o));
      if(k==1)CHECK(drive(&o)==-EIO&&o.phase==XHQ_FAULT&&o.reopened==7);
      else CHECK(!drive(&o)&&o.phase==XHQ_DONE&&o.reopened==7);
    }
    xhqs_owner_close(&o);
  }else close(fd[0]);
  int status;CHECK(waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&!WEXITSTATUS(status));
}
int main(void)
{
  alarm(30);
  scenario(0);scenario(1);scenario(2);
  printf("BOARD_WORKER_OFFLINE=PASS parent_checks=%u DEVICE_ACCESS=NONE\n",checks);
  return 0;
}
