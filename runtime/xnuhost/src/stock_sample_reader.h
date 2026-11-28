/* SPDX-License-Identifier: MIT */
#ifndef XH_STOCK_SAMPLE_READER_H
#define XH_STOCK_SAMPLE_READER_H
#include "sm8850_thermal_source.h"
#include <sys/types.h>

/* External owner, one outstanding sample per reader. Spawn before any
 * threads or vendor Binder initialization. Raw and native are separate
 * children; never wait for native data in the mandatory raw loop.
 * Successful start owns the endpoint, timer and child pidfd. Close does
 * not reap/kill a blocked child; its PID remains for trusted retirement.
 * The caller must keep these processes outside both guest groups and
 * independently supervise owner/cgroup operations and startup. */
enum xh_stock_sample_kind { XH_STOCK_RAW=1, XH_STOCK_NATIVE=2 };
typedef int (*xh_stock_native_read_fn)(const struct oneios_thermal_identity *,
    uint64_t, struct oneios_thermal_native_sample *);
struct xh_stock_reader {
  struct oneios_thermal_identity id;
  pid_t owner, child;
  int fd, pidfd, timerfd, fault;
  enum xh_stock_sample_kind kind;
  uint64_t seq, deadline;
  bool attempted, ready, pending;
};
struct xh_stock_reading {
  struct oneios_thermal_sample raw;
  struct oneios_thermal_native_sample native;
};
int xh_stock_reader_raw(struct xh_stock_reader *, const struct oneios_raw_source *);
int xh_stock_reader_native(struct xh_stock_reader *,
    const struct oneios_thermal_identity *, xh_stock_native_read_fn);
int xh_stock_reader_request(struct xh_stock_reader *, uint64_t absolute_limit);
/* 0 = authenticated fresh reply; -EAGAIN = still pending (nonblocking).
 * A native read error gives -ENODATA, not severity zero. Raw read errors,
 * malformed replies, stale samples, timeout/death fault the channel.
 * out is untouched on any error. */
int xh_stock_reader_take(struct xh_stock_reader *, bool wait, struct xh_stock_reading *);
void xh_stock_reader_close(struct xh_stock_reader *);
#endif
