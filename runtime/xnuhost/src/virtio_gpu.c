// SPDX-License-Identifier: MIT
// virtio-gpu device (VirtIO 1.2, 5.7).
// 2D: the scanout the guest's display driver presents frames on (UniXNU-droidvm's DroidVMVirtioGpuDisplay.cpp under
// IOMobileFramebufferLegacy); the first frame says the guest is up.
// 3D (xh_virtio_gpu_create_3d): crosvm's DRM native context as UniXNU-droidvm's DroidVMVirtioGpu3D.cpp drives it --
// capset 6, CTX_CREATE, RESOURCE_CREATE_BLOB (HOST3D for a context's shmem, HOST3D_GUEST over guest pages),
// MAP_BLOB answered with MAP_INFO_POOL and the offset in /arm-io/virtio-gpu drm-host-pool, SUBMIT_3D with per-ring
// fences (a fenced command is returned when its fence retires). The renderer is behind gpu3d.h (drm2kgsl on KGSL).
#include "xnuhost.h"
#include "xnuhost/frame_trace.h"
#include "gpu_fence_perf.h"
#include "gpu3d.h"
#include <errno.h>
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/eventfd.h>

enum {
  CMD_GET_DISPLAY_INFO = 0x100, CMD_RESOURCE_CREATE_2D, CMD_RESOURCE_UNREF, CMD_SET_SCANOUT, CMD_RESOURCE_FLUSH,
  CMD_TRANSFER_TO_HOST_2D, CMD_RESOURCE_ATTACH_BACKING, CMD_RESOURCE_DETACH_BACKING,
  CMD_GET_CAPSET_INFO = 0x108, CMD_GET_CAPSET = 0x109, CMD_RESOURCE_CREATE_BLOB = 0x10c, CMD_SET_SCANOUT_BLOB = 0x10d,
  CMD_CTX_CREATE = 0x200, CMD_CTX_DESTROY, CMD_CTX_ATTACH_RESOURCE, CMD_CTX_DETACH_RESOURCE,
  CMD_SUBMIT_3D = 0x207, CMD_RESOURCE_MAP_BLOB, CMD_RESOURCE_UNMAP_BLOB,
  RESP_OK_NODATA = 0x1100, RESP_OK_DISPLAY_INFO, RESP_OK_CAPSET_INFO, RESP_OK_CAPSET, RESP_OK_MAP_INFO = 0x1106,
  RESP_ERR_UNSPEC = 0x1200, RESP_ERR_OUT_OF_MEMORY, RESP_ERR_INVALID_SCANOUT_ID, RESP_ERR_INVALID_RESOURCE_ID,
  RESP_ERR_INVALID_CONTEXT_ID, RESP_ERR_INVALID_PARAMETER,
};
enum { FMT_BGRA = 1, FMT_BGRX = 2, FMT_ARGB = 3, FMT_XRGB = 4, FMT_RGBA = 67, FMT_XBGR = 68, FMT_ABGR = 121, FMT_RGBX = 134 };
// Half floats (R,G,B,A, linear extended sRGB): xnuhost's own code, include/xnuhost/pixels.h.
#define FMT_RGBA16F XH_VIRTIO_GPU_FORMAT_RGBA16F

static bool format_known(uint32_t f)
{
  return f == FMT_BGRA || f == FMT_BGRX || f == FMT_ARGB || f == FMT_XRGB || f == FMT_RGBA || f == FMT_XBGR || f == FMT_ABGR ||
         f == FMT_RGBX || f == FMT_RGBA16F;
}

// Bytes a pixel of a scanout format takes in guest memory.
static unsigned format_bpp(uint32_t f) { return f == FMT_RGBA16F ? 8u : 4u; }

// The display's pixels (display-format=): what a resource's host copy and a blob's flush are written in.
static unsigned display_format(void)
{
  xh_display *d = xh_display_get();
  return d && d->format ? d->format : XH_PIXELS_BGRX8;      // 0: a display made before formats (B,G,R,X)
}

typedef struct { uint32_t type, flags; uint64_t fence; uint32_t ctx; uint8_t ring, pad[3]; } gpu_hdr;
typedef struct { uint32_t x, y, w, h; } gpu_rect;
typedef xh_gpu_entry gpu_entry;
enum { FLAG_FENCE = 1, FLAG_RING_IDX = 2, MAP_INFO_POOL = 1u << 31 };
enum { F_VIRGL = 1u << 0, F_RESOURCE_BLOB = 1u << 3, F_CONTEXT_INIT = 1u << 4, F_CREATE_GUEST_HANDLE = 1u << 6 };

#define MAX_RES 64
#define MAX_BACKING 16384              // as MAX_BLOB_ENTRIES: a 2D surface of scattered 4 KiB pages (1440x3120 has 4388)
typedef struct {
  uint32_t id, format, width, height;
  uint64_t serial;
  uint8_t *pixels;                 // host copy, in the display's pixels (dformat: B,G,R,X 8-bit or R,G,B,A half floats)
  unsigned dformat, dbpp;
  gpu_entry *backing;
  unsigned nbacking;
} resource;

#define MAX_CTX 128
#define MAX_BLOB_ENTRIES 16384         // DroidVMVirtioGpu.h MaxEntries
#define BLOB_SLOTS (1u << 15)          // open addressing, linear probing: blob resource id -> blob
#define WORKER_IOV 256

// A blob resource. Guest blobs (GUEST: the display's surfaces; HOST3D_GUEST: a context's BOs) keep the guest's
// segments, so a blob can be a scanout; HOST3D blobs (a context's shmem) are the renderer's alone.
typedef struct {
  uint32_t id, ctx, mem;
  uint64_t size, serial;
  gpu_entry *entries;
  unsigned nentries;
  bool scanout_compacted;          // CPU scanout only, not the backend's import list
} blob;

// A fenced command whose chain goes back to the guest when its context's ring passes the fence.
typedef struct pending {
  struct pending *next;
  uint16_t head;
  uint32_t written, ctx, ring;
  uint64_t fence, gen;
  uint64_t fence_started_ns;           // opt-in: from submit_fence to backend callback
  bool fence_fast;                     // xnu:backboardd at enqueue, never inferred at retirement
} pending;

typedef struct {
  unsigned width, height;
  resource res[MAX_RES];
  uint32_t scanout_resource;
  bool first_frame, trace, fence_trace;
  uint64_t resource_serial;
  struct xh_fence_perf fence_perf;     // guarded by pl, separate from actual scanout/post timings
  uint64_t fence_report_since_ns;      // guarded by pl; 5-second monotonic windows
  // All command-stage metrics are owned by cmd (the two control lanes).
  struct xh_fence_hist queue_wait[2], queue_service[2], submit_service, blob_service, flush_service, dependency_wait;
  uint64_t queue_report_since_ns, queue_invalid;
  // 3D. Both lanes change the resource tables under cmd. pl guards pending fences and worker bookkeeping.
  // gen changes under the device lock; state_gen is the generation of the tables under cmd.
  xh_gpu3d *b;
  xh_virtio *dev;
  uint32_t ctx[MAX_CTX];               // live context ids
  bool ctx_fast[MAX_CTX];              // that context's commands are the fast lane's (the render server's: "xnu:backboardd")
  blob *blobs;                         // BLOB_SLOTS of them; id 0 = free
  unsigned nblobs;
  // The blobs the host holds (2026-11-13): bytes of the live ones, made and unref'd since the start, and the last line's
  // figures (blob_note). Set where the worker changes the table.
  uint64_t blob_bytes, blobs_made, blobs_unref, blob_note_us, noted_made, noted_unref;
  struct { uint32_t width, height, format, stride, offset; } scan;      // the scanout when it is a blob
  pthread_mutex_t pl;
  pthread_cond_t idle;
  pending *fences;
  uint64_t gen, state_gen, kicks, served;
  // Protected by pl, except the atomic fast-path read of gate_closed.
  // Front activity includes generation reconciliation and an entire popped
  // chain (including slow-lane handoff/retry). A parked front consumes none.
  bool gate_closed, front_active, gate_invalid, gate_combined;
  uint64_t gate_ticket, reset_serial, reset_handled;
  // Serializes combined operations, never taken by command workers or
  // retire callbacks. Device lock -> pl for atomic reset/resume ordering.
  pthread_mutex_t quiesce_lock;
  uint64_t backend_ticket;
  bool quiesce_verified;
  int quiesce_fault;
  unsigned retiring_callbacks;
  pthread_cond_t gate_cv;
  int wake;                            // eventfd: the control queue was kicked (written from the trap handler)
  // Two lanes. The queue's thread serves the render server's contexts and every command of no context (the display,
  // the 2D commands) at once, and hands every other context's commands, in their order, to the slow lane's thread.
  // An app that makes 100 blobs at its launch (1-30 ms each on the phone: udmabufs, KGSL's import and bind) then no
  // longer holds back the render server's next frame and the display's flush behind them. `cmd` makes the two take
  // turns at the state above and the renderer (a frame waits for one blob at most, not for all of them).
  pthread_mutex_t cmd;
  pthread_cond_t slow_cv;
  struct slow_job *slow_head, **slow_tail;
  uint64_t slow_queued, slow_done;
} gpu_state;

typedef struct slow_job {
  struct slow_job *next;
  uint16_t head;
  unsigned n;
  uint64_t gen, queued_ns;
  xh_viov iov[];
} slow_job;

static resource *find(gpu_state *g, uint32_t id)
{
  for (unsigned i = 0; id && i < MAX_RES; i++) if (g->res[i].id == id) return &g->res[i];
  return NULL;
}

static void release(resource *r)
{
  free(r->pixels);
  free(r->backing);
  memset(r, 0, sizeof *r);
}

// Byte order of a format's pixel in guest memory -> B,G,R,X.
static void convert(uint8_t *to, const uint8_t *from, uint32_t format, size_t pixels)
{
  switch (format) {
  case FMT_BGRA: case FMT_BGRX: memcpy(to, from, pixels * 4); break;
  case FMT_RGBA: case FMT_RGBX:
    for (size_t i = 0; i < pixels; i++, to += 4, from += 4) { to[0] = from[2]; to[1] = from[1]; to[2] = from[0]; to[3] = from[3]; }
    break;
  case FMT_ARGB: case FMT_XRGB:
    for (size_t i = 0; i < pixels; i++, to += 4, from += 4) { to[0] = from[3]; to[1] = from[2]; to[2] = from[1]; to[3] = from[0]; }
    break;
  default:                         // ABGR, XBGR
    for (size_t i = 0; i < pixels; i++, to += 4, from += 4) { to[0] = from[1]; to[1] = from[2]; to[2] = from[3]; to[3] = from[0]; }
  }
}

// A row of a scanout format's pixels into the display's (display_format()). Half floats into half floats are copied;
// into 8 bits they are encoded to sRGB and clamped (what is outside sRGB and above white is lost, as in the guest's
// own CPU conversion); 8-bit pixels into half floats are decoded to linear light.
static void convert_to(uint8_t *to, unsigned dformat, const uint8_t *from, uint32_t format, size_t pixels)
{
  if (format == FMT_RGBA16F) {
    if (dformat == XH_PIXELS_RGBA16F) memcpy(to, from, pixels * 8);
    else xh_pixels_rgba16f_to_8(to, from, pixels, 0);
    return;
  }
  if (dformat != XH_PIXELS_RGBA16F) { convert(to, from, format, pixels); return; }
  if (format == FMT_BGRA || format == FMT_BGRX) { xh_pixels_bgrx8_to_rgba16f(to, from, pixels); return; }
  uint8_t row[4 * 256];                                // another byte order: through B,G,R,X, 256 pixels at a time
  for (size_t done = 0; done < pixels;) {
    size_t n = pixels - done < 256 ? pixels - done : 256;
    convert(row, from + done * 4, format, n);
    xh_pixels_bgrx8_to_rgba16f(to + done * 8, row, n);
    done += n;
  }
}

// Copies `length` bytes at linear `offset` of a resource's backing into `out`.
static bool backing_read(const resource *r, uint64_t offset, uint8_t *out, uint64_t length)
{
  for (unsigned i = 0; i < r->nbacking && length; i++) {
    uint64_t size = r->backing[i].length;
    if (offset >= size) { offset -= size; continue; }
    uint64_t n = size - offset < length ? size - offset : length;
    const uint8_t *p = xh_virtio_translate(r->backing[i].addr + offset, n);
    if (!p) return false;
    memcpy(out, p, n);
    out += n; length -= n; offset = 0;
  }
  return length == 0;
}

// The guest's display driver also scans out the boot framebuffer itself (DroidVMVirtioGpuDisplay.cpp's `boot`
// resource: the kernel console until the compositor's first frame, and later whenever a blank or CPU-copied frame was
// drawn there). That picture is shown like any other, but it is the console's. A frame of a surface of the guest's
// own goes to main.c's ready rule (ready.c) with whether the display's frame now shows anything: backboardd's first
// frames are black, and the guest is ready (session/ready) at the first that is not (2026-11-15). Called before the
// frame is posted to the display helper, so that session/ready is there when the helper sees the frame.
// `ready` (g->first_frame) stops the calls once the rule has said yes.
static void frame_shown(gpu_state *g, const gpu_entry *entries, unsigned n)
{
  if (g->first_frame || (n && g_info.video[0] && entries[0].addr == g_info.video[0])) return;
  xh_display *d = xh_display_get();
  bool lit = d && xh_pixels_lit(d->pixels, d->stride, d->width, d->height, d->format);
  if (xh_guest_frame(lit)) g->first_frame = true;
}

static bool rect_ok(const gpu_rect *r, uint32_t w, uint32_t h)
{
  return r->w && r->h && r->x <= w && r->y <= h && r->w <= w - r->x && r->h <= h - r->y;
}

// ---- 3D --------------------------------------------------------------------------------------------------------------
static unsigned blob_hash(uint32_t id) { return (id * 2654435761u) >> 17 & (BLOB_SLOTS - 1); }

static blob *blob_find(gpu_state *g, uint32_t id)
{
  if (!id) return NULL;
  for (unsigned i = blob_hash(id); g->blobs[i].id; i = (i + 1) & (BLOB_SLOTS - 1)) if (g->blobs[i].id == id) return &g->blobs[i];
  return NULL;
}

static blob *blob_add(gpu_state *g, uint32_t id)
{
  if (g->nblobs >= BLOB_SLOTS / 4 * 3) return NULL;
  unsigned i = blob_hash(id);
  while (g->blobs[i].id) i = (i + 1) & (BLOB_SLOTS - 1);
  g->blobs[i] = (blob){ .id = id };
  g->nblobs++;
  return &g->blobs[i];
}

static void blob_del(gpu_state *g, blob *b)
{
  unsigned i = (unsigned)(b - g->blobs), j = i;
  free(b->entries);
  g->nblobs--;
  g->blob_bytes -= b->size;
  for (;;) {                                         // backward shift: the probe chains stay whole
    g->blobs[i].id = 0;
    for (;;) {
      j = (j + 1) & (BLOB_SLOTS - 1);
      if (!g->blobs[j].id) return;
      unsigned k = blob_hash(g->blobs[j].id);
      if (i <= j ? (i < k && k <= j) : (i < k || k <= j)) continue;
      break;
    }
    g->blobs[i] = g->blobs[j];
    i = j;
  }
}

static uint32_t *ctx_find(gpu_state *g, uint32_t id)
{
  for (unsigned i = 0; id && i < MAX_CTX; i++) if (g->ctx[i] == id) return &g->ctx[i];
  return NULL;
}


// The copy of each scanout flush, one log line per 10 s while frames come: `display: 10 s: flushes N, copy mean X us
// max Y us (Z MiB)`. The device's one thread does it, so the guest's next commands (a frame's submissions, its blobs)
// wait behind it.
// This clock is only read for scanout timing in explicitly opted-in trace mode.
static uint64_t scanout_now_ns(void)
{
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t)) return 0;
  return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static uint64_t flush_now_us(void)
{
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (uint64_t)t.tv_sec * 1000000u + (uint64_t)t.tv_nsec / 1000u;
}

static void flush_note(uint64_t took, uint64_t bytes)
{
  static uint64_t since, n, sum, max, total;
  uint64_t now = flush_now_us();
  if (!since) since = now;
  n++; sum += took; total += bytes; if (took > max) max = took;
  if (now - since >= 10000000u) {
    LOGI("display: %llu s: flushes %llu, copy mean %llu us max %llu us (%llu MiB)", (unsigned long long)((now - since) / 1000000u),
         (unsigned long long)n, (unsigned long long)(sum / n), (unsigned long long)max, (unsigned long long)(total >> 20));
    since = now; n = sum = max = total = 0;
  }
}

// Compact only the CPU scanout view, once a blob actually becomes the
// scanout. The backend has already imported the original list. Logical
// byte order/length must not change; validate the whole merged RAM span
// and retain distinct runs when it cannot be translated as one.
static void compact_scanout(blob *b)
{
  if (b->scanout_compacted) return;
  unsigned out = 0;
  for (unsigned i = 0; i < b->nentries; i++) {
    gpu_entry e = b->entries[i];
    if (out) {
      gpu_entry *prev = &b->entries[out - 1];
      uint64_t length = (uint64_t)prev->length + e.length;
      if (length <= UINT32_MAX && prev->addr <= UINT64_MAX - prev->length &&
          prev->addr + prev->length == e.addr &&
          xh_virtio_translate(prev->addr, length)) {
        prev->length = (uint32_t)length;
        continue;
      }
    }
    b->entries[out++] = e;
  }
  b->nentries = out;
  b->scanout_compacted = true;
}

// RESOURCE_FLUSH of a blob: when it is the scanout (SET_SCANOUT_BLOB), its rows go from the guest's pages to the display.
static uint32_t flush_blob(gpu_state *g, const blob *b, const gpu_rect *rect)
{
  xh_display *d = xh_display_get();
  if (b->id != g->scanout_resource || !g->scan.width || !d || !d->pixels) return RESP_OK_NODATA;
  if (!rect_ok(rect, g->scan.width, g->scan.height)) return RESP_ERR_INVALID_PARAMETER;
  uint32_t w = rect->x < d->width ? (rect->w < d->width - rect->x ? rect->w : d->width - rect->x) : 0;
  uint32_t hgt = rect->y < d->height ? (rect->h < d->height - rect->y ? rect->h : d->height - rect->y) : 0;
  // Rows straight from the guest's pages into the display's buffer, the blob's segments walked once for the whole
  // rectangle: rows lie at rising offsets. (Each row used to be read into a buffer of its own, the segment list searched
  // from its start for every row: 3120 rows of a 1440x3120 frame over about 1100 segments of 16 KiB pages.)
  // A half-float scanout is 8 bytes a pixel in the guest; the display's pixels are d->format's (display-format=).
  uint32_t status = RESP_OK_NODATA;
  const bool trace_scanout = xh_display_trace_enabled() && w && hgt;
  const uint64_t scanout_start_ns = trace_scanout ? scanout_now_ns() : 0;
  uint64_t t0 = flush_now_us();
  unsigned seg = 0, gbpp = format_bpp(g->scan.format), dformat = display_format(), dbpp = xh_pixels_bpp(dformat);
  uint64_t seg_start = 0;                            // the blob offset at which entries[seg] begins
  // A same-layout, full-width unpadded rectangle is one logical span,
  // even when its backing consists of many noncontiguous guest pages.
  // Keep the segment walker and pixel-carry path for all other layouts.
  bool raw = (g->scan.format == FMT_RGBA16F && dformat == XH_PIXELS_RGBA16F) ||
             ((g->scan.format == FMT_BGRX || g->scan.format == FMT_BGRA) && dformat == XH_PIXELS_BGRX8);
  bool linear = raw && rect->x == 0 && w == g->scan.width &&
                g->scan.stride == (uint64_t)w * gbpp && d->stride == (uint64_t)w * dbpp;
  for (uint32_t y = 0; y < (linear ? (hgt != 0) : hgt) && w && status == RESP_OK_NODATA; y++) {
    uint64_t at = g->scan.offset + (uint64_t)(rect->y + y) * g->scan.stride + (uint64_t)rect->x * gbpp;
    uint64_t left = (uint64_t)w * gbpp * (linear ? hgt : 1u);
    uint8_t *to = d->pixels + (size_t)(rect->y + y) * d->stride + (size_t)rect->x * dbpp;
    uint8_t carry[8];                                // a pixel split between two segments
    unsigned have = 0;
    if (at < seg_start) { seg = 0; seg_start = 0; }  // not expected: rows only rise
    while (left) {
      while (seg < b->nentries && at >= seg_start + b->entries[seg].length) seg_start += b->entries[seg++].length;
      if (seg >= b->nentries) { status = RESP_ERR_INVALID_PARAMETER; break; }
      uint64_t in = at - seg_start, n = b->entries[seg].length - in < left ? b->entries[seg].length - in : left;
      const uint8_t *from = xh_virtio_translate(b->entries[seg].addr + in, n);
      if (!from || (n & 3)) { status = RESP_ERR_INVALID_PARAMETER; break; }
      // Same-layout spans need no pixel reassembly, even for padded
      // or partial-width rows. A split half-float pixel is just bytes
      // in the destination's identical layout. Keep per-segment
      // translation and the alignment/range checks above.
      if (raw) {
        memcpy(to, from, (size_t)n);
        to += n; at += n; left -= n;
        continue;
      }
      uint64_t off = 0;
      if (have) {
        off = gbpp - have < n ? gbpp - have : n;
        memcpy(carry + have, from, off);
        have += (unsigned)off;
        if (have == gbpp) { convert_to(to, dformat, carry, g->scan.format, 1); to += dbpp; have = 0; }
      }
      uint64_t whole = (n - off) / gbpp, rest = n - off - whole * gbpp;
      convert_to(to, dformat, from + off, g->scan.format, (size_t)whole);
      to += whole * dbpp;
      if (rest) { memcpy(carry, from + off + whole * gbpp, rest); have = (unsigned)rest; }
      at += n; left -= n;
    }
  }
  const uint64_t scanout_copied_ns = trace_scanout ? scanout_now_ns() : 0;
  flush_note(flush_now_us() - t0, (uint64_t)w * hgt * gbpp);
  if (status == RESP_OK_NODATA && w && hgt) {
    frame_shown(g, b->entries, b->nentries);     // first: session/ready before the helper is told of the frame
    const struct xh_frame_scanout sample = {
      .start_ns = scanout_start_ns, .copied_ns = scanout_copied_ns,
      .kind = XH_FRAME_SCANOUT_BLOB, .resource_id = b->id,
      .queue_generation = g->state_gen, .resource_generation = b->serial,
      .owner_context = b->ctx   // 0 for GUEST display blob, not the renderer that last wrote it
    };
    xh_display_flush_scanout(rect->x, rect->y, w, hgt, trace_scanout ? &sample : NULL);
  }
  return status;
}

// Publish mergeable completions in their existing list order. Holding the
// device lock covers the generation check and all publications, not a GPU wait.
// Individual (unfenced) replies use a stack record and do not allocate.
static unsigned push_pending(gpu_state *g, const pending *list)
{
  xh_virtio_lock(g->dev);
  xh_virtio_used items[16];
  unsigned n = 0, published = 0;
  for (const pending *p = list; p; p = p->next) {
    bool current = p->gen == g->gen;
    if (g->trace)
      LOGI("gpu trace: %s queue_gen=%llu head=%u context=%u ring=%u fence=%llu bytes=%u",
           current ? "complete" : "discard", (unsigned long long)p->gen, p->head, p->ctx, p->ring,
           (unsigned long long)p->fence, p->written);
    if (!current) continue;
    items[n++] = (xh_virtio_used){ .head = p->head, .written = p->written };
    if (n == sizeof items / sizeof items[0]) {
      published += xh_virtio_push_batch(g->dev, 0, items, n);
      n = 0;
    }
  }
  if (n) published += xh_virtio_push_batch(g->dev, 0, items, n);
  xh_virtio_unlock(g->dev);
  return published;
}

// A callback can retire many mergeable fences on a (context, ring).
// This is a VirtIO wait report, not a Metal/KGSL frame timing or panel FPS.
static void gpu_fence_perf_report(const struct xh_fence_perf *p, uint64_t now_ns, uint64_t window_ns)
{
  if (!p->fast.count && !p->other.count && !p->rejected && !p->canceled && !p->invalid_time) return;
  LOGI("gpu-fence-trace: mono_ms=%llu window_ms=%llu "
       "render_wait_n=%llu mean_us=%llu p95_le_us=%llu p99_le_us=%llu max_us=%llu "
       "other_wait_n=%llu mean_us=%llu p95_le_us=%llu p99_le_us=%llu max_us=%llu "
       "released_on_refusal=%llu canceled_on_destroy_or_reset=%llu invalid_clocks=%llu "
       "used_publish_n=%llu used_publish_mean_us=%llu used_publish_p95_le_us=%llu used_publish_p99_le_us=%llu used_publish_max_us=%llu "
       "used_published_chains=%llu used_unpublished_chains=%llu used_publish_invalid_clocks=%llu "
       "origin=virtio_submit_fence_to_backend_callback_not_GPU_execution_or_panel_present",
       (unsigned long long)(now_ns / UINT64_C(1000000)),
       (unsigned long long)(window_ns / UINT64_C(1000000)),
       (unsigned long long)p->fast.count,
       (unsigned long long)(p->fast.count ? p->fast.sum_us / p->fast.count : 0),
       (unsigned long long)xh_fence_perf_quantile_le_us(&p->fast, 95),
       (unsigned long long)xh_fence_perf_quantile_le_us(&p->fast, 99),
       (unsigned long long)p->fast.max_us,
       (unsigned long long)p->other.count,
       (unsigned long long)(p->other.count ? p->other.sum_us / p->other.count : 0),
       (unsigned long long)xh_fence_perf_quantile_le_us(&p->other, 95),
       (unsigned long long)xh_fence_perf_quantile_le_us(&p->other, 99),
       (unsigned long long)p->other.max_us,
       (unsigned long long)p->rejected,
       (unsigned long long)p->canceled,
       (unsigned long long)p->invalid_time,
       (unsigned long long)p->publish.count,
       (unsigned long long)(p->publish.count ? p->publish.sum_us / p->publish.count : 0),
       (unsigned long long)xh_fence_perf_quantile_le_us(&p->publish, 95),
       (unsigned long long)xh_fence_perf_quantile_le_us(&p->publish, 99),
       (unsigned long long)p->publish.max_us,
       (unsigned long long)p->published_chains,
       (unsigned long long)p->unpublished_chains,
       (unsigned long long)p->invalid_publish_time);
}

// Takes only matching pending commands off the list: a retirement of another
// (context, ring) cannot be attributed here. Context teardown and a refused
// fence release commands but are NOT actual GPU backend completions.
static void retire(gpu_state *g, uint32_t ctx, int64_t ring, uint64_t fence,
                   enum xh_fence_outcome outcome, uint64_t rejected_gen, uint16_t rejected_head)
{
  pending *done = NULL, **tail = &done;
  struct xh_fence_perf report;        // assigned only at the reporting boundary; no default-path zeroing
  uint64_t window_ns = 0;
  bool report_ready = false;
  const uint64_t callback_ns = g->fence_trace && outcome == XH_FENCE_COMPLETED ? scanout_now_ns() : 0;
  pthread_mutex_lock(&g->pl);
  g->retiring_callbacks++;
  for (pending **link = &g->fences; *link;) {
    pending *p = *link;
    // A refused fence is NOT a retirement of every preceding fence.
    bool match = p->ctx == ctx && (ring < 0 || (p->ring == (uint32_t)ring && p->fence <= fence));
    if (outcome == XH_FENCE_REJECTED)
      match = match && p->gen == rejected_gen && p->head == rejected_head && p->fence == fence;
    if (match) {
      *link = p->next; p->next = NULL; *tail = p; tail = &p->next;
    } else link = &p->next;
  }
  pthread_mutex_unlock(&g->pl);
  // Publish matching current-generation chains before optional accounting
  // and formatting. Never acquire pl while holding the device lock.
  unsigned published = done ? push_pending(g, done) : 0;
  if (g->fence_trace && done) {
    const uint64_t publish_end_ns = outcome == XH_FENCE_COMPLETED ? scanout_now_ns() : 0;
    pthread_mutex_lock(&g->pl);
    unsigned matched = 0;
    for (pending *p = done; p; p = p->next) {
      xh_fence_perf_record(&g->fence_perf, outcome, p->fence_fast, p->fence_started_ns, callback_ns);
      matched++;
    }
    if (outcome == XH_FENCE_COMPLETED)
      xh_fence_perf_record_publish(&g->fence_perf, matched, published, callback_ns, publish_end_ns);
    const uint64_t now_ns = scanout_now_ns();
    if (g->fence_report_since_ns && now_ns >= g->fence_report_since_ns &&
        now_ns - g->fence_report_since_ns >= UINT64_C(5000000000)) {
      report = g->fence_perf;
      window_ns = now_ns - g->fence_report_since_ns;
      g->fence_perf = (struct xh_fence_perf){ 0 };
      g->fence_report_since_ns = now_ns;
      report_ready = true;
    }
    pthread_mutex_unlock(&g->pl);
  }
  // Retired records are freed outside device lock.
  while (done) { pending *p = done; done = p->next; free(p); }
  if (report_ready) gpu_fence_perf_report(&report, scanout_now_ns(), window_ns);
  pthread_mutex_lock(&g->pl);
  g->retiring_callbacks--;
  pthread_mutex_unlock(&g->pl);
}

static void gpu_retire(xh_virtio *dev, uint32_t ctx, uint32_t ring, uint64_t fence)
{
  retire(xh_virtio_opaque(dev), ctx, ring, fence, XH_FENCE_COMPLETED, 0, 0);
}

// The 3D commands and the blob ones. 0: not one of them (command() goes on to the 2D ones).
static uint32_t command3d(gpu_state *g, const gpu_hdr *h, const uint8_t *body, size_t left, uint8_t *resp, size_t resp_max, size_t *resp_size)
{
  xh_gpu3d *b = g->b;
  uint32_t a[4];
  switch (h->type) {
  case CMD_GET_CAPSET_INFO: {
    if (left < 8 || resp_max < sizeof *h + 16) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 4);
    uint32_t info[4] = { 0 };
    if (b && a[0] < b->capset_count(b)) b->capset_info(b, a[0], &info[0], &info[1], &info[2]);
    memcpy(resp + sizeof *h, info, sizeof info);
    *resp_size = sizeof *h + 16;
    return RESP_OK_CAPSET_INFO;
  }
  case CMD_GET_CAPSET: {
    if (left < 8) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 8);
    size_t n = b ? b->capset(b, a[0], a[1], resp + sizeof *h, resp_max - sizeof *h) : 0;
    if (!n) return RESP_ERR_INVALID_PARAMETER;
    *resp_size = sizeof *h + n;
    return RESP_OK_CAPSET;
  }
  case CMD_CTX_CREATE: {
    if (left < 8) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 8);
    size_t name = left - 8 < 64 ? left - 8 : 64;
    if (a[0] < name) name = a[0];
    if (!b || !h->ctx || ctx_find(g, h->ctx)) return RESP_ERR_INVALID_CONTEXT_ID;
    uint32_t *slot = NULL;
    for (unsigned i = 0; i < MAX_CTX && !slot; i++) if (!g->ctx[i]) slot = &g->ctx[i];
    if (!slot) return RESP_ERR_OUT_OF_MEMORY;
    int r = b->ctx_create(b, h->ctx, a[1] & 0xff, (const char *)body + 8, name);
    if (g->trace)
      LOGI("gpu trace: context-create queue_gen=%llu context=%u process=%.*s capset=%u backend_status=%d",
           (unsigned long long)g->state_gen, h->ctx, (int)name, (const char *)body + 8, a[1] & 0xff, r);
    if (r) return r == -ENOMEM ? RESP_ERR_OUT_OF_MEMORY : RESP_ERR_UNSPEC;
    *slot = h->ctx;
    g->ctx_fast[slot - g->ctx] = name >= 14 && !memcmp(body + 8, "xnu:backboardd", 14);
    // context_init's bits 8-23: the creating task's role and its thread's QoS (OneiOSAdreno.cpp oneios_gpu_hint).
    if (b->hint) b->hint(b, h->ctx, (const uint8_t[3]){ (uint8_t)(a[1] >> 8), (uint8_t)(a[1] >> 16), 0 });
    return RESP_OK_NODATA;
  }
  case CMD_CTX_DESTROY: {
    uint32_t *slot = ctx_find(g, h->ctx);
    if (!slot) return RESP_ERR_INVALID_CONTEXT_ID;
    b->ctx_destroy(b, h->ctx);
    *slot = 0;
    retire(g, h->ctx, -1, 0, XH_FENCE_CANCELED, 0, 0);  // ctx destroy is not a GPU completion
    return RESP_OK_NODATA;
  }
  case CMD_SUBMIT_3D: {
    if (left < 8) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 4);
    if (!ctx_find(g, h->ctx)) return RESP_ERR_INVALID_CONTEXT_ID;
    if (!a[0] || a[0] > left - 8) return RESP_ERR_INVALID_PARAMETER;
    if (b->hint) b->hint(b, h->ctx, h->pad);         // the submitting task's role, QoS and frame deadline
    return b->submit(b, h->ctx, body + 8, a[0]) ? RESP_ERR_UNSPEC : RESP_OK_NODATA;
  }
  case CMD_RESOURCE_CREATE_BLOB: {
    uint64_t wide[2];
    if (left < 32) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 16);                             // resource, blob_mem, blob_flags, nr_entries
    memcpy(wide, body + 16, 16);                     // blob_id, size
    if (!a[0] || find(g, a[0]) || blob_find(g, a[0])) return RESP_ERR_INVALID_RESOURCE_ID;
    bool guest = a[1] == XH_GPU_BLOB_GUEST || a[1] == XH_GPU_BLOB_HOST3D_GUEST, host = a[1] == XH_GPU_BLOB_HOST3D || a[1] == XH_GPU_BLOB_HOST3D_GUEST;
    if ((!guest && !host) || !wide[1] || a[3] > MAX_BLOB_ENTRIES || (guest ? !a[3] : a[3] != 0) || left - 32 < (size_t)a[3] * sizeof(gpu_entry)) return RESP_ERR_INVALID_PARAMETER;
    if (host && !ctx_find(g, h->ctx)) return RESP_ERR_INVALID_CONTEXT_ID;
    gpu_entry *entries = NULL;
    if (guest) {
      // The segments are guest RAM, whole host pages each (udmabuf takes nothing else), and cover the blob.
      uint64_t total = 0;
      if (!(entries = malloc(a[3] * sizeof *entries))) return RESP_ERR_OUT_OF_MEMORY;
      memcpy(entries, body + 32, a[3] * sizeof *entries);
      for (unsigned i = 0; i < a[3]; i++) {
        if (!entries[i].length || ((entries[i].addr | entries[i].length) & 0xfff) || !xh_virtio_translate(entries[i].addr, entries[i].length)) { free(entries); return RESP_ERR_INVALID_PARAMETER; }
        total += entries[i].length;
      }
      if (total < wide[1]) { free(entries); return RESP_ERR_INVALID_PARAMETER; }
    }
    blob *nb = blob_add(g, a[0]);
    if (!nb) { free(entries); return RESP_ERR_OUT_OF_MEMORY; }
    // The renderer makes every blob of a context, and a display blob it may be asked to attach to one later.
    int r = b && (host || (a[2] & XH_GPU_BLOB_FLAG_GUEST_HANDLE)) ? b->create_blob(b, host ? h->ctx : 0, a[0], a[1], a[2], wide[0], wide[1], entries, a[3]) : 0;
    if (r && host) { nb->entries = entries; blob_del(g, nb); return r == -ENOMEM ? RESP_ERR_OUT_OF_MEMORY : RESP_ERR_UNSPEC; }
    nb->ctx = host ? h->ctx : 0; nb->mem = a[1]; nb->size = wide[1]; nb->entries = entries; nb->nentries = a[3];
    if (g->trace || xh_display_trace_enabled()) nb->serial = ++g->resource_serial;  // unique across ID reuse and resets
    g->blob_bytes += wide[1];
    g->blobs_made++;
    return RESP_OK_NODATA;
  }
  case CMD_RESOURCE_MAP_BLOB: {
    if (left < 16 || resp_max < sizeof *h + 8) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 4);
    blob *bl = blob_find(g, a[0]);
    if (!bl) return RESP_ERR_INVALID_RESOURCE_ID;
    uint64_t offset = 0;
    uint32_t info[2] = { 0 };
    // Only what lies in the pool can be mapped: the guest maps pool base + offset from its own RAM.
    if (!b || bl->mem != XH_GPU_BLOB_HOST3D || b->map_blob(b, a[0], &offset, &info[0]) || offset > UINT32_MAX) return RESP_ERR_INVALID_PARAMETER;
    info[0] |= MAP_INFO_POOL;
    info[1] = (uint32_t)offset;
    memcpy(resp + sizeof *h, info, sizeof info);
    *resp_size = sizeof *h + 8;
    return RESP_OK_MAP_INFO;
  }
  case CMD_RESOURCE_UNMAP_BLOB:
    if (left < 4) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 4);
    return blob_find(g, a[0]) ? RESP_OK_NODATA : RESP_ERR_INVALID_RESOURCE_ID;
  case CMD_CTX_ATTACH_RESOURCE: case CMD_CTX_DETACH_RESOURCE: {
    if (left < 4) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 4);
    if (!ctx_find(g, h->ctx)) return RESP_ERR_INVALID_CONTEXT_ID;
    if (!blob_find(g, a[0])) return RESP_ERR_INVALID_RESOURCE_ID;
    return b->attach(b, h->ctx, a[0], h->type == CMD_CTX_ATTACH_RESOURCE) ? RESP_ERR_UNSPEC : RESP_OK_NODATA;
  }
  case CMD_RESOURCE_UNREF: {
    if (left < 4) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 4);
    blob *bl = blob_find(g, a[0]);
    if (!bl) return 0;                               // a 2D resource, or nothing
    if (g->scanout_resource == a[0]) { g->scanout_resource = 0; g->scan.width = 0; }
    if (b) b->unref(b, a[0]);
    blob_del(g, bl);
    g->blobs_unref++;
    return RESP_OK_NODATA;
  }
  case CMD_SET_SCANOUT_BLOB: {
    gpu_rect rect;
    uint32_t v[14];                                  // scanout, resource, width, height, format, padding, strides[4], offsets[4]
    if (left < 16 + sizeof v) return RESP_ERR_INVALID_PARAMETER;
    memcpy(&rect, body, 16);
    memcpy(v, body + 16, sizeof v);
    if (v[0] != 0) return RESP_ERR_INVALID_SCANOUT_ID;
    if (v[1] == 0) { g->scanout_resource = 0; g->scan.width = 0; return RESP_OK_NODATA; }
    blob *bl = blob_find(g, v[1]);
    if (!bl || !bl->entries) return RESP_ERR_INVALID_RESOURCE_ID;
    if (!format_known(v[4])) return RESP_ERR_INVALID_PARAMETER;
    uint64_t row = (uint64_t)v[2] * format_bpp(v[4]);
    if (!v[2] || !v[3] || v[2] > 16384 || v[3] > 16384 || v[6] < row || (v[6] % format_bpp(v[4])) || !rect_ok(&rect, v[2], v[3]) ||
        v[10] + (uint64_t)(v[3] - 1) * v[6] + row > bl->size) return RESP_ERR_INVALID_PARAMETER;
    static unsigned half_said;
    if (v[4] == FMT_RGBA16F && g->scan.format != FMT_RGBA16F && half_said++ < 4)
      LOGI("display: the guest scans out half floats (R,G,B,A 16F, %ux%u, stride %u) onto a %s frame", v[2], v[3], v[6],
           xh_pixels_name(display_format()));
    compact_scanout(bl);
    g->scanout_resource = v[1];
    g->scan.width = v[2]; g->scan.height = v[3]; g->scan.format = v[4]; g->scan.stride = v[6]; g->scan.offset = v[10];
    return RESP_OK_NODATA;
  }
  }
  return 0;
}

// The blobs the host holds, one line per 10 s while they change: `gpu: 10 s: host blobs N (M MiB), made +A unref'd +B`.
// Against the guest's `oneios-gpu-memory` live count (and the sum of its own and wired MiB): the host holding more than
// the guest has live is blobs the guest released and the host kept; the same is the guest's own holding.
static void blob_note(gpu_state *g)
{
  uint64_t now = flush_now_us();
  if (!g->blob_note_us) g->blob_note_us = now;
  if (now - g->blob_note_us < 10000000u) return;
  if (g->blobs_made != g->noted_made || g->blobs_unref != g->noted_unref)
    LOGI("gpu: %llu s: host blobs %u (%llu MiB), made +%llu unref'd +%llu", (unsigned long long)((now - g->blob_note_us) / 1000000u),
         g->nblobs, (unsigned long long)(g->blob_bytes >> 20), (unsigned long long)(g->blobs_made - g->noted_made),
         (unsigned long long)(g->blobs_unref - g->noted_unref));
  g->blob_note_us = now;
  g->noted_made = g->blobs_made;
  g->noted_unref = g->blobs_unref;
}

static uint32_t command(gpu_state *g, const uint8_t *req, size_t size, uint8_t *resp, size_t resp_max, size_t *resp_size)
{
  const gpu_hdr *h = (const gpu_hdr *)req;
  const uint8_t *body = req + sizeof *h;
  size_t left = size - sizeof *h;
  *resp_size = sizeof *h;
  if (g->blobs) {
    blob_note(g);
    uint32_t status = command3d(g, h, body, left, resp, resp_max, resp_size);
    if (status) return status;
  }
  switch (h->type) {
  case CMD_GET_DISPLAY_INFO: {
    if (resp_max < sizeof *h + 16 * 24) return RESP_ERR_UNSPEC;
    memset(resp + sizeof *h, 0, 16 * 24);
    uint32_t mode[6] = { 0, 0, g->width, g->height, 1, 0 };
    memcpy(resp + sizeof *h, mode, sizeof mode);
    *resp_size = sizeof *h + 16 * 24;
    return RESP_OK_DISPLAY_INFO;
  }
  case CMD_RESOURCE_CREATE_2D: {
    uint32_t a[4];
    if (left < 16) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 16);
    if (!a[0] || find(g, a[0]) || (g->blobs && blob_find(g, a[0]))) return RESP_ERR_INVALID_RESOURCE_ID;
    if (!a[2] || !a[3] || a[2] > 16384 || a[3] > 16384) return RESP_ERR_INVALID_PARAMETER;
    if (!format_known(a[1])) return RESP_ERR_INVALID_PARAMETER;
    resource *r = NULL;
    for (unsigned i = 0; i < MAX_RES && !r; i++) if (!g->res[i].id) r = &g->res[i];
    if (!r) return RESP_ERR_OUT_OF_MEMORY;
    r->dformat = display_format();
    r->dbpp = xh_pixels_bpp(r->dformat);
    r->pixels = calloc((size_t)a[2] * a[3], r->dbpp);
    if (!r->pixels) return RESP_ERR_OUT_OF_MEMORY;
    r->id = a[0]; r->format = a[1]; r->width = a[2]; r->height = a[3];
    if (g->trace || xh_display_trace_enabled()) r->serial = ++g->resource_serial;  // unique across ID reuse and resets
    return RESP_OK_NODATA;
  }
  case CMD_RESOURCE_UNREF: {
    uint32_t id;
    if (left < 4) return RESP_ERR_INVALID_PARAMETER;
    memcpy(&id, body, 4);
    resource *r = find(g, id);
    if (!r) return RESP_ERR_INVALID_RESOURCE_ID;
    if (g->scanout_resource == id) g->scanout_resource = 0;
    release(r);
    return RESP_OK_NODATA;
  }
  case CMD_RESOURCE_ATTACH_BACKING: {
    uint32_t a[2];
    if (left < 8) return RESP_ERR_INVALID_PARAMETER;
    memcpy(a, body, 8);
    resource *r = find(g, a[0]);
    if (!r) return RESP_ERR_INVALID_RESOURCE_ID;
    if (!a[1] || a[1] > MAX_BACKING || left - 8 < (size_t)a[1] * sizeof(gpu_entry)) return RESP_ERR_INVALID_PARAMETER;
    gpu_entry *entries = malloc(a[1] * sizeof *entries);
    if (!entries) return RESP_ERR_OUT_OF_MEMORY;
    memcpy(entries, body + 8, a[1] * sizeof *entries);
    free(r->backing);
    r->backing = entries;
    r->nbacking = a[1];
    return RESP_OK_NODATA;
  }
  case CMD_RESOURCE_DETACH_BACKING: {
    uint32_t id;
    if (left < 4) return RESP_ERR_INVALID_PARAMETER;
    memcpy(&id, body, 4);
    resource *r = find(g, id);
    if (!r) return RESP_ERR_INVALID_RESOURCE_ID;
    free(r->backing);
    r->backing = NULL;
    r->nbacking = 0;
    return RESP_OK_NODATA;
  }
  case CMD_SET_SCANOUT: {
    gpu_rect rect;
    uint32_t a[2];
    if (left < 24) return RESP_ERR_INVALID_PARAMETER;
    memcpy(&rect, body, 16);
    memcpy(a, body + 16, 8);
    if (a[0] != 0) return RESP_ERR_INVALID_SCANOUT_ID;
    if (a[1] == 0) { g->scanout_resource = 0; return RESP_OK_NODATA; }      // scanout disabled
    resource *r = find(g, a[1]);
    if (!r) return RESP_ERR_INVALID_RESOURCE_ID;
    if (!rect_ok(&rect, r->width, r->height)) return RESP_ERR_INVALID_PARAMETER;
    g->scanout_resource = a[1];
    g->scan.width = 0;
    return RESP_OK_NODATA;
  }
  case CMD_TRANSFER_TO_HOST_2D: {
    gpu_rect rect;
    uint64_t offset;
    uint32_t id;
    if (left < 28) return RESP_ERR_INVALID_PARAMETER;
    memcpy(&rect, body, 16);
    memcpy(&offset, body + 16, 8);
    memcpy(&id, body + 24, 4);
    resource *r = find(g, id);
    if (!r) return RESP_ERR_INVALID_RESOURCE_ID;
    if (!rect_ok(&rect, r->width, r->height) || !r->backing) return RESP_ERR_INVALID_PARAMETER;
    unsigned gbpp = format_bpp(r->format);
    uint8_t *row = malloc((size_t)rect.w * gbpp);
    if (!row) return RESP_ERR_OUT_OF_MEMORY;
    uint32_t status = RESP_OK_NODATA;
    for (uint32_t y = 0; y < rect.h; y++) {
      // `offset` is where the rectangle's first pixel is in the backing; rows follow at the resource's stride.
      if (!backing_read(r, offset + (uint64_t)y * r->width * gbpp, row, (uint64_t)rect.w * gbpp)) { status = RESP_ERR_INVALID_PARAMETER; break; }
      convert_to(r->pixels + ((size_t)(rect.y + y) * r->width + rect.x) * r->dbpp, r->dformat, row, r->format, rect.w);
    }
    free(row);
    return status;
  }
  case CMD_RESOURCE_FLUSH: {
    gpu_rect rect;
    uint32_t id;
    if (left < 20) return RESP_ERR_INVALID_PARAMETER;
    memcpy(&rect, body, 16);
    memcpy(&id, body + 16, 4);
    blob *bl = g->blobs ? blob_find(g, id) : NULL;
    if (bl) return flush_blob(g, bl, &rect);
    resource *r = find(g, id);
    if (!r) return RESP_ERR_INVALID_RESOURCE_ID;
    if (!rect_ok(&rect, r->width, r->height)) return RESP_ERR_INVALID_PARAMETER;
    xh_display *d = xh_display_get();
    if (id == g->scanout_resource && d && d->pixels && r->dbpp == xh_pixels_bpp(display_format())) {
      uint32_t w = rect.x < d->width ? (rect.w < d->width - rect.x ? rect.w : d->width - rect.x) : 0;
      uint32_t hgt = rect.y < d->height ? (rect.h < d->height - rect.y ? rect.h : d->height - rect.y) : 0;
      const bool trace_scanout = xh_display_trace_enabled() && w && hgt;
      const uint64_t scanout_start_ns = trace_scanout ? scanout_now_ns() : 0;
      if (w && hgt && rect.x == 0 && w == r->width && d->stride == (size_t)w * r->dbpp)
        memcpy(d->pixels + (size_t)rect.y * d->stride,
               r->pixels + (size_t)rect.y * d->stride, (size_t)hgt * d->stride);
      else for (uint32_t y = 0; y < hgt && w; y++)
        memcpy(d->pixels + (size_t)(rect.y + y) * d->stride + (size_t)rect.x * r->dbpp,
               r->pixels + ((size_t)(rect.y + y) * r->width + rect.x) * r->dbpp, (size_t)w * r->dbpp);
      const uint64_t scanout_copied_ns = trace_scanout ? scanout_now_ns() : 0;
      frame_shown(g, r->backing, r->nbacking);   // first: session/ready before the helper is told of the frame
      if (w && hgt) {
        const struct xh_frame_scanout sample = {
          .start_ns = scanout_start_ns, .copied_ns = scanout_copied_ns,
          .kind = XH_FRAME_SCANOUT_2D, .resource_id = id,
          .queue_generation = g->state_gen, .resource_generation = r->serial,
          .owner_context = 0   // 2D resource has no single 3D context owner
        };
        xh_display_flush_scanout(rect.x, rect.y, w, hgt, trace_scanout ? &sample : NULL);
      }
    }
    return RESP_OK_NODATA;
  }
  }
  return RESP_ERR_UNSPEC;
}

static const char *trace_operation(uint32_t type, size_t *offset)
{
  *offset = 0;
  switch (type) {
  case CMD_RESOURCE_CREATE_2D: return "create-2d";
  case CMD_RESOURCE_CREATE_BLOB: return "create-blob";
  case CMD_RESOURCE_ATTACH_BACKING: return "attach-backing";
  case CMD_RESOURCE_DETACH_BACKING: return "detach-backing";
  case CMD_RESOURCE_UNREF: return "unref";
  case CMD_CTX_ATTACH_RESOURCE: return "context-attach";
  case CMD_CTX_DETACH_RESOURCE: return "context-detach";
  case CMD_RESOURCE_MAP_BLOB: return "map-blob";
  case CMD_RESOURCE_UNMAP_BLOB: return "unmap-blob";
  case CMD_SET_SCANOUT: case CMD_SET_SCANOUT_BLOB: *offset = 20; return "scanout";
  case CMD_CTX_DESTROY: return "context-destroy";
  case CMD_SUBMIT_3D: return "submit";
  default: return NULL;
  }
}

static uint64_t trace_serial(gpu_state *g, uint32_t id, uint32_t *owner)
{
  if (!id) return 0;
  blob *bl = g->blobs ? blob_find(g, id) : NULL;
  if (bl) { *owner = bl->ctx; return bl->serial; }
  resource *r = find(g, id);
  return r ? r->serial : 0;
}

// Runs the command of a chain and writes its response. Returns the response's length (0: a chain that is no command)
// and the command's header in `in`.
static int64_t serve(gpu_state *g, unsigned queue, uint16_t head, xh_viov *iov, unsigned n, gpu_hdr *in, uint32_t *status,
                     pending **reserved)
{
  // Gather the readable parts (the command), find the writable ones (the response).
  size_t req_size = 0, resp_max = 0;
  for (unsigned i = 0; i < n; i++) { if (iov[i].writable) resp_max += iov[i].length; else req_size += iov[i].length; }
  if (req_size < sizeof(gpu_hdr) || req_size > (1u << 20) || resp_max < sizeof(gpu_hdr)) return 0;
  // Small control commands and all fixed-format replies (max 408 bytes)
  // stay on the stack. Keep a private, naturally aligned copy of guest
  // input; the backend may read 32-bit words in place. Only a large capset
  // response needs heap storage; never allocate an unbounded writable iov.
  _Alignas(gpu_hdr) uint8_t req_small[1024];
  uint8_t resp_small[512];
  uint8_t *req = req_size <= sizeof req_small ? req_small : malloc(req_size);
  if (!req) return 0;
  size_t at = 0;
  for (unsigned i = 0; i < n; i++) if (!iov[i].writable && iov[i].length) {
    memcpy(req + at, iov[i].data, iov[i].length); at += iov[i].length;
  }
  size_t resp_size = sizeof(gpu_hdr);
  gpu_hdr out = { 0 };
  memcpy(in, req, sizeof *in);
  size_t limit = in->type == CMD_GET_CAPSET && queue == 0 ? (1u << 20) : sizeof resp_small;
  if (resp_max > limit) resp_max = limit;
  uint8_t *resp = resp_max <= sizeof resp_small ? resp_small : malloc(resp_max);
  if (!resp) { if (req != req_small) free(req); return 0; }
  memset(resp, 0, resp_max);
  // Reserve before executing a potentially fenced command. An allocation
  // failure must not execute a command then silently lose its chain.
  bool need = reserved && in->ctx && (in->flags & (FLAG_FENCE | FLAG_RING_IDX)) == (FLAG_FENCE | FLAG_RING_IDX);
  if (need) *reserved = malloc(sizeof **reserved);
  size_t offset;
  const char *event = g->trace && queue == 0 ? trace_operation(in->type, &offset) : NULL;
  uint32_t id = 0, owner = 0;
  uint64_t serial = 0;
  if (event && in->type != CMD_CTX_DESTROY && in->type != CMD_SUBMIT_3D && req_size >= sizeof *in + offset + sizeof id) {
    memcpy(&id, req + sizeof *in + offset, sizeof id);
    serial = trace_serial(g, id, &owner);
  }
  out.type = need && !*reserved ? RESP_ERR_OUT_OF_MEMORY :
             queue == 0 ? command(g, req, req_size, resp, resp_max, &resp_size) : RESP_OK_NODATA;
  if (event) {
    if (!serial) serial = trace_serial(g, id, &owner);
    LOGI("gpu trace: %s queue_gen=%llu head=%u context=%u resource=%u resource_gen=%llu owner=%u ring=%u fence=%llu status=%#x",
         event, (unsigned long long)g->state_gen, head, in->ctx, id, (unsigned long long)serial,
         owner, in->ring, (unsigned long long)in->fence, out.type);
  }
  if (in->flags & FLAG_FENCE) { out.flags = in->flags & (FLAG_FENCE | FLAG_RING_IDX); out.fence = in->fence; out.ctx = in->ctx; out.ring = in->ring; }
  memcpy(resp, &out, sizeof out);
  if (resp_size > resp_max) resp_size = resp_max;
  at = 0;
  for (unsigned i = 0; i < n && at < resp_size; i++) {
    if (!iov[i].writable) continue;
    size_t len = resp_size - at < iov[i].length ? resp_size - at : iov[i].length;
    if (len) memcpy(iov[i].data, resp + at, len);
    at += len;
  }
  if (req != req_small) free(req);
  if (resp != resp_small) free(resp);
  *status = out.type;
  return (int64_t)resp_size;
}

static int64_t gpu_handle(xh_virtio *dev, unsigned queue, uint16_t head, xh_viov *iov, unsigned n)
{
  gpu_state *g = xh_virtio_opaque(dev);
  gpu_hdr in = { 0 };
  uint32_t status;
  int64_t written = serve(g, queue, head, iov, n, &in, &status, NULL);
  if (g->trace && !g->b && queue == 0)
    LOGI("gpu trace: complete queue_gen=%llu head=%u context=%u ring=%u fence=%llu bytes=%lld",
         (unsigned long long)g->state_gen, head, in.ctx, in.ring,
         (unsigned long long)in.fence, (long long)written);
  return written;
}

static uint32_t gpu_config(xh_virtio *dev, uint32_t offset, unsigned size)
{
  (void)size;
  gpu_state *g = xh_virtio_opaque(dev);
  // events_read, events_clear, num_scanouts = 1, num_capsets
  return offset == 8 ? 1 : offset == 12 && g->b ? g->b->capset_count(g->b) : 0;
}

static void teardown(gpu_state *g)
{
  for (unsigned i = 0; i < MAX_RES; i++) if (g->res[i].id) release(&g->res[i]);
  g->scanout_resource = 0;
  g->scan.width = 0;
  if (!g->blobs) return;
  for (unsigned i = 0; i < BLOB_SLOTS; i++) if (g->blobs[i].id) {
    if (g->b) g->b->unref(g->b, g->blobs[i].id);
    free(g->blobs[i].entries);
  }
  memset(g->blobs, 0, BLOB_SLOTS * sizeof *g->blobs);
  g->nblobs = 0;
  g->blob_bytes = 0;
  for (unsigned i = 0; i < MAX_CTX; i++) if (g->ctx[i]) { g->b->ctx_destroy(g->b, g->ctx[i]); g->ctx[i] = 0; }
  pthread_mutex_lock(&g->pl);
  pending *list = g->fences;
  g->fences = NULL;
  if (g->fence_trace)
    for (pending *p = list; p; p = p->next)
      xh_fence_perf_record(&g->fence_perf, XH_FENCE_CANCELED, p->fence_fast, 0, 0);
  pthread_mutex_unlock(&g->pl);
  while (list) { pending *p = list; list = p->next; free(p); }                // their chains were the old queue's
}

static void gpu_reset(xh_virtio *dev)
{
  gpu_state *g = xh_virtio_opaque(dev);
  teardown(g);
  g->state_gen++;
  if (g->trace) LOGI("gpu trace: reset queue_gen=%llu", (unsigned long long)g->state_gen);
}

// ---- the 3D device's control queue: its own thread -------------------------------------------------------------------
static void wake(gpu_state *g, bool reset)
{
  pthread_mutex_lock(&g->pl);
  if (reset) {
    g->reset_serial++;
    if (__atomic_load_n(&g->gate_closed, __ATOMIC_RELAXED)) g->gate_invalid = true;
  }
  g->kicks++;
  pthread_mutex_unlock(&g->pl);
  uint64_t one = 1;
  while (write(g->wake, &one, 8) < 0 && errno == EINTR) {}
}

static void gpu_kick(xh_virtio *dev, unsigned queue) { (void)queue; wake(xh_virtio_opaque(dev), false); }

// With the device's lock held (virtio.c): the queues are already gone; the worker forgets the rest before its next command.
static void gpu_reset_3d(xh_virtio *dev)
{
  gpu_state *g = xh_virtio_opaque(dev);
  g->gen++;
  wake(g, true);
}

// Called with cmd held. A reset can arrive after a wake or while either lane
// waits for cmd. Reconcile the tables before either lane classifies or runs work.
static uint64_t sync_generation(gpu_state *g)
{
  xh_virtio_lock(g->dev);
  uint64_t gen = g->gen;
  xh_virtio_unlock(g->dev);
  if (g->state_gen != gen) {
    teardown(g);
    g->state_gen = gen;
    if (g->trace) LOGI("gpu trace: reset queue_gen=%llu", (unsigned long long)gen);
  }
  return gen;
}

// A command of the fast lane that names a resource the slow lane has not made yet (an app's IOSurface the render
// server attaches, the unref of an app's blob) waits for the slow lane's commands that came before it, and runs again.
static bool missing_resource(uint32_t status)
{
  return status == RESP_ERR_INVALID_RESOURCE_ID;
}

enum { RESP_PENDING_RETRY = 1 };                     // work(): not answered; run it again once the slow lane caught up

static bool slow_pending(gpu_state *g)
{
  pthread_mutex_lock(&g->pl);
  bool pending = g->slow_done != g->slow_queued;
  pthread_mutex_unlock(&g->pl);
  return pending;
}

// Host stages use a common CLOCK_MONOTONIC domain, but are not GPU
// execution or proof of the critical path of a particular displayed frame.
static void queue_sample(gpu_state *g, struct xh_fence_hist *h, uint64_t start, uint64_t end)
{
  if (!xh_fence_hist_span(h, start, end)) g->queue_invalid++;
}

static void queue_report(gpu_state *g, uint64_t now)
{
  if (!g->queue_report_since_ns) { g->queue_report_since_ns = now; return; }
  if (now < g->queue_report_since_ns || now - g->queue_report_since_ns < UINT64_C(5000000000)) return;
  struct xh_fence_hist *h[] = { &g->queue_wait[0], &g->queue_wait[1],
    &g->queue_service[0], &g->queue_service[1], &g->submit_service,
    &g->blob_service, &g->flush_service, &g->dependency_wait };
  static const char *const names[] = { "fast_wait", "slow_wait", "fast_service", "slow_service",
    "submit_service", "blob_service", "flush_service", "dependency_wait" };
  for (unsigned i = 0; i < sizeof h / sizeof h[0]; i++) {
    if (h[i]->count)
      LOGI("gpu-queue-trace: mono_ms=%llu window_ms=%llu stage=%s n=%llu mean_us=%llu p95_le_us=%llu p99_le_us=%llu max_us=%llu invalid_clocks=%llu",
           (unsigned long long)(now / 1000000u),
           (unsigned long long)((now - g->queue_report_since_ns) / 1000000u),
           names[i], (unsigned long long)h[i]->count,
           (unsigned long long)(h[i]->sum_us / h[i]->count),
           (unsigned long long)xh_fence_perf_quantile_le_us(h[i], 95),
           (unsigned long long)xh_fence_perf_quantile_le_us(h[i], 99),
           (unsigned long long)h[i]->max_us, (unsigned long long)g->queue_invalid);
    *h[i] = (struct xh_fence_hist){ 0 };
  }
  g->queue_invalid = 0;
  g->queue_report_since_ns = now;
}

// Serves a chain and answers it (now, or when its fence retires). With `may_wait`, a command that names a resource
// the slow lane may still be making is not answered: RESP_PENDING_RETRY, and the caller runs it again later.
static uint32_t work(gpu_state *g, uint16_t head, xh_viov *iov, unsigned n, uint64_t gen, bool may_wait,
                     uint64_t queued_ns, bool slow_path)
{
  if (sync_generation(g) != gen) return 0;           // the old queue's chain was invalidated by reset
  gpu_hdr in = { 0 };
  uint32_t status = 0;
  pending *reserved = NULL;
  uint64_t began = g->fence_trace ? scanout_now_ns() : 0;
  int64_t written = serve(g, 0, head, iov, n, &in, &status, &reserved);
  if (g->fence_trace) {
    uint64_t end = scanout_now_ns();
    if (queued_ns) queue_sample(g, &g->queue_wait[slow_path], queued_ns, began);
    queue_sample(g, &g->queue_service[slow_path], began, end);
    if (in.type == CMD_SUBMIT_3D) queue_sample(g, &g->submit_service, began, end);
    else if (in.type == CMD_RESOURCE_CREATE_BLOB) queue_sample(g, &g->blob_service, began, end);
    else if (in.type == CMD_RESOURCE_FLUSH) queue_sample(g, &g->flush_service, began, end);
    queue_report(g, end);
  }
  if (may_wait && missing_resource(status) && slow_pending(g)) { free(reserved); return RESP_PENDING_RETRY; }
  // A command fenced on a context's ring is returned when the ring passes the fence; any other at once (a fence on
  // the device's own ring has nothing to wait for: the 2D commands are done when they return).
  bool hold = written > 0 && status < RESP_ERR_UNSPEC && (in.flags & FLAG_FENCE) && (in.flags & FLAG_RING_IDX) && ctx_find(g, in.ctx);
  pending immediate = { .head = head, .written = (uint32_t)written, .ctx = in.ctx, .ring = in.ring, .fence = in.fence, .gen = gen };
  if (!hold) { free(reserved); push_pending(g, &immediate); return status; }
  // serve() reserved this record before executing the fenced command.
  pending *p = reserved;
  *p = immediate;
  if (g->fence_trace) {
    uint32_t *slot = ctx_find(g, in.ctx);
    p->fence_fast = slot && g->ctx_fast[slot - g->ctx];
    p->fence_started_ns = scanout_now_ns();
  }
  pthread_mutex_lock(&g->pl);
  p->next = g->fences;
  g->fences = p;
  pthread_mutex_unlock(&g->pl);
  // May retire it before it returns. A refused fence is retired here.
  if (g->b->submit_fence(g->b, in.ctx, in.ring, in.fence))
    retire(g, in.ctx, in.ring, in.fence, XH_FENCE_REJECTED, gen, head);
  return status;
}

// The header of a chain, read without taking it (false: shorter than a header).
static bool peek_hdr(const xh_viov *iov, unsigned n, gpu_hdr *h)
{
  size_t at = 0;
  for (unsigned i = 0; i < n && at < sizeof *h; i++) {
    if (iov[i].writable) continue;
    size_t k = iov[i].length < sizeof *h - at ? iov[i].length : sizeof *h - at;
    memcpy((uint8_t *)h + at, iov[i].data, k);
    at += k;
  }
  return at == sizeof *h;
}

// Whether a command is the slow lane's: a context's, and not the render server's. Context creation stays here (it
// decides the lane of what follows).
static bool slow_lane(gpu_state *g, const gpu_hdr *h)
{
  if (!h->ctx || h->type == CMD_CTX_CREATE) return false;
  for (unsigned i = 0; i < MAX_CTX; i++) if (g->ctx[i] == h->ctx) return !g->ctx_fast[i];
  return false;
}

static void *slow_worker(void *arg)
{
  gpu_state *g = arg;
  pthread_mutex_lock(&g->pl);
  for (;;) {
    while (!g->slow_head) pthread_cond_wait(&g->slow_cv, &g->pl);
    slow_job *j = g->slow_head;
    g->slow_head = j->next;
    if (!g->slow_head) g->slow_tail = &g->slow_head;
    pthread_mutex_unlock(&g->pl);
    pthread_mutex_lock(&g->cmd);
    work(g, j->head, j->iov, j->n, j->gen, false, j->queued_ns, true);
    pthread_mutex_unlock(&g->cmd);
    free(j);
    pthread_mutex_lock(&g->pl);
    g->slow_done++;
    pthread_cond_broadcast(&g->slow_cv);
    pthread_cond_broadcast(&g->idle);
  }
  return NULL;
}

// pl held. Publish the parked state before sleeping; a resume changes
// the same flag under pl, so a wake cannot be lost. Never hold cmd or the
// device lock while parked.
static void front_enter_locked(gpu_state *g)
{
  while (__atomic_load_n(&g->gate_closed, __ATOMIC_RELAXED)) {
    g->front_active = false;
    pthread_cond_wait(&g->gate_cv, &g->pl);
  }
  g->front_active = true;
}

static void *worker(void *arg)
{
  gpu_state *g = arg;
  static _Thread_local xh_viov iov[WORKER_IOV];
  for (;;) {
    uint64_t count;
    if (read(g->wake, &count, 8) < 0 && errno != EINTR) break;
    pthread_mutex_lock(&g->pl);
    front_enter_locked(g);
    uint64_t upto = g->kicks, reset_at_start = g->reset_serial;
    pthread_mutex_unlock(&g->pl);
    pthread_mutex_lock(&g->cmd);
    sync_generation(g);
    pthread_mutex_unlock(&g->cmd);
    for (;;) {
      // No additional mutex on the ordinary open hot path. A close racing
      // this read sees front_active=true until this chain finishes and
      // the front parks. The close receipt is not the drain receipt.
      if (__atomic_load_n(&g->gate_closed, __ATOMIC_ACQUIRE)) {
        pthread_mutex_lock(&g->pl);
        front_enter_locked(g);
        pthread_mutex_unlock(&g->pl);
      }
      uint16_t head;
      xh_virtio_lock(g->dev);
      uint64_t gen = g->gen;
      unsigned n = xh_virtio_pop(g->dev, 0, &head, iov, WORKER_IOV);
      xh_virtio_unlock(g->dev);
      if (!n) break;
      uint64_t queued_ns = g->fence_trace ? scanout_now_ns() : 0;
      gpu_hdr h;
      pthread_mutex_lock(&g->cmd);
      bool current = sync_generation(g) == gen;
      bool slow = current && peek_hdr(iov, n, &h) && slow_lane(g, &h);
      if (!current) {
        pthread_mutex_unlock(&g->cmd);
        continue;
      }
      if (slow) {
        pthread_mutex_unlock(&g->cmd);
        slow_job *j = malloc(sizeof *j + n * sizeof *iov);
        if (!j) {
          // Preserve FIFO within the slow lane even on allocation failure.
          // Wait without cmd held, then serve this chain synchronously.
          pthread_mutex_lock(&g->pl);
          uint64_t before = g->slow_queued;
          while (g->slow_done < before) pthread_cond_wait(&g->slow_cv, &g->pl);
          pthread_mutex_unlock(&g->pl);
          pthread_mutex_lock(&g->cmd);
          work(g, head, iov, n, gen, false, queued_ns, true);
          pthread_mutex_unlock(&g->cmd);
          continue;
        }
        *j = (slow_job){ .head = head, .n = n, .gen = gen, .queued_ns = queued_ns };
        memcpy(j->iov, iov, n * sizeof *iov);
        pthread_mutex_lock(&g->pl);
        *g->slow_tail = j;
        g->slow_tail = &j->next;
        g->slow_queued++;
        pthread_cond_broadcast(&g->slow_cv);
        pthread_mutex_unlock(&g->pl);
        continue;
      }
      // Classify and serve the fast chain under the same cmd hold.
      // work() still rechecks the device generation before execution.
      uint32_t status = work(g, head, iov, n, gen, true, queued_ns, false);
      pthread_mutex_unlock(&g->cmd);
      if (status == RESP_PENDING_RETRY) {
        uint64_t retry_ns = g->fence_trace ? scanout_now_ns() : 0;
        pthread_mutex_lock(&g->pl);
        // Only this front worker enqueues slow jobs. No new enqueue
        // can occur between classification and here; therefore the
        // dependency watermark is identical to the earlier snapshot.
        // Do not hold cmd while waiting for the slow worker.
        uint64_t before = g->slow_queued;
        while (g->slow_done < before) pthread_cond_wait(&g->slow_cv, &g->pl);
        pthread_mutex_unlock(&g->pl);
        pthread_mutex_lock(&g->cmd);
        if (g->fence_trace) queue_sample(g, &g->dependency_wait, retry_ns, scanout_now_ns());
        work(g, head, iov, n, gen, false, 0, false);
        pthread_mutex_unlock(&g->cmd);
      }
    }
    pthread_mutex_lock(&g->pl);
    g->served = upto;
    g->reset_handled = reset_at_start;
    g->front_active = false;
    pthread_cond_broadcast(&g->idle);
    pthread_mutex_unlock(&g->pl);
  }
  return NULL;
}

static int gate_lock(xh_virtio *dev, gpu_state **out)
{
  if (!dev) return -EINVAL;
  gpu_state *g = xh_virtio_opaque(dev);
  if (!g || !g->b || !g->blobs) return -ENOTSUP;
  int r = pthread_mutex_trylock(&g->pl);
  if (r) return r == EBUSY ? -EAGAIN : -r;
  *out = g;
  return 0;
}

// pl held. A backend completion removed from the fence list may still be
// publishing its used chain. Keep it visible until the callback is done.
static struct xh_gpu_gate_state gate_state_locked(gpu_state *g)
{
  struct xh_gpu_gate_state s = {
    .lanes_idle = !g->front_active && g->slow_done == g->slow_queued,
    .reset_invalidated = g->gate_invalid || g->reset_serial != g->reset_handled,
    .retiring_callbacks = g->retiring_callbacks
  };
  for (pending *p = g->fences; p; p = p->next) s.pending_fences++;
  s.host_drained = s.lanes_idle && !s.pending_fences &&
                   !s.retiring_callbacks && !s.reset_invalidated;
  return s;
}

// pl held.
static int gate_begin_locked(gpu_state *g, uint64_t *ticket, bool combined)
{
  if (__atomic_load_n(&g->gate_closed, __ATOMIC_RELAXED)) return -EBUSY;
  if (g->gate_ticket == UINT64_MAX) return -EOVERFLOW;
  g->gate_invalid = g->reset_serial != g->reset_handled;
  g->gate_combined = combined;
  *ticket = ++g->gate_ticket;
  __atomic_store_n(&g->gate_closed, true, __ATOMIC_RELEASE);
  return 0;
}
static void gate_open_locked(gpu_state *g)
{
  g->gate_combined = false;
  __atomic_store_n(&g->gate_closed, false, __ATOMIC_RELEASE);
  pthread_cond_broadcast(&g->gate_cv);
}

int xh_virtio_gpu_gate_close(xh_virtio *dev, uint64_t *ticket)
{
  if (!ticket) return -EINVAL;
  gpu_state *g;
  int r = gate_lock(dev, &g);
  if (r) return r;
  r = gate_begin_locked(g, ticket, false);
  pthread_mutex_unlock(&g->pl);
  return r;
}

int xh_virtio_gpu_gate_status(xh_virtio *dev, uint64_t ticket, struct xh_gpu_gate_state *out)
{
  if (!out || !ticket) return -EINVAL;
  gpu_state *g;
  int r = gate_lock(dev, &g);
  if (r) return r;
  if (!__atomic_load_n(&g->gate_closed, __ATOMIC_RELAXED) || ticket != g->gate_ticket)
    r = -ESTALE;
  else *out = gate_state_locked(g);
  pthread_mutex_unlock(&g->pl);
  return r;
}

int xh_virtio_gpu_gate_resume(xh_virtio *dev, uint64_t ticket)
{
  if (!ticket) return -EINVAL;
  gpu_state *g;
  int r = gate_lock(dev, &g);
  if (r) return r;
  if (!__atomic_load_n(&g->gate_closed, __ATOMIC_RELAXED) || ticket != g->gate_ticket)
    r = -ESTALE;
  else if (g->gate_combined) r = -EPERM;
  else {
    struct xh_gpu_gate_state s = gate_state_locked(g);
    if (s.reset_invalidated) r = -ESTALE;
    else if (!s.host_drained) r = -EBUSY;
    else gate_open_locked(g);
  }
  pthread_mutex_unlock(&g->pl);
  return r;
}

// Combined operations are serialized separately so backend polling never
// holds the VirtIO device or fence locks. Only resume calls the backend
// while holding them, and that provider has a strict try-lock contract.
static int quiesce_lock(xh_virtio *dev, gpu_state **out)
{
  if (!dev) return -EINVAL;
  gpu_state *g = xh_virtio_opaque(dev);
  if (!g || !g->blobs || !g->b || g->b->dev != dev ||
      !g->b->drain_close || !g->b->drain_poll || !g->b->drain_resume)
    return -ENOTSUP;
  int r = pthread_mutex_trylock(&g->quiesce_lock);
  if (r) return r == EBUSY ? -EAGAIN : -r;
  *out = g;
  return 0;
}

// Take device lock first, as reset does, so a reset cannot have changed
// the virtqueue yet still be waiting to invalidate the gate on pl.
static int quiesce_gate_lock(gpu_state *g)
{
  if (!xh_virtio_trylock(g->dev)) return -EAGAIN;
  int r = pthread_mutex_trylock(&g->pl);
  if (r) {
    xh_virtio_unlock(g->dev);
    return r == EBUSY ? -EAGAIN : -r;
  }
  return 0;
}
static void quiesce_gate_unlock(gpu_state *g)
{
  pthread_mutex_unlock(&g->pl);
  xh_virtio_unlock(g->dev);
}
static bool combined_ticket_locked(gpu_state *g, uint64_t ticket)
{
  return ticket && g->gate_combined && ticket == g->gate_ticket &&
         __atomic_load_n(&g->gate_closed, __ATOMIC_RELAXED);
}
static int quiesce_snapshot(gpu_state *g, uint64_t ticket, struct xh_gpu_gate_state *out)
{
  int r = quiesce_gate_lock(g);
  if (r) return r;
  if (!combined_ticket_locked(g, ticket)) r = -ESTALE;
  else *out = gate_state_locked(g);
  quiesce_gate_unlock(g);
  return r;
}
static int quiesce_fail(gpu_state *g, int error)
{
  g->quiesce_verified = false;
  g->quiesce_fault = error < 0 ? error : -EPROTO;
  return g->quiesce_fault;
}

int xh_virtio_gpu_quiesce_close(xh_virtio *dev, uint64_t *ticket)
{
  if (!ticket) return -EINVAL;
  gpu_state *g;
  int r = quiesce_lock(dev, &g);
  if (r) return r;
  r = quiesce_gate_lock(g);
  if (!r) {
    r = gate_begin_locked(g, ticket, true);
    if (!r) {
      g->backend_ticket = 0;
      g->quiesce_verified = false;
      g->quiesce_fault = 0;
    }
    quiesce_gate_unlock(g);
  }
  pthread_mutex_unlock(&g->quiesce_lock);
  return r;
}

int xh_virtio_gpu_quiesce_poll(xh_virtio *dev, uint64_t ticket)
{
  if (!ticket) return -EINVAL;
  gpu_state *g;
  int r = quiesce_lock(dev, &g);
  if (r) return r;
  struct xh_gpu_gate_state s = {0};
  r = quiesce_snapshot(g, ticket, &s);
  if (r) goto done; // a stale caller does not mutate another ticket
  if (g->quiesce_fault) { r = g->quiesce_fault; goto done; }
  g->quiesce_verified = false;
  if (s.reset_invalidated) { r = quiesce_fail(g, -ESTALE); goto done; }
  // Already dequeued commands may still need the backend. Once both
  // lanes are parked, close it even if VirtIO fences are still pending.
  if (!s.lanes_idle) { r = -EAGAIN; goto done; }
  if (!g->backend_ticket) {
    uint64_t backend = 0;
    r = g->b->drain_close(g->b, &backend);
    if (r == -EAGAIN && !backend) goto done;
    if (r || !backend) { r = quiesce_fail(g, r == -EAGAIN ? -EPROTO : r); goto done; }
    g->backend_ticket = backend;
  }
  r = g->b->drain_poll(g->b, g->backend_ticket);
  if (r == -EAGAIN) goto done;
  if (r) { r = quiesce_fail(g, r); goto done; }
  // Backend work can take time; recheck host generation and callbacks.
  r = quiesce_snapshot(g, ticket, &s);
  if (r) goto done;
  if (s.reset_invalidated) { r = quiesce_fail(g, -ESTALE); goto done; }
  if (!s.host_drained) { r = -EAGAIN; goto done; }
  g->quiesce_verified = true;
done:
  pthread_mutex_unlock(&g->quiesce_lock);
  return r;
}

int xh_virtio_gpu_quiesce_resume(xh_virtio *dev, uint64_t ticket)
{
  if (!ticket) return -EINVAL;
  gpu_state *g;
  int r = quiesce_lock(dev, &g);
  if (r) return r;
  r = quiesce_gate_lock(g);
  if (r) goto done;
  if (!combined_ticket_locked(g, ticket)) r = -ESTALE;
  else if (g->quiesce_fault) r = g->quiesce_fault;
  else {
    struct xh_gpu_gate_state s = gate_state_locked(g);
    if (s.reset_invalidated) r = quiesce_fail(g, -ESTALE);
    else if (!g->quiesce_verified || !g->backend_ticket || !s.host_drained) r = -EBUSY;
    else {
      // No reset or host lane can enter between these two opens.
      // Backend resume is a nonblocking, ticket-verified state change;
      // if it refuses, leave ingress closed and never synthesize replies.
      r = g->b->drain_resume(g->b, g->backend_ticket);
      if (!r) {
        g->backend_ticket = 0;
        g->quiesce_verified = false;
        gate_open_locked(g);
      } else if (r != -EAGAIN) r = quiesce_fail(g, r);
    }
  }
  quiesce_gate_unlock(g);
done:
  pthread_mutex_unlock(&g->quiesce_lock);
  return r;
}

void xh_virtio_gpu_idle(xh_virtio *dev)
{
  gpu_state *g = xh_virtio_opaque(dev);
  if (!g->blobs) return;
  pthread_mutex_lock(&g->pl);
  while (g->served != g->kicks || g->slow_done != g->slow_queued) pthread_cond_wait(&g->idle, &g->pl);
  pthread_mutex_unlock(&g->pl);
}

#ifdef XH_HOST_TEST
bool xh_virtio_gpu_fence_perf_snapshot(xh_virtio *dev, struct xh_fence_perf *out)
{
  if (!dev || !out) return false;
  gpu_state *g = xh_virtio_opaque(dev);
  if (!g || !g->b || !g->fence_trace) return false;
  pthread_mutex_lock(&g->pl);
  *out = g->fence_perf;
  pthread_mutex_unlock(&g->pl);
  return true;
}
#endif

static const xh_virtio_ops gpu_ops = { .device_id = 16, .features = 0, .nqueues = 2, .handle = gpu_handle,
                                       .config_read = gpu_config, .reset = gpu_reset };
static const xh_virtio_ops gpu_3d_ops = { .device_id = 16, .features = F_VIRGL | F_RESOURCE_BLOB | F_CONTEXT_INIT | F_CREATE_GUEST_HANDLE, .nqueues = 2,
                                          .handle = gpu_handle, .config_read = gpu_config, .reset = gpu_reset_3d, .manual = 1, .kick = gpu_kick };

xh_virtio *xh_virtio_gpu_create(uint64_t base, unsigned spi, unsigned width, unsigned height)
{
  gpu_state *g = calloc(1, sizeof *g);
  if (!g) return NULL;
  g->width = width;
  g->height = height;
  g->trace = getenv("ONEIOS_GPU_TRACE") != NULL;
  return xh_virtio_create(base, spi, &gpu_ops, g, "virtio-gpu");
}

xh_virtio *xh_virtio_gpu_create_3d(uint64_t base, unsigned spi, unsigned width, unsigned height, xh_gpu3d *b)
{
  if (!b) return xh_virtio_gpu_create(base, spi, width, height);
  gpu_state *g = calloc(1, sizeof *g);
  pthread_t thread;
  if (!g) return NULL;
  g->width = width;
  g->height = height;
  g->trace = getenv("ONEIOS_GPU_TRACE") != NULL;
  g->fence_trace = xh_display_trace_enabled();
  if (g->fence_trace) g->fence_report_since_ns = scanout_now_ns();
  g->b = b;
  g->blobs = calloc(BLOB_SLOTS, sizeof *g->blobs);
  g->wake = eventfd(0, EFD_CLOEXEC);
  pthread_mutex_init(&g->pl, NULL);
  pthread_mutex_init(&g->quiesce_lock, NULL);
  pthread_cond_init(&g->idle, NULL);
  pthread_mutex_init(&g->cmd, NULL);
  pthread_cond_init(&g->slow_cv, NULL);
  pthread_cond_init(&g->gate_cv, NULL);
  g->slow_tail = &g->slow_head;
  if (!g->blobs || g->wake < 0 || !(g->dev = xh_virtio_create(base, spi, &gpu_3d_ops, g, "virtio-gpu"))) return NULL;
  b->retire = gpu_retire;
  b->dev = g->dev;
  if (pthread_create(&thread, NULL, worker, g)) return NULL;
  pthread_detach(thread);
  if (pthread_create(&thread, NULL, slow_worker, g)) return NULL;
  pthread_detach(thread);
  return g->dev;
}
