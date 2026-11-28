/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include "stock_sample_reader.h"
#include "quiesce_supervisor.h"
#include <errno.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/timerfd.h>
#include <sys/uio.h>
#include <time.h>
#include <unistd.h>

#define MAGIC UINT32_C(0x31525358)
struct record {
  uint32_t magic, kind;
  uint64_t seq;
  int32_t status;
  struct xh_stock_reading value;
};
static int recv_record(int fd,pid_t pid,uid_t uid,gid_t gid,struct record *r)
{
  union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(struct ucred))+CMSG_SPACE(4*sizeof(int))]; } control;
  struct iovec io={r,sizeof *r};
  struct msghdr m={.msg_iov=&io,.msg_iovlen=1,.msg_control=control.bytes,.msg_controllen=sizeof control.bytes};
  ssize_t n=recvmsg(fd,&m,MSG_DONTWAIT|MSG_TRUNC|MSG_CMSG_CLOEXEC);
  if (n<0) return -errno;
  bool valid=true,cred=false;
  for(struct cmsghdr *c=CMSG_FIRSTHDR(&m);c;c=CMSG_NXTHDR(&m,c)){
    if(c->cmsg_level==SOL_SOCKET && c->cmsg_type==SCM_CREDENTIALS && c->cmsg_len==CMSG_LEN(sizeof(struct ucred))){
      struct ucred u;memcpy(&u,CMSG_DATA(c),sizeof u);
      if(cred||u.pid!=pid||u.uid!=uid||u.gid!=gid) valid=false;
      cred=true;
    }else{
      if(c->cmsg_level==SOL_SOCKET && c->cmsg_type==SCM_RIGHTS && c->cmsg_len>=CMSG_LEN(0)){
        size_t count=(c->cmsg_len-CMSG_LEN(0))/sizeof(int);
        for(size_t i=0;i<count;i++){int x;memcpy(&x,CMSG_DATA(c)+i*sizeof x,sizeof x);close(x);}
      }
      valid=false;
    }
  }
  if(!n)return -ENOTCONN;
  return n==(ssize_t)sizeof *r && !(m.msg_flags&(MSG_TRUNC|MSG_CTRUNC)) && valid && cred ? 0 : -EPROTO;
}
static int send_record(int fd,const struct record *r)
{
  ssize_t n=send(fd,r,sizeof *r,MSG_DONTWAIT|MSG_NOSIGNAL);
  return n==(ssize_t)sizeof *r?0:n<0?-errno:-EIO;
}
static int close_other(int fd)
{
#if defined(SYS_close_range)
  if(fd<3)return -EINVAL;
  if(fd>3 && syscall(SYS_close_range,3u,(unsigned)fd-1u,0u))return -errno;
  return syscall(SYS_close_range,(unsigned)fd+1u,UINT_MAX,0u)?-errno:0;
#else
  (void)fd;return -ENOTSUP;
#endif
}
static _Noreturn void child_loop(int fd,pid_t parent,uid_t uid,gid_t gid,
    enum xh_stock_sample_kind kind,struct oneios_raw_source raw,
    struct oneios_thermal_identity id,xh_stock_native_read_fn native)
{
  if(close_other(fd))_exit(125);
  uint64_t seq=kind==XH_STOCK_RAW?raw.seq:0;
  for(;;){
    struct pollfd p={.fd=fd,.events=POLLIN};
    int n=poll(&p,1,-1);
    if(n<0){if(errno==EINTR)continue;_exit(125);}
    if(p.revents&(POLLHUP|POLLERR|POLLNVAL))_exit(0);
    struct record req;
    int rc=recv_record(fd,parent,uid,gid,&req);
    if(rc==-EINTR||rc==-EAGAIN)continue;
    if(rc==-ENOTCONN)_exit(0);
    if(rc||req.magic!=MAGIC||req.kind!=(unsigned)kind||req.status||seq==UINT64_MAX||req.seq!=seq+1)_exit(125);
    struct record reply={.magic=MAGIC,.kind=kind,.seq=++seq};
    if(kind==XH_STOCK_RAW){
      errno=0;
      if(oneios_raw_source_read(&raw,&reply.value.raw))reply.status=errno?-errno:-EIO;
      if(!reply.status&&reply.value.raw.seq!=seq)reply.status=-EPROTO;
    }else{
      rc=native(&id,seq,&reply.value.native);
      reply.status=rc<0?rc:rc?-EIO:0;
    }
    if(send_record(fd,&reply))_exit(125);
    // A raw error is terminal for its sequence/manifest; do not silently
    // resume with a fresh sequence. Keep endpoint alive for receipt.
    if(kind==XH_STOCK_RAW&&reply.status){
      do n=poll(&p,1,-1);while(n<0&&errno==EINTR);
      _exit(0);
    }
  }
}
static int fail(struct xh_stock_reader *r,int error)
{
  if(!r->fault)r->fault=error<0&&error!=-EAGAIN?error:-EPROTO;
  r->pending=false;
  if(r->fd>=0)(void)shutdown(r->fd,SHUT_RDWR);
  return r->fault;
}
static int live(const struct xh_stock_reader *r)
{
  struct pollfd p={.fd=r->pidfd,.events=POLLIN};
  int n;
  do n=poll(&p,1,0);while(n<0&&errno==EINTR);
  return n<0?-errno:n?-ESRCH:0;
}
static int before(uint64_t limit)
{
  uint64_t now;int rc=xhqs_now(&now);
  return rc?rc:now>=limit?-ETIMEDOUT:0;
}
static int arm(const struct xh_stock_reader *r,uint64_t limit)
{
  struct itimerspec t={0};
  t.it_value.tv_sec=(time_t)(limit/1000000000u);
  t.it_value.tv_nsec=(long)(limit%1000000000u);
  if(t.it_value.tv_sec<0||(uint64_t)t.it_value.tv_sec!=limit/1000000000u)return -EOVERFLOW;
  return timerfd_settime(r->timerfd,TFD_TIMER_ABSTIME,&t,NULL)?-errno:0;
}
static int start(struct xh_stock_reader *r,enum xh_stock_sample_kind kind,
    const struct oneios_raw_source *raw,const struct oneios_thermal_identity *id,
    xh_stock_native_read_fn native)
{
  if(!r||r->attempted||!id||(kind==XH_STOCK_RAW&&(!raw||!raw->ready))||
     (kind==XH_STOCK_NATIVE&&!native))return -EINVAL;
  struct sigaction sa;
  if(sigaction(SIGCHLD,NULL,&sa)||sa.sa_handler!=SIG_DFL||(sa.sa_flags&SA_NOCLDWAIT))return -EPERM;
  *r=(struct xh_stock_reader){.id=*id,.owner=getpid(),.fd=-1,.pidfd=-1,.timerfd=-1,
      .kind=kind,.attempted=true,.seq=raw?raw->seq:0};
  int pair[2],rc=xhqs_pair(pair);
  if(rc)return fail(r,rc);
  pid_t pid=fork();
  if(!pid){
    close(pair[0]);
    child_loop(pair[1],r->owner,getuid(),getgid(),kind,raw?*raw:(struct oneios_raw_source){0},*id,native);
  }
  close(pair[1]);
  if(pid<0){rc=-errno;close(pair[0]);return fail(r,rc);}
  r->child=pid;r->fd=pair[0];
#if defined(SYS_pidfd_open)
  r->pidfd=(int)syscall(SYS_pidfd_open,pid,0);
  if(r->pidfd<0)return fail(r,-errno);
#else
  return fail(r,-ENOTSUP);
#endif
  r->timerfd=timerfd_create(CLOCK_BOOTTIME,TFD_NONBLOCK|TFD_CLOEXEC);
  if(r->timerfd<0)return fail(r,-errno);
  if((rc=live(r)))return fail(r,rc);
  r->ready=true;return 0;
}
int xh_stock_reader_raw(struct xh_stock_reader *r,const struct oneios_raw_source *s)
{ return s?start(r,XH_STOCK_RAW,s,&s->id,NULL):-EINVAL; }
int xh_stock_reader_native(struct xh_stock_reader *r,const struct oneios_thermal_identity *id,xh_stock_native_read_fn read)
{ return start(r,XH_STOCK_NATIVE,NULL,id,read); }
int xh_stock_reader_request(struct xh_stock_reader *r,uint64_t limit)
{
  if(!r||!r->ready||r->owner!=getpid()||r->pending)return -EINVAL;
  if(r->fault)return r->fault;
  if(r->seq==UINT64_MAX)return fail(r,-EOVERFLOW);
  int rc;
  if((rc=before(limit))||(rc=live(r))||(rc=arm(r,limit)))return fail(r,rc);
  struct record m={.magic=MAGIC,.kind=r->kind,.seq=++r->seq};
  if((rc=send_record(r->fd,&m)))return fail(r,rc);
  r->pending=true;r->deadline=limit;return 0;
}
static bool identity_equal(const struct oneios_thermal_identity *a,const struct oneios_thermal_identity *b)
{
  return !memcmp(a->boot,b->boot,sizeof a->boot)&&
    !memcmp(a->generation,b->generation,sizeof a->generation)&&
    !memcmp(a->token,b->token,sizeof a->token);
}
int xh_stock_reader_take(struct xh_stock_reader *r,bool wait,struct xh_stock_reading *out)
{
  if(!r||!out||!r->ready||r->owner!=getpid())return -EINVAL;
  if(r->fault)return r->fault;
  if(!r->pending)return -EINVAL;
  struct pollfd p[]={{.fd=r->timerfd,.events=POLLIN},{.fd=r->pidfd,.events=POLLIN},{.fd=r->fd,.events=POLLIN}};
  for(;;){
    int rc=before(r->deadline);
    if(rc)return fail(r,rc);
    int n=poll(p,3,wait?-1:0);
    if(n<0){if(errno==EINTR)continue;return fail(r,-errno);}
    if(!n)return -EAGAIN;
    if((rc=before(r->deadline)))return fail(r,rc);
    if(p[0].revents)return fail(r,-ETIMEDOUT);
    if(p[1].revents)return fail(r,-ESRCH);
    if(p[2].revents&(POLLHUP|POLLERR|POLLNVAL))return fail(r,-ENOTCONN);
    if(!(p[2].revents&POLLIN))continue;
    struct record m;
    rc=recv_record(r->fd,r->child,getuid(),getgid(),&m);
    if(rc==-EAGAIN||rc==-EINTR){if(!wait)return -EAGAIN;continue;}
    if(rc)return fail(r,rc);
    if(m.magic!=MAGIC||m.kind!=(unsigned)r->kind||m.seq!=r->seq||m.status>0)return fail(r,-EPROTO);
    if((rc=before(r->deadline))||(rc=live(r))||(rc=arm(r,0)))return fail(r,rc);
    r->pending=false;
    if(m.status)return r->kind==XH_STOCK_RAW?fail(r,m.status):-ENODATA;
    uint64_t ns; if((rc=xhqs_now(&ns)))return fail(r,rc);
    bool raw=r->kind==XH_STOCK_RAW;
    const struct oneios_thermal_identity *id=raw?&m.value.raw.id:&m.value.native.id;
    uint64_t seq=raw?m.value.raw.seq:m.value.native.seq,ms=raw?m.value.raw.ms:m.value.native.ms;
    if(!identity_equal(id,&r->id)||seq!=r->seq||ms>ns/1000000u||
       ns/1000000u-ms>ONEIOS_THERMAL_MAX_SAMPLE_AGE_MS)return fail(r,-ESTALE);
    if(!raw&&(m.value.native.severity<0||m.value.native.severity>6))return fail(r,-EPROTO);
    *out=m.value;return 0;
  }
}
void xh_stock_reader_close(struct xh_stock_reader *r)
{
  if(!r||!r->attempted||r->owner!=getpid())return;
  if(r->fd>=0){(void)shutdown(r->fd,SHUT_RDWR);close(r->fd);}
  if(r->pidfd>=0)close(r->pidfd);
  if(r->timerfd>=0)close(r->timerfd);
  r->fd=r->pidfd=r->timerfd=-1;r->ready=r->pending=false;
}
