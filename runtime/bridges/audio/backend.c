// SPDX-License-Identifier: MIT
// Audio back ends for the virtio-snd device: the AAudio helper process and a null one.
//
// Why a helper: AAudio is a shared library (libaaudio.so) and xnuhost is a static binary. The
// helper (bin/oneios-audio, audio/aaudio_helper.c) is a small dynamic executable that plays what it
// is sent through One UI's audioserver, which keeps running in a session, and sends back what the
// microphone records.
#define _GNU_SOURCE
#include "bridges/bridges.h"
#include "audio_proto.h"
#include "quiesce_link.h"
#include <errno.h>
#include <poll.h>
#include <spawn.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

extern char **environ;

// ---- null ---------------------------------------------------------------------------------------
static int null_start(void *ctx, bool output, unsigned rate, unsigned channels) { (void)ctx; (void)output; (void)rate; (void)channels; return 0; }
static int null_stop(void *ctx, bool output) { (void)ctx; (void)output; return 0; }
static int null_write(void *ctx, const int16_t *pcm, unsigned frames) { (void)ctx; (void)pcm; return (int)frames; }
static int null_read(void *ctx, int16_t *pcm, unsigned frames)
{
  (void)ctx;
  usleep(frames * 1000000u / 48000u);          // silence in real time
  memset(pcm, 0, frames * 2);
  return (int)frames;
}
static void null_close(void *ctx) { (void)ctx; }
static const br_audio_backend null_backend = { null_start, null_stop, null_write, null_read, null_close };
const br_audio_backend *br_audio_null(void **ctx) { *ctx = NULL; return &null_backend; }

// ---- the helper ---------------------------------------------------------------------------------
typedef struct { int fd; pid_t pid; unsigned in_channels; auq_link barrier; bool report_fault; } helper;

static int send_message(helper *h, const struct au_header *header, const void *payload, size_t length)
{
  struct iovec iov[2] = { { (void *)(uintptr_t)header, sizeof *header }, { (void *)(uintptr_t)payload, length } };
  struct msghdr message = { .msg_iov = iov, .msg_iovlen = payload ? 2 : 1 };
  // Never block a vCPU on a helper that is behind: a full socket drops the period.
  return sendmsg(h->fd, &message, MSG_DONTWAIT | MSG_NOSIGNAL) < 0 ? -errno : 0;
}

static int helper_start(void *ctx, bool output, unsigned rate, unsigned channels)
{
  helper *h = ctx;
  struct au_header header = { .kind = AU_START, .output = output, .channels = (uint8_t)channels, .value = rate };
  if (!output) {
    // What the last recording left in the socket (and the helper's reports) is old: drop it.
    struct { struct au_header header; int16_t pcm[AU_MAX_FRAMES]; } stale;
    ssize_t n;
    while ((n = recv(h->fd, &stale, sizeof stale, MSG_DONTWAIT)) > 0) {
      if (n >= (ssize_t)sizeof stale.header && stale.header.kind == AU_STATE && stale.header.value)
        __atomic_store_n(&h->report_fault, true, __ATOMIC_RELEASE);
    }
    h->in_channels = channels;
  }
  return send_message(h, &header, NULL, 0);
}

static int helper_stop(void *ctx, bool output)
{
  struct au_header header = { .kind = AU_STOP, .output = output };
  return send_message(ctx, &header, NULL, 0);
}

static int helper_write(void *ctx, const int16_t *pcm, unsigned frames)
{
  if (frames > AU_MAX_FRAMES) frames = AU_MAX_FRAMES;
  struct au_header header = { .kind = AU_PCM, .output = 1, .channels = 2, .value = frames };
  return send_message(ctx, &header, pcm, frames * 4u) ? 0 : (int)frames;
}

static int helper_read(void *ctx, int16_t *pcm, unsigned frames)
{
  helper *h = ctx;
  struct { struct au_header header; int16_t pcm[AU_MAX_FRAMES]; } packet;
  struct pollfd wait = { .fd = h->fd, .events = POLLIN };
  for (;;) {
    if (poll(&wait, 1, 100) <= 0) return 0;
    ssize_t got = recv(h->fd, &packet, sizeof packet, MSG_DONTWAIT);
    if (got < (ssize_t)sizeof packet.header) return got == 0 ? -EPIPE : 0;
    if (packet.header.kind == AU_STATE) {
      if (packet.header.value) {
        __atomic_store_n(&h->report_fault, true, __ATOMIC_RELEASE);
        br_log(0, "audio: helper: %s stream: %s", packet.header.output ? "speaker" : "microphone", strerror((int)packet.header.value));
      }
      continue;
    }
    if (packet.header.kind != AU_PCM || packet.header.output) continue;
    unsigned have = (unsigned)(((size_t)got - sizeof packet.header) / 2);
    if (have > packet.header.value) have = packet.header.value;
    if (have > frames) have = frames;
    memcpy(pcm, packet.pcm, have * 2);
    return (int)have;
  }
}

static void helper_close(void *ctx)
{
  helper *h = ctx;
  close(h->fd);                                  // the helper exits when its socket closes
  if (h->barrier.pidfd >= 0) close(h->barrier.pidfd);
  free(h);
}

static const br_audio_backend helper_backend = { helper_start, helper_stop, helper_write, helper_read, helper_close };

int br_audio_probe_latency(const br_audio_backend *backend, void *ctx, unsigned timeout_ms)
{
  if (backend != &helper_backend || !ctx) return -ENOTSUP;
  helper *h = ctx;
  struct au_header ask = { .kind = AU_PROBE, .output = 1 };
  int rc = send_message(h, &ask, NULL, 0);
  if (rc) return rc;
  struct { struct au_header header; int16_t pcm[AU_MAX_FRAMES]; } packet;
  struct timespec t0, t;
  clock_gettime(CLOCK_MONOTONIC, &t0);
  for (;;) {
    clock_gettime(CLOCK_MONOTONIC, &t);
    long spent = (long)(t.tv_sec - t0.tv_sec) * 1000 + (t.tv_nsec - t0.tv_nsec) / 1000000;
    if (spent >= (long)timeout_ms) return -ETIMEDOUT;
    struct pollfd wait = { .fd = h->fd, .events = POLLIN };
    if (poll(&wait, 1, (int)(timeout_ms - (unsigned)spent)) <= 0) continue;
    ssize_t got = recv(h->fd, &packet, sizeof packet, MSG_DONTWAIT);
    if (got == 0) return -EPIPE;
    if (got < (ssize_t)sizeof packet.header) continue;
    if (packet.header.kind == AU_STATE && packet.header.value) {
      __atomic_store_n(&h->report_fault, true, __ATOMIC_RELEASE);
      br_log(0, "audio: helper: %s stream: %s", packet.header.output ? "speaker" : "microphone", strerror((int)packet.header.value));
    }
    if (packet.header.kind == AU_LATENCY) return packet.header.value ? (int)packet.header.value : -EIO;
  }
}

void br_audio_told(const br_audio_backend *backend, void *ctx, unsigned frames)
{
  if (backend != &helper_backend || !ctx) return;
  struct au_header told = { .kind = AU_TOLD, .output = 1, .value = frames };
  (void)send_message(ctx, &told, NULL, 0);
}

const br_audio_backend *br_audio_helper(const char *path, void **ctx)
{
  int pair[2];
  if (socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, pair)) { br_log(0, "audio: off: socketpair: %s", strerror(errno)); return NULL; }
  // Enable credentials before the child can send anything. Legacy audio
  // remains available if this kernel cannot qualify the control protocol.
  int one = 1;
  bool passcred = setsockopt(pair[0], SOL_SOCKET, SO_PASSCRED, &one, sizeof one) == 0;
  helper *h = calloc(1, sizeof *h);
  posix_spawn_file_actions_t actions;
  posix_spawn_file_actions_init(&actions);
  posix_spawn_file_actions_adddup2(&actions, pair[1], 3);       // the helper's end is its descriptor 3
  char *argv[] = { (char *)(uintptr_t)path, (char *)"3", NULL };
  int rc = h ? posix_spawn(&h->pid, path, &actions, NULL, argv, environ) : ENOMEM;
  posix_spawn_file_actions_destroy(&actions);
  close(pair[1]);
  if (rc) { br_log(0, "audio: off: %s: %s", path, strerror(rc)); close(pair[0]); free(h); return NULL; }
  h->fd = pair[0];
  h->barrier = (auq_link){ .fd = pair[0], .pidfd = -1, .pid = h->pid, .uid = getuid(), .gid = getgid() };
#ifdef SYS_pidfd_open
  // This is our own unreaped posix_spawn child (no concurrent reaper
  // in xnuhost). A zombie cannot be reused. Verify still our live child
  // around pidfd acquisition; no ordinary PID fallback for a receipt.
  siginfo_t info = {0};
  if (passcred && !waitid(P_PID, (id_t)h->pid, &info, WEXITED | WNOHANG | WNOWAIT) && !info.si_pid) {
    int pidfd = (int)syscall(SYS_pidfd_open, h->pid, 0);
    memset(&info, 0, sizeof info);
    if (pidfd >= 0) {
      if (!waitid(P_PID, (id_t)h->pid, &info, WEXITED | WNOHANG | WNOWAIT) && !info.si_pid)
        h->barrier.pidfd = pidfd;
      else close(pidfd);
    }
  }
#else
  (void)passcred;
#endif
  br_log(1, "audio: on: helper %s (pid %d)", path, (int)h->pid);
  *ctx = h;
  return &helper_backend;
}

// These calls are serialized under the exact virtio-snd lock, with both
// logical streams stopped and the host capture thread joined. The helper
// socket has one reader here. Null has no independent worker or stream.
static int audio_gate(const br_audio_backend *backend, void *ctx, uint64_t ticket, unsigned op)
{
  if (!ticket) return -EINVAL;
  if (backend == &null_backend && !ctx) return 0;
  if (backend != &helper_backend || !ctx) return -ENOTSUP;
  helper *h = ctx;
  if (__atomic_load_n(&h->report_fault, __ATOMIC_ACQUIRE)) return -ESTALE;
  if (op == AU_QUIESCE) return auq_close(&h->barrier, ticket);
  if (op == AU_QUIESCED) return auq_poll(&h->barrier, ticket);
  return auq_resume(&h->barrier, ticket);
}
int br_audio_quiesce_close(const br_audio_backend *b, void *ctx, uint64_t t) { return audio_gate(b, ctx, t, AU_QUIESCE); }
int br_audio_quiesce_poll(const br_audio_backend *b, void *ctx, uint64_t t) { return audio_gate(b, ctx, t, AU_QUIESCED); }
int br_audio_quiesce_resume(const br_audio_backend *b, void *ctx, uint64_t t) { return audio_gate(b, ctx, t, AU_RESUME); }
