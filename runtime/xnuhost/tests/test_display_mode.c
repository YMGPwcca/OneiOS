// SPDX-License-Identifier: MIT
// The real display.c against a stand-in helper on the real socket: where the guest's mode comes from.
#define _GNU_SOURCE
#include "xnuhost.h"
#include "../../display/src/xhd.h"
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
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

static int barrier_case;
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
static int barrier_test(unsigned w, unsigned h)
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
  struct xhd_frame frame = { .width = w, .height = h };
  struct xhd_rect damage = {0,0,w,h};
  struct xhd_trace_state trace = {0};
  if (barrier_case == 2) {
    // A forged/stale ticket on the connected peer must not certify park.
    struct xh_display_barrier bad = xh_display_barrier_make('A', t+1);
    B(send(helper.fd, &bad, sizeof bad, MSG_NOSIGNAL) == (ssize_t)sizeof bad, 15);
    B(retry_display(xh_display_quiesce_poll, t, -EPROTO) == -EPROTO, 16);
    B(xh_display_quiesce_resume(t) == -EPROTO, 17);
    return 0;
  }
  unsigned accepted = 0;
  // Q is read while the helper hypothetically owns a full window lock.
  B(!xhd_drain_after_lock(helper.fd, &frame, damage, &damage, &trace, &accepted), 18);
  B(trace.barrier == XHD_PARK_ACK && trace.barrier_ticket == t, 19);
  B(xh_display_quiesce_poll(t) == -EAGAIN, 20); // no premature ACK
  // Only the boundary after copy/post may emit A.
  B(xhd_quiesce_boundary(helper.fd, &frame, &damage, &trace) == 1, 21);
  B(trace.barrier == XHD_PARKED && !damage.w, 22);
  B(!retry_display(xh_display_quiesce_poll, t, 0), 23);
  B(!xh_display_quiesce_poll(t), 24);
  B(xh_display_quiesce_resume(t+1) == -ESTALE, 25);
  B(xh_display_quiesce_resume(t) == -EAGAIN, 26);
  B(!xhd_drain_trace(helper.fd, &frame, &damage, &trace), 27);
  B(trace.barrier == XHD_RESUME_ACK && !damage.w, 28);
  B(!xhd_quiesce_boundary(helper.fd, &frame, &damage, &trace), 29);
  B(trace.barrier == XHD_OPEN && damage.w == w && damage.h == h, 30);
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
  xh_config c;
  xh_config_defaults(&c);
  strcpy(c.mode, mode);
  strcpy(c.session, dir);
  c.scale = 3; c.width = cw; c.height = ch; c.hz = chz;
  snprintf(helper.path, sizeof helper.path, "%s/display.sock", dir);
  pthread_t thread;
  pthread_create(&thread, NULL, helper_main, NULL);
  struct timespec t0, t1;
  clock_gettime(CLOCK_MONOTONIC, &t0);
  unsigned gw = 0, gh = 0, ghz = 0;
  if (xh_display_init(&c, &gw, &gh, &ghz)) _exit(2);
  clock_gettime(CLOCK_MONOTONIC, &t1);
  if (gw != w || gh != h || ghz != hz) { fprintf(stderr, "guest %ux%u at %u\n", gw, gh, ghz); _exit(3); }
  if ((t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9 > most_seconds) _exit(4);
  pthread_join(thread, NULL);
  if (!helper.ok || helper.w != w || helper.h != h || helper.stride != w * 4 || helper.format != 1) _exit(5);
  if (helper.memfd_size != (off_t)((size_t)w * 4 * h)) _exit(6);       // what the guest's scanout has to fit: 17.97 MB at 1440x3120
  xh_display *d = xh_display_get();
  if (!d || d->width != w || d->height != h || d->stride != w * 4) _exit(7);
  if (__atomic_load_n(&guest_flushes, __ATOMIC_RELAXED) != 0) _exit(8);
  xh_display_flush(0, 0, 1, 1);
  if (__atomic_load_n(&guest_flushes, __ATOMIC_RELAXED) != 1) _exit(9);
  if (barrier_case) _exit(barrier_test(w,h));
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
  char command[100];
  snprintf(command, sizeof command, "rm -rf %s", dir);
  if (system(command)) failures++;
  printf("display mode tests: %d failed\n", failures);
  return failures != 0;
}
