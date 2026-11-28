/* SPDX-License-Identifier: MIT
 * Physical actuator capability test ONLY. Two idle sleep processes,
 * fresh private leaves, Framework ON. No image, XNUHost, admission,
 * clock votes or modification to the existing guest stage. */
#define _GNU_SOURCE
#include "sm8850_guest_launch.h"
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int init_ns(void)
{
    struct stat a,b;
    return !stat("/proc/self/ns/mnt",&a)&&!stat("/proc/1/ns/mnt",&b)&&
        a.st_dev==b.st_dev&&a.st_ino==b.st_ino;
}
static int report(const char *step,int rc)
{
    if(rc)fprintf(stderr,"%s=FAIL errno=%d (%s)\n",step,errno,strerror(errno));
    else printf("%s=PASS\n",step);
    return rc;
}
static int retire_child(pid_t pid)
{
    if(pid<=1)return 0;
    int st;
    pid_t r=waitpid(pid,&st,WNOHANG);
    if(r==pid)return 0;
    if(r<0)return errno==ECHILD?0:-1;
    // Exclusive waitpid owner; this unreaped child PID cannot be reused.
    if(kill(pid,SIGKILL)&&errno!=ESRCH)return -1;
    for(unsigned i=0;i<100;i++){
        r=waitpid(pid,&st,WNOHANG);
        if(r==pid)return 0;
        if(r<0&&errno!=EINTR)return -1;
        nanosleep(&(struct timespec){.tv_nsec=20000000L},NULL);
    }
    errno=ETIMEDOUT;return -1;
}
int main(int argc,char **argv)
{
    setvbuf(stdout,NULL,_IONBF,0);
    if(argc==3&&!strcmp(argv[1],"--idle")){
        // A parent failure must not leave these diagnostic children
        // executing. No access to guest files or devices.
        pid_t p=getppid();
        char *end;long expected=strtol(argv[2],&end,10);
        if(*end||expected<=1||p!=(pid_t)expected||
           prctl(PR_SET_PDEATHSIG,SIGKILL,0,0,0)||getppid()!=p)return 2;
        struct timespec t={.tv_sec=20};
        while(nanosleep(&t,&t)&&errno==EINTR){}
        return 0;
    }
    if(argc!=2||geteuid()!=0||getegid()!=0||!init_ns()||
       strlen(argv[1])!=32||strspn(argv[1],"0123456789abcdef")!=32||
       prctl(PR_SET_CHILD_SUBREAPER,1,0,0,0))return 2;
    char exe[512],pid[32];
    ssize_t n=readlink("/proc/self/exe",exe,sizeof exe-1);
    if(n<=0||(size_t)n>=sizeof exe-1)return 2;
    exe[n]=0;snprintf(pid,sizeof pid,"%ld",(long)getpid());
    char *const child[]={exe,"--idle",pid,NULL};
    char *const env[]={"PATH=/system/bin:/system/xbin",NULL};
    struct oneios_owned_groups g;
    struct oneios_guest_launch l={0};
    int rc=1;
    // 10 and 20 are ONLY idle actuator readback test values.
    // They are not startup budget recommendations or qualification.
    if(report("PRIVATE_LEAF_CREATE",oneios_owned_groups_create(&g,argv[1],10)))return 4;
    if(report("HELD_LAUNCH_INIT",oneios_guest_launch_init(&l,&g)))goto out;
    if(report("HELD_ROOT_0",oneios_guest_launch_hold(&l,ONEIOS_GUEST_XNUHOST,exe,child,env,NULL,0)))goto out;
    if(report("HELD_ROOT_1",oneios_guest_launch_hold(&l,ONEIOS_GUEST_DISPLAY,exe,child,env,NULL,0)))goto out;
    if(report("PRIVATE_ROOT_READBACK",oneios_guest_launch_check_roots(&l)))goto out;
    if(report("PRIVATE_ROOT_RELEASE",oneios_guest_launch_release(&l)))goto out;
    if(report("PRIVATE_CPU_QUOTA_20",oneios_owned_cpu_set(&g,20)))goto out;
    if(report("PRIVATE_CPU_QUOTA_10",oneios_owned_cpu_set(&g,10)))goto out;
    if(report("PRIVATE_FREEZE_ACK",oneios_owned_freeze(&g,1000)))goto out;
    if(report("PRIVATE_FREEZE_VERIFY",oneios_owned_groups_verify(&g,true)))goto out;
    int tree=-1;
    for(unsigned i=0;i<3;i++){
        tree=oneios_guest_launch_check_tree(&l,NULL,0);
        if(!tree||errno!=EAGAIN)break;
    }
    if(report("PRIVATE_TREE_READBACK",tree))goto out;
    // Idle diagnostic children, never actual guest/provider gates.
    if(report("PRIVATE_THAW_ACK",oneios_owned_thaw(&g,1000)))goto out;
    if(report("PRIVATE_THAW_VERIFY",oneios_owned_groups_verify(&g,false)))goto out;
    rc=0;
out:
    // Terminal kill only of this new identity-pinned private leaf.
    if(report("PRIVATE_LEAF_KILL",oneios_owned_groups_kill(&g)))rc=1;
    oneios_guest_launch_close(&l);
    for(unsigned i=0;i<ONEIOS_GUEST_ROOTS;i++)
        if(report("PRIVATE_CHILD_RETIRE",retire_child(l.root[i].pid)))rc=1;
    int removed=-1;
    for(unsigned i=0;i<50;i++){
        removed=oneios_owned_groups_remove_empty(&g);
        if(!removed||g.cpu<0||g.freezer<0)break;
        nanosleep(&(struct timespec){.tv_nsec=20000000L},NULL);
    }
    if(report("PRIVATE_LEAF_REMOVE_EMPTY",removed))rc=1;
    oneios_owned_groups_close(&g);
    puts(rc?"STOCK_PHYSICAL_ACTUATORS=FAIL":"STOCK_PHYSICAL_ACTUATORS=PASS");
    puts("GUEST_BOOT=NONE; FRAMEWORK_STOP=NONE; LIVE_ADMISSION=NONE");
    return rc?4:0;
}
