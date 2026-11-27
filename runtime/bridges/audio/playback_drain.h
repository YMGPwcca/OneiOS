// SPDX-License-Identifier: MIT
#ifndef ONEIOS_PLAYBACK_DRAIN_H
#define ONEIOS_PLAYBACK_DRAIN_H
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>

// Offline qualification bounds, not a thermal policy. Each step makes at
// most one nonblocking write. The independent owner still owns its deadline.
#define AUPD_CHUNK 240u
#define AUPD_PAD_MAX 48000u
#define AUPD_MAX_HOLD_NS UINT64_C(3000000000)
#define AUPD_MAX_STAMP_AGE_NS INT64_C(1000000000)
typedef struct {
  int (*peek)(void *, int16_t *, unsigned); // exact requested stereo frames, no mutation
  void (*consume)(void *, unsigned);       // only frames actually accepted
  int (*write)(void *, const int16_t *, unsigned); // nonblocking, short or zero allowed
  int64_t (*written)(void *);
  int (*timestamp)(void *, int64_t *position, int64_t *stamp, int64_t *now);
} aupd_ops;
typedef struct {
  uint64_t deadline, last_now;
  unsigned remaining, padding;
  int64_t written, target, position, stamp;
  bool target_set, sampled, done, fault;
} aupd_state;
static inline int aupd_init(aupd_state *s, unsigned retained, uint64_t now, uint64_t deadline, int64_t written)
{
  if (!s || !now || deadline <= now || deadline-now > AUPD_MAX_HOLD_NS || written < 0) return -EINVAL;
  *s = (aupd_state){ .deadline=deadline, .last_now=now, .remaining=retained, .written=written };
  return 0;
}
static inline int aupd_fail(aupd_state *s, int r) { s->fault=true; return r; }
static inline int aupd_step(aupd_state *s, const aupd_ops *o, void *ctx, uint64_t now)
{
  if (!s || !o || !o->peek || !o->consume || !o->write || !o->written || !o->timestamp) return -EINVAL;
  if (s->fault) return -ESTALE;
  if (now < s->last_now || now >= s->deadline) return aupd_fail(s, now < s->last_now ? -ESTALE : -ETIMEDOUT);
  s->last_now=now;
  if (s->done) return 1;
  // Neither FramesRead nor extrapolated time is proof of presentation.
  int64_t w=o->written(ctx);
  if (w < s->written) return aupd_fail(s,-EPROTO);
  s->written=w;
  int16_t pcm[AUPD_CHUNK*2] = {0};
  bool tail=s->remaining!=0;
  unsigned n;
  if (tail) {
    n=s->remaining < AUPD_CHUNK ? s->remaining : AUPD_CHUNK;
    if (o->peek(ctx,pcm,n)!=(int)n) return aupd_fail(s,-ESTALE);
  } else {
    if (!s->target_set) { s->target=w; s->target_set=true; }
    if (!s->target) { s->done=true; return 1; }
    int64_t pos=0, stamp=0, mono=0;
    int r=o->timestamp(ctx,&pos,&stamp,&mono);
    if (r && r!=-EAGAIN) return aupd_fail(s,r<0?r:-EIO);
    if (!r) {
      if (pos<0 || pos>w || stamp<=0 || mono<stamp || (s->sampled && (pos<s->position || stamp<s->stamp || (stamp==s->stamp && pos!=s->position))))
        return aupd_fail(s,-EPROTO);
      s->position=pos; s->stamp=stamp; s->sampled=true;
      if (pos>=s->target && mono-stamp<=AUPD_MAX_STAMP_AGE_NS) { s->done=true; return 1; }
    }
    // Only zeros after the fixed final PCM fence; never move that fence
    // forward with padding. Some mixer/DSP paths need a complete burst.
    if (s->padding==AUPD_PAD_MAX) return 0;
    n=AUPD_PAD_MAX-s->padding;
    if (n>AUPD_CHUNK) n=AUPD_CHUNK;
  }
  int got=o->write(ctx,pcm,n);
  if (got<0 || got>(int)n) return aupd_fail(s,got<0?got:-EPROTO);
  if (got) {
    // Once accepted, do not replay even if later readback is ambiguous.
    if (tail) { o->consume(ctx,(unsigned)got); s->remaining-=(unsigned)got; }
    else s->padding+=(unsigned)got;
    int64_t next=o->written(ctx);
    if (w>INT64_MAX-got || next<w+got) return aupd_fail(s,-EPROTO);
    s->written=next;
  }
  return 0;
}
#endif
