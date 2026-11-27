// SPDX-License-Identifier: MIT
#include "playback_drain.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); exit(1); } } while (0)
typedef struct { unsigned left, sent, pads, calls, limit; int64_t written, pos, stamp, mono; int ts_rc, write_rc; bool bad_count, bad_peek; } fixture;
static int peek(void *v,int16_t *p,unsigned n) { fixture *f=v; if (f->bad_peek || n>f->left) return -1; for(unsigned i=0;i<n*2;i++) p[i]=123; return (int)n; }
static void consume(void *v,unsigned n) { fixture *f=v; CHECK(n<=f->left); f->left-=n; f->sent+=n; }
static int write_pcm(void *v,const int16_t *p,unsigned n) { fixture *f=v; f->calls++; if(f->write_rc) return f->write_rc; if(n>f->limit)n=f->limit; for(unsigned i=0;i<n*2;i++) CHECK(p[i]==(f->left?123:0)); if(!f->left)f->pads+=n; if(!f->bad_count)f->written+=n; return (int)n; }
static int64_t written(void *v){return ((fixture*)v)->written;}
static int timestamp(void *v,int64_t *p,int64_t *s,int64_t *m){fixture*f=v;*p=f->pos;*s=f->stamp;*m=f->mono;return f->ts_rc;}
static const aupd_ops ops={peek,consume,write_pcm,written,timestamp};
int main(void){
  uint64_t now=100, end=now+AUPD_MAX_HOLD_NS; aupd_state s;
  fixture f={.left=481,.limit=17,.written=1000,.ts_rc=-EAGAIN,.stamp=1,.mono=1};
  CHECK(aupd_init(&s,481,now,end,f.written)==0);
  f.limit=0; CHECK(aupd_step(&s,&ops,&f,now)==0 && s.remaining==481 && f.left==481);
  f.limit=17; while(s.remaining)CHECK(aupd_step(&s,&ops,&f,++now)==0);
  CHECK(f.sent==481 && !f.left && f.written==1481);
  f.limit=240; CHECK(aupd_step(&s,&ops,&f,++now)==0 && s.target==1481 && f.pads==240);
  f.ts_rc=0; f.pos=1480; f.stamp=20; f.mono=20;
  CHECK(aupd_step(&s,&ops,&f,++now)==0 && s.target==1481 && f.pads==480);
  f.pos=1481; f.stamp=21; f.mono=21; unsigned calls=f.calls;
  CHECK(aupd_step(&s,&ops,&f,++now)==1 && f.calls==calls && s.done);
  CHECK(aupd_step(&s,&ops,&f,++now)==1 && f.calls==calls);
  CHECK(aupd_step(&s,&ops,&f,end)==-ETIMEDOUT && s.fault);
  for(int mode=0;mode<9;mode++){
    now=100; end=now+AUPD_MAX_HOLD_NS; memset(&f,0,sizeof f); f.limit=240; f.written=100; f.stamp=10; f.mono=10;
    if(mode<3){f.left=1;if(mode==0)f.bad_peek=true;if(mode==1)f.write_rc=-EIO;if(mode==2)f.bad_count=true;}
    CHECK(aupd_init(&s,f.left,now,end,f.written)==0);
    if(mode==3)f.pos=-1;
    if(mode==4)f.pos=101;
    if(mode==5)f.mono=9;
    if(mode==6){f.pos=50;CHECK(aupd_step(&s,&ops,&f,++now)==0);f.pos=49;f.stamp++;f.mono++;}
    if(mode==7){f.pos=50;CHECK(aupd_step(&s,&ops,&f,++now)==0);f.pos=51;}
    if(mode==8){now--;}
    CHECK(aupd_step(&s,&ops,&f,now)<0 && s.fault && !s.done);
    CHECK(aupd_step(&s,&ops,&f,now)==-ESTALE);
  }
  now=100;end=now+AUPD_MAX_HOLD_NS;memset(&f,0,sizeof f);f.limit=240;f.written=1;f.ts_rc=-EAGAIN;
  CHECK(aupd_init(&s,0,now,end,f.written)==0);
  while(s.padding<AUPD_PAD_MAX)CHECK(aupd_step(&s,&ops,&f,++now)==0);
  calls=f.calls; CHECK(f.pads==AUPD_PAD_MAX && aupd_step(&s,&ops,&f,++now)==0 && f.calls==calls);
  CHECK(aupd_step(&s,&ops,&f,end)==-ETIMEDOUT);
  now=100;end=now+AUPD_MAX_HOLD_NS;memset(&f,0,sizeof f);f.limit=240;f.written=100;f.pos=100;f.stamp=1;f.mono=AUPD_MAX_STAMP_AGE_NS+2;
  CHECK(aupd_init(&s,0,now,end,f.written)==0);
  CHECK(aupd_step(&s,&ops,&f,++now)==0 && !s.done); // stale timestamp is not a receipt
  f.stamp=f.mono;CHECK(aupd_step(&s,&ops,&f,++now)==1);
  CHECK(aupd_init(&s,0,now,end,0)==0);f.written=0;CHECK(aupd_step(&s,&ops,&f,now)==1);
  CHECK(aupd_init(&s,0,now,now,0)==-EINVAL);
  printf("playback drain: %u checks, 0 failed\n",checks);return 0;
}
