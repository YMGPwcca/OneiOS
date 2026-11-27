// SPDX-License-Identifier: MIT
#ifndef XH_DISPLAY_QUIESCE_H
#define XH_DISPLAY_QUIESCE_H
#include <stdint.h>
#include <string.h>

// One little-endian 20-byte SOCK_SEQPACKET record. Q/A = park/ACK,
// R/B = explicit resume/ACK. Ticket is scoped to a single connection.
// An ACK is a helper userspace buffer-post boundary, NOT a present fence.
struct xh_display_barrier {
  char magic[4];
  uint32_t lo, hi, version, reserved;
};
static inline struct xh_display_barrier xh_display_barrier_make(char op, uint64_t ticket)
{
  return (struct xh_display_barrier){ {'X','H','D',op},
    (uint32_t)ticket, (uint32_t)(ticket >> 32), 1, 0 };
}
static inline uint64_t xh_display_barrier_ticket(const struct xh_display_barrier *p)
{
  return (uint64_t)p->lo | (uint64_t)p->hi << 32;
}
static inline int xh_display_barrier_valid(const struct xh_display_barrier *p, char op)
{
  return !memcmp(p->magic, "XHD", 3) && p->magic[3] == op &&
         p->version == 1 && !p->reserved && xh_display_barrier_ticket(p);
}
#endif
