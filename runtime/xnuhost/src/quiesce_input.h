// SPDX-License-Identifier: MIT
#ifndef XH_QUIESCE_INPUT_H
#define XH_QUIESCE_INPUT_H
#include <stdbool.h>
#include <stdint.h>

/* Process-lifetime registry for the native evdev reader (touch, keys,
 * pen) and the input script. Register before starting or configuring a
 * source; seal once after startup. The reader acknowledges only between
 * complete feed calls. A live script is not parkable: do not alter a
 * workload's time base or abandon a partial gesture. One control owner.
 * This fences the known source threads, not arbitrary new producers,
 * kernel evdev queues, input device resets or hardware bridge workers. */
enum xhqi_source { XHQI_READER, XHQI_SCRIPT };
int xhqi_start(enum xhqi_source);
void xhqi_finish(enum xhqi_source, bool failed);
int xhqi_seal(void);
/* Native reader only, before reading the next batch. False means exit
 * without another read/feed. Normal open path: one atomic load. */
extern unsigned xhqi_flags;
#define XHQI_CLOSED 1u
#define XHQI_STOP 2u
bool xhqi_reader_wait(void);
static inline bool xhqi_reader_checkpoint(void)
{
  return !(__atomic_load_n(&xhqi_flags, __ATOMIC_ACQUIRE) & (XHQI_CLOSED | XHQI_STOP)) || xhqi_reader_wait();
}
/* Terminal shutdown of the reader (not resume); wake it so join and
 * release of the exclusive touchscreen are not blocked by park. */
void xhqi_reader_stop(void);
/* Read-only registry/startup check. Active scripts are unsupported. */
int xhqi_ready(void);
int xhqi_close(uint64_t *ticket);
int xhqi_poll(uint64_t ticket);
/* Explicitly authorized release, only after every other drain/reopen.
 * Kernel events may have accumulated/overflowed during the hold. */
int xhqi_resume(uint64_t ticket);
#endif
