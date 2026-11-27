/* SPDX-License-Identifier: MIT */
#define _GNU_SOURCE
#include "stock_hal.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static bool valid_id(const struct oneios_thermal_identity *id)
{
    if (!id || !memchr(id->boot,0,sizeof id->boot) ||
        !memchr(id->generation,0,sizeof id->generation) ||
        !memchr(id->token,0,sizeof id->token) ||
        strlen(id->boot)!=36 || strlen(id->token)!=32 ||
        strspn(id->token,"0123456789abcdef")!=32 ||
        !id->generation[0] ||
        strspn(id->generation,"0123456789abcdef.-")!=strlen(id->generation))
        return false;
    for (unsigned i=0;i<36;i++) {
        bool hyphen=i==8||i==13||i==18||i==23;
        if (hyphen ? id->boot[i]!='-' :
            !strchr("0123456789abcdef",id->boot[i])) return false;
    }
    return true;
}
static int now_ms(uint64_t *ms)
{
    struct timespec t;
    if (clock_gettime(CLOCK_BOOTTIME,&t) || t.tv_sec<0) return -EIO;
    *ms=(uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;
    return 0;
}
static bool boot_matches(const struct oneios_thermal_identity *id)
{
    FILE *f=fopen("/proc/sys/kernel/random/boot_id","r");
    if (!f) return false;
    char b[64]={0};
    size_t n=fread(b,1,sizeof b,f);
    bool ok=!ferror(f) && n==37 && b[36]=='\n' && !memcmp(b,id->boot,36);
    fclose(f);
    return ok;
}
int oneios_stock_hal_from_snapshot(const struct oneios_thermal_identity *id,
    uint64_t seq,uint64_t start,uint64_t end,const hal_thermal_snapshot *snapshot,
    struct oneios_thermal_native_sample *out)
{
    if (!out || !valid_id(id) || !seq || end<start ||
        end-start>ONEIOS_THERMAL_MAX_SAMPLE_AGE_MS) return -EINVAL;
    int severity=hal_thermal_snapshot_severity(snapshot);
    if (severity<0 || severity>6) return -ENODATA;
    *out=(struct oneios_thermal_native_sample){.id=*id,.seq=seq,.ms=start,.severity=severity};
    return 0;
}
int oneios_stock_hal_read(const struct oneios_thermal_identity *id,uint64_t seq,
    struct oneios_thermal_native_sample *out)
{
    uint64_t start,end;
    if (!out || !valid_id(id) || !seq || geteuid()!=0) return -EPERM;
    if (now_ms(&start) || !boot_matches(id)) return -ESTALE;
    hal_thermal_snapshot snapshot;
    char why[256]="";
    int rc=br_hal_thermal_snapshot_read(NULL,&snapshot,why,sizeof why);
    if (rc) return rc<0 ? rc : -EIO;
    if (!boot_matches(id) || now_ms(&end)) return -ESTALE;
    return oneios_stock_hal_from_snapshot(id,seq,start,end,&snapshot,out);
}
