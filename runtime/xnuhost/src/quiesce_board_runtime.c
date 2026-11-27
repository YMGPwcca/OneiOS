#include "quiesce_board.h"
#include "quiesce_vcpu.h"
#include "quiesce_input.h"
#include "xnuhost.h"
#include <errno.h>

static int membership(const struct xhqb_binding *b)
{
  int r = xhqb_match(&b->board);
  if (!r) r = xhqb_console_poll(b->console_ticket);
  if (!r) r = xh_tasks_quiesce_check(b->vcpu_ticket);
  if (!r) r = xhqi_poll(b->input_ticket);
  return r ? r : xh_display_quiesce_verify_helper();
}
static int guard_board(void *ctx, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  struct xhqb_binding *b = ctx;
  int r = membership(b);
  if (!r) r = b->guard(b->ctx, owner, cycle, phase);
  return r ? r : membership(b);
}
int xhqb_runtime_init(struct xhq *q, struct xhqb_binding *b, uint64_t owner,
                      uint64_t console_ticket, uint64_t vcpu_ticket, uint64_t input_ticket,
                      int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase), void *ctx)
{
  if (!q || !b || !owner || !console_ticket || !vcpu_ticket || !input_ticket || !guard) return -EINVAL;
  struct xhqb_binding tmp = { .console_ticket = console_ticket, .vcpu_ticket = vcpu_ticket, .input_ticket = input_ticket, .guard = guard, .ctx = ctx };
  int r = xhqb_snapshot(&tmp.board);
  // An enumerated transport is not a drained producer. No audio, net,
  // camera, media or hardware bridge provider has qualified yet.
  for (unsigned i = 0; !r && i < tmp.board.count; i++) {
    unsigned type = tmp.board.members[i].type;
    if (type != 2 && type != 16 && type != 18) r = -ENOTSUP;
  }
  if (!r) r = membership(&tmp);
  if (r) return r;
  *b = tmp;
  return xhq_runtime_init(q, &b->runtime, owner, b->board.gpu, b->board.blocks,
                          b->board.nblocks, b->board.nblocks, guard_board, b);
}
