#define _GNU_SOURCE
#include "quiesce_supervisor.h"
#include <errno.h>
#include <dirent.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
enum { NORMAL, STALL, DEATH, PARTIAL, DENY, DROP, BAD_CMD, BAD_SEQ, BAD_CRED, RIGHTS, SHORT, UNSOLICITED };
struct fixture { int kind, report, release; unsigned closed, reopened, polls; };
static int now(void *ctx, uint64_t *ns) { (void)ctx; return xhqs_now(ns); }
static int guard(void *ctx, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  struct fixture *f = ctx;
  CHECK(owner == 17 && cycle);
  return f->kind == DENY && phase == XHQ_RESUME_CHECK ? -EPERM : 0;
}
static int close_gate(void *ctx, unsigned m, uint64_t *t)
{
  struct fixture *f = ctx;
  if (m == 0) f->closed = f->reopened = 0;
  CHECK(!(f->closed & (1u << m)));
  f->closed |= 1u << m;
  *t = 100 + m;
  return 0;
}
static int poll_gate(void *ctx, unsigned m, uint64_t t)
{
  struct fixture *f = ctx;
  CHECK(t == 100 + m && (f->closed & (1u << m)) && !(f->reopened & (1u << m)));
  f->polls++;
  if (m == 1 && f->kind == DEATH) _exit(0);
  if ((m == 1 && f->kind == STALL) || (m == 0 && f->kind == DROP)) {
    char c = 'x';
    CHECK(write(f->report, &c, 1) == 1);
    CHECK(read(f->release, &c, 1) == 1);
  }
  return 0;
}
static int resume_gate(void *ctx, unsigned m, uint64_t t)
{
  struct fixture *f = ctx;
  CHECK(t == 100 + m && !(f->reopened & (1u << m)));
  if (m == 1 && f->kind == PARTIAL) return -EIO;
  f->reopened |= 1u << m;
  return 0;
}
static const struct xhq_ops ops = { now, guard, close_gate, poll_gate, resume_gate };
static void wait_disconnect(int fd)
{
  struct pollfd p = { .fd = fd, .events = POLLIN };
  CHECK(poll(&p, 1, 10000) == 1);
  CHECK(p.revents & (POLLHUP | POLLERR | POLLIN));
}
/* Malicious fixture peers use the same fixed-size local wire layout. */
struct wire {
  uint64_t owner, cycle, seq, deadline;
  uint32_t magic, op, phase, closed, verified, attempted, reopened;
  int32_t result;
};
_Static_assert(sizeof(struct wire) == 64, "test wire ABI");
static void raw_worker(int fd, int kind, int report)
{
  struct wire a = {0};
  if (kind != UNSOLICITED) {
    struct pollfd p = { .fd = fd, .events = POLLIN };
    CHECK(poll(&p, 1, 10000) == 1);
    CHECK(recv(fd, &a, sizeof a, 0) == sizeof a);
  }
  a.op |= UINT32_C(0x80000000);
  a.phase = XHQ_CLOSING;
  if (kind == BAD_SEQ) a.seq++;
  if (kind == BAD_CRED) {
    pid_t impostor = fork(); CHECK(impostor >= 0);
    if (!impostor) { CHECK(send(fd, &a, sizeof a, MSG_NOSIGNAL) == sizeof a); _exit(0); }
    int status; CHECK(waitpid(impostor, &status, 0) == impostor && WIFEXITED(status) && !WEXITSTATUS(status));
  } else if (kind == RIGHTS) {
    union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(int))]; } ancillary = {0};
    struct iovec iov = { &a, sizeof a };
    struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1, .msg_control = ancillary.bytes, .msg_controllen = sizeof ancillary.bytes };
    struct cmsghdr *c = CMSG_FIRSTHDR(&msg);
    c->cmsg_level = SOL_SOCKET; c->cmsg_type = SCM_RIGHTS; c->cmsg_len = CMSG_LEN(sizeof(int));
    *(int *)CMSG_DATA(c) = fd;
    CHECK(sendmsg(fd, &msg, MSG_NOSIGNAL) == sizeof a);
  } else {
    size_t n = kind == SHORT ? 1 : sizeof a;
    CHECK(send(fd, &a, n, MSG_NOSIGNAL) == (ssize_t)n);
  }
  if (kind == UNSOLICITED) { char c = 'x'; CHECK(write(report, &c, 1) == 1); }
  wait_disconnect(fd);
}
struct child { pid_t pid; int report, release; struct xhqs_owner owner; };
static struct child launch(int kind)
{
  int fd[2], report[2], release[2];
  CHECK(xhqs_pair(fd) == 0 && pipe(report) == 0 && pipe(release) == 0);
  pid_t parent = getpid();
  pid_t pid = fork(); CHECK(pid >= 0);
  if (!pid) {
    close(fd[0]); close(report[0]); close(release[1]);
    if (kind >= BAD_SEQ) raw_worker(fd[1], kind, report[1]);
    else {
      struct fixture f = { .kind = kind, .report = report[1], .release = release[0] };
      struct xhq q; struct xhqs_worker w;
      CHECK(xhq_init(&q, &ops, &f, 17, 1) == 0);
      CHECK(xhqs_worker_init(&w, fd[1], parent, getuid(), getgid(), &q) == 0);
      for (;;) {
        struct pollfd p[] = {{ .fd = w.peer.fd, .events = POLLIN }, { .fd = w.peer.pidfd, .events = POLLIN }};
        int n = poll(p, 2, 10000); CHECK(n == 1 || n == 2);
        if (p[1].revents || p[0].revents & (POLLHUP | POLLERR | POLLNVAL)) break;
        int r = xhqs_worker_once(&w);
        if (r && r != -EAGAIN) {
          if (kind == BAD_CMD) {
            CHECK(r == -EPROTO && q.phase == XHQ_IDLE && !f.closed);
            char c = 'x'; CHECK(write(report[1], &c, 1) == 1);
          }
          wait_disconnect(w.peer.fd); break;
        }
      }
      if (kind == DROP) CHECK(q.phase == XHQ_FAULT && f.polls == 1 && !f.reopened);
      xhqs_worker_close(&w);
    }
    _exit(0);
  }
  close(fd[1]); close(report[1]); close(release[0]);
  struct child c = { .pid = pid, .report = report[0], .release = release[1] };
  CHECK(xhqs_owner_init(&c.owner, fd[0], pid, getuid(), getgid(), 17, 1) == 0);
  return c;
}
static unsigned fd_count(void)
{
  DIR *d = opendir("/proc/self/fd"); CHECK(d);
  unsigned n = 0;
  while (readdir(d)) n++;
  CHECK(closedir(d) == 0);
  return n;
}
static uint64_t deadline(unsigned ms)
{
  uint64_t n = 0; CHECK(xhqs_now(&n) == 0); return n + (uint64_t)ms * 1000000;
}
static void finish(struct child *c)
{
  xhqs_owner_close(&c->owner); close(c->report); close(c->release);
  int status; CHECK(waitpid(c->pid, &status, 0) == c->pid && WIFEXITED(status) && !WEXITSTATUS(status));
}
static int drive(struct xhqs_owner *o)
{
  int r = -EAGAIN;
  for (unsigned i = 0; i < 16 && r == -EAGAIN; i++) r = xhqs_owner_step(o);
  return r;
}
static void park(struct xhqs_owner *o)
{
  CHECK(drive(o) == 0 && o->phase == XHQ_PARKED && o->verified == 7);
}
int main(void)
{
  alarm(60); /* Test-only upper bound; no production signal/reboot action. */
  struct child c = launch(NORMAL);
  CHECK(xhqs_owner_check(&c.owner) == 0 && xhqs_owner_resume(&c.owner) == -EBUSY);
  for (unsigned i = 1; i <= 2; i++) {
    CHECK(xhqs_owner_begin(&c.owner, deadline(5000)) == 0 && c.owner.cycle == i);
    CHECK(xhqs_owner_begin(&c.owner, deadline(5000)) == -EBUSY);
    park(&c.owner); CHECK(xhqs_owner_check(&c.owner) == 0);
    CHECK(xhqs_owner_step(&c.owner) == 0 && c.owner.phase == XHQ_PARKED);
    CHECK(xhqs_owner_resume(&c.owner) == 0 && drive(&c.owner) == 0 && c.owner.phase == XHQ_DONE);
    CHECK(c.owner.reopened == 7 && c.owner.attempted == 7);
  }
  finish(&c);
  c = launch(STALL);
  CHECK(xhqs_owner_begin(&c.owner, deadline(1000)) == 0);
  CHECK(xhqs_owner_step(&c.owner) == -EAGAIN && c.owner.phase == XHQ_DRAINING);
  CHECK(xhqs_owner_step(&c.owner) == -ETIMEDOUT && c.owner.phase == XHQ_FAULT);
  struct pollfd p = { .fd = c.report, .events = POLLIN };
  char byte; CHECK(poll(&p, 1, 1000) == 1 && read(c.report, &byte, 1) == 1);
  int status; CHECK(waitpid(c.pid, &status, WNOHANG) == 0); /* worker remains blocked */
  CHECK(xhqs_owner_resume(&c.owner) == -ETIMEDOUT && xhqs_owner_begin(&c.owner, deadline(5000)) == -ETIMEDOUT);
  CHECK(write(c.release, &byte, 1) == 1); finish(&c);
  c = launch(DEATH);
  CHECK(xhqs_owner_begin(&c.owner, deadline(5000)) == 0);
  int r = drive(&c.owner); CHECK((r == -ESRCH || r == -ENOTCONN) && c.owner.phase == XHQ_FAULT); finish(&c);
  c = launch(PARTIAL); CHECK(xhqs_owner_begin(&c.owner, deadline(5000)) == 0); park(&c.owner);
  CHECK(xhqs_owner_resume(&c.owner) == 0 && drive(&c.owner) == -EIO && c.owner.phase == XHQ_FAULT);
  CHECK(c.owner.reopened == 4 && c.owner.attempted == 6 && xhqs_owner_check(&c.owner) == -EIO); finish(&c);
  c = launch(DENY); CHECK(xhqs_owner_begin(&c.owner, deadline(5000)) == 0); park(&c.owner);
  CHECK(xhqs_owner_resume(&c.owner) == -EPERM && !c.owner.attempted); finish(&c);
  c = launch(DROP);
  CHECK(xhqs_owner_begin(&c.owner, deadline(10000)) == 0);
  CHECK(xhqs_owner_step(&c.owner) == -EAGAIN && c.owner.phase == XHQ_DRAINING);
  struct wire cmd = { .owner = c.owner.owner, .cycle = c.owner.cycle, .seq = c.owner.seq+1,
                      .deadline = c.owner.deadline, .magic = UINT32_C(0x31535158), .op = 2 };
  CHECK(send(c.owner.peer.fd, &cmd, sizeof cmd, MSG_NOSIGNAL) == sizeof cmd);
  p = (struct pollfd){ .fd = c.report, .events = POLLIN };
  CHECK(poll(&p, 1, 5000) == 1 && read(c.report, &byte, 1) == 1);
  CHECK(shutdown(c.owner.peer.fd, SHUT_RDWR) == 0);
  CHECK(write(c.release, &byte, 1) == 1); finish(&c);
  c = launch(BAD_CMD);
  cmd = (struct wire){ .owner = 17, .cycle = 1, .seq = 2, .deadline = deadline(5000),
                       .magic = UINT32_C(0x31535158), .op = 1 };
  CHECK(send(c.owner.peer.fd, &cmd, sizeof cmd, MSG_NOSIGNAL) == sizeof cmd);
  p = (struct pollfd){ .fd = c.report, .events = POLLIN };
  CHECK(poll(&p, 1, 5000) == 1 && read(c.report, &byte, 1) == 1); finish(&c);
  for (int kind = BAD_SEQ; kind <= SHORT; kind++) {
    c = launch(kind);
    unsigned count = fd_count();
    CHECK(xhqs_owner_begin(&c.owner, deadline(5000)) == -EPROTO);
    CHECK(fd_count() == count);
    CHECK(c.owner.phase == XHQ_FAULT && xhqs_owner_check(&c.owner) == -EPROTO); finish(&c);
  }
  c = launch(UNSOLICITED);
  p = (struct pollfd){ .fd = c.report, .events = POLLIN };
  CHECK(poll(&p, 1, 1000) == 1 && read(c.report, &byte, 1) == 1);
  CHECK(xhqs_owner_check(&c.owner) == -EPROTO); finish(&c);
  c = launch(NORMAL); CHECK(xhqs_owner_begin(&c.owner, deadline(1500)) == 0); park(&c.owner);
  p = (struct pollfd){ .fd = c.owner.timerfd, .events = POLLIN };
  CHECK(poll(&p, 1, 5000) == 1 && xhqs_owner_check(&c.owner) == -ETIMEDOUT);
  CHECK(xhqs_owner_resume(&c.owner) == -ETIMEDOUT); finish(&c);
  printf("quiescence independent IPC: %u parent checks, 0 failed\n", checks);
  return 0;
}
