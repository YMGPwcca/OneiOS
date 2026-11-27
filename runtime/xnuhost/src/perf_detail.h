// SPDX-License-Identifier: MIT
// Opt-in host attribution. The guest's 0041/0075 profiler already reports
// individual syscall numbers; these classes describe host-side interval tails.
#ifndef XNUHOST_PERF_DETAIL_H
#define XNUHOST_PERF_DETAIL_H
#include <stdint.h>
#include <stdbool.h>
#include <errno.h>
#include <string.h>
#include "xnuhost/hostcall.h"

enum xh_detail_class {
  XH_DC_BSD_DIRECT, XH_DC_BSD_INDIRECT, XH_DC_MACH, XH_DC_PLATFORM,
  XH_DC_FAULT_READ, XH_DC_FAULT_WRITE, XH_DC_FAULT_EXEC, XH_DC_FAULT_UNKNOWN,
  XH_DC_COUNT
};
enum xh_detail_timer {
  XH_DT_SAME_FUTURE, XH_DT_CANCEL_ARMED, XH_DT_CANCEL_DISARMED,
  XH_DT_DUE, XH_DT_ARM, XH_DT_CANCEL_SKIPPED, XH_DT_DUE_SKIPPED, XH_DT_ERRORS, XH_DT_COUNT
};
enum xh_detail_wait {
  XH_DW_RETURNED, XH_DW_CHANGED, XH_DW_SIGNAL, XH_DW_TIMEOUT, XH_DW_OTHER,
  XH_DW_COUNT
};
typedef struct {
  unsigned previous_class;  // vCPU owner only; readers never inspect this field
  uint64_t intervals[XH_DC_COUNT], over_budget[XH_DC_COUNT];
  uint64_t timer[XH_DT_COUNT];
  uint64_t futex[2][XH_DW_COUNT]; // 0: thread_run, 1: cpu_idle
} xh_detail_profile;
static inline void xh_detail_inc(uint64_t *p)
{
  __atomic_fetch_add(p, 1, __ATOMIC_RELAXED);
}
static inline uint64_t xh_detail_read(const uint64_t *p)
{
  return __atomic_load_n(p, __ATOMIC_RELAXED);
}
static inline unsigned xh_detail_classify(uint32_t kind, uint32_t access, uint64_t x16)
{
  if (kind == XH_TRAP_SYSCALL) {
    // Match signed-low-32-bit classification in guest patch 0041.
    if ((uint32_t)x16 == UINT32_C(0x80000000)) return XH_DC_PLATFORM;
    if ((int32_t)x16 < 0) return XH_DC_MACH;
    return x16 == 0 ? XH_DC_BSD_INDIRECT : XH_DC_BSD_DIRECT;
  }
  if (kind == XH_TRAP_FAULT) {
    switch (access) {
      case XH_PROT_READ: return XH_DC_FAULT_READ;
      case XH_PROT_WRITE: return XH_DC_FAULT_WRITE;
      case XH_PROT_EXEC: return XH_DC_FAULT_EXEC;
      default: return XH_DC_FAULT_UNKNOWN;
    }
  }
  return XH_DC_COUNT;
}
// Trap to next thread_run on the same vCPU, less observed idle.
// Not isolated syscall CPU time; not a frame-to-trap dependency.
static inline void xh_detail_interval(xh_detail_profile *p, unsigned cls, uint64_t ns)
{
  if (cls >= XH_DC_COUNT) return;
  xh_detail_inc(&p->intervals[cls]);
  if (ns >= UINT64_C(16666667)) xh_detail_inc(&p->over_budget[cls]);
}
static inline void xh_detail_timer_result(xh_detail_profile *p, unsigned reason, int rc)
{
  if (reason >= XH_DT_ERRORS) return;
  xh_detail_inc(&p->timer[reason]);
  if (rc != 0) xh_detail_inc(&p->timer[XH_DT_ERRORS]);
}
static inline unsigned xh_detail_wait_result(long rc, int error)
{
  if (rc == 0) return XH_DW_RETURNED;
  if (rc == -1) {
    if (error == EAGAIN) return XH_DW_CHANGED;
    if (error == EINTR) return XH_DW_SIGNAL;
    if (error == ETIMEDOUT) return XH_DW_TIMEOUT;
  }
  return XH_DW_OTHER;
}
static inline void xh_detail_futex(xh_detail_profile *p, bool idle, long rc, int error)
{
  xh_detail_inc(&p->futex[idle ? 1 : 0][xh_detail_wait_result(rc, error)]);
}
// Parse the complete kernel-reported allowed list; reject truncated lines.
static inline bool xh_detail_allowed_list(const char *line, char *out, size_t cap)
{
  static const char key[] = "Cpus_allowed_list:";
  if (!out || !cap || strncmp(line, key, sizeof key - 1)) return false;
  const char *p = line + sizeof key - 1;
  p += strspn(p, " \t");
  size_t n = strcspn(p, "\r\n \t");
  if (!n || n >= cap || strspn(p, "0123456789,-") != n) return false;
  if (p[n] != '\n' && p[n] != '\r') return false;
  memcpy(out, p, n);
  out[n] = '\0';
  return true;
}
#endif
