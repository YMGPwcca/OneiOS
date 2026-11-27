#ifndef XH_QUIESCE_VCPU_H
#define XH_QUIESCE_VCPU_H
#include <stdbool.h>
#include <stdint.h>

/* One process-lifetime gate, initialized before vCPU creation. Only one
 * serialized control owner may close/poll/resume. Each configured vCPU
 * registers exactly once and checkpoints only itself, in host context,
 * outside host/device locks and after its prior user release has ended.
 * No forced preemption; a CPU that never arrives prevents a receipt.
 * Other host producers and independent process membership are separate. */
#define XHQV_MAX_CPUS 8u
#define XHQV_CLOSED (UINT32_C(1) << 16)
extern uint32_t xhqv_state; /* internal atomic word; only gate implementation writes */
int xhqv_configure(unsigned ncpu);
void xhqv_register(unsigned index);
void xhqv_park(unsigned index);
static inline void xhqv_checkpoint(unsigned index)
{
  if (__atomic_load_n(&xhqv_state, __ATOMIC_ACQUIRE) & XHQV_CLOSED) xhqv_park(index);
}
/* Permanent fault, or fault only if a cycle is currently closed. Neither
 * releases parked CPUs or changes the existing process shutdown path. */
void xhqv_invalidate(void);
void xhqv_invalidate_if_closed(void);
int xhqv_close(uint64_t *ticket);
int xhqv_poll(uint64_t ticket);
/* Only after all other drains/reopens and external authorization. */
int xhqv_resume(uint64_t ticket);
/* Tracked task audit, implemented in task.c. Requires a verified parked
 * vCPU ticket. Not a proof of the OS-level descendant set or factory
 * identity; no service requests are sent, no deferred maps are flushed. */
int xh_tasks_quiesce_check(uint64_t ticket);
#endif
