#include "quiesce_board.h"
#include "quiesce_vcpu.h"
#include "quiesce_input.h"
#include "xnuhost.h"
#include "bridges/devices.h"
#include "oneios_bridge_proto.h"
#include <errno.h>

int xhqb_binding_verify(const struct xhqb_binding *b)
{
  int r = xhqb_match(&b->board);
  if (!r) r = xhqb_console_poll(b->console_ticket);
  if (!r) r = xh_tasks_quiesce_check(b->vcpu_ticket);
  if (!r) r = xhqi_poll(b->input_ticket);
  if (!r && b->bridge) r = br_bridge_quiesce_poll(b->bridge, b->bridge_ticket, NULL);
  if (!r && b->sound) r = br_snd_quiesce_poll(b->sound, b->sound_ticket);
  return r ? r : xh_display_quiesce_verify_helper();
}
/* All callers must classify the actual sealed board, not requested flags.
 * Unknown transports (including camera, encoder and network) remain refused. */
int xhqb_binding_snapshot(struct xhqb_binding *b)
{
  if (!b) return -EINVAL;
  b->bridge = b->sound = NULL;
  int r = xhqb_snapshot(&b->board);
  for (unsigned i = 0; !r && i < b->board.count; i++) {
    unsigned type = b->board.members[i].type;
    if (type == OB_VIRTIO_DEVICE_ID && !b->bridge) b->bridge = b->board.members[i].dev;
    else if (type == 25 && !b->sound) b->sound = b->board.members[i].dev;
    else if (type != 2 && type != 16 && type != 18) r = -ENOTSUP;
  }
  return r;
}

static int guard_board(void *ctx, uint64_t owner, uint64_t cycle, enum xhq_phase phase)
{
  struct xhqb_binding *b = ctx;
  int r = xhqb_binding_verify(b);
  if (!r) r = b->guard(b->ctx, owner, cycle, phase);
  return r ? r : xhqb_binding_verify(b);
}
int xhqb_runtime_init(struct xhq *q, struct xhqb_binding *b, uint64_t owner,
                      uint64_t console_ticket, uint64_t vcpu_ticket, uint64_t input_ticket, uint64_t bridge_ticket, uint64_t sound_ticket,
                      int (*guard)(void *, uint64_t, uint64_t, enum xhq_phase), void *ctx)
{
  if (!q || !b || !owner || !console_ticket || !vcpu_ticket || !input_ticket || !guard) return -EINVAL;
  struct xhqb_binding tmp = { .console_ticket = console_ticket, .vcpu_ticket = vcpu_ticket, .input_ticket = input_ticket, .bridge_ticket = bridge_ticket, .sound_ticket = sound_ticket, .guard = guard, .ctx = ctx };
  int r = xhqb_binding_snapshot(&tmp);
  if (!r && ((!!tmp.bridge != !!bridge_ticket) || (!!tmp.sound != !!sound_ticket))) r = -EINVAL;
  if (!r) r = xhqb_binding_verify(&tmp);
  if (r) return r;
  *b = tmp;
  return xhq_runtime_init(q, &b->runtime, owner, b->board.gpu, b->board.blocks,
                          b->board.nblocks, b->board.nblocks, guard_board, b);
}
