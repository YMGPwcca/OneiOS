// SPDX-License-Identifier: MIT
#ifndef ONEIOS_AUDIO_QUIESCE_LINK_H
#define ONEIOS_AUDIO_QUIESCE_LINK_H
// Linux local process protocol. Include with _GNU_SOURCE enabled.
#include "audio_proto.h"
#include <errno.h>
#include <poll.h>
#include <stdbool.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

enum auq_phase { AUQ_OPEN, AUQ_CLOSING, AUQ_PARKED, AUQ_RESUMING, AUQ_FAULT };
typedef struct {
  int fd, pidfd;
  pid_t pid;
  uid_t uid;
  gid_t gid;
  enum auq_phase phase;
  uint32_t ticket;
} auq_link;

static inline int auq_fault(auq_link *q, int r)
{
  q->phase = AUQ_FAULT;
  return r;
}
static inline int auq_live(auq_link *q)
{
  if (q->phase == AUQ_FAULT) return -ESTALE;
  if (q->pidfd < 0) return -ENOTSUP;
  struct pollfd p[2] = {{ .fd = q->pidfd, .events = POLLIN },
                        { .fd = q->fd, .events = POLLIN | POLLRDHUP }};
  int r = poll(p, 2, 0);
  if (r < 0) return errno == EINTR ? -EAGAIN : auq_fault(q, -errno);
  if (p[0].revents) return auq_fault(q, -ESRCH);
  if (p[1].revents & (POLLRDHUP | POLLHUP | POLLERR | POLLNVAL)) return auq_fault(q, -ENOTCONN);
  return 0;
}
static inline int auq_send(auq_link *q, unsigned kind, uint32_t t)
{
  int r = auq_live(q);
  if (r) return r;
  struct au_header h = { .kind = kind, .value = t };
  ssize_t n = send(q->fd, &h, sizeof h, MSG_DONTWAIT | MSG_NOSIGNAL);
  if (n < 0 && (errno == EAGAIN || errno == EINTR)) return -EAGAIN;
  if (n != sizeof h) return auq_fault(q, n < 0 ? -errno : -EPROTO);
  return 0;
}
// At most one packet per call. The caller retries within an independent
// deadline. Only pre-barrier capture PCM and successful state reports may
// be retired, after the guest capture thread has already joined.
static inline int auq_receive(auq_link *q, unsigned kind, bool stale)
{
  int r = auq_live(q);
  if (r) return r;
  struct { struct au_header h; uint8_t pcm[AU_MAX_FRAMES*2]; } packet;
  union { struct cmsghdr align; unsigned char bytes[CMSG_SPACE(sizeof(struct ucred)) + CMSG_SPACE(4*sizeof(int))]; } anc;
  struct iovec iov = { &packet, sizeof packet };
  struct msghdr msg = { .msg_iov = &iov, .msg_iovlen = 1, .msg_control = anc.bytes, .msg_controllen = sizeof anc.bytes };
  ssize_t n = recvmsg(q->fd, &msg, MSG_DONTWAIT | MSG_TRUNC | MSG_CMSG_CLOEXEC);
  if (n < 0) return errno == EAGAIN || errno == EINTR ? -EAGAIN : auq_fault(q, -errno);
  bool valid = true, cred = false;
  for (struct cmsghdr *c = CMSG_FIRSTHDR(&msg); c; c = CMSG_NXTHDR(&msg,c)) {
    if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_CREDENTIALS && c->cmsg_len == CMSG_LEN(sizeof(struct ucred))) {
      struct ucred u; memcpy(&u, CMSG_DATA(c), sizeof u);
      if (cred || u.pid != q->pid || u.uid != q->uid || u.gid != q->gid) valid = false;
      cred = true;
    } else {
      if (c->cmsg_level == SOL_SOCKET && c->cmsg_type == SCM_RIGHTS && c->cmsg_len >= CMSG_LEN(0)) {
        size_t count = (c->cmsg_len - CMSG_LEN(0))/sizeof(int);
        for (size_t i = 0; i < count; i++) { int fd; memcpy(&fd, CMSG_DATA(c)+i*sizeof fd, sizeof fd); close(fd); }
      }
      valid = false;
    }
  }
  if (n < (ssize_t)sizeof packet.h || (msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC)) || !valid || !cred)
    return auq_fault(q, -EPROTO);
  struct au_header h = packet.h;
  if (stale && !h.reserved) {
    if (h.kind == AU_STATE && h.output <= 1 && !h.channels && n == sizeof h)
      return h.value ? auq_fault(q, -EIO) : -EAGAIN;
    if (h.kind == AU_PCM && !h.output && h.channels == 1 && h.value && h.value <= AU_MAX_FRAMES && n == (ssize_t)(sizeof h + 2u*h.value)) return -EAGAIN;
  }
  if (!kind || n != sizeof h || h.kind != kind || h.output || h.channels || h.reserved || h.value != q->ticket)
    return auq_fault(q, -EPROTO);
  r = auq_live(q);
  return r == -EAGAIN ? auq_fault(q, -EINTR) : r;
}
static inline int auq_close(auq_link *q, uint64_t ticket)
{
  if (q->phase == AUQ_FAULT) return -ESTALE;
  if (q->phase != AUQ_OPEN) return -EBUSY;
  if (!ticket || ticket > UINT32_MAX || ticket <= q->ticket) return -ESTALE;
  int r = auq_send(q, AU_QUIESCE, (uint32_t)ticket);
  if (!r) { q->ticket = (uint32_t)ticket; q->phase = AUQ_CLOSING; }
  return r;
}
static inline int auq_poll(auq_link *q, uint64_t ticket)
{
  if (ticket != q->ticket || !ticket || (q->phase != AUQ_CLOSING && q->phase != AUQ_PARKED)) return -ESTALE;
  if (q->phase == AUQ_PARKED) {
    int r = auq_live(q);
    if (r) return r;
    struct pollfd p = { .fd = q->fd, .events = POLLIN };
    r = poll(&p, 1, 0);
    if (r < 0) return errno == EINTR ? -EAGAIN : auq_fault(q, -errno);
    if (r) return auq_fault(q, -EPROTO); // no packets allowed after ACK
    return auq_live(q);
  }
  int r = auq_receive(q, AU_QUIESCED, true);
  if (!r) q->phase = AUQ_PARKED;
  return r;
}
static inline int auq_resume(auq_link *q, uint64_t ticket)
{
  if (!ticket || ticket != q->ticket) return -ESTALE;
  if (q->phase == AUQ_PARKED) {
    int r = auq_poll(q, ticket);
    if (r) return r;
    r = auq_send(q, AU_RESUME, q->ticket);
    if (r) return r;
    q->phase = AUQ_RESUMING;
  }
  if (q->phase != AUQ_RESUMING) return -ESTALE;
  int r = auq_receive(q, AU_RESUMED, false);
  if (!r) q->phase = AUQ_OPEN;
  return r;
}
#endif
