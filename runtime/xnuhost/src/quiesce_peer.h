#ifndef XH_QUIESCE_PEER_H
#define XH_QUIESCE_PEER_H
#include <stddef.h>
#include <sys/types.h>

/* Linux local socket identity. The launcher must supply a trusted pidfd
 * for the intended, distinct helper and expected UID/GID. Bind to the
 * actual socket peer's kernel pidfd, not a fresh lookup of a numeric PID.
 * The peer owns its pidfd; socket and expected pidfd remain borrowed.
 * No protection against privileged root or a malicious trusted helper. */
struct xhqp_peer {
  int pidfd;
  pid_t pid;
  uid_t uid;
  gid_t gid;
};
int xhqp_bind(struct xhqp_peer *, int socket_fd, int expected_pidfd, uid_t, gid_t);
int xhqp_check(const struct xhqp_peer *, int socket_fd);
/* Exact-size packet, per-message credentials, no ancillary FDs retained.
 * -EAGAIN is retry; all other failures invalidate the caller's receipt. */
int xhqp_recv(const struct xhqp_peer *, int socket_fd, void *, size_t);
void xhqp_release(struct xhqp_peer *);
#endif
