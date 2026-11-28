#define _GNU_SOURCE
#include "quiesce_supervisor.h"
#include <errno.h>
#include <poll.h>
#include <stdbool.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/timerfd.h>
#include <sys/uio.h>
#include <time.h>
#include <unistd.h>

#define MAGIC UINT32_C(0x31535158) /* XQS1, local same-ABI channel */
#define ACK UINT32_C(0x80000000)
enum { BEGIN = 1, STEP, RESUME, RUNTIME_READY };
struct packet {
  uint64_t owner, cycle, seq, deadline;
  uint32_t magic, op, phase, closed, verified, attempted, reopened;
  int32_t result;
};
_Static_assert(sizeof(struct packet) == 64, "quiescence control ABI");

int xhqs_now(uint64_t *ns)
{
  struct timespec ts;
  if (!ns) return -EINVAL;
  if (clock_gettime(CLOCK_BOOTTIME, &ts)) return -errno;
  if (ts.tv_sec < 0 || (uint64_t)ts.tv_sec > (UINT64_MAX - (uint64_t)ts.tv_nsec) / 1000000000u)
    return -EOVERFLOW;
  *ns = (uint64_t)ts.tv_sec * 1000000000u + (uint64_t)ts.tv_nsec;
  return 0;
}
static int before(uint64_t deadline)
{
  uint64_t ns = 0;
  int r = xhqs_now(&ns);
  return r ? r : ns >= deadline ? -ETIMEDOUT : 0;
}
int xhqs_pair(int fd[2])
{
  if (!fd) return -EINVAL;
  if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_NONBLOCK | SOCK_CLOEXEC, 0, fd)) return -errno;
  int one = 1;
  if (setsockopt(fd[0], SOL_SOCKET, SO_PASSCRED, &one, sizeof one) ||
      setsockopt(fd[1], SOL_SOCKET, SO_PASSCRED, &one, sizeof one)) {
    int r = -errno;
    close(fd[0]); close(fd[1]); fd[0] = fd[1] = -1;
    return r;
  }
  return 0;
}
static int alive(const struct xhqs_peer *p)
{
  struct pollfd f = { .fd = p->pidfd, .events = POLLIN };
  int n;
  do n = poll(&f, 1, 0); while (n < 0 && errno == EINTR);
  return n < 0 ? -errno : n ? -ESRCH : 0;
}
static int peer_init(struct xhqs_peer *p, int fd, pid_t pid, uid_t uid, gid_t gid)
{
  if (fd < 0 || pid <= 0 || pid == getpid()) return -EINVAL;
  int type = 0, pass = 0;
  socklen_t len = sizeof type;
  if (getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &len)) return -errno;
  len = sizeof pass;
  if (getsockopt(fd, SOL_SOCKET, SO_PASSCRED, &pass, &len)) return -errno;
  struct sockaddr_storage sa;
  len = sizeof sa;
  if (getpeername(fd, (struct sockaddr *)&sa, &len)) return -errno;
  if (type != SOCK_SEQPACKET || !pass || sa.ss_family != AF_UNIX) return -EPROTOTYPE;
#if defined(SYS_pidfd_open)
  int pidfd = (int)syscall(SYS_pidfd_open, pid, 0);
  if (pidfd < 0) return -errno;
  *p = (struct xhqs_peer){ fd, pidfd, pid, uid, gid };
  int r = alive(p);
  if (r) close(pidfd);
  return r;
#else
  (void)p; (void)uid; (void)gid;
  return -ENOTSUP;
#endif
}
static void peer_close(struct xhqs_peer *p)
{
  close(p->pidfd); close(p->fd);
  p->pidfd = p->fd = -1;
}
static int send_packet(const struct xhqs_peer *p, const struct packet *m)
{
  ssize_t n = send(p->fd, m, sizeof *m, MSG_DONTWAIT | MSG_NOSIGNAL);
  return n == (ssize_t)sizeof *m ? 0 : n < 0 ? -errno : -EIO;
}
static int recv_packet(const struct xhqs_peer *p, struct packet *m)
{
  union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(struct ucred)) + CMSG_SPACE(4 * sizeof(int))]; } ancillary;
  struct iovec iov = { m, sizeof *m };
  struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1,
                        .msg_control = ancillary.bytes, .msg_controllen = sizeof ancillary.bytes };
  ssize_t n = recvmsg(p->fd, &msg, MSG_DONTWAIT | MSG_TRUNC | MSG_CMSG_CLOEXEC);
  if (n < 0) return -errno;
  bool valid = true, credential = false;
  for (struct cmsghdr *c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg, c)) {
    if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_CREDENTIALS && c->cmsg_len == CMSG_LEN(sizeof(struct ucred))) {
      struct ucred u;
      memcpy(&u, CMSG_DATA(c), sizeof u);
      if (credential || u.pid != p->pid || u.uid != p->uid || u.gid != p->gid) valid = false;
      credential = true;
    } else {
      /* Never retain a received descriptor, even on malformed packets. */
      if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS && c->cmsg_len >= CMSG_LEN(0)) {
        size_t nf = (c->cmsg_len - CMSG_LEN(0)) / sizeof(int);
        for (size_t i = 0; i < nf; i++) { int fd; memcpy(&fd, CMSG_DATA(c) + i * sizeof fd, sizeof fd); close(fd); }
      }
      valid = false;
    }
  }
  if (!n) return -ENOTCONN;
  if (n != (ssize_t)sizeof *m || msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC) || !valid || !credential) return -EPROTO;
  return 0;
}
static int owner_fault(struct xhqs_owner *o, int r)
{
  o->fault = r == -EAGAIN ? -ENOBUFS : r < 0 ? r : -EPROTO;
  o->phase = XHQ_FAULT;
  (void)shutdown(o->peer.fd, SHUT_RDWR);
  return o->fault;
}
int xhqs_owner_init(struct xhqs_owner *o, int fd, pid_t pid, uid_t uid, gid_t gid, uint64_t owner, unsigned nblocks)
{
  if (!o || !owner || !nblocks || nblocks > XHQ_MAX_BLOCKS) return -EINVAL;
  struct xhqs_owner tmp = { .owner = owner, .members = (1u << (nblocks+2u)) - 1u };
  int r = peer_init(&tmp.peer, fd, pid, uid, gid);
  if (r) return r;
  tmp.timerfd = timerfd_create(CLOCK_BOOTTIME, TFD_NONBLOCK | TFD_CLOEXEC);
  if (tmp.timerfd < 0) { r = -errno; close(tmp.peer.pidfd); return r; }
  *o = tmp;
  return 0;
}
/* A private channel cannot carry a second command while one is executing.
 * Recheck around the upstream guard at every coordinator boundary. An
 * owner fault/disconnect prevents the next provider call, not the completion
 * of one already in progress. The original guard still owns all other proofs. */
int xhqs_worker_check(struct xhqs_worker *w, uint64_t deadline)
{
  if (!w || !w->q || w->fault) return w && w->fault ? w->fault : -EINVAL;
  int r = before(deadline);
  if (r) return r;
  if ((r = alive(&w->peer))) return r;
  struct pollfd p = { .fd = w->peer.fd, .events = POLLIN };
  int n = poll(&p, 1, 0);
  if (n < 0) return -errno;
  if (p.revents & (POLLHUP | POLLERR | POLLNVAL)) return -ENOTCONN;
  return n ? -EPROTO : 0;
}
static int bound_now(void *ctx, uint64_t *ns)
{
  struct xhqs_worker *w = ctx;
  return w->upstream.now(w->upstream_ctx, ns);
}
static int bound_guard(void *ctx, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  struct xhqs_worker *w = ctx;
  int r = xhqs_worker_check(w, w->q->deadline);
  if (!r) r = w->upstream.guard(w->upstream_ctx, owner, cycle, phase);
  return r ? r : xhqs_worker_check(w, w->q->deadline);
}
static int bound_close(void *ctx, unsigned m, uint64_t *t)
{
  struct xhqs_worker *w = ctx;
  return w->upstream.close(w->upstream_ctx, m, t);
}
static int bound_poll(void *ctx, unsigned m, uint64_t t)
{
  struct xhqs_worker *w = ctx;
  return w->upstream.poll(w->upstream_ctx, m, t);
}
static int bound_resume(void *ctx, unsigned m, uint64_t t)
{
  struct xhqs_worker *w = ctx;
  return w->upstream.resume(w->upstream_ctx, m, t);
}
int xhqs_worker_init(struct xhqs_worker *w, int fd, pid_t pid, uid_t uid, gid_t gid, struct xhq *q)
{
  if (!w || !q || !q->owner || q->phase != XHQ_IDLE || q->cycle ||
      !q->ops.now || !q->ops.guard || !q->ops.close || !q->ops.poll || !q->ops.resume ||
      q->ops.guard == bound_guard) return -EINVAL;
  struct xhqs_worker tmp = { .q = q, .upstream = q->ops, .upstream_ctx = q->ctx };
  int r = peer_init(&tmp.peer, fd, pid, uid, gid);
  if (!r) {
    *w = tmp;
    q->ctx = w;
    q->ops = (struct xhq_ops){ bound_now, bound_guard, bound_close, bound_poll, bound_resume };
  }
  return r;
}
void xhqs_owner_close(struct xhqs_owner *o) { close(o->timerfd); o->timerfd = -1; peer_close(&o->peer); }
void xhqs_worker_close(struct xhqs_worker *w) { peer_close(&w->peer); }
static int arm(struct xhqs_owner *o, uint64_t ns)
{
  struct itimerspec t = {0};
  t.it_value.tv_sec = (time_t)(ns / 1000000000u);
  t.it_value.tv_nsec = (long)(ns % 1000000000u);
  if (t.it_value.tv_sec < 0 || (uint64_t)t.it_value.tv_sec != ns / 1000000000u) return -EOVERFLOW;
  return timerfd_settime(o->timerfd, TFD_TIMER_ABSTIME, &t, NULL) ? -errno : 0;
}
static int wait_ack(struct xhqs_owner *o, struct packet *a, uint64_t limit)
{
  struct pollfd f[] = {{ .fd = o->timerfd, .events = POLLIN },
                       { .fd = o->peer.pidfd, .events = POLLIN },
                       { .fd = o->peer.fd, .events = POLLIN }};
  for (;;) {
    int r = before(limit);
    if (r) return r;
    int n = poll(f, 3, -1);
    if (n < 0) { if (errno == EINTR) continue; return -errno; }
    if ((r = before(limit))) return r;
    if (f[0].revents) return -ETIMEDOUT;
    if (f[1].revents) return -ESRCH;
    if (f[2].revents & (POLLHUP | POLLERR | POLLNVAL)) return -ENOTCONN;
    if (!(f[2].revents & POLLIN)) continue;
    r = recv_packet(&o->peer, a);
    if (r == -EAGAIN || r == -EINTR) continue;
    if (r) return r;
    if ((r = before(limit))) return r;
    return alive(&o->peer);
  }
}
static bool step_phase(enum xhq_phase old, uint32_t phase)
{
  switch (old) {
  case XHQ_CLOSING: return phase == XHQ_CLOSING || phase == XHQ_DRAINING;
  case XHQ_DRAINING: return phase == XHQ_DRAINING || phase == XHQ_DISPLAY_CLOSE;
  case XHQ_DISPLAY_CLOSE: return phase == XHQ_DISPLAY_CLOSE || phase == XHQ_VERIFY;
  case XHQ_VERIFY: case XHQ_PARKED: return phase == XHQ_VERIFY || phase == XHQ_PARKED;
  case XHQ_RESUME_CHECK: return phase == XHQ_RESUME_CHECK || phase == XHQ_RESUMING;
  case XHQ_RESUMING: return phase == XHQ_RESUMING || phase == XHQ_DONE;
  default: return false;
  }
}
int xhqs_owner_check(struct xhqs_owner *o)
{
  if (!o) return -EINVAL;
  if (o->fault) return o->fault;
  if (o->phase != XHQ_IDLE && o->phase != XHQ_DONE) {
    int r = before(o->deadline);
    if (r) return owner_fault(o, r);
  }
  int r = alive(&o->peer);
  if (r) return owner_fault(o, r);
  struct packet a;
  /* No outstanding command: any unsolicited/stale packet is a fault. */
  r = recv_packet(&o->peer, &a);
  return r == -EAGAIN ? 0 : owner_fault(o, r ? r : -EPROTO);
}
int xhqs_owner_ready_until(struct xhqs_owner *o, uint64_t limit)
{
  if (!o || o->phase != XHQ_IDLE || o->cycle || o->runtime_ready) return -EINVAL;
  int r = xhqs_owner_check(o);
  if (r) return r;
  if ((r = before(limit)) || (r = arm(o, limit))) return owner_fault(o, r);
  if (o->seq == UINT64_MAX) return owner_fault(o, -EOVERFLOW);
  struct packet m = { .owner=o->owner, .seq=++o->seq, .deadline=limit,
    .magic=MAGIC, .op=RUNTIME_READY }, a;
  if ((r=send_packet(&o->peer,&m)) || (r=wait_ack(o,&a,limit)))
    return owner_fault(o,r);
  if (a.magic!=MAGIC || a.op!=(RUNTIME_READY|ACK) ||
      a.owner!=m.owner || a.seq!=m.seq || a.deadline!=limit ||
      a.cycle || a.phase!=XHQ_IDLE || a.closed || a.verified ||
      a.attempted || a.reopened || a.result>0)
    return owner_fault(o,-EPROTO);
  if (a.result && a.result!=-EAGAIN) return owner_fault(o,a.result);
  struct itimerspec off={0};
  if (timerfd_settime(o->timerfd,0,&off,NULL)) return owner_fault(o,-errno);
  if ((r=before(limit)) || (r=alive(&o->peer))) return owner_fault(o,r);
  if (!a.result) o->runtime_ready=true;
  return a.result;
}
static int exchange(struct xhqs_owner *o, unsigned op, uint64_t limit)
{
  int r = xhqs_owner_check(o);
  if (r) return r;
  if (limit > o->deadline) limit = o->deadline;
  if ((r = before(limit)) || (r = arm(o, limit))) return owner_fault(o, r);
  struct packet a;
  if (o->seq == UINT64_MAX) return owner_fault(o, -EOVERFLOW);
  struct packet m = { .owner = o->owner, .cycle = o->cycle, .seq = ++o->seq,
                      .deadline = o->deadline, .magic = MAGIC, .op = op };
  if ((r = send_packet(&o->peer, &m)) || (r = wait_ack(o, &a, limit))) return owner_fault(o, r);
  if (a.magic != MAGIC || a.op != (op | ACK) || a.owner != m.owner || a.cycle != m.cycle ||
      a.seq != m.seq || a.deadline != m.deadline || a.result > 0 || a.phase > XHQ_FAULT ||
      (a.closed & ~o->members) || (a.verified & ~a.closed) || (a.attempted & ~a.closed) ||
      (a.reopened & ~a.attempted) || (o->closed & ~a.closed) ||
      (o->attempted & ~a.attempted) || (o->reopened & ~a.reopened)) return owner_fault(o, -EPROTO);
  /* Preserve observed side effects even on a valid negative receipt. */
  o->closed = a.closed; o->verified = a.verified; o->attempted = a.attempted; o->reopened = a.reopened;
  if (a.result && a.result != -EAGAIN) return owner_fault(o, a.result);
  if (a.phase == XHQ_FAULT || (a.phase == XHQ_PARKED && (a.verified != o->members || a.reopened)) ||
      (a.phase == XHQ_DONE && a.reopened != o->members) ||
      (op == BEGIN && (a.result || a.phase != XHQ_CLOSING || a.closed)) ||
      (op == RESUME && (a.result || a.phase != XHQ_RESUME_CHECK)) ||
      (op == STEP && (!step_phase(o->phase, a.phase) ||
        ((!a.result) != (a.phase == XHQ_PARKED || a.phase == XHQ_DONE))))) return owner_fault(o, -EPROTO);
  if ((r = before(limit)) || (r = alive(&o->peer))) return owner_fault(o, r);
  o->phase = (enum xhq_phase)a.phase;
  if (o->phase == XHQ_DONE) {
    struct itimerspec off = {0};
    if (timerfd_settime(o->timerfd, 0, &off, NULL)) return owner_fault(o, -errno);
  } else if ((r = before(o->deadline)) || (r = arm(o, o->deadline))) {
    return owner_fault(o, r);
  }
  return a.result;
}
int xhqs_owner_begin_until(struct xhqs_owner *o, uint64_t deadline, uint64_t limit)
{
  if (!o) return -EINVAL;
  if (o->fault) return o->fault;
  if (o->phase != XHQ_IDLE && o->phase != XHQ_DONE) return -EBUSY;
  if (o->cycle == UINT64_MAX) return owner_fault(o, -EOVERFLOW);
  int r = before(deadline);
  if (r) return owner_fault(o, r);
  if ((r = before(limit))) return owner_fault(o, r);
  o->cycle++; o->deadline = deadline;
  o->closed = o->verified = o->attempted = o->reopened = 0;
  return exchange(o, BEGIN, limit);
}
int xhqs_owner_begin(struct xhqs_owner *o, uint64_t deadline)
{ return xhqs_owner_begin_until(o, deadline, deadline); }
int xhqs_owner_step_until(struct xhqs_owner *o, uint64_t limit)
{
  if (!o) return -EINVAL;
  if (o->fault) return o->fault;
  if (o->phase == XHQ_IDLE || o->phase == XHQ_DONE) return -EBUSY;
  return exchange(o, STEP, limit);
}
int xhqs_owner_step(struct xhqs_owner *o)
{ return o ? xhqs_owner_step_until(o, o->deadline) : -EINVAL; }
int xhqs_owner_resume_until(struct xhqs_owner *o, uint64_t limit)
{
  if (!o) return -EINVAL;
  if (o->fault) return o->fault;
  if (o->phase != XHQ_PARKED) return -EBUSY;
  return exchange(o, RESUME, limit);
}
int xhqs_owner_resume(struct xhqs_owner *o)
{ return o ? xhqs_owner_resume_until(o, o->deadline) : -EINVAL; }
static int worker_fault(struct xhqs_worker *w, int r)
{
  w->fault = r == -EAGAIN ? -ENOBUFS : r < 0 ? r : -EPROTO;
  return w->fault;
}
int xhqs_worker_once(struct xhqs_worker *w)
{
  if (!w) return -EINVAL;
  if (w->fault) return w->fault;
  int r = alive(&w->peer);
  if (r) return worker_fault(w, r);
  struct packet m;
  r = recv_packet(&w->peer, &m);
  if (r == -EAGAIN || r == -EINTR) return -EAGAIN;
  if (r) return worker_fault(w, r);
  struct xhq *q = w->q;
  if (m.magic != MAGIC || m.owner != q->owner || w->seq == UINT64_MAX || m.seq != w->seq+1 ||
      m.phase || m.closed || m.verified || m.attempted || m.reopened || m.result ||
      (m.op != BEGIN && m.op != STEP && m.op != RESUME && m.op != RUNTIME_READY))
    return worker_fault(w,-EPROTO);
  if (m.op==RUNTIME_READY) {
    if (m.cycle || q->cycle || q->phase!=XHQ_IDLE || w->runtime_ready ||
        !w->ready_check) return worker_fault(w,-EPROTO);
    if ((r=xhqs_worker_check(w,m.deadline))) return worker_fault(w,r);
    w->seq=m.seq;
    r=w->ready_check(w->ready_ctx);
    if (r>0) r=-EPROTO;
    int check=xhqs_worker_check(w,m.deadline);
    if (check) return worker_fault(w,check);
    struct packet a={.owner=m.owner,.seq=m.seq,.deadline=m.deadline,
      .magic=MAGIC,.op=RUNTIME_READY|ACK,.result=r};
    if ((check=send_packet(&w->peer,&a))) return worker_fault(w,check);
    if (!r) w->runtime_ready=true;
    else if (r!=-EAGAIN) worker_fault(w,r);
    return 0;
  }
  if (!m.cycle || (w->ready_check && !w->runtime_ready))
    return worker_fault(w,-EPROTO);
  if ((m.op == BEGIN && (q->cycle == UINT64_MAX || m.cycle != q->cycle+1 ||
      (q->phase != XHQ_IDLE && q->phase != XHQ_DONE))) ||
      (m.op != BEGIN && (m.cycle != q->cycle || m.deadline != q->deadline))) return worker_fault(w, -ESTALE);
  if ((r = before(m.deadline)) || (r = alive(&w->peer))) return worker_fault(w, r);
  w->seq = m.seq;
  if (m.op == BEGIN) { uint64_t cycle = 0; r = xhq_begin(q, m.owner, m.deadline, &cycle); if (!r && cycle != m.cycle) r = -EPROTO; }
  else if (m.op == STEP) {
    enum xhq_phase prior = q->phase;
    r = xhq_step(q, m.owner, m.cycle);
    // The actual board worker releases the outer producers only after all
    // inner providers reopened. Never ACK DONE before that succeeds.
    if (!r && prior == XHQ_RESUMING && q->phase == XHQ_DONE && w->finish_resume) {
      r = xhqs_worker_check(w, m.deadline);
      if (!r) r = w->finish_resume(w->finish_ctx, m.owner, m.cycle);
      if (!r) r = xhqs_worker_check(w, m.deadline);
      if (r) {
        q->fault = r < 0 && r != -EAGAIN ? r : -EPROTO;
        q->phase = XHQ_FAULT;
        r = q->fault;
      }
    }
  }
  else r = xhq_request_resume(q, m.owner, m.cycle);
  struct packet a = { .owner = m.owner, .cycle = m.cycle, .seq = m.seq, .deadline = m.deadline,
    .magic = MAGIC, .op = m.op | ACK, .phase = q->phase, .closed = q->closed,
    .verified = q->verified, .attempted = q->resume_attempted, .reopened = q->reopened, .result = r };
  int c = before(m.deadline);
  if (c || (c = alive(&w->peer)) || (c = send_packet(&w->peer, &a))) return worker_fault(w, c);
  if (r && r != -EAGAIN) worker_fault(w, r);
  return 0;
}
