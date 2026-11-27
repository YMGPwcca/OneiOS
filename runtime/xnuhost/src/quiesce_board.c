#include "quiesce_board.h"
#include <errno.h>
#include <limits.h>
#include <pthread.h>

/* Registry only runs on boot-time creation and the control path. No
 * extra lock on ordinary MMIO, GPU submission or input delivery. */
static pthread_mutex_t board_lock = PTHREAD_MUTEX_INITIALIZER;
static struct {
  bool begun, sealed;
  int fault;
  uint64_t base, stride;
  unsigned spi, expected_disks;
  struct xhqb_snapshot view;
} board;

static int try_lock(pthread_mutex_t *lock)
{
  int r = pthread_mutex_trylock(lock);
  return r == EBUSY ? -EAGAIN : -r;
}
int xhqb_begin(uint64_t base, uint64_t stride, unsigned spi, unsigned ndisk)
{
  if (!base || !stride || ndisk > XHQ_MAX_BLOCKS ||
      stride > (UINT64_MAX - base) / (XHQB_MAX_DEVICES-1u) ||
      spi > UINT_MAX - (XHQB_MAX_DEVICES-1u)) return -EINVAL;
  pthread_mutex_lock(&board_lock);
  int r = board.begun ? -EBUSY : 0;
  if (!r) {
    board.begun = true;
    board.base = base; board.stride = stride;
    board.spi = spi; board.expected_disks = ndisk;
  }
  pthread_mutex_unlock(&board_lock);
  return r;
}
static void record(struct xh_virtio *dev, uint64_t base, unsigned spi, unsigned type)
{
  struct xhqb_snapshot *v = &board.view;
  if (board.fault) return;
  if (v->count >= XHQB_MAX_DEVICES || !dev || !type ||
      base != board.base + board.stride * v->count || spi != board.spi + v->count) {
    board.fault = -EPROTO; return;
  }
  for (unsigned i = 0; i < v->count; i++)
    if (v->members[i].dev == dev) { board.fault = -EPROTO; return; }
  if (type == 2) { /* VIRTIO_ID_BLOCK */
    if (v->nblocks >= XHQ_MAX_BLOCKS) { board.fault = -EOVERFLOW; return; }
    v->blocks[v->nblocks++] = dev;
  } else if (type == 16) { /* VIRTIO_ID_GPU */
    if (v->gpu) { board.fault = -EPROTO; return; }
    v->gpu = dev;
  }
  v->members[v->count++] = (struct xhqb_member){dev, base, spi, type};
}
int xhqb_map(struct xh_virtio *dev, uint64_t base, unsigned spi, unsigned type,
             int (*map)(void *), void *ctx)
{
  if (!map) return -EINVAL;
  pthread_mutex_lock(&board_lock);
  if (board.sealed) {
    board.fault = -ESTALE;
    pthread_mutex_unlock(&board_lock);
    return -EPERM;
  }
  int r = map(ctx);
  if (!r && board.begun) record(dev, base, spi, type);
  pthread_mutex_unlock(&board_lock);
  return r;
}
int xhqb_seal(unsigned count)
{
  pthread_mutex_lock(&board_lock);
  int r = 0;
  if (!board.begun || board.sealed) r = -EINVAL;
  else {
    board.sealed = true;
    if (!board.fault && (board.view.count != count || board.view.nblocks != board.expected_disks || !board.view.gpu))
      board.fault = -EPROTO;
    r = board.fault ? board.fault : !board.view.nblocks ? -ENOTSUP : 0;
  }
  pthread_mutex_unlock(&board_lock);
  return r;
}
static int valid_board(void)
{
  if (!board.sealed) return -EBUSY;
  if (board.fault) return board.fault;
  return board.view.nblocks ? 0 : -ENOTSUP;
}
int xhqb_snapshot(struct xhqb_snapshot *out)
{
  if (!out) return -EINVAL;
  int r = try_lock(&board_lock);
  if (r) return r;
  r = valid_board();
  if (!r) *out = board.view;
  pthread_mutex_unlock(&board_lock);
  return r;
}
int xhqb_match(const struct xhqb_snapshot *s)
{
  if (!s) return -EINVAL;
  int r = try_lock(&board_lock);
  if (r) return r;
  r = valid_board();
  const struct xhqb_snapshot *v = &board.view;
  if (!r && (s->count != v->count || s->nblocks != v->nblocks || s->gpu != v->gpu)) r = -ESTALE;
  for (unsigned i = 0; !r && i < v->nblocks; i++) if (s->blocks[i] != v->blocks[i]) r = -ESTALE;
  for (unsigned i = 0; !r && i < v->count; i++) {
    const struct xhqb_member *a = &s->members[i], *b = &v->members[i];
    if (a->dev != b->dev || a->base != b->base || a->spi != b->spi || a->type != b->type) r = -ESTALE;
  }
  pthread_mutex_unlock(&board_lock);
  return r;
}

static pthread_mutex_t console_lock = PTHREAD_MUTEX_INITIALIZER;
static bool console_closed; /* atomic access, transitions under lock */
static bool console_verified;
static uint64_t console_ticket;
bool xhqb_console_enter(void)
{
  if (__atomic_load_n(&console_closed, __ATOMIC_ACQUIRE)) return false;
  pthread_mutex_lock(&console_lock);
  if (!__atomic_load_n(&console_closed, __ATOMIC_RELAXED)) return true;
  pthread_mutex_unlock(&console_lock);
  return false;
}
void xhqb_console_leave(void) { pthread_mutex_unlock(&console_lock); }
int xhqb_console_close(uint64_t *ticket)
{
  if (!ticket) return -EINVAL;
  int r = try_lock(&console_lock);
  if (r) return r;
  if (__atomic_load_n(&console_closed, __ATOMIC_RELAXED)) r = -EBUSY;
  else if (console_ticket == UINT64_MAX) r = -EOVERFLOW;
  else {
    console_verified = false;
    __atomic_store_n(&console_closed, true, __ATOMIC_RELEASE);
    *ticket = ++console_ticket;
  }
  pthread_mutex_unlock(&console_lock);
  return r;
}
static int console_match(uint64_t ticket)
{
  return ticket && ticket == console_ticket && __atomic_load_n(&console_closed, __ATOMIC_RELAXED) ? 0 : -ESTALE;
}
int xhqb_console_poll(uint64_t ticket)
{
  int r = try_lock(&console_lock);
  if (r) return r;
  r = console_match(ticket);
  if (!r) console_verified = true;
  pthread_mutex_unlock(&console_lock);
  return r;
}
int xhqb_console_resume(uint64_t ticket)
{
  int r = try_lock(&console_lock);
  if (r) return r;
  r = console_match(ticket);
  if (!r && !console_verified) r = -EBUSY;
  if (!r) {
    console_verified = false;
    __atomic_store_n(&console_closed, false, __ATOMIC_RELEASE);
  }
  pthread_mutex_unlock(&console_lock);
  return r;
}
