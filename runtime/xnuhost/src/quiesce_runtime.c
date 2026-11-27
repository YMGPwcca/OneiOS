#define _GNU_SOURCE
#include "quiesce.h"
#include "xnuhost.h"
#include "gpu3d.h"
#include <errno.h>
#include <time.h>

_Static_assert(XHQ_MAX_BLOCKS == XH_MAX_DISKS, "update quiescence membership bound");
static int runtime_now(void *ctx, uint64_t *ns)
{
  (void)ctx;
#ifdef CLOCK_BOOTTIME
  struct timespec t;
  if (clock_gettime(CLOCK_BOOTTIME, &t)) return -errno;
  if (t.tv_sec < 0 || (uint64_t)t.tv_sec > (UINT64_MAX - (uint64_t)t.tv_nsec) / 1000000000u) return -EOVERFLOW;
  *ns = (uint64_t)t.tv_sec * 1000000000u + (uint64_t)t.tv_nsec;
  return 0;
#else
  (void)ns;
  return -ENOTSUP;
#endif
}
static int runtime_guard(void *ctx, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  struct xhq_runtime *b = ctx;
  return b->guard(b->guard_ctx, owner, cycle, phase);
}
static int runtime_close(void *ctx, unsigned m, uint64_t *t)
{
  struct xhq_runtime *b = ctx;
  if (m == XHQ_GPU) return xh_virtio_gpu_quiesce_close(b->gpu, t);
  if (m <= b->nblocks) return xh_virtio_blk_quiesce_close(b->blocks[m-1], t);
  if (m == b->nblocks + 1u) return xh_display_quiesce_close(t);
  return -EINVAL;
}
static int runtime_poll(void *ctx, unsigned m, uint64_t t)
{
  struct xhq_runtime *b = ctx;
  if (m == XHQ_GPU) return xh_virtio_gpu_quiesce_poll(b->gpu, t);
  if (m <= b->nblocks) return xh_virtio_blk_quiesce_poll(b->blocks[m-1], t);
  if (m == b->nblocks + 1u) return xh_display_quiesce_poll(t);
  return -EINVAL;
}
static int runtime_resume(void *ctx, unsigned m, uint64_t t)
{
  struct xhq_runtime *b = ctx;
  if (m == XHQ_GPU) return xh_virtio_gpu_quiesce_resume(b->gpu, t);
  if (m <= b->nblocks) return xh_virtio_blk_quiesce_resume(b->blocks[m-1], t);
  if (m == b->nblocks + 1u) return xh_display_quiesce_resume(t);
  return -EINVAL;
}
int xhq_runtime_init(struct xhq *q, struct xhq_runtime *b, uint64_t owner,
                     struct xh_virtio *gpu, struct xh_virtio *const *blocks,
                     unsigned nblocks, unsigned configured_ndisk,
                     int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase), void *ctx)
{
  if (!q || !b || !gpu || !blocks || !guard || !owner || !nblocks ||
      nblocks != configured_ndisk || nblocks > XHQ_MAX_BLOCKS) return -EINVAL;
  struct xhq_runtime tmp = { .gpu = gpu, .nblocks = nblocks, .guard = guard, .guard_ctx = ctx };
  for (unsigned i = 0; i < nblocks; i++) {
    if (!blocks[i] || blocks[i] == gpu) return -EINVAL;
    for (unsigned j = 0; j < i; j++) if (blocks[i] == blocks[j]) return -EINVAL;
    tmp.blocks[i] = blocks[i];
  }
  *b = tmp;
  const struct xhq_ops ops = { runtime_now, runtime_guard, runtime_close, runtime_poll, runtime_resume };
  return xhq_init(q, &ops, b, owner, nblocks);
}
