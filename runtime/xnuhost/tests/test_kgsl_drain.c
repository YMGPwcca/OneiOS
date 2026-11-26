// Host-only regression for the renderer's actual ledger.
#include "oneios_kgsl_drain.h"
#include <stdio.h>
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); } } while (0)
struct receipt { int fd; uint32_t ctx, ts; };
struct fake_wait { struct receipt got[128]; unsigned n; int result; };
static int wait_fake(int fd, uint32_t ctx, uint32_t ts, void *arg)
{
   struct fake_wait *w=arg;
   CHECK(w->n < sizeof w->got / sizeof w->got[0]);
   w->got[w->n++]=(struct receipt){fd,ctx,ts};
   return w->result;
}
static bool seen(const struct fake_wait *w, int fd, uint32_t ctx, uint32_t ts)
{
   for(unsigned i=0;i<w->n;i++)
      if(w->got[i].fd==fd && w->got[i].ctx==ctx && w->got[i].ts==ts) return true;
   return false;
}
static void submit(struct oneios_kgsl_drain *d,int fd,uint32_t ctx,uint32_t ts,bool accepted)
{
   struct oneios_kgsl_drain_entry *e=NULL;
   CHECK(!oneios_kgsl_drain_begin(d,fd,ctx,false,&e) && e);
   oneios_kgsl_drain_finish(d,e,accepted,ts);
}
static void cleanup(struct oneios_kgsl_drain *d)
{
   while(d->entries) {
      struct oneios_kgsl_drain_entry *e=d->entries;
      d->entries=e->next; free(e);
   }
   CHECK(!pthread_mutex_destroy(&d->lock));
}
static void normal(void)
{
   struct oneios_kgsl_drain d=ONEIOS_KGSL_DRAIN_INITIALIZER;
   struct fake_wait w={0};
   struct oneios_kgsl_drain_entry *hold=NULL,*skip=NULL;
   submit(&d,4,7,100,true); submit(&d,4,7,101,true);
   submit(&d,5,7,41,true); submit(&d,4,8,9,true);
   CHECK(!oneios_kgsl_drain_begin(&d,9,3,true,&hold));
   uint64_t t=0,t2=0;
   CHECK(!oneios_kgsl_drain_close(&d,&t) && t);
   CHECK(oneios_kgsl_drain_close(&d,&t2)==-EBUSY && !t2);
   CHECK(oneios_kgsl_drain_begin(&d,9,3,true,&skip)==1 && !skip);
   CHECK(oneios_kgsl_drain_poll(&d,t,wait_fake,&w)==-EAGAIN && !w.n);
   CHECK(oneios_kgsl_drain_resume(&d,t)==-EBUSY);
   oneios_kgsl_drain_finish(&d,hold,true,88);
   w.result=-EAGAIN;
   CHECK(oneios_kgsl_drain_poll(&d,t,wait_fake,&w)==-EAGAIN && w.n==1);
   CHECK(oneios_kgsl_drain_resume(&d,t)==-EBUSY);
   w.result=0; w.n=0;
   CHECK(!oneios_kgsl_drain_poll(&d,t,wait_fake,&w) && w.n==4);
   CHECK(seen(&w,4,7,101) && !seen(&w,4,7,100));
   CHECK(seen(&w,5,7,41) && seen(&w,4,8,9) && seen(&w,9,3,88));
   CHECK(!oneios_kgsl_drain_poll(&d,t,wait_fake,&w) && w.n==4);
   CHECK(oneios_kgsl_drain_resume(&d,t+1)==-ESTALE);
   CHECK(!oneios_kgsl_drain_resume(&d,t) && !oneios_kgsl_drain_closed(&d));
   submit(&d,4,7,102,true);
   CHECK(!oneios_kgsl_drain_close(&d,&t2) && t2>t);
   CHECK(oneios_kgsl_drain_poll(&d,t,wait_fake,&w)==-ESTALE);
   w.n=0;
   CHECK(!oneios_kgsl_drain_poll(&d,t2,wait_fake,&w) && w.n==1 && seen(&w,4,7,102));
   CHECK(!oneios_kgsl_drain_resume(&d,t2));
   cleanup(&d);
}
static void faults(void)
{
   for(unsigned k=0;k<6;k++) {
      struct oneios_kgsl_drain d=ONEIOS_KGSL_DRAIN_INITIALIZER;
      struct fake_wait w={0};
      submit(&d,4,7,100,true);
      if(k==0) submit(&d,4,7,101,false);
      if(k==1) submit(&d,4,7,99,true);
      if(k==2) submit(&d,4,7,0,true);
      if(k==3) { w.result=-EAGAIN; oneios_kgsl_drain_forget(&d,4,7,false,wait_fake,&w); }
      if(k==4) oneios_kgsl_drain_fault(&d);
      uint64_t t=0;
      CHECK(!oneios_kgsl_drain_close(&d,&t));
      if(k==5) w.result=-EDEADLK;
      CHECK(oneios_kgsl_drain_poll(&d,t,wait_fake,&w)==-EIO);
      CHECK(oneios_kgsl_drain_resume(&d,t)==-EIO);
      CHECK(oneios_kgsl_drain_closed(&d));
      cleanup(&d);
   }
   struct oneios_kgsl_drain d=ONEIOS_KGSL_DRAIN_INITIALIZER;
   struct oneios_kgsl_drain_entry *e=NULL;
   struct fake_wait w={0};
   uint64_t t=0;
   CHECK(!oneios_kgsl_drain_close(&d,&t));
   CHECK(oneios_kgsl_drain_begin(&d,7,8,false,&e)==-EBUSY && !e);
   CHECK(oneios_kgsl_drain_poll(&d,t,wait_fake,&w)==-EIO);
   CHECK(oneios_kgsl_drain_resume(&d,t)==-EIO);
   cleanup(&d);
}
static void lifetime(void)
{
   struct oneios_kgsl_drain d=ONEIOS_KGSL_DRAIN_INITIALIZER;
   struct fake_wait w={0};
   submit(&d,4,7,UINT32_MAX-1,true); submit(&d,4,7,1,true);
   oneios_kgsl_drain_forget(&d,4,7,false,wait_fake,&w);
   CHECK(w.n==1 && seen(&w,4,7,1) && !d.fault);
   submit(&d,4,7,1,true);
   oneios_kgsl_drain_forget(&d,4,0,true,wait_fake,&w);
   CHECK(!d.entries && !d.fault);
   w.n=0;
   for(unsigned i=0;i<35;i++) submit(&d,4,i+1,i+1,true);
   uint64_t t=0;
   CHECK(!oneios_kgsl_drain_close(&d,&t));
   CHECK(oneios_kgsl_drain_poll(&d,t,wait_fake,&w)==-EAGAIN && w.n==16);
   CHECK(oneios_kgsl_drain_poll(&d,t,wait_fake,&w)==-EAGAIN && w.n==32);
   CHECK(!oneios_kgsl_drain_poll(&d,t,wait_fake,&w) && w.n==35);
   oneios_kgsl_drain_forget(&d,4,0,true,wait_fake,&w);
   CHECK(oneios_kgsl_drain_resume(&d,t)==-EIO);
   cleanup(&d);
}
int main(void)
{
   normal(); faults(); lifetime();
   printf("KGSL_ACCEPTED_TIMESTAMP_DRAIN=PASS checks=%u DEVICE_ACCESS=NONE\n",checks);
   return 0;
}
