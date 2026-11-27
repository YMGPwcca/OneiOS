// SPDX-License-Identifier: MIT
#define _GNU_SOURCE
#include "audio/quiesce_link.h"
#include <stdio.h>
#include <stdlib.h>
#include <sys/syscall.h>
#include <sys/wait.h>
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
static void exchange(int fd, unsigned ask, unsigned answer, unsigned t, int mode)
{
  struct au_header h;
  if (recv(fd, &h, sizeof h, 0) != sizeof h || h.kind != ask || h.value != t) _exit(2);
  h.kind = answer;
  if (mode == 1) h.value++;
  if (mode == 2) {
    struct au_header stale = { .kind = AU_STATE };
    if (send(fd, &stale, sizeof stale, 0) != sizeof stale) _exit(3);
    struct { struct au_header h; int16_t pcm[2]; } p = {{.kind=AU_PCM,.channels=1,.value=2},{1,2}};
    if (send(fd, &p, sizeof p, 0) != sizeof p) _exit(4);
  }
  if (mode == 3) {
    pid_t impostor = fork();
    if (impostor < 0) _exit(5);
    if (!impostor) _exit(send(fd, &h, sizeof h, 0) == sizeof h ? 0 : 6);
    int status;
    if (waitpid(impostor, &status, 0) != impostor || status) _exit(7);
  } else if (mode == 4) {
    union { struct cmsghdr align; char bytes[CMSG_SPACE(sizeof(int))]; } anc = {0};
    struct iovec iov = {&h, sizeof h};
    struct msghdr m = {.msg_iov=&iov,.msg_iovlen=1,.msg_control=anc.bytes,.msg_controllen=sizeof anc.bytes};
    struct cmsghdr *c=CMSG_FIRSTHDR(&m);
    c->cmsg_level=SOL_SOCKET; c->cmsg_type=SCM_RIGHTS; c->cmsg_len=CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(c),&fd,sizeof fd);
    if (sendmsg(fd,&m,0)!=sizeof h) _exit(8);
  } else if (send(fd, &h, sizeof h, 0) != sizeof h) _exit(9);
}
static void child(int fd, int mode)
{
  if (mode == 5) { struct au_header h; if (recv(fd,&h,sizeof h,0)!=sizeof h) _exit(2); _exit(0); }
  exchange(fd, AU_QUIESCE, AU_QUIESCED, 1, mode);
  if (mode == 0 || mode == 2) {
    exchange(fd, AU_RESUME, AU_RESUMED, 1, 0);
    exchange(fd, AU_QUIESCE, AU_QUIESCED, 2, 0);
    exchange(fd, AU_RESUME, AU_RESUMED, 2, 0);
  }
  char end;
  if (recv(fd,&end,1,0)!=0) _exit(10);
  _exit(0);
}
static int wait_poll(auq_link *q, uint64_t t, bool resume)
{
  for (int i=0;i<2000;i++) { int r=resume?auq_resume(q,t):auq_poll(q,t); if(r!=-EAGAIN)return r; usleep(1000); }
  return -ETIMEDOUT;
}
int main(void)
{
  alarm(30);
  for (int mode=0;mode<6;mode++) {
    int f[2], one=1;
    CHECK(socketpair(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0,f)==0);
    CHECK(setsockopt(f[0],SOL_SOCKET,SO_PASSCRED,&one,sizeof one)==0);
    pid_t pid=fork(); CHECK(pid>=0);
    if(!pid){close(f[0]);child(f[1],mode);}
    close(f[1]);
    auq_link q={.fd=f[0],.pidfd=(int)syscall(SYS_pidfd_open,pid,0),.pid=pid,.uid=getuid(),.gid=getgid()};
    CHECK(q.pidfd>=0);
    CHECK(auq_close(&q,0)==-ESTALE && auq_close(&q,1)==0);
    CHECK(auq_resume(&q,1)==-ESTALE && auq_poll(&q,2)==-ESTALE);
    int r=wait_poll(&q,1,false);
    if(mode==0||mode==2){
      CHECK(r==0 && q.phase==AUQ_PARKED && auq_poll(&q,1)==0);
      CHECK(wait_poll(&q,1,true)==0 && q.phase==AUQ_OPEN);
      CHECK(auq_close(&q,1)==-ESTALE && auq_close(&q,2)==0);
      CHECK(wait_poll(&q,2,false)==0 && wait_poll(&q,2,true)==0);
    } else {CHECK(r<0 && r!=-ETIMEDOUT && q.phase==AUQ_FAULT); CHECK(auq_resume(&q,1)==-ESTALE);}
    close(q.fd);close(q.pidfd);
    int status;CHECK(waitpid(pid,&status,0)==pid&&status==0);
  }
  printf("audio helper link: %u checks, 0 failed\n",checks);return 0;
}
