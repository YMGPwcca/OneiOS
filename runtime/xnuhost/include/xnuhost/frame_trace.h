// SPDX-License-Identifier: MIT
// Optional XHDF extension: legacy 20-byte rectangle prefix stays byte-for-byte identical.
// SOCK_SEQPACKET receivers reading only 20 bytes still accept this record and show the frame.
// v1 is 40 bytes (flush); v2 is 64 (scanout copy); v3 is 88 (resource provenance).
// All timestamps are CLOCK_MONOTONIC nanoseconds on the same Linux/Android host.
#ifndef XNUHOST_FRAME_TRACE_H
#define XNUHOST_FRAME_TRACE_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define XH_FRAME_TRACE_VERSION 1u
#define XH_FRAME_TRACE_VERSION_SCANOUT 2u
#define XH_FRAME_TRACE_VERSION_PROVENANCE 3u

enum { XH_FRAME_SCANOUT_BLOB = 1, XH_FRAME_SCANOUT_2D = 2 };

// Metadata captured around VirtIO GPU's scanout-memory copy. A valid GPU
// submission fence is NOT implied by a RESOURCE_FLUSH, so none is invented.
struct xh_frame_scanout {
  uint64_t start_ns, copied_ns;
  uint32_t kind, resource_id;
  // Source identity, NOT render-fence ownership. Queue generation may be zero
  // before the first GPU reset; resource_generation is never zero if supplied.
  uint64_t queue_generation, resource_generation;
  uint32_t owner_context;            // 0: the scanout is not owned by one GPU context
};

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

// v2 is only sent for GPU scanout flushes (not helper attach / generic flush).
// The first 40 bytes remain the v1 layout; the first 20 are legacy XHDF.
struct xh_frame_trace_packet_v2 {
  struct xh_frame_trace_packet base;
  uint64_t scanout_start_ns, scanout_copied_ns;
  uint32_t scanout_kind, resource_id;
};
_Static_assert(sizeof(struct xh_frame_trace_packet_v2) == 64, "XHDF scanout packet size");
_Static_assert(offsetof(struct xh_frame_trace_packet_v2, scanout_start_ns) == 40, "XHDF v2 prefix");

static inline int xh_frame_trace_scanout_fields_valid(const struct xh_frame_trace_packet_v2 *p)
{
  return p && !memcmp(p->base.magic, "XHDF", 4) &&
         p->base.seq != 0 && p->base.flush_mono_ns != 0 &&
         p->scanout_start_ns != 0 && p->scanout_start_ns <= p->scanout_copied_ns &&
         p->scanout_copied_ns <= p->base.flush_mono_ns &&
         (p->scanout_kind == XH_FRAME_SCANOUT_BLOB || p->scanout_kind == XH_FRAME_SCANOUT_2D) &&
         p->resource_id != 0;
}

static inline int xh_frame_trace_v2_valid(const struct xh_frame_trace_packet_v2 *p)
{
  return p && p->base.version == XH_FRAME_TRACE_VERSION_SCANOUT &&
         xh_frame_trace_scanout_fields_valid(p);
}

// First 64 bytes are XHDF v2's layout. A version-2 helper can keep rendering
// the first 20 bytes, but must NOT claim to understand v3 provenance.
struct xh_frame_trace_packet_v3 {
  struct xh_frame_trace_packet_v2 base;
  uint64_t queue_generation;
  uint64_t resource_generation;
  uint32_t owner_context;
  uint32_t reserved;
};
_Static_assert(sizeof(struct xh_frame_trace_packet_v3) == 88, "XHDF provenance packet size");
_Static_assert(offsetof(struct xh_frame_trace_packet_v3, queue_generation) == 64, "XHDF v3 prefix");

static inline int xh_frame_trace_v3_valid(const struct xh_frame_trace_packet_v3 *p)
{
  return p && p->base.base.version == XH_FRAME_TRACE_VERSION_PROVENANCE &&
         xh_frame_trace_scanout_fields_valid(&p->base) &&
         p->resource_generation != 0 && p->reserved == 0;
}

#endif
