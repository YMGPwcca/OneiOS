// SPDX-License-Identifier: MIT
// Optional XHDF extension: legacy 20-byte rectangle prefix stays byte-for-byte identical.
// SOCK_SEQPACKET receivers reading only 20 bytes still accept this record and show the frame.
// New helpers read the full 40 bytes to correlate host flush -> Android buffer post.
// All timestamps are CLOCK_MONOTONIC nanoseconds on the same Linux/Android host.
#ifndef XNUHOST_FRAME_TRACE_H
#define XNUHOST_FRAME_TRACE_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define XH_FRAME_TRACE_VERSION 1u

struct xh_frame_trace_packet {
  char magic[4];                 // "XHDF": legacy consumer still sees a normal flush
  uint32_t x, y, w, h;          // first 20 bytes: legacy XHDF message
  uint32_t version;             // version 1; also provides alignment for 64-bit fields
  uint64_t seq;                 // monotone within this XNUHost process, starts at 1
  uint64_t flush_mono_ns;       // after XNUHost's scanout copy, before socket send
};
_Static_assert(sizeof(struct xh_frame_trace_packet) == 40, "XHDF trace packet size");
_Static_assert(offsetof(struct xh_frame_trace_packet, version) == 20, "XHDF legacy prefix");
_Static_assert(offsetof(struct xh_frame_trace_packet, seq) == 24, "XHDF trace layout");

static inline int xh_frame_trace_valid(const struct xh_frame_trace_packet *p)
{
  return p && !memcmp(p->magic, "XHDF", 4) && p->version == XH_FRAME_TRACE_VERSION &&
         p->seq != 0 && p->flush_mono_ns != 0;
}

#endif
