#define _GNU_SOURCE
#include "quiesce_peer.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s (errno=%d)\n", __FILE__, __LINE__, #x, errno); exit(1); } } while (0)
static const char packet[20] = "XHDA-valid-ticket";
enum { GOOD, IMPOSTOR, RIGHTS, SHORT, LONG, DEAD, DISCONNECT };
static unsigned fd_count(void)
{
  DIR *d = opendir("/proc/self/fd"); CHECK(d);
  unsigned n = 0; while (readdir(d)) n++;
  CHECK(closedir(d) == 0); return n;
}
static void send_rights(int fd)
{
  union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(12*sizeof(int))]; } c = {0};
  struct iovec iov = { (void *)packet, sizeof packet };
  struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1, .msg_control = c.bytes, .msg_controllen = sizeof c.bytes };
  struct cmsghdr *h = CMSG_FIRSTHDR(&msg);
  h->cmsg_level = SOL_SOCKET; h->cmsg_type = SCM_RIGHTS; h->cmsg_len = CMSG_LEN(12*sizeof(int));
  int fds[12]; for (unsigned i = 0; i < 12; i++) fds[i] = fd;
  memcpy(CMSG_DATA(h), fds, sizeof fds);
  CHECK(sendmsg(fd, &msg, MSG_NOSIGNAL) == sizeof packet);
}
static int pidfd(pid_t p) { return (int)syscall(SYS_pidfd_open, p, 0); }
static void run(int kind)
{
  int listener = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0), go[2], ready[2];
  CHECK(listener >= 0 && pipe(go) == 0 && pipe(ready) == 0);
  struct sockaddr_un a = { .sun_family = AF_UNIX };
  snprintf(a.sun_path+1, sizeof a.sun_path-1, "oneios-peer-%d-%d", getpid(), kind);
  int one = 1;
  CHECK(setsockopt(listener, SOL_SOCKET, SO_PASSCRED, &one, sizeof one) == 0);
  CHECK(bind(listener, (struct sockaddr *)&a, sizeof a) == 0 && listen(listener, 1) == 0);
  pid_t child = fork(); CHECK(child >= 0);
  if (!child) {
    close(listener); close(go[1]); close(ready[0]);
    int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0); CHECK(fd >= 0);
    CHECK(connect(fd, (struct sockaddr *)&a, sizeof a) == 0);
    /* Queue a packet before the parent accepts; listener PASSCRED must cover it. */
    CHECK(send(fd, packet, sizeof packet, MSG_NOSIGNAL) == sizeof packet);
    char c; CHECK(write(ready[1], "r", 1) == 1 && read(go[0], &c, 1) == 1);
    if (kind == IMPOSTOR || kind == DEAD) {
      pid_t other = fork(); CHECK(other >= 0);
      if (!other) {
        if (kind == IMPOSTOR) CHECK(send(fd, packet, sizeof packet, MSG_NOSIGNAL) == sizeof packet);
        else { CHECK(write(ready[1], "h", 1) == 1); (void)read(go[0], &c, 1); }
        _exit(0);
      }
      if (kind == DEAD) _exit(0);
      int status; CHECK(waitpid(other, &status, 0) == other && WIFEXITED(status) && !WEXITSTATUS(status));
    } else if (kind == RIGHTS) send_rights(fd);
    else if (kind == SHORT) CHECK(send(fd, packet, 1, MSG_NOSIGNAL) == 1);
    else if (kind == LONG) { char big[21] = {0}; CHECK(send(fd, big, sizeof big, MSG_NOSIGNAL) == sizeof big); }
    else if (kind == DISCONNECT) CHECK(shutdown(fd, SHUT_RDWR) == 0);
    else CHECK(send(fd, packet, sizeof packet, MSG_NOSIGNAL) == sizeof packet);
    CHECK(write(ready[1], "d", 1) == 1);
    CHECK(read(go[0], &c, 1) == 1); _exit(0);
  }
  close(go[0]); close(ready[1]);
  int expected = pidfd(child), self = pidfd(getpid()); CHECK(expected >= 0 && self >= 0);
  char c; CHECK(read(ready[0], &c, 1) == 1);
  int fd = accept4(listener, NULL, NULL, SOCK_CLOEXEC); CHECK(fd >= 0);
  close(listener);
  struct xhqp_peer p = { .pidfd = -1 };
  unsigned count = fd_count();
  CHECK(xhqp_bind(&p, fd, self, getuid(), getgid()) == -ESTALE && p.pidfd == -1);
  CHECK(xhqp_bind(&p, fd, expected, getuid() ^ 1u, getgid()) == -EPERM);
  CHECK(xhqp_bind(&p, fd, expected, getuid(), getgid() ^ 1u) == -EPERM);
  CHECK(fd_count() == count);
  CHECK(xhqp_bind(&p, fd, expected, getuid(), getgid()) == 0);
  CHECK(p.pid == child && (fcntl(p.pidfd, F_GETFD) & FD_CLOEXEC));
  close(expected); close(self);
  char buf[20]; CHECK(xhqp_recv(&p, fd, buf, sizeof buf) == 0 && !memcmp(buf, packet, sizeof buf));
  CHECK(xhqp_recv(&p, fd, buf, sizeof buf) == -EAGAIN);
  CHECK(write(go[1], "x", 1) == 1 && read(ready[0], &c, 1) == 1);
  if (kind == DEAD) {
    int status; CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && !WEXITSTATUS(status));
    struct pollfd s = { .fd = fd, .events = POLLIN | POLLRDHUP };
    CHECK(poll(&s, 1, 0) == 0); /* another process still holds the socket */
    CHECK(xhqp_check(&p, fd) == -ESRCH && xhqp_recv(&p, fd, buf, sizeof buf) == -ESRCH);
  } else {
    count = fd_count();
    int r = xhqp_recv(&p, fd, buf, sizeof buf);
    CHECK(r == (kind == GOOD ? 0 : kind == DISCONNECT ? -ENOTCONN : -EPROTO));
    CHECK(fd_count() == count);
    if (kind == GOOD) CHECK(!memcmp(buf, packet, sizeof buf));
    CHECK(write(go[1], "x", 1) == 1);
    int status; CHECK(waitpid(child, &status, 0) == child && WIFEXITED(status) && !WEXITSTATUS(status));
  }
  xhqp_release(&p); CHECK(p.pidfd == -1); close(fd); close(go[1]); close(ready[0]);
}
int main(void)
{
  alarm(30);
  for (int i = GOOD; i <= DISCONNECT; i++) run(i);
  printf("display peer identity: %u parent checks, 0 failed\n", checks);
  return 0;
}
