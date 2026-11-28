/* SPDX-License-Identifier: MIT
 * SM8850 root-side session owner. Runs in init's namespace and outside
 * both guest leaves. The switcher owns admission and independent recovery.
 * This program never stops Framework, changes clocks, thaws on fault,
 * reboots, or fabricates a board/drain receipt. */
#define _GNU_SOURCE
#include "stock_session_runner.h"
#include "stock_hal.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define STAGE "/data/adb/oneios-m3q-framework"
#define CTL STAGE "/control"
#define SESSION STAGE "/session"
#define SWITCH STAGE "/oneios_switch.sh"
#define NS_PER_S UINT64_C(1000000000)
struct owner {
    struct oneios_stock_session session;
    struct oneios_guest_launch launch;
    struct xh_stock_reader raw,native;
    struct xhqs_owner peer;
    struct xh_stock_runner runner;
    struct oneios_thermal_identity id;
    struct oneios_thermal_sample sample;
    struct oneios_thermal_native_sample native_sample;
    struct oneios_thermal_policy setup;
    bool native_valid, peer_open, ready;
    int ctl, channel, helper_copy;
    uint64_t deadline, owner_id, prearm_end;
    const char *busybox;
};
static int number(const char *s,uint64_t *n)
{
    if(!s||!*s||strspn(s,"0123456789")!=strlen(s))return -EINVAL;
    char *end;errno=0;
    unsigned long long v=strtoull(s,&end,10);
    if(errno||*end)return -EINVAL;
    *n=v;return 0;
}
static int line_at(int dir,const char *name,char *buf,size_t size,bool trusted)
{
    int fd=openat(dir,name,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0)return -errno;
    struct stat st;
    if(fstat(fd,&st)||!S_ISREG(st.st_mode)||
       (trusted&&(st.st_uid!=0||(st.st_mode&0022)))){close(fd);return -EPERM;}
    size_t off=0;
    while(off<size-1){
        ssize_t n=read(fd,buf+off,size-1-off);
        if(n<0&&errno==EINTR)continue;
        if(n<0){int r=-errno;close(fd);return r;}
        if(!n)break;
        off+=(size_t)n;
    }
    close(fd);
    if(!off||off==size-1||memchr(buf,0,off))return -EINVAL;
    if(buf[off-1]=='\n')off--;
    buf[off]=0;
    return !off||strchr(buf,'\n')||strchr(buf,'\r')?-EINVAL:0;
}
static bool ctl_is(struct owner *o,const char *key,const char *value)
{
    char b[256];
    return !line_at(o->ctl,key,b,sizeof b,true)&&!strcmp(b,value);
}
static bool same_ctl(struct owner *o)
{
    struct stat a,b;
    return o->ctl>=0&&!fstat(o->ctl,&a)&&!lstat(CTL,&b)&&
      S_ISDIR(b.st_mode)&&a.st_dev==b.st_dev&&a.st_ino==b.st_ino;
}
static bool current(struct owner *o)
{
    char boot[64];
    return same_ctl(o)&&!line_at(AT_FDCWD,"/proc/sys/kernel/random/boot_id",boot,sizeof boot,false)&&
      !strcmp(boot,o->id.boot)&&ctl_is(o,"boot",o->id.boot)&&
      ctl_is(o,"watchdog.generation",o->id.generation)&&ctl_is(o,"framework.launch",o->id.token)&&
      ctl_is(o,"framework.stock-profile","ui-v1")&&
      (ctl_is(o,"state","starting")||ctl_is(o,"state","running"))&&
      access(SESSION "/return.request",F_OK)!=0;
}
static int record(struct owner *o,const char *key,const char *line)
{
    char tmp[96];
    if(!same_ctl(o)||snprintf(tmp,sizeof tmp,"%s.next.%ld",key,(long)getpid())>=(int)sizeof tmp)return -ESTALE;
    int fd=openat(o->ctl,tmp,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600);
    if(fd<0)return -errno;
    size_t len=strlen(line);ssize_t n=write(fd,line,len);
    int c=close(fd);
    if(n!=(ssize_t)len||c||renameat(o->ctl,tmp,o->ctl,key)){
        unlinkat(o->ctl,tmp,0);return -EIO;
    }
    return 0;
}
static int heartbeat(struct owner *o,const char *phase,const struct oneios_thermal_sample *s)
{
    uint64_t now;
    if(!current(o)||!s||!s->seq||xhqs_now(&now)||now/1000000u<s->ms||
       now/1000000u-s->ms>ONEIOS_THERMAL_MAX_SAMPLE_AGE_MS)return -ESTALE;
    char b[320];
    int n=snprintf(b,sizeof b,"v1 %s %s %s %ld %llu %llu %s\n",
      o->id.boot,o->id.generation,o->id.token,(long)getpid(),
      (unsigned long long)s->seq,(unsigned long long)(s->ms/1000u),phase);
    if(n<=0||(size_t)n>=sizeof b)return -EOVERFLOW;
    return record(o,"stock.owner.heartbeat",b);
}
static bool ns_equal(pid_t a,pid_t b)
{
    char p[64],q[64];struct stat x,y;
    snprintf(p,sizeof p,"/proc/%ld/ns/mnt",(long)a);
    snprintf(q,sizeof q,"/proc/%ld/ns/mnt",(long)b);
    return !stat(p,&x)&&!stat(q,&y)&&x.st_dev==y.st_dev&&x.st_ino==y.st_ino;
}
static bool trusted_executable(const char *p)
{
    struct stat s;
    return p&&p[0]=='/'&&!lstat(p,&s)&&S_ISREG(s.st_mode)&&
      s.st_uid==0&&!(s.st_mode&0022)&&(s.st_mode&0100);
}
static uint64_t limit(uint64_t end,unsigned ms)
{
    uint64_t now;
    if(xhqs_now(&now)||now>=end)return 0;
    uint64_t delta=(uint64_t)ms*1000000u;
    return end-now<delta?end:now+delta;
}
/* The native reader is optional for sampling but not for new work. Raw
 * progress never waits for Binder. No stale severity is promoted to zero. */
static void take_native(struct owner *o)
{
    if(o->native.fault){o->native_valid=false;return;}
    if(!o->native.pending)return;
    struct xh_stock_reading r;
    int rc=xh_stock_reader_take(&o->native,false,&r);
    if(!rc){o->native_sample=r.native;o->native_valid=true;}
    else if(rc!=-EAGAIN)o->native_valid=false;
}
static int sample_setup(struct owner *o,uint64_t end,bool request_native)
{
    uint64_t t=limit(end,ONEIOS_THERMAL_MAX_SAMPLE_AGE_MS);
    if(!t)return -ETIMEDOUT;
    take_native(o);
    if(request_native&&!o->native.pending&&!o->native.fault&&
       xh_stock_reader_request(&o->native,t))o->native_valid=false;
    struct xh_stock_reading r;
    int rc=xh_stock_reader_request(&o->raw,t);
    if(!rc)rc=xh_stock_reader_take(&o->raw,true,&r);
    if(rc)return rc;
    o->sample=r.raw;take_native(o);
    uint64_t now;
    if(xhqs_now(&now)||!o->native_valid||now/1000000u<o->native_sample.ms||
       now/1000000u-o->native_sample.ms>ONEIOS_THERMAL_MAX_SAMPLE_AGE_MS)o->native_valid=false;
    return 0;
}
/* Apply the existing raw policy during pre-guest setup, but never raise
 * the explicitly qualified initial demand before the full controller.
 * A severe setup sample requires terminal retirement: a not-yet-bound
 * board cannot claim a GPU drain. No automatic thaw or thermal reboot. */
static int setup_reduce(struct owner *o)
{
    enum oneios_thermal_action a=oneios_thermal_policy_step(&o->setup,&o->sample);
    if(a==ONEIOS_THERMAL_INVALID)return -EINVAL;
    unsigned cap=o->setup.cpu_pct;
    static const unsigned native_cap[]={100,80,60,25,10,10,10};
    if(o->native_valid&&cap>native_cap[o->native_sample.severity])
        cap=native_cap[o->native_sample.severity];
    if(cap>o->session.groups.cpu_pct)cap=o->session.groups.cpu_pct;
    if(oneios_owned_cpu_set(&o->session.groups,cap))return -EPERM;
    o->setup.cpu_pct=cap;
    return a==ONEIOS_THERMAL_QUIESCE||
      (o->native_valid&&o->native_sample.severity>=4)?1:0;
}
static bool setup_cool(struct owner *o)
{
    const struct oneios_thermal_sample *s=&o->sample;
    return o->native_valid&&o->native_sample.severity==0&&!o->setup.hard&&
      !o->setup.paused&&s->cpu_mc<70000&&s->gpu_mc<70000&&s->ddr_mc<70000&&
      s->battery_dc<340&&s->lrp_dc<370&&s->board_ap_dc<450;
}
static int admitted_deadline(struct owner *o)
{
    char want[192],text[64];uint64_t seconds,now;
    snprintf(want,sizeof want,"%s %s %s",o->id.generation,o->id.token,o->id.boot);
    if(!ctl_is(o,"framework.stock-admission",want))return -EAGAIN;
    if(!ctl_is(o,"framework.mode","run")||!ctl_is(o,"framework.return","reboot")||
       !ctl_is(o,"framework.interaction-profile","off")||
       !ctl_is(o,"framework.own-presence","0")||
       faccessat(o->ctl,"stopped",F_OK,0)||
       !faccessat(o->ctl,"thermal.guard.required",F_OK,0)||
       !faccessat(o->ctl,"thermal.cap.required",F_OK,0)||
       !faccessat(o->ctl,"thermal.cap.prearm.required",F_OK,0)||
       line_at(o->ctl,"framework.deadline",text,sizeof text,true)||
       number(text,&seconds)||seconds>UINT64_MAX/NS_PER_S||
       xhqs_now(&now)||seconds*NS_PER_S<=now||
       seconds*NS_PER_S-now>600u*NS_PER_S)return -EPERM;
    o->deadline=seconds*NS_PER_S;return 0;
}
static int verify_tree(struct owner *o)
{
    pid_t controls[]={o->raw.child,o->native.child};
    for(unsigned attempt=0;attempt<3;attempt++){
        if(!oneios_guest_launch_check_tree(&o->launch,controls,2))return 0;
        if(errno!=EAGAIN)return -EPERM;
        nanosleep(&(struct timespec){.tv_nsec=2000000L},NULL);
    }
    return -EAGAIN;
}
static int verify_owner(void *ctx,const struct oneios_thermal_identity *id)
{
    struct owner *o=ctx;
    uint64_t now;
    if(strcmp(id->boot,o->id.boot)||strcmp(id->generation,o->id.generation)||
       strcmp(id->token,o->id.token)||!current(o)||xhqs_now(&now)||now>=o->deadline||
       !ns_equal(o->launch.root[ONEIOS_GUEST_DISPLAY].pid,1)||
       ns_equal(o->launch.root[ONEIOS_GUEST_XNUHOST].pid,1))return -ESTALE;
    return verify_tree(o);
}
static int verify_outer(void *ctx,bool parked)
{
    struct owner *o=ctx;
    // The supervisor itself validates the complete credentialed board
    // receipt and separate freezer ACK. Here recheck external ownership,
    // both namespace roles and current session; phase alone is not proof.
    if(parked?o->peer.phase!=XHQ_PARKED:
       (o->peer.phase!=XHQ_IDLE&&o->peer.phase!=XHQ_DONE))return -EPERM;
    return verify_owner(o,&o->id);
}
static int launch_roots(struct owner *o)
{
    int pair[2];
    if(oneios_guest_launch_init(&o->launch,&o->session.groups)||xhqs_pair(pair))return -EPERM;
    o->channel=pair[0];
    char *const display[]={"/system/bin/sh",SWITCH,"--stock-display",NULL};
    char *const env[]={"PATH=/system/bin:/system/xbin","HOME=/",NULL};
    int rc=oneios_guest_launch_hold(&o->launch,ONEIOS_GUEST_DISPLAY,display[0],display,env,NULL,0);
    if(rc){close(pair[1]);return -EPERM;}
    o->helper_copy=fcntl(o->launch.root[ONEIOS_GUEST_DISPLAY].pidfd,F_DUPFD_CLOEXEC,3);
    if(o->helper_copy<0){close(pair[1]);return -errno;}
    char fd[64],helper[64],pid[64],owner[64],deadline[64],token[80],gen[160],boot[80],bb[256];
    snprintf(fd,sizeof fd,"ONEIOS_STOCK_CONTROL_FD=%d",pair[1]);
    snprintf(helper,sizeof helper,"ONEIOS_STOCK_HELPER_PIDFD=%d",o->helper_copy);
    snprintf(pid,sizeof pid,"ONEIOS_STOCK_OWNER_PID=%ld",(long)getpid());
    snprintf(owner,sizeof owner,"ONEIOS_STOCK_OWNER_ID=%llu",(unsigned long long)o->owner_id);
    snprintf(deadline,sizeof deadline,"ONEIOS_STOCK_DEADLINE_NS=%llu",(unsigned long long)o->deadline);
    snprintf(token,sizeof token,"ONEIOS_STOCK_TOKEN=%s",o->id.token);
    snprintf(gen,sizeof gen,"ONEIOS_STOCK_GENERATION=%s",o->id.generation);
    snprintf(boot,sizeof boot,"ONEIOS_STOCK_BOOT=%s",o->id.boot);
    if(snprintf(bb,sizeof bb,"BB=%s",o->busybox)>=(int)sizeof bb){close(pair[1]);return -EOVERFLOW;}
    char *const inner[]={(char *)o->busybox,"unshare","-m","/system/bin/sh",SWITCH,"--stock-inner",NULL};
    char *const inner_env[]={"PATH=/system/bin:/system/xbin","HOME=/","ONEIOS_CAMERA=0",
        fd,helper,pid,owner,deadline,token,gen,boot,bb,NULL};
    int pass[]={pair[1],o->helper_copy};
    rc=oneios_guest_launch_hold(&o->launch,ONEIOS_GUEST_XNUHOST,inner[0],inner,inner_env,pass,2);
    close(pair[1]);close(o->helper_copy);o->helper_copy=-1;
    if(rc)return -EPERM;
    char ids[64];
    snprintf(ids,sizeof ids,"%ld %ld\n",(long)o->launch.root[ONEIOS_GUEST_XNUHOST].pid,
      (long)o->launch.root[ONEIOS_GUEST_DISPLAY].pid);
    if(record(o,"stock.roots",ids)||!current(o)||
       oneios_guest_launch_release(&o->launch))return -EPERM;
    return 0;
}
static int bind_ready(struct owner *o)
{
    if(o->ready)return 0;
    char b[32];uint64_t blocks;
    // This guest-writable file is only a scheduling hint. The IPC
    // handshake verifies the actual sealed board member mask independently.
    int r=line_at(AT_FDCWD,SESSION "/stock.setup-ready",b,sizeof b,false);
    if(r==-ENOENT)return -EAGAIN;
    if(r||number(b,&blocks)||!blocks||blocks>XHQ_MAX_BLOCKS)return -EPROTO;
    if(verify_owner(o,&o->id))return -EPERM;
    if(!o->peer_open){
        r=xhqs_owner_init(&o->peer,o->channel,o->launch.root[ONEIOS_GUEST_XNUHOST].pid,
             0,0,o->owner_id,(unsigned)blocks);
        if(r)return r;
        o->peer_open=true;o->channel=-1;
    }
    uint64_t t=limit(o->deadline,ONEIOS_THERMAL_ACK_MS);
    if(!t)return -ETIMEDOUT;
    r=xhqs_owner_ready_until(&o->peer,t);
    if(!r)o->ready=true;
    return r;
}
static void nap(void)
{
    nanosleep(&(struct timespec){.tv_nsec=250000000L},NULL);
}
/* The caller has already armed independent deadline/recovery. The
 * PREARM heartbeat is evidence only; it cannot release either child. */
static int drive(struct owner *o,unsigned pct)
{
    if(oneios_stock_session_prepare(&o->session,&o->id,pct))return -EPERM;
    o->setup=(struct oneios_thermal_policy){.freq_pct=100,.floor_pct=100,.cpu_pct=pct};
    if(xh_stock_reader_raw(&o->raw,&o->session.raw)||
       xh_stock_reader_native(&o->native,&o->id,oneios_stock_hal_read))return -EIO;
    for(;;){
        if(!current(o))return -ECANCELED;
        int r=admitted_deadline(o);
        if(r&&r!=-EAGAIN)return r;
        uint64_t end=r?o->prearm_end:o->deadline;
        if((r=sample_setup(o,end,true)))return r;
        r=setup_reduce(o);
        if(r<0)return r;
        if(heartbeat(o,"prearm",&o->sample))return -ESTALE;
        if(o->deadline&&setup_cool(o))break;
        nap();
    }
    if(launch_roots(o))return -EPERM;
    for(;;){
        if(!current(o))return -ECANCELED;
        int r=sample_setup(o,o->deadline,!o->ready);
        if(r)return r;
        r=setup_reduce(o);
        if(r<0)return r;
        if(r>0){fprintf(stderr,"STOCK_SETUP_RETIRE=THERMAL_NO_GUEST_ENTRY\n");return -ERANGE;}
        if(verify_tree(o)||heartbeat(o,"setup",&o->sample))return -ESTALE;
        r=bind_ready(o);
        if(r&&r!=-EAGAIN)return r;
        if(o->ready&&!o->native.pending)break;
        nap();
    }
    if(o->native.fault)return -ENODATA;
    int rc=xh_stock_runner_bind(&o->runner,&o->session,&o->launch,&o->peer,
        &o->raw,&o->native,o->deadline,verify_owner,verify_outer,o);
    if(rc)return rc;
    for(;;){
        uint64_t now;
        if(xhqs_now(&now)||now>=o->deadline||!current(o))return 0;
        enum oneios_thermal_result r=xh_stock_runner_tick(&o->runner);
        if(r!=ONEIOS_THERMAL_RUNNING&&r!=ONEIOS_THERMAL_PAUSED)return -EIO;
        if(heartbeat(o,r==ONEIOS_THERMAL_PAUSED?"paused":"running",&o->session.controller.last))return -ESTALE;
        if(!o->peer.guest_started){
            rc=xh_stock_runner_start_guest(&o->runner);
            if(rc&&rc!=-EAGAIN)return rc;
            if(!rc)fprintf(stderr,"STOCK_OWNER_GUEST_START=ACK\n");
        }
        nap();
    }
}
/* The owner never signals an arbitrary numeric PID. These are its
 * own unreaped direct children, whose PID cannot have been reused. */
static void stop_child(pid_t pid)
{
    if(pid<=1)return;
    int status;pid_t got=waitpid(pid,&status,WNOHANG);
    if(got==0)(void)kill(pid,SIGKILL);
}
static void cleanup(struct owner *o)
{
    if(o->peer_open)xhqs_owner_close(&o->peer);
    if(o->channel>=0)close(o->channel);
    if(o->helper_copy>=0)close(o->helper_copy);
    oneios_guest_launch_close(&o->launch);
    if(o->session.groups_owned&&oneios_owned_groups_kill(&o->session.groups))
        fprintf(stderr,"STOCK_OWNER_LEAF_KILL=UNCONFIRMED\n");
    for(unsigned i=0;i<ONEIOS_GUEST_ROOTS;i++)stop_child(o->launch.root[i].pid);
    xh_stock_reader_close(&o->raw);xh_stock_reader_close(&o->native);
    stop_child(o->raw.child);stop_child(o->native.child);
    // Bounded best-effort retirement, never thaw a frozen leaf. The
    // independent root recovery path remains authoritative if this fails.
    for(unsigned n=0;n<8&&o->session.groups_owned;n++){
        if(!oneios_stock_session_retire_empty(&o->session))break;
        nap();
    }
    if(o->session.groups_owned)fprintf(stderr,"STOCK_OWNER_RETIRE=UNCONFIRMED\n");
    oneios_stock_session_close(&o->session);
    if(o->ctl>=0)close(o->ctl);
}
int main(int argc,char **argv)
{
    if(argc==2&&!strcmp(argv[1],"--build-info")){
        puts("SM8850_STOCK_OWNER_ABI=1; SETUP_PROTECTION=SOURCE_CANDIDATE; DEVICE_ACCESS=NONE");
        return 0;
    }
    if(argc!=7||strcmp(argv[1],"--prearm")||geteuid()!=0||getegid()!=0||
       !ns_equal(getpid(),1)||!trusted_executable(argv[6]))return 2;
    struct owner o={.ctl=-1,.channel=-1,.helper_copy=-1,.busybox=argv[6]};
    uint64_t pct,now;
    if(strlen(argv[2])!=36||strlen(argv[3])>=sizeof o.id.generation||
       strlen(argv[4])!=32||strspn(argv[4],"0123456789abcdef")!=32||
       number(argv[5],&pct)||pct<10||pct>100||xhqs_now(&now)||
       prctl(PR_SET_CHILD_SUBREAPER,1,0,0,0))return 2;
    strcpy(o.id.boot,argv[2]);strcpy(o.id.generation,argv[3]);strcpy(o.id.token,argv[4]);
    char hex[17];memcpy(hex,o.id.token,16);hex[16]=0;
    o.owner_id=strtoull(hex,NULL,16);
    if(!o.owner_id)return 2;
    o.prearm_end=now+45u*NS_PER_S;
    o.ctl=open(CTL,O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW);
    struct stat st;
    if(o.ctl<0||fstat(o.ctl,&st)||st.st_uid!=0||(st.st_mode&0022)||
       !current(&o)||!ctl_is(&o,"framework.stock-budget",argv[5])){cleanup(&o);return 2;}
    int rc=drive(&o,(unsigned)pct);
    if(rc&&current(&o)){
        char b[64];snprintf(b,sizeof b,"owner-fault %d\n",rc);
        (void)record(&o,"stock.owner.fault",b);
    }
    fprintf(stderr,"STOCK_OWNER_EXIT=%d\n",rc);
    cleanup(&o);
    return rc?4:0;
}
