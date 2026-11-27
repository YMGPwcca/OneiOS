/* Host-only native HAL-to-controller typed sample test.
 * Uses the real AIDL parcel decoder and exact qualified severity function;
 * never opens Binder, a device or the production HAL reader. */
#include "stock_hal.h"
#include <stdio.h>
#include <string.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"FAIL %d: %s\n",__LINE__,#x); return 1; } } while (0)

int main(void)
{
    struct oneios_thermal_identity id={
        "51ca8a7b-7fe0-4075-be5f-6a9029b8d392",
        "51ca8a7b-7fe0-4075-be5f-6a9029b8d392.123.456",
        "ee7c626acb814d92901a8672dc8169ef"
    };
    hal_temperature entries[]={
        {0,"AP",49.5f,0},{5,"PA",48.6f,0},{2,"BAT",40.9f,0},
        {4,"USB",35.6f,0},{3,"SKIN",42.8f,2},{2,"SUBBAT",0.0f,0}
    };
    ab_parcel p; ab_reader reader;
    hal_thermal_snapshot snap={.version=3};
    ab_init(&p); hal_temperatures_encode(&p,entries,6);
    ab_reader_init(&reader,p.data,p.size,NULL,0);
    CHECK(!hal_thermal_snapshot_decode(&reader,&snap));
    struct oneios_thermal_native_sample out={0};
    CHECK(!oneios_stock_hal_from_snapshot(&id,1,1000,1010,&snap,&out));
    CHECK(out.seq==1 && out.ms==1000 && out.severity==2);
    CHECK(!strcmp(out.id.boot,id.boot) && !strcmp(out.id.generation,id.generation) && !strcmp(out.id.token,id.token));
    snap.temps[4].throttling=4;
    CHECK(!oneios_stock_hal_from_snapshot(&id,2,2000,2001,&snap,&out) && out.severity==4);
    CHECK(oneios_stock_hal_from_snapshot(&id,3,3000,5001,&snap,&out)<0 && out.seq==2);
    CHECK(oneios_stock_hal_from_snapshot(&id,0,3000,3001,&snap,&out)<0 && out.seq==2);
    CHECK(oneios_stock_hal_from_snapshot(&id,3,3000,2999,&snap,&out)<0);
    snap.temps[4].celsius=0;
    CHECK(oneios_stock_hal_from_snapshot(&id,3,3000,3001,&snap,&out)<0 && out.seq==2 && out.severity==4);
    snap.temps[4].celsius=47; snap.version=2;
    CHECK(oneios_stock_hal_from_snapshot(&id,3,3000,3001,&snap,&out)<0);
    snap.version=3; id.token[0]='z';
    CHECK(oneios_stock_hal_from_snapshot(&id,3,3000,3001,&snap,&out)<0);
    printf("STOCK_HAL_SAMPLE=PASS checks=%u DEVICE_ACCESS=NONE\n",checks);
    return 0;
}
