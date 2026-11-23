// SPDX-License-Identifier: MIT
// encctl: the phone test of the video encoder bridge, as camctl/bridgectl are. It runs the whole host path -- the
// "droidvm,virtio-media" device (media_device.c) on xnuhost's real transport, with the real MediaCodec backend
// (backend_ndk.c) -- with a guest made of plain memory in this process, encodes an NV12 test pattern through the
// phone's hardware encoder as root with One UI up, and checks the bitstream. No xnuhost, no Apple code.
//
//   encctl hevc|h264 [WIDTH HEIGHT]        direct MediaCodec backend (phone A/B)
//   encctl --helper PATH hevc|h264 [WIDTH HEIGHT]  virtio-media -> socket -> real helper -> MediaCodec
//   ONEIOS_ENCODER_BINDER_POOL=1           opt-in only for direct MediaCodec backend
//
// A pass prints the backend, the encoded size, the first parameter sets (VPS/SPS/PPS for HEVC, SPS/PPS for H.264) and
// the keyframe, and "ok". `error:` lines say which step failed.
#define _GNU_SOURCE
#include "encoder.h"
#include "media_proto.h"
#include "binder_pool.h"
#include <pthread.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// What xnuhost supplies around virtio.c (encctl stands in for xnuhost, as camctl does for the camera).
void xh_gic_set_spi(unsigned intid, bool level) { (void)intid; (void)level; }
int xh_mmio_add(const xh_mmio_region *region) { (void)region; return 0; }
void *xh_ram(uint64_t pa, uint64_t len) { (void)len; return (void *)(uintptr_t)pa; }

// libonebridges' log goes to stderr here.
void (*br_log_sink)(int level, const char *line);
void br_log(int level, const char *fmt, ...) {
  va_list ap; va_start(ap, fmt);
  fprintf(stderr, "%s ", level == 0 ? "error:" : level == 1 ? "encctl:" : "debug:");
  vfprintf(stderr, fmt, ap); fprintf(stderr, "\n"); va_end(ap);
}

static void nap(unsigned ms) { struct timespec ts = { 0, (long)ms * 1000000L }; nanosleep(&ts, NULL); }

// ---- a guest of plain memory over xnuhost's real transport (as tests/test_encoder.c) -----------------------------
#define QN 32u
typedef struct { uint64_t addr; uint32_t len; uint16_t flags, next; } vdesc;
typedef struct {
  vdesc desc[QN];
  struct { uint16_t flags, idx, ring[QN]; } avail;
  struct { uint16_t flags, idx; struct { uint32_t id, len; } ring[QN]; } used;
  uint16_t next_desc, seen_used;
} gqueue;
typedef struct { xh_virtio *dev; gqueue q[2]; } guest;
static void w32(guest *g, uint64_t o, uint32_t v) { xh_virtio_mmio_write(g->dev, o, 4, v); }

static void guest_up(guest *g, xh_virtio *dev) {
  memset(g, 0, sizeof *g); g->dev = dev;
  w32(g, 0x70, 0); w32(g, 0x70, 1); w32(g, 0x70, 3);
  w32(g, 0x24, 0); w32(g, 0x20, 0); w32(g, 0x24, 1); w32(g, 0x20, 1);
  w32(g, 0x70, 11);
  for (unsigned q = 0; q < 2; q++) {
    w32(g, 0x30, q); w32(g, 0x38, QN);
    uint64_t d = (uint64_t)(uintptr_t)g->q[q].desc, a = (uint64_t)(uintptr_t)&g->q[q].avail, u = (uint64_t)(uintptr_t)&g->q[q].used;
    w32(g, 0x80, (uint32_t)d); w32(g, 0x84, (uint32_t)(d >> 32));
    w32(g, 0x90, (uint32_t)a); w32(g, 0x94, (uint32_t)(a >> 32));
    w32(g, 0xa0, (uint32_t)u); w32(g, 0xa4, (uint32_t)(u >> 32));
    w32(g, 0x44, 1);
  }
  w32(g, 0x70, 15);
}
static void post(guest *g, unsigned q, void **bufs, const uint32_t *lens, const bool *wr, unsigned n) {
  gqueue *gq = &g->q[q];
  uint16_t head = gq->next_desc;
  for (unsigned i = 0; i < n; i++) {
    uint16_t at = (uint16_t)((gq->next_desc + i) % QN);
    gq->desc[at] = (vdesc){ (uint64_t)(uintptr_t)bufs[i], lens[i],
                            (uint16_t)((wr[i] ? 2 : 0) | (i + 1 < n ? 1 : 0)), (uint16_t)((at + 1) % QN) };
  }
  gq->next_desc = (uint16_t)((gq->next_desc + n) % QN);
  gq->avail.ring[gq->avail.idx % QN] = head;
  __atomic_add_fetch(&gq->avail.idx, 1, __ATOMIC_SEQ_CST);
  w32(g, 0x50, q);
}
static int reap(guest *g, unsigned q, uint32_t *id) {
  gqueue *gq = &g->q[q];
  if (__atomic_load_n(&gq->used.idx, __ATOMIC_SEQ_CST) == gq->seen_used) return -1;
  if (id) *id = gq->used.ring[gq->seen_used % QN].id;
  return (int)gq->used.ring[gq->seen_used++ % QN].len;
}
static uint32_t command(guest *g, const void *cmd, uint32_t cl, void *out, uint32_t ol,
                        uint8_t *resp, uint32_t rl, void *in, uint32_t il) {
  void *bufs[4]; uint32_t lens[4]; bool wr[4]; unsigned n = 0;
  bufs[n] = (void *)cmd; lens[n] = cl; wr[n] = false; n++;
  if (out) { bufs[n] = out; lens[n] = ol; wr[n] = false; n++; }
  bufs[n] = resp; lens[n] = rl; wr[n] = true; n++;
  if (in) { bufs[n] = in; lens[n] = il; wr[n] = true; n++; }
  memset(resp, 0, rl);
  post(g, MEDIA_QUEUE_COMMAND, bufs, lens, wr, n);
  reap(g, MEDIA_QUEUE_COMMAND, NULL);
  uint32_t s; memcpy(&s, resp, 4); return s;
}
static uint32_t ioc(guest *g, uint32_t sess, uint32_t nr, void *p, uint32_t len) {
  uint32_t c[4] = { MEDIA_CMD_IOCTL, 0, sess, nr }; uint8_t r[8];
  return command(g, c, sizeof c, p, len, r, sizeof r, p, len);
}
static uint64_t mmap_buf(guest *g, uint32_t sess, uint64_t h) {
  uint32_t c[5] = { MEDIA_CMD_MMAP, 0, sess, 1, (uint32_t)h }; uint8_t r[24];
  if (command(g, c, sizeof c, NULL, 0, r, sizeof r, NULL, 0)) return 0;
  uint64_t gpa; memcpy(&gpa, r + 8, 8); return gpa;
}
// Fail closed if an ioctl/status was rejected: the original phone harness
// ignored several failures and then misleadingly printed "0 errors".
#define ENCCTL_IO_CHECK(call, label) do { \
  uint32_t status_ = (call); \
  if (status_) { fprintf(stderr, "error: %s rejected: status %u\n", label, status_); return 1; } \
} while (0)
#define EVENT_BUFS 8
static uint8_t event_store[EVENT_BUFS][MEDIA_EVENT_BYTES];
static uint8_t *wait_event(guest *g, uint32_t *kind) {
  for (unsigned i = 0; i < 5000; i++) {
    uint32_t id; int len = reap(g, MEDIA_QUEUE_EVENT, &id);
    if (len >= 8) { uint8_t *b = (uint8_t *)(uintptr_t)g->q[MEDIA_QUEUE_EVENT].desc[id % QN].addr; memcpy(kind, b, 4); return b; }
    nap(1);
  }
  return NULL;
}

// A/B phone test: default remains identical to the original no-pool case.
// With opt-in, use the same bootstrap used by the production helper.
static int maybe_start_binder_pool(void) {
  const char *opt = getenv("ONEIOS_ENCODER_BINDER_POOL");
  if (!opt || strcmp(opt, "1")) return 0;
  return oneios_encoder_start_binder_pool();
}

int main(int argc, char **argv) {
  // --helper tests the *actual production route* through backend_helper.c:
  // virtio-media -> UNIX socket -> oneios-encoder -> MediaCodec -> socket.
  // Neither this harness nor the real helper starts an iOS guest.
  const char *helper = NULL;
  int codec_arg = 1;
  if (argc > 1 && strcmp(argv[1], "--helper") == 0) {
    if (argc < 4 || !argv[2][0]) {
      fprintf(stderr, "usage: encctl --helper /absolute/path/to/oneios-encoder hevc|h264 [WIDTH HEIGHT]\n");
      return 2;
    }
    helper = argv[2];
    codec_arg = 3;
  }
  const char *codec_name = argc > codec_arg ? argv[codec_arg] : "hevc";
  if (strcmp(codec_name, "hevc") && strcmp(codec_name, "h264")) {
    fprintf(stderr, "error: unsupported codec %s (expected hevc or h264)\n", codec_name);
    return 2;
  }
  if (argc > codec_arg + 1 && argc != codec_arg + 3) {
    fprintf(stderr, "error: WIDTH and HEIGHT must be specified together\n");
    return 2;
  }
  uint32_t W = argc > codec_arg + 2 ? (uint32_t)atoi(argv[codec_arg + 1]) : 256;
  uint32_t H = argc > codec_arg + 2 ? (uint32_t)atoi(argv[codec_arg + 2]) : 256;
  if (W < 96 || H < 96 || W > 4096 || H > 4096 || (W & 1) || (H & 1)) {
    fprintf(stderr, "error: invalid encoder dimensions %ux%u (even values 96..4096 required)\n", W, H);
    return 2;
  }
  uint32_t codec = !strcmp(codec_name, "h264") ? MEDIA_PIXFMT_H264 : MEDIA_PIXFMT_HEVC;
  const br_encoder_backend *backend;
  if (helper) {
    // The spawned production helper owns its Binder pool. Do not start
    // another pool in this test harness or mask the helper's bootstrap.
    backend = br_encoder_backend_helper(helper);
    printf("encctl: production helper route: %s\n", helper);
  } else {
    // Must precede any MediaCodec, CCodec2 or Binder service lookup.
    if (maybe_start_binder_pool()) return 1;
    backend = br_encoder_backend_ndk();
  }

  static guest g;
  uint64_t pool_size = 32ull << 20;
  uint8_t *pool = malloc(pool_size);
  if (!pool) { fprintf(stderr, "error: no pool\n"); return 1; }
  xh_virtio *dev = br_encoder_create(0x0a000000, 40, backend, pool, (uint64_t)(uintptr_t)pool, pool_size);
  if (!dev) { fprintf(stderr, "error: the encoder device could not be made\n"); return 1; }
  guest_up(&g, dev);
  for (unsigned i = 0; i < EVENT_BUFS; i++) { void *b = event_store[i]; uint32_t l = MEDIA_EVENT_BYTES; bool w = true; post(&g, MEDIA_QUEUE_EVENT, &b, &l, &w, 1); }

  uint32_t open_cmd[2] = { MEDIA_CMD_OPEN, 0 }; uint8_t open_resp[16];
  if (command(&g, open_cmd, sizeof open_cmd, NULL, 0, open_resp, sizeof open_resp, NULL, 0)) { fprintf(stderr, "error: OPEN\n"); return 1; }
  uint32_t sess; memcpy(&sess, open_resp + 8, 4);

  struct media_v4l2_format f; memset(&f, 0, sizeof f);
  f.type = MEDIA_BUF_TYPE_VIDEO_CAPTURE_MPLANE; f.width = W; f.height = H; f.pixelformat = codec; f.num_planes = 1;
  if (ioc(&g, sess, MEDIA_VIDIOC_S_FMT, &f, sizeof f)) { fprintf(stderr, "error: S_FMT capture\n"); return 1; }
  memset(&f, 0, sizeof f);
  f.type = MEDIA_BUF_TYPE_VIDEO_OUTPUT_MPLANE; f.width = W; f.height = H; f.pixelformat = MEDIA_PIXFMT_NV12; f.num_planes = 1;
  if (ioc(&g, sess, MEDIA_VIDIOC_S_FMT, &f, sizeof f)) { fprintf(stderr, "error: S_FMT output\n"); return 1; }

  uint32_t ro[5] = { 2, MEDIA_BUF_TYPE_VIDEO_OUTPUT_MPLANE, MEDIA_MEMORY_MMAP, 0, 0 };
  ENCCTL_IO_CHECK(ioc(&g, sess, MEDIA_VIDIOC_REQBUFS, ro, sizeof ro), "REQBUFS OUTPUT");
  struct media_v4l2_buffer qb; memset(&qb, 0, sizeof qb); qb.type = MEDIA_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
  ENCCTL_IO_CHECK(ioc(&g, sess, MEDIA_VIDIOC_QUERYBUF, &qb, sizeof qb), "QUERYBUF OUTPUT");
  uint8_t *out_buf = (uint8_t *)(uintptr_t)mmap_buf(&g, sess, qb.plane.m);
  uint32_t rc[5] = { 4, MEDIA_BUF_TYPE_VIDEO_CAPTURE_MPLANE, MEDIA_MEMORY_MMAP, 0, 0 };
  ENCCTL_IO_CHECK(ioc(&g, sess, MEDIA_VIDIOC_REQBUFS, rc, sizeof rc), "REQBUFS CAPTURE");
  for (unsigned i = 0; i < 4; i++) {
    struct media_v4l2_buffer cb; memset(&cb, 0, sizeof cb); cb.type = MEDIA_BUF_TYPE_VIDEO_CAPTURE_MPLANE; cb.index = i;
    ENCCTL_IO_CHECK(ioc(&g, sess, MEDIA_VIDIOC_QUERYBUF, &cb, sizeof cb), "QUERYBUF CAPTURE");
    if (!mmap_buf(&g, sess, cb.plane.m)) { fprintf(stderr, "error: MMAP CAPTURE index %u\n", i); return 1; }
    ENCCTL_IO_CHECK(ioc(&g, sess, MEDIA_VIDIOC_QBUF, &cb, sizeof cb), "QBUF CAPTURE");
  }
  uint32_t t = MEDIA_BUF_TYPE_VIDEO_OUTPUT_MPLANE; uint8_t rr[8];
  ENCCTL_IO_CHECK(command(&g, (uint32_t[]){ MEDIA_CMD_IOCTL, 0, sess, MEDIA_VIDIOC_STREAMON }, 16, &t, 4, rr, 8, NULL, 0), "STREAMON OUTPUT");
  t = MEDIA_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
  ENCCTL_IO_CHECK(command(&g, (uint32_t[]){ MEDIA_CMD_IOCTL, 0, sess, MEDIA_VIDIOC_STREAMON }, 16, &t, 4, rr, 8, NULL, 0), "STREAMON CAPTURE");

  if (!out_buf) { fprintf(stderr, "error: no output buffer\n"); return 1; }
  uint32_t frame = W * H * 3 / 2;
  for (uint32_t y = 0; y < H; y++) for (uint32_t x = 0; x < W; x++) out_buf[y * W + x] = (uint8_t)((x ^ y) + y);
  memset(out_buf + W * H, 128, W * H / 2);                     // grey chroma: a visible gradient
  struct media_v4l2_buffer qo; memset(&qo, 0, sizeof qo);
  qo.type = MEDIA_BUF_TYPE_VIDEO_OUTPUT_MPLANE; qo.index = 0; qo.sec = 1; qo.plane.bytesused = frame;
  ENCCTL_IO_CHECK(ioc(&g, sess, MEDIA_VIDIOC_QBUF, &qo, sizeof qo), "QBUF OUTPUT (feed)");
  br_encoder_stats after_feed;
  br_encoder_get_stats(dev, &after_feed);
  printf("encctl: after feed: sessions %llu, frames_in %llu, frames_out %llu, errors %llu\n",
         (unsigned long long)after_feed.sessions, (unsigned long long)after_feed.frames_in,
         (unsigned long long)after_feed.frames_out, (unsigned long long)after_feed.errors);

  // Keep the exact original one-frame-then-drain order for a diagnostic
  // comparison; the host fake test drains *after* coded CAPTURE arrives.
  uint32_t enc[10] = { MEDIA_ENC_CMD_STOP };
  ENCCTL_IO_CHECK(ioc(&g, sess, MEDIA_VIDIOC_ENCODER_CMD, enc, sizeof enc), "ENCODER_CMD STOP");

  uint32_t total = 0, aus = 0; bool key = false, eos = false, idr = false, failed = false;
  for (unsigned e = 0; e < 16 && !eos; e++) {
    uint32_t kind; uint8_t *ev = wait_event(&g, &kind);
    if (!ev) { printf("encctl: event timeout (5 s without a completed event)\n"); break; }
    uint32_t event_session;
    memcpy(&event_session, ev + 4, sizeof event_session);
    if (event_session != sess) { printf("encctl: event from unexpected session %u (wanted %u)\n", event_session, sess); continue; }
    if (kind == MEDIA_EVT_DQBUF) {
      struct media_v4l2_buffer b; memcpy(&b, ev + 8, sizeof b);
      printf("encctl: DQBUF %s index %u, %u bytes, flags %#x\n",
             b.type == MEDIA_BUF_TYPE_VIDEO_CAPTURE_MPLANE ? "CAPTURE" :
             b.type == MEDIA_BUF_TYPE_VIDEO_OUTPUT_MPLANE ? "OUTPUT" : "UNKNOWN",
             b.index, b.plane.bytesused, b.flags);
      if (b.type == MEDIA_BUF_TYPE_VIDEO_CAPTURE_MPLANE && b.plane.bytesused) {
        total += b.plane.bytesused; aus++;
        if (b.flags & MEDIA_BUF_FLAG_KEYFRAME) key = true;
        struct media_v4l2_buffer cb; memset(&cb, 0, sizeof cb); cb.type = MEDIA_BUF_TYPE_VIDEO_CAPTURE_MPLANE; cb.index = b.index;
        ENCCTL_IO_CHECK(ioc(&g, sess, MEDIA_VIDIOC_QUERYBUF, &cb, sizeof cb), "QUERYBUF CODED");
        uint8_t *nal = (uint8_t *)(uintptr_t)mmap_buf(&g, sess, cb.plane.m);
        if (nal && b.plane.bytesused >= 6) {
          unsigned first_type = codec == MEDIA_PIXFMT_HEVC ? (nal[4] >> 1) & 0x3f : nal[4] & 0x1f;
          printf("encctl: AU %u bytes, first NAL type %u%s\n", b.plane.bytesused, first_type, (b.flags & MEDIA_BUF_FLAG_KEYFRAME) ? " (keyframe)" : "");
          // Codec-config output itself carries the KEYFRAME bit in the NDK
          // backend. Do not report success without a *real IDR* NAL type.
          // Scan all Annex-B start codes: host stub packs parameter sets
          // and IDR together, while Qualcomm emits them as separate AUs.
          for (uint32_t at = 0; at + 5 < b.plane.bytesused; at++) {
            if (nal[at] || nal[at + 1]) continue;
            uint32_t header = 0;
            if (nal[at + 2] == 1) header = at + 3;
            else if (nal[at + 2] == 0 && nal[at + 3] == 1) header = at + 4;
            if (!header || header + (codec == MEDIA_PIXFMT_HEVC ? 1u : 0u) >= b.plane.bytesused) continue;
            unsigned type = codec == MEDIA_PIXFMT_HEVC ? (nal[header] >> 1) & 0x3f : nal[header] & 0x1f;
            if (codec == MEDIA_PIXFMT_HEVC ? (type == 19 || type == 20) : type == 5) idr = true;
          }
        }
        if (b.flags & MEDIA_BUF_FLAG_LAST) eos = true;
      }
    } else if (kind == MEDIA_EVT_ERROR) {
      uint32_t err;
      memcpy(&err, ev + 8, sizeof err);
      fprintf(stderr, "error: virtio-media session %u backend ERROR errno %u\n", sess, err);
      failed = true;
      break;
    } else if (kind == MEDIA_EVT_EVENT) {
      uint32_t what;
      memcpy(&what, ev + 8, sizeof what);
      printf("encctl: event type %u (EOS expected %u)\n", what, (unsigned)MEDIA_EVENT_EOS);
      if (what == MEDIA_EVENT_EOS) eos = true;
    } else {
      printf("encctl: unrecognized event kind %u\n", kind);
    }
  }

  br_encoder_stats st; br_encoder_get_stats(dev, &st);
  printf("encctl: stats: sessions %llu, frames_in %llu, frames_out %llu, errors %llu\n",
         (unsigned long long)st.sessions, (unsigned long long)st.frames_in,
         (unsigned long long)st.frames_out, (unsigned long long)st.errors);
  if (aus && key && idr && eos && total && !failed && !st.errors) { printf("encctl: %s %ux%u: %u access unit(s), %u bytes, IDR+EOS present; ok\n", codec_name, W, H, aus, total); return 0; }
  fprintf(stderr, "error: %s %ux%u: %u access units, %u bytes, key %d, idr %d, eos %d, %llu errors\n", codec_name, W, H, aus, total, key, idr, eos, (unsigned long long)st.errors);
  return 1;
}
