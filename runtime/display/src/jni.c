// SPDX-License-Identifier: MIT
// liboneios-display.so: the native half of OneiOSDisplay (java/OneiOSDisplay.java). It owns the
// socket, the mapped frame and the copy into the layer's buffers; the Java half owns the layers.
#define _GNU_SOURCE
#include "xhd.h"
#include "frame_perf.h"
#include <android/native_window.h>
#include <android/native_window_jni.h>
#include <errno.h>
#include <fcntl.h>
#include <jni.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define FORMAT_BGRA_8888 XHD_BUFFER_BGRA_8888    // HAL_PIXEL_FORMAT_BGRA_8888: the guest's 8-bit bytes as they are
#define FORMAT_RGBX_8888 XHD_BUFFER_RGBX_8888
#define FORMAT_RGBA_FP16 XHD_BUFFER_RGBA_FP16    // the guest's half floats as they are

// ANativeWindow_setBuffersDataSpace and _get are API 28 and libnativewindow's (the Makefile links it: libandroid does
// not have them); the library is built for 30, so they are there.
struct context { int fd; struct xhd_frame frame; };

// SIGTERM, SIGINT and SIGHUP end the run loop through a pipe, so the Java half removes the layers.
static int signal_pipe[2] = { -1, -1 };
static volatile int stopping;
static void on_signal(int number)
{
  int saved = errno;
  char byte = (char)number;
  stopping = 1;
  if (signal_pipe[1] >= 0 && write(signal_pipe[1], &byte, 1) < 0) { }
  errno = saved;
}

JNIEXPORT jlong JNICALL Java_OneiOSDisplay_nOpen(JNIEnv *env, jclass type, jstring socket_path, jint wait_ms)
{
  (void)type;
  if (signal_pipe[0] < 0 && !pipe2(signal_pipe, O_CLOEXEC | O_NONBLOCK)) {
    struct sigaction action = { .sa_handler = on_signal, .sa_flags = SA_RESTART };
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    sigaction(SIGHUP, &action, NULL);
  }
  const char *path = (*env)->GetStringUTFChars(env, socket_path, NULL);
  if (!path) return 0;
  struct context *c = calloc(1, sizeof *c);
  int fd = c ? xhd_connect(path, wait_ms, &stopping) : -ENOMEM;
  if (fd < 0) fprintf(stderr, "oneios-display: %s: %s\n", path, stopping ? "stopped while waiting" : strerror(-fd));
  (*env)->ReleaseStringUTFChars(env, socket_path, path);
  if (fd < 0) { free(c); return 0; }
  c->fd = fd;
  c->frame.memfd = -1;
  return (jlong)(intptr_t)c;
}

// Reports the panel's mode, then takes xnuhost's hello. JNI_FALSE: no usable hello (nClose is still the caller's).
JNIEXPORT jboolean JNICALL Java_OneiOSDisplay_nHello(JNIEnv *env, jclass type, jlong handle, jint width, jint height, jint hz)
{
  (void)env; (void)type;
  struct context *c = (struct context *)(intptr_t)handle;
  int error = xhd_send_panel(c->fd, (uint32_t)width, (uint32_t)height, (uint32_t)hz);
  if (error) fprintf(stderr, "oneios-display: the panel's mode could not be sent: %s\n", strerror(-error));
  error = xhd_recv_hello(c->fd, &c->frame, 10000);
  if (error) fprintf(stderr, "oneios-display: no usable hello from xnuhost: %s\n", strerror(-error));
  return error ? JNI_FALSE : JNI_TRUE;
}

JNIEXPORT jintArray JNICALL Java_OneiOSDisplay_nInfo(JNIEnv *env, jclass type, jlong handle)
{
  (void)type;
  struct context *c = (struct context *)(intptr_t)handle;
  jint values[4] = { (jint)c->frame.width, (jint)c->frame.height, (jint)c->frame.stride, (jint)c->frame.format };
  jintArray array = (*env)->NewIntArray(env, 4);
  if (array) (*env)->SetIntArrayRegion(env, array, 0, 4, values);
  return array;
}

JNIEXPORT jintArray JNICALL Java_OneiOSDisplay_nFit(JNIEnv *env, jclass type, jint sw, jint sh, jint dw, jint dh)
{
  (void)type;
  struct xhd_fit fit;
  xhd_fit((uint32_t)sw, (uint32_t)sh, (uint32_t)dw, (uint32_t)dh, &fit);
  jint values[4] = { (jint)fit.x, (jint)fit.y, (jint)fit.w, (jint)fit.h };
  jintArray array = (*env)->NewIntArray(env, 4);
  if (array) (*env)->SetIntArrayRegion(env, array, 0, 4, values);
  return array;
}

// Posts frames until the socket closes (0) or a signal asks to stop (1); negative on an error.
// Pacing: the next buffer is only handed out when surfaceflinger has taken the last one, so
// ANativeWindow_lock blocks to the panel's vsync, and every flush that came meanwhile is one post.
// The buffer layout and dataspace a frame format gets (xhd_buffer_for): {buffer, dataspace}.
JNIEXPORT jintArray JNICALL Java_OneiOSDisplay_nBuffer(JNIEnv *env, jclass type, jint format)
{
  (void)type;
  int dataspace = 0;
  jint values[2] = { (jint)xhd_buffer_for((uint32_t)format, &dataspace), (jint)dataspace };
  jintArray array = (*env)->NewIntArray(env, 2);
  if (array) (*env)->SetIntArrayRegion(env, array, 0, 2, values);
  return array;
}

// Tags the window's buffers with the dataspace: what the numbers in them mean, so that surfaceflinger turns them into
// the panel's colours (One UI's colour mode decides how; nothing of it is changed here). Logs what the window has.
static void set_dataspace(ANativeWindow *window, int dataspace)
{
  int error = ANativeWindow_setBuffersDataSpace(window, dataspace);
  int now = ANativeWindow_getBuffersDataSpace(window);
  if (error) fprintf(stderr, "oneios-display: the dataspace %s (%#x) was refused (%d); the buffers say %s (%#x)\n",
                     xhd_dataspace_name(dataspace), (unsigned)dataspace, error, xhd_dataspace_name(now), (unsigned)now);
  else fprintf(stderr, "oneios-display: buffers tagged %s (dataspace %#x)\n", xhd_dataspace_name(now), (unsigned)now);
}

static const char *format_name(int format)
{
  return format == FORMAT_BGRA_8888 ? "BGRA_8888" : format == FORMAT_RGBX_8888 ? "RGBX_8888" : format == FORMAT_RGBA_FP16 ? "RGBA_FP16" : "other";
}

static double seconds_since(const struct timespec *t0)
{
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return (double)(t.tv_sec - t0->tv_sec) + (double)(t.tv_nsec - t0->tv_nsec) / 1e9;
}

// One line per five seconds (and a final partial window). These are posted
// SurfaceFlinger buffers, NOT guest animation frames. Active cadence only
// includes inter-post gaps <=250ms and needs at least three samples.
static void log_frame_perf(const struct xhd_frame_perf *p, uint64_t now_ns)
{
  uint64_t window_ms = now_ns > p->window_start_ns ? (now_ns - p->window_start_ns) / 1000000u : 0;
  fprintf(stderr,
          "oneios-display: perf: mono_ms=%llu window_ms=%llu posts=%llu posted_rate=%.2f "
          "active_cadence=%.2f active_gaps=%llu gap_p95_us=%llu "
          "lock_p95_us=%llu lock_max_us=%llu copy_p95_us=%llu copy_max_us=%llu "
          "post_p95_us=%llu post_max_us=%llu full_copies=%llu copied_pixels=%llu\n",
          (unsigned long long)(now_ns / 1000000u),
          (unsigned long long)window_ms,
          (unsigned long long)p->posts,
          xhd_perf_post_rate(p, now_ns),
          xhd_perf_active_cadence(p),
          (unsigned long long)p->active_gap_count,
          (unsigned long long)xhd_perf_quantile_bound_us(&p->gap, 95),
          (unsigned long long)xhd_perf_quantile_bound_us(&p->lock, 95),
          (unsigned long long)p->lock.max_us,
          (unsigned long long)xhd_perf_quantile_bound_us(&p->copy, 95),
          (unsigned long long)p->copy.max_us,
          (unsigned long long)xhd_perf_quantile_bound_us(&p->post, 95),
          (unsigned long long)p->post.max_us,
          (unsigned long long)p->full_copies,
          (unsigned long long)p->copied_pixels);
}

// Optional transport->buffer-post report; actual panel presentation is NOT sampled.
// One Android post can include several guest flush records. The oldest/latest ages
// bound coalesced flushes instead of pretending each is a separate displayed frame.
static void log_frame_trace(const struct xhd_frame_perf *p, uint64_t now_ns)
{
  fprintf(stderr,
          "oneios-display: frame-trace: mono_ms=%llu traced_posts=%llu traced_flushes=%llu coalesced=%llu "
          "seq_gaps=%llu invalid=%llu legacy_after_enable=%llu "
          "flush_to_helper_p95_us=%llu flush_to_post_latest_p95_us=%llu "
          "flush_to_post_oldest_p95_us=%llu latest_max_us=%llu oldest_max_us=%llu "
          "endpoint=ANativeWindow_unlockAndPost_not_physical_present\n",
          (unsigned long long)(now_ns / 1000000u),
          (unsigned long long)p->traced_posts,
          (unsigned long long)p->traced_flushes,
          (unsigned long long)p->traced_coalesced,
          (unsigned long long)p->traced_gaps,
          (unsigned long long)p->traced_bad,
          (unsigned long long)p->traced_legacy,
          (unsigned long long)xhd_perf_quantile_bound_us(&p->flush_to_helper, 95),
          (unsigned long long)xhd_perf_quantile_bound_us(&p->flush_to_post_latest, 95),
          (unsigned long long)xhd_perf_quantile_bound_us(&p->flush_to_post_oldest, 95),
          (unsigned long long)p->flush_to_post_latest.max_us,
          (unsigned long long)p->flush_to_post_oldest.max_us);
}

// ready_path: SESSION/ready (--session), or NULL (--socket): the first post waits for it (xhd_hold_first). Until the
// first post the layer has no buffer and the OneOS boot screen under it shows.
JNIEXPORT jint JNICALL Java_OneiOSDisplay_nRun(JNIEnv *env, jclass type, jlong handle, jobject surface, jint format, jint dataspace,
                                               jstring ready_path)
{
  (void)type;
  struct context *c = (struct context *)(intptr_t)handle;
  const struct xhd_frame *f = &c->frame;
  ANativeWindow *window = ANativeWindow_fromSurface(env, surface);
  if (!window) { fprintf(stderr, "oneios-display: no native window for the layer\n"); return -1; }
  ANativeWindow_setBuffersGeometry(window, (int32_t)f->width, (int32_t)f->height, format);
  set_dataspace(window, dataspace);
  char ready_file[600] = "";
  if (ready_path) {
    const char *p = (*env)->GetStringUTFChars(env, ready_path, NULL);
    if (p) { snprintf(ready_file, sizeof ready_file, "%s", p); (*env)->ReleaseStringUTFChars(env, ready_path, p); }
  }
  struct xhd_rect pending = { 0, 0, f->width, f->height };
  unsigned long frames = 0, held_flushes = 0;
  bool held = false;
  struct timespec hold_start;
  int result;
  struct xhd_frame_perf perf;
  struct xhd_trace_state trace = { 0 };
  xhd_perf_begin(&perf, xhd_perf_clock_ns());
  for (;;) {
    // Held: the guest's frame is not shown yet, the damage adds up, and `ready` is looked for at every flush and
    // every XHD_HOLD_POLL_MS between them (a guest that drew its frame with content and then nothing more).
    bool hold = frames == 0 && xhd_hold_first(ready_file);
    if (hold && !held) {
      held = true;
      clock_gettime(CLOCK_MONOTONIC, &hold_start);
      fprintf(stderr, "oneios-display: the first frame waits for %s (xnuhost's first frame of the guest's own with content); the boot screen stays\n", ready_file);
    }
    struct pollfd fds[2] = { { c->fd, POLLIN, 0 }, { signal_pipe[0], POLLIN, 0 } };
    // Wake once per second while static, so the five-second profiler prints
    // idle windows as idle (not as phantom 60 FPS). No timer touches the guest.
    int ready = poll(fds, 2, hold ? XHD_HOLD_POLL_MS : pending.w ? 0 : 1000);
    if (ready < 0 && errno != EINTR) { result = -3; break; }
    if (stopping || (ready > 0 && fds[1].revents)) { result = 1; break; }
    if (xhd_drain_trace(c->fd, f, &pending, &trace) < 0) { result = 0; break; }
    uint64_t tick_ns = xhd_perf_clock_ns();
    if (xhd_perf_due(&perf, tick_ns)) {
      log_frame_perf(&perf, tick_ns);
      if (trace.active) log_frame_trace(&perf, tick_ns);
      xhd_perf_next_window(&perf, tick_ns);
    }
    if (hold) { if (ready > 0) held_flushes++; continue; }
    if (!pending.w) continue;
    // The first posts fill whole buffers; after that the window copies back what the last frame
    // had and hands out the rectangle that has to be drawn (it may be larger than what was asked).
    ARect dirty = { (int32_t)pending.x, (int32_t)pending.y, (int32_t)(pending.x + pending.w), (int32_t)(pending.y + pending.h) };
    if (frames < 4) dirty = (ARect){ 0, 0, (int32_t)f->width, (int32_t)f->height };
    ANativeWindow_Buffer buffer;
    uint64_t lock_start_ns = xhd_perf_clock_ns();
    int error = ANativeWindow_lock(window, &buffer, &dirty);
    uint64_t lock_done_ns = xhd_perf_clock_ns();
    if (error) {
      if (frames == 0 && format != FORMAT_RGBX_8888) {
        // No B,G,R,A buffers here: R,G,B,X and a swap. No RGBA_FP16 ones: B,G,R,A, the half floats encoded to sRGB
        // and clamped (what is outside sRGB is lost), tagged sRGB.
        int next = format == FORMAT_RGBA_FP16 ? FORMAT_BGRA_8888 : FORMAT_RGBX_8888;
        fprintf(stderr, "oneios-display: no buffer in format %d %s (%d), using %s\n", format, format_name(format), error, format_name(next));
        format = next;
        ANativeWindow_setBuffersGeometry(window, (int32_t)f->width, (int32_t)f->height, format);
        if (dataspace == XHD_DATASPACE_SCRGB_LINEAR || dataspace == XHD_DATASPACE_SCRGB) set_dataspace(window, dataspace = XHD_DATASPACE_SRGB);
        continue;
      }
      fprintf(stderr, "oneios-display: the layer's buffer could not be locked (%d)\n", error);
      result = -2;
      break;
    }
    uint64_t copy_start_ns = xhd_perf_clock_ns();
    uint64_t copied_pixels = 0;
    bool full_copy = false;
    struct xhd_rect r = { 0, 0, 0, 0 };
    if (dirty.left < 0) dirty.left = 0;
    if (dirty.top < 0) dirty.top = 0;
    if (dirty.right > dirty.left && dirty.bottom > dirty.top) {
      r = (struct xhd_rect){ (uint32_t)dirty.left, (uint32_t)dirty.top, (uint32_t)(dirty.right - dirty.left), (uint32_t)(dirty.bottom - dirty.top) };
      uint32_t width = (uint32_t)buffer.width < f->width ? (uint32_t)buffer.width : f->width;
      uint32_t height = (uint32_t)buffer.height < f->height ? (uint32_t)buffer.height : f->height;
      // The buffer's own format decides the copy (RGBA_8888 and RGBX_8888 are both R,G,B bytes).
      int layout = buffer.format == FORMAT_BGRA_8888 || buffer.format == FORMAT_RGBA_FP16 ? buffer.format : FORMAT_RGBX_8888;
      size_t bytes = layout == FORMAT_RGBA_FP16 ? 8 : 4;
      if (buffer.width > 0 && buffer.height > 0 && buffer.stride >= buffer.width && xhd_rect_clip(&r, width, height)) {
        if (xhd_copy(buffer.bits, (size_t)buffer.stride * bytes, layout, f->pixels, f->stride, f->format, r) == 0) {
          copied_pixels = (uint64_t)r.w * r.h;
          full_copy = r.w == f->width && r.h == f->height;
        }
      }
    }
    uint64_t copy_done_ns = xhd_perf_clock_ns();
    ANativeWindow_unlockAndPost(window);
    uint64_t post_done_ns = xhd_perf_clock_ns();
    xhd_perf_record(&perf, post_done_ns, lock_done_ns - lock_start_ns,
                    copy_done_ns - copy_start_ns, post_done_ns - copy_done_ns,
                    copied_pixels, full_copy);
    if (trace.active) xhd_perf_record_trace(&perf, &trace.pending, post_done_ns);
    trace.pending = (struct xhd_trace_pending){ 0 };  // only after a buffer was posted
    if (frames++ == 0) {
      char waited[96] = "";
      if (held) snprintf(waited, sizeof waited, "; held %.1f s for session/ready, %lu wakes for flushes not shown", seconds_since(&hold_start), held_flushes);
      fprintf(stderr, "oneios-display: first frame posted (%dx%d buffer, stride %d, format %d %s, dataspace %#x %s; the guest's frame: %s%s)\n",
              buffer.width, buffer.height, buffer.stride, buffer.format, format_name(buffer.format), (unsigned)ANativeWindow_getBuffersDataSpace(window),
              xhd_dataspace_name(ANativeWindow_getBuffersDataSpace(window)), xh_pixels_name(f->format), waited);
    }
    pending = (struct xhd_rect){ 0, 0, 0, 0 };
  }
  // Preserve the last partial window even when the guest disconnects or the
  // device-side timeout stops the preview while a UI animation is in flight.
  uint64_t finished_ns = xhd_perf_clock_ns();
  if (perf.posts || xhd_perf_due(&perf, finished_ns)) {
    log_frame_perf(&perf, finished_ns);
    if (trace.active) log_frame_trace(&perf, finished_ns);
  }
  ANativeWindow_release(window);
  fprintf(stderr, "oneios-display: %s after %lu frames\n", result == 0 ? "the socket closed" : result == 1 ? "asked to stop" : "error", frames);
  return result;
}

JNIEXPORT void JNICALL Java_OneiOSDisplay_nClose(JNIEnv *env, jclass type, jlong handle)
{
  (void)env; (void)type;
  struct context *c = (struct context *)(intptr_t)handle;
  if (!c) return;
  close(c->fd);
  xhd_frame_close(&c->frame);
  free(c);
}
