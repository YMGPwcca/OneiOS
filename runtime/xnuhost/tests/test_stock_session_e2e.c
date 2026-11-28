/* Integration fixture ONLY: real root launch barrier, source parser,
 * sampler processes, controller, board/IPC worker and vCPU/input/console
 * gates. Mock cgroupfs ACK, native HAL, GPU/IO/display/bridge providers.
 * No Android paths, kernel controls or iOS image. */
#define ONEIOS_OWNED_GROUPS_TEST
#define main standalone_board_fixture
#include "test_quiesce_board_worker.c"
#undef main
#include "sm8850_owned_groups.c"
#include "stock_session_runner.h"

static const struct oneios_thermal_identity test_id={
  "51ca8a7b-7fe0-4075-be5f-6a9029b8d392",
  "51ca8a7b-7fe0-4075-be5f-6a9029b8d392.123.456",
  "ee7c626acb814d92901a8672dc8169ef"
};
static void put(int fd,const char *name,const char *s)
{
  int p=openat(fd,name,O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW|O_CLOEXEC,0600);
  CHECK(p>=0&&write(p,s,strlen(s))==(ssize_t)strlen(s)&&!close(p));
}
static int fixture_create_nodes(int fd,bool cpu)
{
  put(fd,"cgroup.procs","");
  if(cpu){put(fd,"cpu.cfs_period_us","100000\n");put(fd,"cpu.cfs_quota_us","-1\n");put(fd,"cpu.cfs_burst_us","0\n");}
  else{put(fd,"cgroup.freeze","0\n");put(fd,"cgroup.events","populated 0\nfrozen 0\n");}
  return 0;
}
static int fixture_remove_nodes(int fd,bool cpu)
{
  if(unlinkat(fd,"cgroup.procs",0))return -1;
  if(cpu)return unlinkat(fd,"cpu.cfs_period_us",0)||unlinkat(fd,"cpu.cfs_quota_us",0)||unlinkat(fd,"cpu.cfs_burst_us",0)?-1:0;
  return unlinkat(fd,"cgroup.freeze",0)||unlinkat(fd,"cgroup.events",0)?-1:0;
}
struct emulator { int leaf,parent; bool stop; };
static void *emulate_freezer(void *ctx)
{
  struct emulator *e=ctx;
  while(!__atomic_load_n(&e->stop,__ATOMIC_ACQUIRE)){
    long desired,actual;
    if(!read_number(e->leaf,"cgroup.freeze",&desired)&&!frozen_event(e->leaf,&actual)&&desired!=actual){
      // Publish complete ACK file atomically, without sharing CHECK counter.
      const char *s=desired?"populated 1\nfrozen 1\n":"populated 1\nfrozen 0\n";
      int f=openat(e->parent,"events.next",O_WRONLY|O_CREAT|O_TRUNC|O_CLOEXEC,0600);
      if(f<0||write(f,s,strlen(s))!=(ssize_t)strlen(s)||close(f)||
         renameat(e->parent,"events.next",e->leaf,"cgroup.events"))abort();
    }
    usleep(1000);
  }
  return NULL;
}
static int native_read(const struct oneios_thermal_identity *id,uint64_t seq,struct oneios_thermal_native_sample *n)
{
  uint64_t t;if(xhqs_now(&t))return -EIO;
  *n=(struct oneios_thermal_native_sample){.id=*id,.seq=seq,.ms=t/1000000u,.severity=0};
  return 0;
}
static int slow_native(const struct oneios_thermal_identity *id,uint64_t seq,struct oneios_thermal_native_sample *n)
{ sleep(2);return native_read(id,seq,n); }
static void wait_child(pid_t pid,bool timed_out)
{
  int status;CHECK(waitpid(pid,&status,0)==pid&&WIFEXITED(status));
  CHECK(!WEXITSTATUS(status)||(timed_out&&WEXITSTATUS(status)==125));
}
static pthread_t boot_threads[2];
static int start_fixture_guest(void *ctx)
{
  (void)ctx;
  for(unsigned i=0;i<2;i++) {
    if(xhqv_reserve_start(i)||pthread_create(&boot_threads[i],NULL,vcpu,(void *)(uintptr_t)i))
      return -EIO;
  }
  return 0;
}
static int worker_child(int fd,pid_t parent)
{
  make_board(0);
  CHECK(!xhqv_configure(2)&&!xhqv_enable_startup());
  struct xhqb_worker w={0};
  CHECK(!xhqb_worker_init(&w,fd,parent,getuid(),getgid(),17,99,getuid(),getgid(),guard,NULL));
  w.ipc.start_guest=start_fixture_guest;
  int r=xhqb_worker_run(&w);
  CHECK(r==-ENOTCONN||r==-ESRCH);
  // Final raw fault leaves the mock device/real producer gates parked.
  CHECK(w.q.phase==XHQ_PARKED&&inner==7&&external==3);
  xhqb_worker_close(&w);
  _exit(0);
}
struct ownership { struct oneios_guest_launch *launch; struct xhqs_owner *peer; };
static int verify_owner(void *ctx,const struct oneios_thermal_identity *id)
{
  struct ownership *o=ctx;
  if(strcmp(id->token,test_id.token))return -ESTALE;
  // Fixture has exactly two roots and no guest descendants (only threads).
  return oneios_guest_launch_check_roots(o->launch)?-EPERM:0;
}
static int verify_outer(void *ctx,bool paused)
{
  struct ownership *o=ctx;
  return paused?(o->peer->phase==XHQ_PARKED?0:-EPERM):
    (o->peer->phase==XHQ_IDLE||o->peer->phase==XHQ_DONE?0:-EPERM);
}
int main(int argc,char **argv)
{
  if(argc==4&&!strcmp(argv[1],"--worker"))return worker_child(atoi(argv[2]),(pid_t)atoi(argv[3]));
  if(argc==3&&!strcmp(argv[1],"--display")){
    char b;ssize_t n=read(atoi(argv[2]),&b,1);return n==0?0:2;
  }
  CHECK(argc==2&&argv[1][0]=='/');
  alarm(60);
  int dir=open(argv[1],DIR_FLAGS);CHECK(dir>=0);
  CHECK(!mkdirat(dir,"cpu",0700)&&!mkdirat(dir,"freezer",0700));
  int cp=openat(dir,"cpu",DIR_FLAGS),fp=openat(dir,"freezer",DIR_FLAGS);
  CHECK(cp>=0&&fp>=0);
  struct oneios_stock_session s={.id=test_id,.phase=ONEIOS_STOCK_PREPARED};
  CHECK(!oneios_raw_source_fixture(&s.raw,&s.id,argv[1]));
  struct oneios_thermal_sample first;CHECK(!oneios_raw_source_read(&s.raw,&first));
  CHECK(!create_parents(&s.groups,dup(cp),dup(fp),test_id.token,70));s.groups_owned=true;
  struct xh_stock_reader raw={0},native={0},slow={0};
  CHECK(!xh_stock_reader_raw(&raw,&s.raw));
  CHECK(!xh_stock_reader_native(&native,&s.id,native_read));
  CHECK(!xh_stock_reader_native(&slow,&s.id,slow_native));
  uint64_t now;CHECK(!xhqs_now(&now));
  CHECK(!xh_stock_reader_request(&slow,now+250000000ull));
  struct xh_stock_reading sample;
  CHECK(!xh_stock_reader_request(&raw,now+1000000000ull));
  CHECK(!xh_stock_reader_take(&raw,true,&sample)&&sample.raw.seq==first.seq+1);
  CHECK(xh_stock_reader_take(&slow,true,&sample)==-ETIMEDOUT&&slow.fault);
  xh_stock_reader_close(&slow);wait_child(slow.child,true);
  int sock[2],display[2];CHECK(!xhqs_pair(sock)&&!pipe2(display,O_CLOEXEC));
  char self[512],fdtext[32],pidtext[32],dptext[32];
  ssize_t len=readlink("/proc/self/exe",self,sizeof self-1);
  CHECK(len>0&&(size_t)len<sizeof self-1);self[len]=0;
  snprintf(fdtext,sizeof fdtext,"%d",sock[1]);snprintf(pidtext,sizeof pidtext,"%ld",(long)getpid());
  snprintf(dptext,sizeof dptext,"%d",display[0]);
  char *const worker_argv[]={self,"--worker",fdtext,pidtext,NULL};
  char *const display_argv[]={self,"--display",dptext,NULL};
  char *const env[]={"PATH=/usr/bin:/bin",NULL};
  struct oneios_guest_launch l={0};CHECK(!oneios_guest_launch_init(&l,&s.groups));
  CHECK(!oneios_guest_launch_hold(&l,ONEIOS_GUEST_XNUHOST,self,worker_argv,env,&sock[1],1));
  CHECK(!oneios_guest_launch_hold(&l,ONEIOS_GUEST_DISPLAY,self,display_argv,env,&display[0],1));
  close(sock[1]);close(display[0]);
  CHECK(!oneios_guest_launch_release(&l));
  struct xhqs_owner peer;CHECK(!xhqs_owner_init(&peer,sock[0],l.root[0].pid,getuid(),getgid(),17,1));
  struct ownership proof={&l,&peer};
  struct xh_stock_runner runner={0};CHECK(!xhqs_now(&now));
  uint64_t deadline=now+40000000000ull;
  CHECK(xh_stock_runner_bind(&runner,&s,&l,&peer,&raw,&native,deadline,verify_owner,verify_outer,&proof)==-EINVAL);
  uint64_t ready_limit=end();int r;
  do{r=xhqs_owner_ready_until(&peer,ready_limit);if(r==-EAGAIN)usleep(1000);}while(r==-EAGAIN);
  CHECK(!r&&peer.runtime_ready);
  CHECK(!xh_stock_runner_bind(&runner,&s,&l,&peer,&raw,&native,deadline,verify_owner,verify_outer,&proof));
  struct emulator e={s.groups.freezer,fp,false};pthread_t ack;
  CHECK(!pthread_create(&ack,NULL,emulate_freezer,&e));
  CHECK(xh_stock_runner_start_guest(&runner)==-EINVAL);
  CHECK(xh_stock_runner_tick(&runner)==ONEIOS_THERMAL_RUNNING);
  put(dir,"sys/class/thermal/thermal_zone2/temp","104800\n");
  CHECK(xh_stock_runner_tick(&runner)==ONEIOS_THERMAL_PAUSED);
  CHECK(s.groups.freeze_confirmed&&s.groups.cpu_pct==10&&peer.phase==XHQ_PARKED);
  CHECK(xh_stock_runner_start_guest(&runner)==-EAGAIN&&!peer.guest_started);
  uint64_t seq=peer.seq;
  put(dir,"sys/class/thermal/thermal_zone2/temp","45000\n");
  enum oneios_thermal_result result=ONEIOS_THERMAL_PAUSED;
  for(unsigned i=0;i<14&&result==ONEIOS_THERMAL_PAUSED;i++){
    sleep(1);result=xh_stock_runner_tick(&runner);
    if(result==ONEIOS_THERMAL_PAUSED)CHECK(peer.seq==seq);
  }
  CHECK(result==ONEIOS_THERMAL_RUNNING&&!s.groups.freeze_confirmed&&peer.phase==XHQ_DONE);
  CHECK(s.groups.cpu_pct==10&&!s.controller.freq_applied);
  CHECK(!xh_stock_runner_start_guest(&runner)&&peer.guest_started);
  CHECK(xh_stock_runner_start_guest(&runner)==-EINVAL);
  put(dir,"sys/class/thermal/thermal_zone2/type","wrong-cpu\n");
  CHECK(xh_stock_runner_tick(&runner)==ONEIOS_THERMAL_FAULT_QUIESCED);
  CHECK(s.controller.fault&&s.groups.freeze_confirmed&&peer.phase==XHQ_PARKED);
  CHECK(xh_stock_runner_tick(&runner)==ONEIOS_THERMAL_FAULT_QUIESCED);
  xhqs_owner_close(&peer);close(display[1]);
  xh_stock_reader_close(&raw);xh_stock_reader_close(&native);
  wait_child(l.root[0].pid,false);wait_child(l.root[1].pid,false);
  wait_child(raw.child,false);wait_child(native.child,false);
  oneios_guest_launch_close(&l);
  __atomic_store_n(&e.stop,true,__ATOMIC_RELEASE);CHECK(!pthread_join(ack,NULL));
  put(s.groups.cpu,"cgroup.procs","");put(s.groups.freezer,"cgroup.procs","");
  CHECK(!oneios_stock_session_retire_empty(&s));
  close(cp);close(fp);close(dir);
  printf("STOCK_SESSION_E2E_OFFLINE=PASS parent_checks=%u DEVICE_ACCESS=NONE\n",checks);
  return 0;
}
