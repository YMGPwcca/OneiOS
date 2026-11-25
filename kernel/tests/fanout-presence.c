#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "hosted_presence.h"

static uint64_t tags[HOSTED_PRESENCE_SETS], bits[HOSTED_PRESENCE_SETS];
#define N (256u * 64u)
static unsigned char mapped[N];
static uint32_t rng = 0xa1346b27;
static uint32_t random32(void) {
    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
    return rng;
}
static void reset(void) {
    memset(tags,0,sizeof tags); memset(bits,0,sizeof bits); memset(mapped,0,sizeof mapped);
}
static void mark(uint64_t page) {
    hosted_presence_mark(tags,bits,page); mapped[page]=1;
}
static void forget(uint64_t first,uint64_t end) {
    hosted_presence_forget(tags,bits,first,end); memset(mapped+first,0,(size_t)(end-first));
}
static void verify(uint64_t first,uint64_t end) {
    bool maybe=hosted_presence_maybe(tags,bits,first,end);
    for(uint64_t p=first;p<end;p++) if(mapped[p]) assert(maybe);
}
int main(void) {
    reset();
    assert(!hosted_presence_maybe(tags,bits,3,4));
    mark(3);
    assert(hosted_presence_maybe(tags,bits,3,4));
    assert(!hosted_presence_maybe(tags,bits,4,5));
    mark(63); mark(64); mark(65);
    forget(63,65);
    assert(!hosted_presence_maybe(tags,bits,63,65));
    assert(hosted_presence_maybe(tags,bits,65,66));
    /* Accepted unmap, then a later queued map before the host runs the queue. */
    forget(3,4); assert(!hosted_presence_maybe(tags,bits,3,4));
    mark(3); assert(hosted_presence_maybe(tags,bits,3,4));
    reset();
    unsigned coll=1; while(hosted_presence_index(coll)!=hosted_presence_index(0)) coll++;
    mark(0); mark((uint64_t)coll*64);
    assert(tags[hosted_presence_index(0)]==HOSTED_PRESENCE_UNKNOWN);
    forget(0,1); forget((uint64_t)coll*64,(uint64_t)coll*64+1);
    assert(hosted_presence_maybe(tags,bits,0,1)); /* collision stays conservative */
    assert(hosted_presence_maybe(tags,bits,0,8192)); /* broad range fallback */
    reset();
    for (unsigned i=0;i<200000;i++) {
        if ((i%1024)==0) reset();
        uint64_t first=random32()%N, end=first+1+random32()%96;
        if(end>N) end=N;
        switch(random32()%4) {
        case 0: mark(first); break;
        case 1: forget(first,end); break;
        case 2: verify(first,end); break;
        case 3: mark(first); verify(first,first+1); break;
        }
        verify(first,end);
        /* Check every known live page periodically, including collisions. */
        if((i%256)==0) for(uint64_t p=0;p<N;p++) if(mapped[p]) verify(p,p+1);
    }
    puts("G2_PRESENCE_MODEL=PASS (200000 deterministic operations)");
}
