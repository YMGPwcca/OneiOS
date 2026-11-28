/* SPDX-License-Identifier: MIT */
#ifndef XH_STOCK_SESSION_RUNNER_H
#define XH_STOCK_SESSION_RUNNER_H
#include "stock_sample_reader.h"
#include "stock_thermal_supervisor.h"
#include "sm8850_guest_launch.h"
#include "sm8850_stock_session.h"

/* Root-side, post-bootstrap assembly, not startup admission. The creator
 * must independently protect startup BEFORE release, hold the actual
 * worker READY receipt, verify all descendants and non-VirtIO producers,
 * and supervise this owner's deadlines/actuator calls. No production
 * switcher caller until those conditions are qualified. All pointers
 * remain stable; this object owns no child, fd or cgroup destruction. */
struct xh_stock_runner {
  struct oneios_stock_session *session;
  struct oneios_guest_launch *launch;
  struct xhqs_owner *peer;
  struct xh_stock_reader *raw,*native;
  struct xh_stock_supervisor adapter;
  struct oneios_thermal_ops ops;
  uint64_t deadline;
  int (*verify)(void *,const struct oneios_thermal_identity *);
  int (*outer)(void *,bool);
  void *ctx;
  struct oneios_thermal_native_sample native_cache;
  bool native_valid;
  bool attempted,bound,activated;
  enum oneios_thermal_result last;
};
int xh_stock_runner_bind(struct xh_stock_runner *,struct oneios_stock_session *,
    struct oneios_guest_launch *,struct xhqs_owner *,struct xh_stock_reader *raw,
    struct xh_stock_reader *native,uint64_t deadline,
    int (*verify)(void *,const struct oneios_thermal_identity *),
    int (*outer)(void *,bool),void *);
/* Call at a separately supervised cadence (also while PAUSED).
 * Raw requests are bounded; optional native reader is never waited on.
 * Missing mandatory raw input faults the actual stock controller.
 * Return value must not be treated as a startup/physical qualification. */
enum oneios_thermal_result xh_stock_runner_tick(struct xh_stock_runner *);
#endif
