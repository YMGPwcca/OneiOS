#ifndef XH_QUIESCE_SUPERVISOR_H
#define XH_QUIESCE_SUPERVISOR_H

#include "quiesce.h"
#include <stdbool.h>
#include <sys/types.h>

/* Private Linux/Android AF_UNIX SOCK_SEQPACKET channel. Create before
 * spawning the two participants; each must close its unused endpoint.
 * A trusted launcher must pin the exact distinct process identities,
 * UID/GID, endpoint ownership and session membership. Neither peer may
 * share its endpoint. pidfd pins liveness, SCM_CREDENTIALS checks each
 * packet. Not a security boundary against privileged root. No live launcher.
 * All calls are serialized by each endpoint's sole owner. */
struct xhqs_peer {
  int fd, pidfd;
  pid_t pid;
  uid_t uid;
  gid_t gid;
};
struct xhqs_owner {
  struct xhqs_peer peer;
  int timerfd, fault;
  uint64_t owner, cycle, seq, deadline;
  unsigned members, closed, verified, attempted, reopened;
  enum xhq_phase phase;
  bool runtime_ready;
};
struct xhqs_worker {
  struct xhqs_peer peer;
  struct xhq *q;
  struct xhq_ops upstream;
  void *upstream_ctx;
  uint64_t seq;
  int fault;
  /* Optional one-time worker-owned outer release, before DONE ACK. */
  int (*finish_resume)(void *, uint64_t owner, uint64_t cycle);
  void *finish_ctx;
  /* Optional real runtime-ready handshake before the first BEGIN. */
  int (*ready_check)(void *);
  void *ready_ctx;
  bool runtime_ready;
};
int xhqs_pair(int fd[2]);
int xhqs_now(uint64_t *ns);
/* Successful init takes ownership of fd. On failure caller retains fd.
 * Call close only after successful init. No close operation thaws or kills. */
int xhqs_owner_init(struct xhqs_owner *, int fd, pid_t worker, uid_t, gid_t,
                    uint64_t owner, unsigned nblocks);
/* Worker binding is one-time: q and worker must remain at stable addresses.
 * All coordinator calls go through worker_once; q is not reusable after
 * worker_close. The original guard is retained, with channel/liveness
 * checks before and after it; a currently executing syscall may still finish. */
int xhqs_worker_init(struct xhqs_worker *, int fd, pid_t owner, uid_t, gid_t, struct xhq *);
void xhqs_owner_close(struct xhqs_owner *);
void xhqs_worker_close(struct xhqs_worker *);
/* One absolute CLOCK_BOOTTIME deadline covers park/hold/resume. No
 * deadline extension. Each exchange waits independently of the worker.
 * Fault is terminal for the channel; never auto-resume or cancel a syscall.
 * On timeout the worker may still be running. A trusted external owner
 * must keep the session fenced and handle the failure independently. */
/* Between exchanges, independently poll timerfd, peer.pidfd and peer.fd
 * from the owner event loop while a cycle is active; call check on
 * readiness (do not consume
 * packets or timer events yourself). Check is NOT a renewed park receipt.
 * No autonomous event loop or production launcher is installed here. */
int xhqs_owner_check(struct xhqs_owner *);
/* Authenticated, bounded startup receipt. -EAGAIN means not yet ready;
 * this is not a parked receipt or physical admission. */
int xhqs_owner_ready_until(struct xhqs_owner *, uint64_t call_limit);
int xhqs_owner_begin(struct xhqs_owner *, uint64_t deadline);
int xhqs_owner_step(struct xhqs_owner *);
int xhqs_owner_resume(struct xhqs_owner *);
/* The cycle deadline covers park/hold/resume. The earlier absolute
 * call limit bounds one exchange without shortening/extending the cycle
 * on success. Timeout latches the existing terminal channel fault. */
int xhqs_owner_begin_until(struct xhqs_owner *, uint64_t cycle_deadline, uint64_t call_limit);
int xhqs_owner_step_until(struct xhqs_owner *, uint64_t call_limit);
int xhqs_owner_resume_until(struct xhqs_owner *, uint64_t call_limit);
/* Execute at most one command on a dedicated worker. -EAGAIN means no
 * command ready; 0 means a response was sent, NOT that it succeeded.
 * Other errors latch worker fault. No call may be made from a device handler. */
/* For the sole worker owner during a command: check deadline, peer
 * liveness and absence of unexpected pending commands. */
int xhqs_worker_check(struct xhqs_worker *, uint64_t deadline);
int xhqs_worker_once(struct xhqs_worker *);
#endif
