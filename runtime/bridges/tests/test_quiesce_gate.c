// SPDX-License-Identifier: MIT
#include "bridges/quiesce.h"
#include <stdio.h>
#include <stdlib.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
int main(void)
{
  brq_gate g = {0};
  uint64_t ticket = 0, last = 0;
  CHECK(brq_close(&g, false, NULL) == -EINVAL);
  CHECK(brq_poll(&g, 0, false) == -ESTALE && !brq_late(&g));
  for (unsigned i = 0; i < 12; i++) {
    CHECK(brq_close(&g, true, &ticket) == -EAGAIN && ticket == last && !g.closed);
    CHECK(brq_close(&g, false, &ticket) == 0 && ticket == last+1 && g.closed);
    CHECK(brq_close(&g, false, &last) == -EBUSY && last+1 == ticket);
    CHECK(brq_poll(&g, last, false) == -ESTALE);
    CHECK(brq_poll(&g, ticket, true) == -EAGAIN && !g.verified);
    CHECK(brq_resume(&g, ticket, false) == -EBUSY && g.closed);
    CHECK(brq_poll(&g, ticket, false) == 0 && g.verified);
    CHECK(brq_resume(&g, ticket, true) == -EAGAIN && g.closed);
    CHECK(brq_can_resume(&g, ticket, false) == 0 && g.closed);
    CHECK(brq_resume(&g, ticket, false) == 0 && !g.closed);
    CHECK(brq_poll(&g, ticket, false) == -ESTALE && !g.verified);
    last = ticket;
  }
  CHECK(brq_close(&g, false, &ticket) == 0 && brq_poll(&g, ticket, false) == 0);
  CHECK(brq_late(&g) && g.fault);
  CHECK(brq_resume(&g, ticket, false) == -ESTALE && g.closed);
  CHECK(brq_poll(&g, ticket, false) == -ESTALE && brq_close(&g, false, &last) == -ESTALE);
  brq_gate full = { .generation = UINT64_MAX };
  CHECK(brq_close(&full, false, &ticket) == -EOVERFLOW && !full.closed);
  brq_report slots[BRQ_REPORTS] = {0};
  unsigned value = 0;
  CHECK(brq_report_mask(slots) == 0);
  CHECK(brq_store(slots, BRQ_REPORTS, &value, sizeof value) == -EINVAL);
  CHECK(brq_store(slots, 0, NULL, sizeof value) == -EINVAL);
  CHECK(brq_store(slots, 0, &value, 0) == -EINVAL);
  CHECK(brq_store(slots, 0, &value, BRQ_REPORT_BYTES+1) == -EINVAL);
  CHECK(brq_report_mask(slots) == 0);
  for (unsigned i = 0; i < 500; i++) {
    for (unsigned j = 0; j < BRQ_REPORTS; j++) {
      value = i*BRQ_REPORTS+j;
      CHECK(brq_store(slots, j, &value, sizeof value) == 0);
      CHECK(slots[j].length == sizeof value && !memcmp(slots[j].bytes, &value, sizeof value));
    }
    CHECK(brq_report_mask(slots) == 7);
  }
  for (unsigned j = 0; j < BRQ_REPORTS; j++) {
    value = 499*BRQ_REPORTS+j;
    CHECK(!memcmp(slots[j].bytes, &value, sizeof value));
  }
  unsigned char large[BRQ_REPORT_BYTES]; memset(large, 0x5a, sizeof large);
  CHECK(brq_store(slots, 0, large, sizeof large) == 0 && !memcmp(slots[0].bytes, large, sizeof large));
  memset(slots, 0, sizeof slots);
  CHECK(brq_report_mask(slots) == 0);
  printf("bridge gate and telemetry: %u checks, 0 failed\n", checks);
  return 0;
}
