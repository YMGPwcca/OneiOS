// SPDX-License-Identifier: MIT
// Host-only isolated tests of the real SM8850 stage admission policy.
// No Android services, root, phone, APFS Data or thermal nodes touched.
#include <stdio.h>
#include "../src/sm8850_stage_admission.h"

static int checks, failures;
#define CHECK(ok) do { \
  checks++; \
  if (!(ok)) { \
    fprintf(stderr, "FAIL %s:%d: %s\\n", __FILE__, __LINE__, #ok); \
    failures++; \
  } \
} while (0)

#define PROFILE(gen, soft, duration, confirmed, deadline, guard, cap) \
  xh_sm8850_classify_stage(gen, soft, duration, confirmed, deadline, guard, cap)

int main(void)
{
  const char *g = "dc38c332-7223-48e6-bdcf-672f3cf99ed4.9036.500404";
  const char *old = "a903e9a5-dc25-4c53-a848-6ab2bd5d3a20.21821.1663370";

  // Normal production run must continue to require BOTH real workers.
  CHECK(PROFILE(g, NULL, NULL, NULL, NULL, g, g) == XH_SM8850_STAGE_GUARDED);
  CHECK(PROFILE(g, "", NULL, NULL, NULL, g, g) == XH_SM8850_STAGE_GUARDED);
  CHECK(PROFILE(g, NULL, NULL, NULL, NULL, old, g) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, NULL, NULL, NULL, NULL, g, old) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, NULL, NULL, NULL, NULL, g, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, NULL, NULL, NULL, NULL, NULL, g) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE("", NULL, NULL, NULL, NULL, "", "") == XH_SM8850_STAGE_REFUSED);

  // The actual physical failed session: no guard/cap markers, but a
  // current-generation Framework stop and an armed 180s reboot deadline.
  CHECK(PROFILE(g, "disabled-180s", "180", g, "5236", NULL, NULL) ==
        XH_SM8850_STAGE_NO_USERSPACE_THERMAL_180S);
  // Even stale worker markers cannot manufacture this opt-in.
  CHECK(PROFILE(g, "disabled-180s", "180", g, "5236", old, old) ==
        XH_SM8850_STAGE_NO_USERSPACE_THERMAL_180S);

  // All incomplete or forged exceptional admissions MUST still refuse,
  // including unknown soft-thermal labels even if valid workers exist.
  CHECK(PROFILE(g, "monitor-only", "180", g, "5236", g, g) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled", "180", g, "5236", g, g) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "600", g, "5236", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "0180", g, "5236", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", NULL, g, "5236", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "180", old, "5236", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "180", NULL, "5236", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "180", g, NULL, NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "180", g, "", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "180", g, "0", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "180", g, "-1", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "180", g, "5236x", NULL, NULL) == XH_SM8850_STAGE_REFUSED);
  CHECK(PROFILE(g, "disabled-180s", "180", g, "999999999999999999999999", NULL, NULL) == XH_SM8850_STAGE_REFUSED);

  printf("SM8850 admission policy: %d checks, %d failures\\n", checks, failures);
  return failures ? 1 : 0;
}
