// SPDX-License-Identifier: MIT
#ifndef ONEIOS_BRIDGE_QUIESCE_H
#define ONEIOS_BRIDGE_QUIESCE_H
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* All operations under the owning device/worker lock. This is only a
 * ticket primitive; the caller must independently prove its work idle. */
typedef struct {
  uint64_t generation;
  bool closed, verified, fault;
} brq_gate;
static inline int brq_close(brq_gate *g, bool busy, uint64_t *ticket)
{
  if (!ticket) return -EINVAL;
  if (g->fault) return -ESTALE;
  if (g->closed) return -EBUSY;
  if (g->generation == UINT64_MAX) return -EOVERFLOW;
  if (busy) return -EAGAIN;
  g->closed = true; g->verified = false;
  *ticket = ++g->generation;
  return 0;
}
static inline int brq_check(const brq_gate *g, uint64_t ticket, bool busy)
{
  if (!ticket || !g->closed || ticket != g->generation || g->fault) return -ESTALE;
  return busy ? -EAGAIN : 0;
}
static inline int brq_poll(brq_gate *g, uint64_t ticket, bool busy)
{
  int r = brq_check(g, ticket, busy);
  if (!r) g->verified = true;
  return r;
}
static inline int brq_can_resume(const brq_gate *g, uint64_t ticket, bool busy)
{
  int r = brq_check(g, ticket, busy);
  return r ? r : g->verified ? 0 : -EBUSY;
}
static inline int brq_resume(brq_gate *g, uint64_t ticket, bool busy)
{
  int r = brq_can_resume(g, ticket, busy);
  if (!r) { g->closed = false; g->verified = false; }
  return r;
}
static inline bool brq_late(brq_gate *g)
{
  if (g->closed) g->fault = true;
  return g->closed;
}

/* Bounded, latest-value telemetry, not a lossless event queue. One
 * slot per typed report; callers validate the exact protocol size. */
#define BRQ_REPORTS 3u
#define BRQ_REPORT_BYTES 64u
typedef struct { size_t length; uint8_t bytes[BRQ_REPORT_BYTES]; } brq_report;
static inline int brq_store(brq_report slots[BRQ_REPORTS], unsigned slot, const void *data, size_t n)
{
  if (slot >= BRQ_REPORTS || !data || !n || n > BRQ_REPORT_BYTES) return -EINVAL;
  memcpy(slots[slot].bytes, data, n);
  slots[slot].length = n;
  return 0;
}
static inline unsigned brq_report_mask(const brq_report slots[BRQ_REPORTS])
{
  unsigned mask = 0;
  for (unsigned i = 0; i < BRQ_REPORTS; i++) if (slots[i].length) mask |= 1u << i;
  return mask;
}
#endif
