// SPDX-License-Identifier: MIT
// Pure SM8850 full-bridges admission profile classification.
//
// The guarded profile still requires both root thermal workers from THIS
// watchdog generation. An explicit, one-session 180s no-userspace-thermal
// experiment replaces those workers with the current generation's
// Framework-stop confirmation and an armed numeric reboot deadline.
// Boot, isolated namespace, stopped zygotes and absent system_server are
// independently verified by main.c before touching host hardware.
#ifndef ONEIOS_SM8850_STAGE_ADMISSION_H
#define ONEIOS_SM8850_STAGE_ADMISSION_H

#include <limits.h>
#include <stdbool.h>
#include <string.h>

typedef enum {
  XH_SM8850_STAGE_REFUSED = 0,
  XH_SM8850_STAGE_GUARDED = 1,
  XH_SM8850_STAGE_NO_USERSPACE_THERMAL_180S = 2,
} xh_sm8850_stage_profile;

static inline bool xh_sm8850_positive_decimal(const char *text)
{
  if (!text || !*text) return false;
  unsigned long long value = 0;
  for (const char *p = text; *p; ++p) {
    if (*p < '0' || *p > '9') return false;
    unsigned int digit = (unsigned int)(*p - '0');
    if (value > (ULLONG_MAX - digit) / 10u) return false;
    value = value * 10u + digit;
  }
  return value != 0;
}

static inline xh_sm8850_stage_profile xh_sm8850_classify_stage(
    const char *generation, const char *software_thermal,
    const char *duration, const char *framework_stop_confirmed,
    const char *reboot_deadline, const char *thermal_guard_generation,
    const char *thermal_cap_generation)
{
  if (!generation || !*generation) return XH_SM8850_STAGE_REFUSED;

  if (software_thermal && *software_thermal) {
    // Deliberately do NOT accept a passive monitor or a loose "off" flag.
    // The stage owns the explicit opt-in and only emits this exact marker
    // after the user requested a 180s reboot-only full takeover.
    if (strcmp(software_thermal, "disabled-180s") ||
        !duration || strcmp(duration, "180") ||
        !framework_stop_confirmed ||
        strcmp(framework_stop_confirmed, generation) ||
        !xh_sm8850_positive_decimal(reboot_deadline))
      return XH_SM8850_STAGE_REFUSED;
    return XH_SM8850_STAGE_NO_USERSPACE_THERMAL_180S;
  }

  if (!thermal_guard_generation ||
      strcmp(thermal_guard_generation, generation) ||
      !thermal_cap_generation ||
      strcmp(thermal_cap_generation, generation))
    return XH_SM8850_STAGE_REFUSED;

  return XH_SM8850_STAGE_GUARDED;
}

#endif  // ONEIOS_SM8850_STAGE_ADMISSION_H
