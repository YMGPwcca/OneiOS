#define _GNU_SOURCE
#include "quiesce_peer.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/uio.h>
#include <unistd.h>

/* Linux generic/arm64 UAPI (asm-generic/socket.h); older Android NDK
 * headers may predate this option. No numeric-PID fallback. */
#ifndef SO_PEERPIDFD
#define SO_PEERPIDFD 77
#endif

static int live(int fd)
{
  if (fd < 0) return -EINVAL;
  struct pollfd p = { .fd = fd, .events = POLLIN };
  int r = poll(&p, 1, 0);
  return r < 0 ? -errno : r ? -ESRCH : 0;
}
/* Both pidfds must remain live around the comparison, and procfs must
 * expose PIDs in our namespace. Live PIDs in one namespace are unique.
 * fdinfo is read only; no /proc/<numeric-pid> reopen or signal. */
static int fd_pid(int fd, pid_t *pid)
{
  char path[64], line[256], self[32];
  int r = live(fd);
  if (r) return r;
  ssize_t n = readlink("/proc/self", self, sizeof self-1);
  if (n <= 0 || n >= (ssize_t)sizeof self-1) return -ENOTSUP;
  self[n] = 0;
  char *end;
  long value = strtol(self, &end, 10);
  if (*end || value != getpid()) return -ENOTSUP;
  snprintf(path, sizeof path, "/proc/self/fdinfo/%d", fd);
  FILE *f = fopen(path, "re");
  if (!f) return -errno;
  r = -EPROTO;
  while (fgets(line, sizeof line, f)) {
    if (strncmp(line, "Pid:", 4)) continue;
    errno = 0;
    value = strtol(line+4, &end, 10);
    if (!errno && end != line+4 && (*end == '\n' || !*end) && value > 0 && value <= INT_MAX) {
      *pid = (pid_t)value;
      r = 0;
    }
    break;
  }
  fclose(f);
  return r ? r : live(fd);
}
int xhqp_check(const struct xhqp_peer *p, int fd)
{
  if (!p || fd < 0) return -ENOTCONN;
  int r = live(p->pidfd);
  if (r) return r;
  struct pollfd s = { .fd = fd, .events = POLLIN | POLLRDHUP };
  r = poll(&s, 1, 0);
  if (r < 0) return -errno;
  return s.revents & (POLLHUP | POLLRDHUP | POLLERR | POLLNVAL) ? -ENOTCONN : 0;
}
int xhqp_bind(struct xhqp_peer *out, int fd, int expected, uid_t uid, gid_t gid)
{
  if (!out || fd < 0 || expected < 0) return -EINVAL;
  int pass = 0, type = 0;
  socklen_t len = sizeof pass;
  if (getsockopt(fd, SOL_SOCKET, SO_PASSCRED, &pass, &len)) return -errno;
  len = sizeof type;
  if (getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &len)) return -errno;
  struct sockaddr_storage sa;
  len = sizeof sa;
  if (getpeername(fd, (struct sockaddr *)&sa, &len)) return -errno;
  if (!pass || type != SOCK_SEQPACKET || sa.ss_family != AF_UNIX) return -ENOTSUP;
  struct ucred u;
  len = sizeof u;
  if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &u, &len)) return -errno;
  if (len != sizeof u || u.pid <= 0 || u.pid == getpid() || u.uid != uid || u.gid != gid) return -EPERM;
  int peer = -1;
  len = sizeof peer;
  if (getsockopt(fd, SOL_SOCKET, SO_PEERPIDFD, &peer, &len)) return -errno;
  if (peer < 0) return -EPROTO;
  struct xhqp_peer tmp = { peer, u.pid, u.uid, u.gid };
  pid_t a = 0, b = 0;
  int r = len != sizeof peer ? -EPROTO : fd_pid(expected, &a);
  if (!r) r = fd_pid(peer, &b);
  if (!r && (a != b || a != u.pid)) r = -ESTALE;
  if (!r) r = live(expected);
  if (!r) r = xhqp_check(&tmp, fd);
  if (!r && fcntl(peer, F_SETFD, FD_CLOEXEC)) r = -errno;
  if (r) close(peer);
  else *out = tmp;
  return r;
}
int xhqp_recv(const struct xhqp_peer *p, int fd, void *buf, size_t size)
{
  if (!buf || !size || size > SSIZE_MAX) return -EINVAL;
  int r = xhqp_check(p, fd);
  if (r) return r;
  union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(struct ucred)) + CMSG_SPACE(4*sizeof(int))]; } ancillary;
  struct iovec iov = { buf, size };
  struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1,
                        .msg_control = ancillary.bytes, .msg_controllen = sizeof ancillary.bytes };
  ssize_t n = recvmsg(fd, &msg, MSG_DONTWAIT | MSG_TRUNC | MSG_CMSG_CLOEXEC);
  if (n < 0) return errno == EINTR ? -EAGAIN : -errno;
  bool valid = true, cred = false;
  for (struct cmsghdr *c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg,c)) {
    if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_CREDENTIALS && c->cmsg_len == CMSG_LEN(sizeof(struct ucred))) {
      struct ucred u;
      memcpy(&u, CMSG_DATA(c), sizeof u);
      if (cred || u.pid != p->pid || u.uid != p->uid || u.gid != p->gid) valid = false;
      cred = true;
    } else {
      if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS && c->cmsg_len >= CMSG_LEN(0)) {
        size_t count = (c->cmsg_len - CMSG_LEN(0))/sizeof(int);
        for (size_t i = 0; i < count; i++) { int received; memcpy(&received, CMSG_DATA(c)+i*sizeof received, sizeof received); close(received); }
      }
      valid = false;
    }
  }
  if (!n) return -ENOTCONN;
  if (n != (ssize_t)size || (msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) || !valid || !cred) return -EPROTO;
  return xhqp_check(p, fd);
}
void xhqp_release(struct xhqp_peer *p)
{
  if (p && p->pidfd >= 0) { close(p->pidfd); p->pidfd = -1; }
}
