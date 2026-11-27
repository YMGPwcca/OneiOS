// SPDX-License-Identifier: MIT
// The real display.c against a stand-in helper on the real socket: where the guest's mode comes from.
#define _GNU_SOURCE
#include "xnuhost.h"
#include "../../display/src/xhd.h"
#include <errno.h>
#include <pthread.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

// display.c ends input.c's touch-to-frame measurement at each shown frame; input.c is not linked here.
static unsigned guest_flushes;
void xh_input_frame_shown(void) { __atomic_add_fetch(&guest_flushes, 1u, __ATOMIC_RELAXED); }

struct message { char magic[4]; uint32_t a, b, c, d; };
static struct { char path[300]; uint32_t w, h, stride, format; off_t memfd_size; int ok, fd; } helper;

static uint32_t report_w = 1440, report_h = 3120, report_hz = 120;

static void *helper_main(void *arg)
{
  (void)arg;
  struct sockaddr_un addr = { .sun_family = AF_UNIX };
  strcpy(addr.sun_path, helper.path);
  int fd = socket(AF_UNIX, SOCK_SEQPACKET, 0);
  for (int i = 0; i < 300 && connect(fd, (struct sockaddr *)&addr, sizeof addr); i++) usleep(10000);
  struct message panel = { { 'X', 'H', 'D', 'P' }, report_w, report_h, report_hz, 0 }, hello;
  send(fd, &panel, sizeof panel, MSG_NOSIGNAL);
  char control[CMSG_SPACE(sizeof(int))];
  struct iovec iov = { &hello, sizeof hello };
  struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1, .msg_control = control, .msg_controllen = sizeof control };
  if (recvmsg(fd, &msg, 0) == (ssize_t)sizeof hello && !memcmp(hello.magic, "XHD1", 4)) {
    int memfd;
    memcpy(&memfd, CMSG_DATA(CMSG_FIRSTHDR(&msg)), sizeof memfd);
    struct stat st;
    fstat(memfd, &st);
    helper.w = hello.a; helper.h = hello.b; helper.stride = hello.c; helper.format = hello.d; helper.memfd_size = st.st_size;
    helper.ok = 1;
    helper.fd = fd;
    close(memfd);
  }
  return NULL;
}

static int barrier_case, control_fd = -1;

static void helper_process(int ctl)
{
  alarm(25);
  helper_main(NULL);
  if (!helper.ok || send(ctl, &helper, sizeof helper, MSG_NOSIGNAL) != sizeof helper) _exit(1);
  struct xhd_frame frame = { .width = helper.w, .height = helper.h };
  struct xhd_rect damage = {0,0,helper.w,helper.h};
  struct xhd_trace_state trace = {0};
  char command;
  while (recv(ctl, &command, 1, 0) == 1) {
    int rc = 0;
    if (command == 'X') _exit(0);
    if (command == 'P') {
      unsigned accepted = 0;
      rc = xhd_drain_after_lock(helper.fd, &frame, damage, &damage, &trace, &accepted);
      if (!rc && (trace.barrier != XHD_PARK_ACK || !trace.barrier_ticket)) rc = -EPROTO;
    } else if (command == 'A') {
      if (xhd_quiesce_boundary(helper.fd, &frame, &damage, &trace) != 1 ||
          trace.barrier != XHD_PARKED || damage.w) rc = -EPROTO;
    } else if (command == 'R') {
      rc = xhd_drain_trace(helper.fd, &frame, &damage, &trace);
      if (!rc && (trace.barrier != XHD_RESUME_ACK || damage.w)) rc = -EPROTO;
    } else if (command == 'B') {
      if (xhd_quiesce_boundary(helper.fd, &frame, &damage, &trace) ||
          trace.barrier != XHD_OPEN || damage.w != frame.width || damage.h != frame.height) rc = -EPROTO;
    } else if (command == 'W' || command == 'I') {
      struct xh_display_barrier a = xh_display_barrier_make('A', trace.barrier_ticket + (command == 'W'));
      if (command == 'W') {
        if (send(helper.fd, &a, sizeof a, MSG_NOSIGNAL) != sizeof a) rc = -EIO;
      } else {
        // A different process with the same inherited socket, UID and GID,
        // and the correct ticket must NOT be accepted as the bound helper.
        pid_t impostor = fork();
        if (!impostor) _exit(send(helper.fd, &a, sizeof a, MSG_NOSIGNAL) == sizeof a ? 0 : 1);
        int status;
        if (impostor < 0 || waitpid(impostor, &status, 0) != impostor ||
            !WIFEXITED(status) || WEXITSTATUS(status)) rc = -EIO;
      }
    } else rc = -EINVAL;
    if (send(ctl, &rc, sizeof rc, MSG_NOSIGNAL) != sizeof rc) _exit(2);
  }
  _exit(0);
}
static int helper_rpc(char command)
{
  int rc = -EIO;
  if (send(control_fd, &command, 1, MSG_NOSIGNAL) != 1 ||
      recv(control_fd, &rc, sizeof rc, MSG_TRUNC) != sizeof rc) return -EIO;
  return rc;
}
static int bind_retry(int fd)
{
  int r = -EAGAIN;
  for (unsigned i = 0; i < 2000; i++) {
    r = xh_display_quiesce_bind_helper(fd, getuid(), getgid());
    if (r != -EAGAIN && r != -ENOTCONN) break;
    usleep(1000);
  }
  return r;
}
static int retry_display(int (*op)(uint64_t), uint64_t ticket, int expected)
{
  for (unsigned i = 0; i < 2000; i++) {
    int r = op(ticket);
    if (r != -EAGAIN || expected == -EAGAIN) return r;
    usleep(1000);
  }
  return -ETIMEDOUT;
}
// Real host transport + real helper parser on the existing socket.
// Only ANativeWindow's boundary is simulated; no physical present claim.
static int barrier_test(void)
{
#define B(cond, code) do { if (!(cond)) return code; } while (0)
  uint64_t t = 0, t2 = 0;
  int rc = -EAGAIN;
  for (unsigned i = 0; i < 2000 && rc == -EAGAIN; i++) {
    rc = xh_display_quiesce_close(&t);
    if (rc == -EAGAIN) usleep(1000);
  }
  B(!rc && t, 10);
  B(xh_display_quiesce_close(&t2) == -EBUSY && !t2, 11);
  B(xh_display_quiesce_resume(t) == -EBUSY, 12);
  B(xh_display_quiesce_poll(t+1) == -ESTALE, 13);
  B(xh_display_quiesce_poll(t) == -EAGAIN, 14);
  B(!helper_rpc('P'), 18);
  if (barrier_case == 2 || barrier_case == 3) {
    B(!helper_rpc(barrier_case == 2 ? 'W' : 'I'), 15);
    B(retry_display(xh_display_quiesce_poll, t, -EPROTO) == -EPROTO, 16);
    B(xh_display_quiesce_resume(t) == -EPROTO, 17);
    return 0;
  }
  B(xh_display_quiesce_poll(t) == -EAGAIN, 20); // no premature ACK
  B(!helper_rpc('A'), 21);
  B(!retry_display(xh_display_quiesce_poll, t, 0), 23);
  B(!xh_display_quiesce_poll(t), 24);
  B(xh_display_quiesce_resume(t+1) == -ESTALE, 25);
  B(xh_display_quiesce_resume(t) == -EAGAIN, 26);
  B(!helper_rpc('R'), 27);
  B(!helper_rpc('B'), 29);
  B(!retry_display(xh_display_quiesce_resume, t, 0), 31);
  B(xh_display_quiesce_poll(t) == -ESTALE, 32);
  B(!xh_display_quiesce_close(&t2) && t2 > t, 33);
  // A producer that was not stopped invalidates the next receipt.
  xh_display_flush(0,0,1,1);
  B(xh_display_quiesce_poll(t2) == -EIO, 34);
  B(xh_display_quiesce_resume(t2) == -EIO, 35);
  return 0;
#undef B
}

// In a child: display.c's state is once per process. 0 when the frame, the hello and the time are as expected.
static int run(const char *dir, const char *mode, unsigned cw, unsigned ch, unsigned chz, unsigned w, unsigned h, unsigned hz, double most_seconds)
{
  pid_t child = fork();
  if (child) { int status = 1; waitpid(child, &status, 0); return WIFEXITED(status) ? WEXITSTATUS(status) : 99; }
  alarm(25);
  xh_config c;
  xh_config_defaults(&c);
  strcpy(c.mode, mode);
  strcpy(c.session, dir);
  c.scale = 3; c.width = cw; c.height = ch; c.hz = chz;
  snprintf(helper.path, sizeof helper.path, "%s/display.sock", dir);
  pthread_t thread;
  pid_t pid = -1;
  int expected = -1;
  if (barrier_case) {
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair)) _exit(36);
    pid = fork();
    if (pid < 0) _exit(37);
    if (!pid) { close(pair[0]); helper_process(pair[1]); _exit(38); }
    close(pair[1]);
    control_fd = pair[0];
    expected = (int)syscall(SYS_pidfd_open, pid, 0);
    if (expected < 0) _exit(39);
  } else if (pthread_create(&thread, NULL, helper_main, NULL)) _exit(40);
  struct timespec t0, t1;
  clock_gettime(CLOCK_MONOTONIC, &t0);
  unsigned gw = 0, gh = 0, ghz = 0;
  if (xh_display_init(&c, &gw, &gh, &ghz)) _exit(2);
  clock_gettime(CLOCK_MONOTONIC, &t1);
  if (gw != w || gh != h || ghz != hz) { fprintf(stderr, "guest %ux%u at %u\n", gw, gh, ghz); _exit(3); }
  if ((t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9 > most_seconds) _exit(4);
  if (barrier_case) {
    if (recv(control_fd, &helper, sizeof helper, MSG_TRUNC) != sizeof helper) _exit(41);
    helper.fd = -1;
  } else pthread_join(thread, NULL);
  if (!helper.ok || helper.w != w || helper.h != h || helper.stride != w * 4 || helper.format != 1) _exit(5);
  if (helper.memfd_size != (off_t)((size_t)w * 4 * h)) _exit(6);       // what the guest's scanout has to fit: 17.97 MB at 1440x3120
  xh_display *d = xh_display_get();
  if (!d || d->width != w || d->height != h || d->stride != w * 4) _exit(7);
  if (__atomic_load_n(&guest_flushes, __ATOMIC_RELAXED) != 0) _exit(8);
  xh_display_flush(0, 0, 1, 1);
  if (__atomic_load_n(&guest_flushes, __ATOMIC_RELAXED) != 1) _exit(9);
  if (barrier_case) {
    uint64_t t = 0;
    if (xh_display_quiesce_close(&t) != -EPERM || t ||
        xh_display_quiesce_verify_helper() != -EPERM) _exit(42);
    int self = (int)syscall(SYS_pidfd_open, getpid(), 0);
    if (self < 0 || bind_retry(self) != -ESTALE) _exit(43);
    close(self);
    if (bind_retry(expected) || xh_display_quiesce_bind_helper(expected, getuid(), getgid()) != -EBUSY) _exit(44);
    close(expected);
    if (xh_display_quiesce_verify_helper()) _exit(45);
    // Even while open, a pinned helper cannot be replaced or share the memfd
    // with another connection. This new peer must get no hello.
    struct sockaddr_un addr = { .sun_family = AF_UNIX };
    strcpy(addr.sun_path, helper.path);
    int replacement = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
    if (replacement < 0 || connect(replacement, (struct sockaddr *)&addr, sizeof addr)) _exit(46);
    struct pollfd p = { .fd = replacement, .events = POLLIN };
    if (poll(&p, 1, 2000) != 1) _exit(47);
    char byte;
    ssize_t n = recv(replacement, &byte, 1, MSG_DONTWAIT);
    if (n != 0 && !(n < 0 && errno == ECONNRESET)) _exit(48);
    close(replacement);
    int result = barrier_test();
    if (send(control_fd, "X", 1, MSG_NOSIGNAL) != 1) _exit(49);
    close(control_fd);
    int status;
    if (waitpid(pid, &status, 0) != pid || !WIFEXITED(status) || WEXITSTATUS(status)) _exit(50);
    _exit(result);
  }
  _exit(0);
}

int main(void)
{
  char dir[] = "/tmp/xnuhost-display-XXXXXX";
  if (!mkdtemp(dir)) return 2;
  xh_log_open(NULL, XH_LOG_ERROR);
  int failures = 0, r;
#define CASE(name, ...) do { r = run(dir, __VA_ARGS__); printf("%s: %s (%d)\n", name, r ? "FAILED" : "ok", r); failures += r != 0; } while (0)
  CASE("a session takes the helper's report", "takeover", 0, 0, 0, 1440, 3120, 120, 5.0);
  report_w = 1260; report_h = 2800; report_hz = 90;                      // not the default: only the report can give this
  CASE("another panel's report is the guest's mode", "takeover", 0, 0, 0, 1260, 2800, 90, 5.0);
  report_w = 1440; report_h = 3120; report_hz = 120;
  CASE("a configured mode wins, without waiting", "takeover", 1080, 2340, 60, 1080, 2340, 60, 1.0);
  CASE("a bench run assumes the S24 Ultra's, without waiting", "bench", 0, 0, 0, 1440, 3120, 120, 1.0);
  barrier_case = 1;
  CASE("real socket: park only at helper boundary, resume, late producer refusal", "takeover", 0, 0, 0, 1440, 3120, 120, 5.0);
  barrier_case = 2;
  CASE("real socket: wrong ACK ticket latches fault", "takeover", 0, 0, 0, 1440, 3120, 120, 5.0);
  barrier_case = 3;
  CASE("real socket: correct ACK from inherited socket but wrong process", "takeover", 0, 0, 0, 1440, 3120, 120, 5.0);
  char command[100];
  snprintf(command, sizeof command, "rm -rf %s", dir);
  if (system(command)) failures++;
  printf("display mode tests: %d failed\n", failures);
  return failures != 0;
}
