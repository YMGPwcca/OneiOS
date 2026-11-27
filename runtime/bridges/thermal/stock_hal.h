/* SPDX-License-Identifier: MIT */
#ifndef ONEIOS_STOCK_HAL_H
#define ONEIOS_STOCK_HAL_H
#include "sm8850_thermal_controller.h"
#include "../hal/hal.h"

/* Typed adapter for a separately supervised native HAL reader, never
 * called by the independent raw sampler. The caller supplies the trusted
 * session identity and monotonic sequence; transport/peer ownership and
 * deadline are the root creator's responsibility. No recovery actions.
 * A missing/partial/expired reply produces no sample, NOT severity zero. */
int oneios_stock_hal_from_snapshot(const struct oneios_thermal_identity *,
    uint64_t seq,uint64_t start_ms,uint64_t end_ms,
    const hal_thermal_snapshot *,struct oneios_thermal_native_sample *);
int oneios_stock_hal_read(const struct oneios_thermal_identity *,uint64_t seq,
    struct oneios_thermal_native_sample *);
#endif
