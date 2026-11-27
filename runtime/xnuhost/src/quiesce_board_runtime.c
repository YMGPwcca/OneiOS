#include "quiesce_board.h"
#include <errno.h>

static int membership(const struct xhqb_binding *b)
{
  int r = xhqb_match(&b->board);
  return r ? r : xhqb_console_poll(b->console_ticket);
}
static int guard_board(void *ctx, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  struct xhqb_binding *b = ctx;
  int r = membership(b);
  if (!r) r = b->guard(b->ctx, owner, cycle, phase);
  return r ? r : membership(b);
}
int xhqb_runtime_init(struct xhq *q, struct xhqb_binding *b, uint64_t owner,
                      uint64_t console_ticket,
                      int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase), void *ctx)
{
  if (!q || !b || !owner || !console_ticket || !guard) return -EINVAL;
  struct xhqb_binding tmp = { .console_ticket = console_ticket, .guard = guard, .ctx = ctx };
  int r = xhqb_snapshot(&tmp.board);
  if (!r) r = membership(&tmp);
  if (r) return r;
  *b = tmp;
  return xhq_runtime_init(q, &b->runtime, owner, b->board.gpu, b->board.blocks,
                          b->board.nblocks, b->board.nblocks, guard_board, b);
}
