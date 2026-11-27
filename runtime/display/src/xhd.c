// SPDX-License-Identifier: MIT
#define _GNU_SOURCE
#include "xhd.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <poll.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

static long long now_ms(void)
{
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

int xhd_check_hello(const struct xhd_message *m, size_t length, off_t memfd_size)
{
  if (length != sizeof *m || memcmp(m->magic, "XHD1", 4)) return -EPROTO;
  uint32_t width = m->a, height = m->b, stride = m->c, format = m->d;
  if (!width || !height || width > XHD_MAX_SIDE || height > XHD_MAX_SIDE) return -EINVAL;
  unsigned bpp = xh_pixels_bpp(format);
  if (!bpp) return -EINVAL;
  if (stride < width * bpp || stride > XHD_MAX_SIDE * 8 || stride % bpp) return -EINVAL;
  if (memfd_size < 0 || (uint64_t)stride * height > (uint64_t)memfd_size) return -EINVAL;
  return 0;
}

int xhd_connect(const char *path, int wait_ms, const volatile int *stop)
{
  struct sockaddr_un addr = { .sun_family = AF_UNIX };
  if (strlen(path) >= sizeof addr.sun_path) return -ENAMETOOLONG;
  strcpy(addr.sun_path, path);
  long long end = now_ms() + (wait_ms > 0 ? wait_ms : 0);
  int error = ENOENT;
  for (;;) {
    struct stat st;
    if (lstat(path, &st)) error = errno;
    else if (!S_ISSOCK(st.st_mode)) return -ENOTSOCK;       // a link or a file put there: not ours to follow
    else {
      int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
      if (fd < 0) return -errno;
      if (!connect(fd, (struct sockaddr *)&addr, sizeof addr)) return fd;
      error = errno;
      close(fd);
      if (error != ECONNREFUSED && error != ENOENT && error != EAGAIN && error != EINTR) return -error;
    }
    if ((stop && *stop) || now_ms() >= end) return -error;
    struct timespec nap = { 0, 100 * 1000000 };
    nanosleep(&nap, NULL);
  }
}

int xhd_send_panel(int fd, uint32_t width, uint32_t height, uint32_t hz)
{
  struct xhd_message m = { { 'X', 'H', 'D', 'P' }, width, height, hz, 0 };
  return send(fd, &m, sizeof m, MSG_NOSIGNAL) < 0 ? -errno : 0;
}

int xhd_recv_hello(int fd, struct xhd_frame *frame, int timeout_ms)
{
  memset(frame, 0, sizeof *frame);
  frame->memfd = -1;
  struct pollfd p = { fd, POLLIN, 0 };
  int ready;
  do ready = poll(&p, 1, timeout_ms); while (ready < 0 && errno == EINTR);
  if (ready < 0) return -errno;
  if (!ready) return -ETIMEDOUT;
  struct xhd_message hello;
  char control[CMSG_SPACE(sizeof(int) * 4)];
  struct iovec iov = { &hello, sizeof hello };
  struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1, .msg_control = control, .msg_controllen = sizeof control };
  ssize_t n;
  do n = recvmsg(fd, &msg, MSG_CMSG_CLOEXEC); while (n < 0 && errno == EINTR);
  if (n < 0) return -errno;
  // Every descriptor that came is ours to close; the first is the frame.
  int memfd = -1;
  for (struct cmsghdr *cm = CMSG_FIRSTHDR(&msg); cm; cm = CMSG_NXTHDR(&msg, cm)) {
    if (cm->cmsg_level != SOL_SOCKET || cm->cmsg_type != SCM_RIGHTS) continue;
    size_t count = (cm->cmsg_len - CMSG_LEN(0)) / sizeof(int);
    for (size_t i = 0; i < count; i++) {
      int got;
      memcpy(&got, CMSG_DATA(cm) + i * sizeof(int), sizeof(int));
      if (memfd < 0) memfd = got; else close(got);
    }
  }
  if (n == 0) { if (memfd >= 0) close(memfd); return -ECONNRESET; }
  if (memfd < 0 || (msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC))) { if (memfd >= 0) close(memfd); return -EPROTO; }
  struct stat st;
  int bad = fstat(memfd, &st) ? -errno : !S_ISREG(st.st_mode) ? -EINVAL : xhd_check_hello(&hello, (size_t)n, st.st_size);
  if (bad) { close(memfd); return bad; }
  size_t bytes = (size_t)hello.c * hello.b;
  void *map = mmap(NULL, bytes, PROT_READ, MAP_SHARED, memfd, 0);
  if (map == MAP_FAILED) { int e = errno; close(memfd); return -e; }
  frame->width = hello.a; frame->height = hello.b; frame->stride = hello.c; frame->format = hello.d;
  frame->memfd = memfd; frame->pixels = map; frame->bytes = bytes;
  return 0;
}

void xhd_frame_close(struct xhd_frame *frame)
{
  if (frame->pixels) munmap((void *)frame->pixels, frame->bytes);
  if (frame->memfd >= 0) close(frame->memfd);
  frame->pixels = NULL;
  frame->memfd = -1;
}

int xhd_rect_clip(struct xhd_rect *r, uint32_t width, uint32_t height)
{
  if (!r->w || !r->h || r->x >= width || r->y >= height) { r->x = r->y = r->w = r->h = 0; return 0; }
  if (r->w > width - r->x) r->w = width - r->x;
  if (r->h > height - r->y) r->h = height - r->y;
  return 1;
}

void xhd_rect_union(struct xhd_rect *into, const struct xhd_rect *r)
{
  if (!r->w || !r->h) return;
  if (!into->w || !into->h) { *into = *r; return; }
  uint32_t x0 = into->x < r->x ? into->x : r->x, y0 = into->y < r->y ? into->y : r->y;
  uint64_t ax = (uint64_t)into->x + into->w, bx = (uint64_t)r->x + r->w, ay = (uint64_t)into->y + into->h, by = (uint64_t)r->y + r->h;
  uint64_t x1 = ax > bx ? ax : bx, y1 = ay > by ? ay : by;
  into->x = x0; into->y = y0; into->w = (uint32_t)(x1 - x0); into->h = (uint32_t)(y1 - y0);
}

int xhd_hold_first(const char *ready)
{
  struct stat st;
  return ready && *ready && stat(ready, &st) && errno == ENOENT;
}

static uint64_t xhd_mono_ns(void)
{
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t)) return 0;
  return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static void xhd_trace_note(struct xhd_trace_state *state, const struct xh_frame_trace_packet_v3 *packet,
                           bool valid, uint64_t received_ns)
{
  struct xhd_trace_pending *p = &state->pending;
  const struct xh_frame_trace_packet *base = &packet->base.base;
  const struct xh_frame_trace_packet_v2 *scanout = &packet->base;
  // Never attribute malformed, future or out-of-order timestamps to a post.
  if (!valid || base->flush_mono_ns > received_ns || !received_ns ||
      (state->last_seq && base->seq <= state->last_seq)) {
    p->bad++;
    return;
  }
  state->active = true;
  if (state->last_seq && base->seq - state->last_seq > 1) p->seq_gaps += base->seq - state->last_seq - 1;
  state->last_seq = base->seq;
  if (!p->traced || base->flush_mono_ns < p->oldest_flush_ns) p->oldest_flush_ns = base->flush_mono_ns;
  if (!p->traced || base->flush_mono_ns >= p->newest_flush_ns) {
    p->newest_flush_ns = base->flush_mono_ns;
    p->newest_recv_ns = received_ns;
  }
  if (!p->traced) p->first_seq = base->seq;
  p->last_seq = base->seq;
  p->traced++;

  if (base->version != XH_FRAME_TRACE_VERSION_SCANOUT &&
      base->version != XH_FRAME_TRACE_VERSION_PROVENANCE) return;
  if (!p->scanout_packets || scanout->scanout_start_ns < p->oldest_scanout_start_ns)
    p->oldest_scanout_start_ns = scanout->scanout_start_ns;
  const uint64_t copy_ns = scanout->scanout_copied_ns - scanout->scanout_start_ns;
  p->scanout_copy_sum_ns += copy_ns;
  if (copy_ns > p->scanout_copy_max_ns) p->scanout_copy_max_ns = copy_ns;
  p->scanout_packets++;
  if (scanout->scanout_kind == XH_FRAME_SCANOUT_BLOB) p->scanout_blob++;
  else p->scanout_2d++;

  if (base->version != XH_FRAME_TRACE_VERSION_PROVENANCE) return;
  if (!p->provenance_packets) {
    p->provenance_queue_gen = packet->queue_generation;
    p->provenance_resource_gen = packet->resource_generation;
    p->provenance_resource_id = scanout->resource_id;
    p->provenance_owner_ctx = packet->owner_context;
  } else if (p->provenance_queue_gen != packet->queue_generation ||
             p->provenance_resource_gen != packet->resource_generation ||
             p->provenance_resource_id != scanout->resource_id ||
             p->provenance_owner_ctx != packet->owner_context) {
    p->provenance_mixed = true;
  }
  p->provenance_packets++;
}

static int drain_trace_limit(int fd, const struct xhd_frame *frame, struct xhd_rect *damage,
                             struct xhd_trace_state *trace, unsigned limit, unsigned *accepted)
{
  // Bounded, nonblocking drain: an overactive guest cannot starve posting.
  if (accepted) *accepted = 0;
  for (unsigned i = 0; i < limit; i++) {
    struct xh_frame_trace_packet_v3 packet;
    // Linux SOCK_SEQPACKET + MSG_TRUNC returns the actual record length even
    // when only the prefix fits. Never accept an oversized record as valid v3.
    ssize_t n = recv(fd, &packet, sizeof packet, MSG_DONTWAIT | MSG_TRUNC);
    if (n < 0) {
      if (errno == EINTR) continue;
      if (errno == EAGAIN || errno == EWOULDBLOCK) return 0;
      fprintf(stderr, "oneios-display: reading xnuhost's socket failed: %s\n", strerror(errno));
      return -1;
    }
    if (n == 0) { fprintf(stderr, "oneios-display: xnuhost closed the socket\n"); return -1; }
    if (trace && n >= 4 &&
        (!memcmp(packet.base.base.magic, "XHDQ", 4) || !memcmp(packet.base.base.magic, "XHDR", 4))) {
      struct xh_display_barrier p;
      if (n != (ssize_t)sizeof p) return -1;
      memcpy(&p, &packet, sizeof p);
      uint64_t t = xh_display_barrier_ticket(&p);
      if (xh_display_barrier_valid(&p, 'Q') && trace->barrier == XHD_OPEN &&
          t > trace->barrier_ticket) {
        trace->barrier_ticket = t;
        trace->barrier = XHD_PARK_ACK;
      } else if (xh_display_barrier_valid(&p, 'R') &&
                 trace->barrier == XHD_PARKED && t == trace->barrier_ticket) {
        trace->barrier = XHD_RESUME_ACK;
      } else return -1;
      // Preserve record order. If called after a successful window lock,
      // finish that copy/post first; do not ACK from this parser.
      return 0;
    }
    if (n < 4 || memcmp(packet.base.base.magic, "XHDF", 4)) continue;
    if (trace && trace->barrier != XHD_OPEN) return -1;
    // Keep legacy-compatible damage for an unknown/truncated extension only
    // when the complete 20-byte rectangle exists; never use its metadata.
    if (trace && n != 20) trace->active = true;
    if (n < 20) {
      if (trace) trace->pending.bad++;
      continue;
    }
    struct xhd_rect r = { packet.base.base.x, packet.base.base.y,
                          packet.base.base.w, packet.base.base.h };
    if (!xhd_rect_clip(&r, frame->width, frame->height)) {
      if (trace && n != 20) trace->pending.bad++;
      continue;
    }
    xhd_rect_union(damage, &r);
    if (accepted) (*accepted)++;
    if (!trace) continue;
    if (n == (ssize_t)sizeof packet.base.base)
      xhd_trace_note(trace, &packet, xh_frame_trace_valid(&packet.base.base), xhd_mono_ns());
    else if (n == (ssize_t)sizeof packet.base)
      xhd_trace_note(trace, &packet, xh_frame_trace_v2_valid(&packet.base), xhd_mono_ns());
    else if (n == (ssize_t)sizeof packet)
      xhd_trace_note(trace, &packet, xh_frame_trace_v3_valid(&packet), xhd_mono_ns());
    else if (n == 20) trace->pending.legacy++;
    else trace->pending.bad++;
  }
  return 0;
}

int xhd_quiesce_boundary(int fd, const struct xhd_frame *frame,
                         struct xhd_rect *damage, struct xhd_trace_state *trace)
{
  if (trace->barrier == XHD_OPEN) return 0;
  if (trace->barrier == XHD_PARKED) return 1;
  bool park = trace->barrier == XHD_PARK_ACK;
  if (park) {
    *damage = (struct xhd_rect){0};
    trace->pending = (struct xhd_trace_pending){0};
  }
  struct xh_display_barrier p = xh_display_barrier_make(park ? 'A' : 'B', trace->barrier_ticket);
  ssize_t n = send(fd, &p, sizeof p, MSG_DONTWAIT | MSG_NOSIGNAL);
  if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)) return 1;
  if (n != (ssize_t)sizeof p) return -1;
  trace->barrier = park ? XHD_PARKED : XHD_OPEN;
  if (!park) *damage = (struct xhd_rect){0, 0, frame->width, frame->height};
  return park ? 1 : 0;
}

int xhd_drain_trace(int fd, const struct xhd_frame *frame, struct xhd_rect *damage, struct xhd_trace_state *trace)
{
  return drain_trace_limit(fd, frame, damage, trace, 4096, NULL);
}

int xhd_drain_after_lock(int fd, const struct xhd_frame *frame, struct xhd_rect locked,
                         struct xhd_rect *damage, struct xhd_trace_state *trace, unsigned *accepted)
{
  if (accepted) *accepted = 0;
  if (locked.x || locked.y || locked.w != frame->width || locked.h != frame->height ||
      !locked.w || !locked.h) return 0;
  return drain_trace_limit(fd, frame, damage, trace, XHD_POST_LOCK_DRAIN_LIMIT, accepted);
}

int xhd_drain(int fd, const struct xhd_frame *frame, struct xhd_rect *damage)
{
  return xhd_drain_trace(fd, frame, damage, NULL);
}

void xhd_fit(uint32_t sw, uint32_t sh, uint32_t dw, uint32_t dh, struct xhd_fit *fit)
{
  memset(fit, 0, sizeof *fit);
  if (!sw || !sh || !dw || !dh) return;
  uint64_t w, h;
  if ((uint64_t)sw * dh <= (uint64_t)sh * dw) {        // the source is the narrower: full height, bars left and right
    h = dh;
    w = ((uint64_t)sw * dh + sh / 2) / sh;
  } else {                                             // full width, bars above and below
    w = dw;
    h = ((uint64_t)sh * dw + sw / 2) / sw;
  }
  if (w < 1) w = 1;
  if (h < 1) h = 1;
  if (w > dw) w = dw;
  if (h > dh) h = dh;
  fit->w = (uint32_t)w; fit->h = (uint32_t)h;
  fit->x = (dw - fit->w) / 2; fit->y = (dh - fit->h) / 2;
}

int xhd_copy(uint8_t *dst, size_t dst_stride, int buffer, const uint8_t *src, size_t src_stride, uint32_t format, struct xhd_rect r)
{
  unsigned in = xh_pixels_bpp(format), out = buffer == XHD_BUFFER_RGBA_FP16 ? 8 : buffer == XHD_BUFFER_BGRA_8888 || buffer == XHD_BUFFER_RGBX_8888 ? 4 : 0;
  if (!in || !out) return -EINVAL;
  if (!r.w || !r.h) return 0;
  // Identical layout, no row padding, and full-width damage: the exact rows
  // form a single contiguous span. Never include padding or adjacent pixels.
  const bool raw = (format == XHD_FORMAT_RGBA16F && buffer == XHD_BUFFER_RGBA_FP16) ||
                   (format == XHD_FORMAT_BGRX && buffer == XHD_BUFFER_BGRA_8888);
  if (raw && r.x == 0 && (size_t)r.w <= SIZE_MAX / in) {
    const size_t row_bytes = (size_t)r.w * in;
    if (src_stride == row_bytes && dst_stride == row_bytes &&
        (uint64_t)r.y + r.h <= SIZE_MAX / row_bytes) {
      memcpy(dst + (size_t)r.y * row_bytes, src + (size_t)r.y * row_bytes,
             (size_t)r.h * row_bytes);
      return 0;
    }
  }
  for (uint32_t row = r.y; row < r.y + r.h; row++) {
    const uint8_t *s = src + (size_t)row * src_stride + (size_t)r.x * in;
    uint8_t *d = dst + (size_t)row * dst_stride + (size_t)r.x * out;
    if (format == XHD_FORMAT_RGBA16F) {
      if (buffer == XHD_BUFFER_RGBA_FP16) memcpy(d, s, (size_t)r.w * 8);
      else xh_pixels_rgba16f_to_8(d, s, r.w, buffer == XHD_BUFFER_RGBX_8888);
    } else if (buffer == XHD_BUFFER_BGRA_8888) memcpy(d, s, (size_t)r.w * 4);
    else if (buffer == XHD_BUFFER_RGBA_FP16) xh_pixels_bgrx8_to_rgba16f(d, s, r.w);
    else for (uint32_t i = 0; i < r.w; i++, s += 4, d += 4) { d[0] = s[2]; d[1] = s[1]; d[2] = s[0]; d[3] = 0xff; }
  }
  return 0;
}

int xhd_buffer_for(uint32_t format, int *dataspace)
{
  if (format == XHD_FORMAT_BGRX) { *dataspace = XHD_DATASPACE_SRGB; return XHD_BUFFER_BGRA_8888; }
  if (format == XHD_FORMAT_RGBA16F) { *dataspace = XHD_DATASPACE_SCRGB_LINEAR; return XHD_BUFFER_RGBA_FP16; }
  *dataspace = XHD_DATASPACE_UNKNOWN;
  return 0;
}

static const struct { const char *name; int value; } dataspaces[] = {
  { "unknown", XHD_DATASPACE_UNKNOWN }, { "srgb", XHD_DATASPACE_SRGB }, { "p3", XHD_DATASPACE_DISPLAY_P3 },
  { "scrgb", XHD_DATASPACE_SCRGB }, { "scrgb-linear", XHD_DATASPACE_SCRGB_LINEAR },
};

const char *xhd_dataspace_name(int dataspace)
{
  for (size_t i = 0; i < sizeof dataspaces / sizeof *dataspaces; i++) if (dataspaces[i].value == dataspace) return dataspaces[i].name;
  return "other";
}

int xhd_dataspace_parse(const char *name)
{
  if (!strcmp(name, "auto")) return -1;
  for (size_t i = 0; i < sizeof dataspaces / sizeof *dataspaces; i++) if (!strcmp(dataspaces[i].name, name)) return dataspaces[i].value;
  return -2;
}

int xhd_listen(const char *path)
{
  struct sockaddr_un addr = { .sun_family = AF_UNIX };
  if (strlen(path) >= sizeof addr.sun_path) return -ENAMETOOLONG;
  strcpy(addr.sun_path, path);
  unlink(path);
  int fd = socket(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0);
  if (fd < 0) return -errno;
  if (bind(fd, (struct sockaddr *)&addr, sizeof addr) || listen(fd, 2)) { int e = errno; close(fd); return -e; }
  return fd;
}

int xhd_send_hello(int fd, uint32_t width, uint32_t height, uint32_t stride, uint32_t format, int memfd)
{
  struct xhd_message hello = { { 'X', 'H', 'D', '1' }, width, height, stride, format };
  char control[CMSG_SPACE(sizeof(int))];
  struct iovec iov = { &hello, sizeof hello };
  struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1, .msg_control = control, .msg_controllen = sizeof control };
  memset(control, 0, sizeof control);
  struct cmsghdr *cm = CMSG_FIRSTHDR(&msg);
  cm->cmsg_level = SOL_SOCKET;
  cm->cmsg_type = SCM_RIGHTS;
  cm->cmsg_len = CMSG_LEN(sizeof(int));
  memcpy(CMSG_DATA(cm), &memfd, sizeof(int));
  return sendmsg(fd, &msg, MSG_NOSIGNAL) < 0 ? -errno : 0;
}

int xhd_send_flush(int fd, uint32_t x, uint32_t y, uint32_t w, uint32_t h)
{
  struct xhd_message m = { { 'X', 'H', 'D', 'F' }, x, y, w, h };
  return send(fd, &m, sizeof m, MSG_NOSIGNAL) < 0 ? -errno : 0;
}

int xhd_memfd(const char *name, size_t bytes)
{
  int fd = (int)syscall(SYS_memfd_create, name, 1u /* MFD_CLOEXEC */);
  if (fd < 0) return -errno;
  if (ftruncate(fd, (off_t)bytes)) { int e = errno; close(fd); return -e; }
  return fd;
}
