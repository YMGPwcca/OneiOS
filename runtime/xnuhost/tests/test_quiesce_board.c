#define _GNU_SOURCE
#include "quiesce_board.h"
#include "quiesce_vcpu.h"
#include "quiesce_input.h"
#include "bridges/devices.h"
#include "oneios_bridge_proto.h"
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
struct xh_virtio { unsigned member; };
static struct xh_virtio devices[32];
static unsigned maps, closes, polls, resumes, order[8];
static int helper_error, guest_error, bridge_error;
int br_bridge_quiesce_poll(xh_virtio *d, uint64_t t, unsigned *mask)
{ (void)mask; return d == &devices[9] && t == 31 ? bridge_error : -ESTALE; }
int xh_tasks_quiesce_check(uint64_t t) { return t == 23 ? guest_error : -ESTALE; }
int xh_display_quiesce_verify_helper(void) { return helper_error; }
static int map_ok(void *ctx) { CHECK(ctx == &maps); maps++; return 0; }
static int map_fail(void *ctx) { CHECK(ctx == &maps); return -EIO; }
#define BASE UINT64_C(0x10000)
#define STRIDE UINT64_C(0x1000)
#define SPI 32u
static int add(unsigned i, unsigned type)
{
  return xhqb_map(&devices[i], BASE + i * STRIDE, SPI + i, type, map_ok, &maps);
}
static int gate_close(unsigned m, uint64_t *ticket)
{
  CHECK(!(closes & (1u << m)));
  closes |= 1u << m; *ticket = m+1; return 0;
}
static int gate_poll(unsigned m, uint64_t ticket)
{
  CHECK(ticket == m+1 && (closes & (1u << m))); polls++; return 0;
}
static int gate_resume(unsigned m, uint64_t ticket)
{
  CHECK(ticket == m+1 && (closes & (1u << m)) && resumes < 8);
  order[resumes++] = m; closes &= ~(1u << m); return 0;
}
int xh_virtio_gpu_quiesce_close(struct xh_virtio *d, uint64_t *t) { CHECK(d->member == 0); return gate_close(d->member, t); }
int xh_virtio_gpu_quiesce_poll(struct xh_virtio *d, uint64_t t) { CHECK(d->member == 0); return gate_poll(d->member, t); }
int xh_virtio_gpu_quiesce_resume(struct xh_virtio *d, uint64_t t) { CHECK(d->member == 0); return gate_resume(d->member, t); }
int xh_virtio_blk_quiesce_close(struct xh_virtio *d, uint64_t *t) { CHECK(d->member >= 1 && d->member <= 6); return gate_close(d->member, t); }
int xh_virtio_blk_quiesce_poll(struct xh_virtio *d, uint64_t t) { CHECK(d->member >= 1 && d->member <= 6); return gate_poll(d->member, t); }
int xh_virtio_blk_quiesce_resume(struct xh_virtio *d, uint64_t t) { CHECK(d->member >= 1 && d->member <= 6); return gate_resume(d->member, t); }
int xh_display_quiesce_close(uint64_t *t) { CHECK(closes == 127); return gate_close(7, t); }
int xh_display_quiesce_poll(uint64_t t) { return gate_poll(7, t); }
int xh_display_quiesce_resume(uint64_t t) { return gate_resume(7, t); }
static int guard(void *ctx, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  CHECK(ctx == &maps && owner == 17 && cycle && phase != XHQ_FAULT);
  CHECK(!xhqb_console_enter()); return 0;
}
static int drive(struct xhq *q, uint64_t cycle)
{
  int r = -EAGAIN;
  for (unsigned i = 0; i < 20 && r == -EAGAIN; i++) r = xhq_step(q, 17, cycle);
  return r;
}
static void make_board(unsigned bridge_type)
{
  struct xhqb_snapshot s;
  CHECK(xhqb_snapshot(&s) == -EBUSY);
  CHECK(xhqb_begin(BASE, STRIDE, SPI, 6) == 0);
  CHECK(xhqb_begin(BASE, STRIDE, SPI, 6) == -EBUSY);
  CHECK(xhqb_map(&devices[0], BASE, SPI, 2, map_fail, &maps) == -EIO && !maps);
  for (unsigned i = 0; i < 6; i++) { devices[i].member = i+1; CHECK(add(i, 2) == 0); }
  devices[7].member = 0;
  CHECK(add(6, 18) == 0 && add(7, 16) == 0 && add(8, 18) == 0);
  unsigned count = bridge_type ? 10 : 9;
  if (bridge_type) CHECK(add(9, bridge_type) == 0);
  CHECK(xhqb_seal(count) == 0 && maps == count);
  CHECK(xhqb_seal(count) == -EINVAL);
  CHECK(xhqb_snapshot(&s) == 0 && s.count == count && s.nblocks == 6 && s.gpu == &devices[7]);
  for (unsigned i = 0; i < 6; i++) CHECK(s.blocks[i] == &devices[i]);
  for (unsigned i = 0; i < count; i++) CHECK(s.members[i].dev == &devices[i] && s.members[i].base == BASE+i*STRIDE && s.members[i].spi == SPI+i);
  CHECK(s.members[6].type == 18 && s.members[8].type == 18);
  if (bridge_type) CHECK(s.members[9].type == bridge_type);
  CHECK(xhqb_match(&s) == 0); s.members[6].type = 16; CHECK(xhqb_match(&s) == -ESTALE);
  CHECK(xhqb_snapshot(&s) == 0); s.blocks[0] = &devices[1]; CHECK(xhqb_match(&s) == -ESTALE);
  CHECK(xhqb_snapshot(&s) == 0); s.count = count-1; CHECK(xhqb_match(&s) == -ESTALE);
}
static void lifecycle(int late)
{
  make_board(late >= 4 ? OB_VIRTIO_DEVICE_ID : 0);
  uint64_t bt = late >= 4 ? 31 : 0;
  struct xhq q; struct xhqb_binding b;
  uint64_t t = 0, it = 0, cycle = 0;
  CHECK(xhqi_seal() == 0 && xhqi_close(&it) == 0);
  CHECK(xhqb_runtime_init(&q, &b, 17, 1, 23, it, bt, guard, &maps) == -ESTALE);
  CHECK(xhqb_console_close(&t) == 0 && t != 0);
  CHECK(xhqb_runtime_init(&q, &b, 17, t+1, 23, it, bt, guard, &maps) == -ESTALE);
  helper_error = -EPERM;
  CHECK(xhqb_runtime_init(&q, &b, 17, t, 23, it, bt, guard, &maps) == -EPERM && !closes);
  helper_error = 0;
  CHECK(xhqb_runtime_init(&q, &b, 17, t, 24, it, bt, guard, &maps) == -ESTALE && !closes);
  guest_error = -EBUSY;
  CHECK(xhqb_runtime_init(&q, &b, 17, t, 23, it, bt, guard, &maps) == -EBUSY && !closes);
  guest_error = 0;
  CHECK(xhqb_runtime_init(&q, &b, 17, t, 23, it+1, bt, guard, &maps) == -ESTALE && !closes);
  CHECK(xhqb_runtime_init(&q, &b, 17, t, 23, it, bt ? 0 : 31, guard, &maps) == -EINVAL && !closes);
  if (bt) {
    CHECK(xhqb_runtime_init(&q, &b, 17, t, 23, it, bt+1, guard, &maps) == -ESTALE && !closes);
    bridge_error = -EAGAIN;
    CHECK(xhqb_runtime_init(&q, &b, 17, t, 23, it, bt, guard, &maps) == -EAGAIN && !closes);
    bridge_error = 0;
  }
  CHECK(xhqb_runtime_init(&q, &b, 17, t, 23, it, bt, guard, &maps) == 0 && q.nblocks == 6);
  CHECK(xhq_begin(&q, 17, UINT64_MAX, &cycle) == 0);
  CHECK(drive(&q, cycle) == 0 && q.phase == XHQ_PARKED && q.verified == 255 && closes == 255);
  if (late == 4) {
    unsigned old = polls;
    bridge_error = -ESTALE;
    CHECK(xhq_request_resume(&q, 17, cycle) == -ESTALE && q.phase == XHQ_FAULT);
    CHECK(xhq_step(&q, 17, cycle) == -ESTALE && polls == old && !resumes);
  } else if (late == 3) {
    unsigned old = polls;
    CHECK(xhqi_start(XHQI_SCRIPT) == -EPERM);
    CHECK(xhq_request_resume(&q, 17, cycle) == -ESTALE && q.phase == XHQ_FAULT);
    CHECK(xhq_step(&q, 17, cycle) == -ESTALE && polls == old && !resumes);
    CHECK(xhqi_resume(it) == -ESTALE);
  } else if (late == 2) {
    unsigned old = polls;
    guest_error = -ESTALE;
    CHECK(xhq_request_resume(&q, 17, cycle) == -ESTALE && q.phase == XHQ_FAULT);
    CHECK(xhq_step(&q, 17, cycle) == -ESTALE && polls == old && !resumes && !xhqb_console_enter());
  } else if (late == 1) {
    unsigned old = polls;
    CHECK(add(9, 18) == -EPERM && maps == 9);
    CHECK(xhqb_match(&b.board) == -ESTALE);
    CHECK(xhq_request_resume(&q, 17, cycle) == -ESTALE && q.phase == XHQ_FAULT);
    CHECK(xhq_step(&q, 17, cycle) == -ESTALE && polls == old && !resumes && !xhqb_console_enter());
  } else {
    CHECK(xhq_request_resume(&q, 17, cycle) == 0);
    CHECK(drive(&q, cycle) == 0 && q.phase == XHQ_DONE && q.reopened == 255);
    CHECK(resumes == 8 && order[0] == 7 && order[7] == 0);
    for (unsigned i = 1; i <= 6; i++) CHECK(order[i] == i);
    CHECK(!xhqb_console_enter() && xhqb_console_poll(t) == 0);
    CHECK(xhqb_console_resume(t) == 0 && xhqb_console_enter()); xhqb_console_leave();
    CHECK(xhqi_resume(it) == 0);
  }
}
static void unsupported(unsigned type)
{
  make_board(type);
  struct xhq q; struct xhqb_binding b;
  uint64_t t = 0, it = 0;
  CHECK(xhqb_console_close(&t) == 0 && xhqi_seal() == 0 && xhqi_close(&it) == 0);
  CHECK(xhqb_runtime_init(&q, &b, 17, t, 23, it, 0, guard, &maps) == -ENOTSUP && !closes);
}
static int entered[2], release_writer[2];
static void *writer(void *unused)
{
  (void)unused;
  if (!xhqb_console_enter()) return (void *)1;
  char c = 'x';
  if (write(entered[1], &c, 1) != 1 || read(release_writer[0], &c, 1) != 1) abort();
  xhqb_console_leave(); return NULL;
}
static void console(void)
{
  CHECK(pipe(entered) == 0 && pipe(release_writer) == 0);
  pthread_t th;
  CHECK(pthread_create(&th, NULL, writer, NULL) == 0);
  char c; CHECK(read(entered[0], &c, 1) == 1);
  uint64_t t = 0, t2 = 0;
  CHECK(xhqb_console_close(&t) == -EAGAIN && !t);
  CHECK(write(release_writer[1], &c, 1) == 1);
  void *result = (void *)1; CHECK(pthread_join(th, &result) == 0 && !result);
  CHECK(xhqb_console_close(&t) == 0 && t);
  CHECK(xhqb_console_close(&t2) == -EBUSY && !t2);
  CHECK(xhqb_console_resume(t) == -EBUSY && !xhqb_console_enter());
  CHECK(xhqb_console_poll(t+1) == -ESTALE && xhqb_console_poll(t) == 0);
  CHECK(xhqb_console_resume(t+1) == -ESTALE && !xhqb_console_enter());
  CHECK(xhqb_console_resume(t) == 0 && xhqb_console_poll(t) == -ESTALE);
  CHECK(xhqb_console_enter()); xhqb_console_leave();
  CHECK(xhqb_console_close(&t2) == 0 && t2 > t);
  CHECK(xhqb_console_resume(t) == -ESTALE && xhqb_console_poll(t2) == 0 && xhqb_console_resume(t2) == 0);
  close(entered[0]); close(entered[1]); close(release_writer[0]); close(release_writer[1]);
}
static void invalid(int which)
{
  struct xhqb_snapshot s;
  CHECK(xhqb_begin(0, STRIDE, SPI, 1) == -EINVAL);
  CHECK(xhqb_begin(BASE, UINT64_MAX, SPI, 1) == -EINVAL);
  CHECK(xhqb_begin(BASE, STRIDE, SPI, 7) == -EINVAL);
  CHECK(xhqb_begin(BASE, STRIDE, SPI, which == 0 ? 0 : 1) == 0);
  if (which == 0) { CHECK(add(0, 16) == 0 && xhqb_seal(1) == -ENOTSUP && xhqb_snapshot(&s) == -ENOTSUP); return; }
  CHECK(add(0, 2) == 0);
  if (which == 1) { CHECK(xhqb_seal(1) == -EPROTO); }
  else if (which == 2) { CHECK(add(1, 16) == 0 && xhqb_seal(3) == -EPROTO); }
  else if (which == 3) { CHECK(add(2, 16) == 0 && xhqb_seal(2) == -EPROTO); }
  else if (which == 4) { CHECK(xhqb_map(&devices[1], BASE+STRIDE, SPI+2, 16, map_ok, &maps) == 0 && xhqb_seal(2) == -EPROTO); }
  else if (which == 5) { CHECK(xhqb_map(&devices[0], BASE+STRIDE, SPI+1, 16, map_ok, &maps) == 0 && xhqb_seal(2) == -EPROTO); }
  else if (which == 6) { CHECK(add(1, 16) == 0 && add(2, 16) == 0 && xhqb_seal(3) == -EPROTO); }
  else { CHECK(add(1, 2) == 0 && add(2, 16) == 0 && xhqb_seal(3) == -EPROTO); }
  CHECK(xhqb_snapshot(&s) == -EPROTO);
}
int main(void)
{
  alarm(30);
  /* Global process-lifetime registry: fork a fresh fixture for each case. */
  for (int i = 0; i < 21; i++) {
    int p[2]; CHECK(pipe(p) == 0);
    pid_t pid = fork(); CHECK(pid >= 0);
    if (!pid) {
      close(p[0]); checks = 0;
      if (i == 0) { CHECK(add(0, 2) == 0 && maps == 1); struct xhqb_snapshot s; CHECK(xhqb_snapshot(&s) == -EBUSY); }
      else if (i == 1) console();
      else if (i == 2 || i == 3) lifecycle(i == 3);
      else if (i == 12) lifecycle(2);
      else if (i == 13) lifecycle(3);
      else if (i == 14 || i == 15) lifecycle(i-10);
      else if (i >= 16) unsupported((const unsigned[]){1,25,0x4f43,48,0xffff}[i-16]);
      else invalid(i-4);
      if (write(p[1], &checks, sizeof checks) != sizeof checks) _exit(2);
      close(p[1]); _exit(0);
    }
    close(p[1]); unsigned child = 0;
    CHECK(read(p[0], &child, sizeof child) == sizeof child); close(p[0]);
    int status; CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && !WEXITSTATUS(status));
    checks += child;
  }
  printf("quiescence board and console: %u checks, 0 failed\n", checks);
  return 0;
}
