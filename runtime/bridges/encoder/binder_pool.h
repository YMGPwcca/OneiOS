// SPDX-License-Identifier: MIT
// Private, process-level Android Binder callback pool bootstrap for the
// standalone encoder diagnostics and the real oneios-encoder helper.
// No AOSP platform headers or link-time dependency on libbinder_ndk.so.
#ifndef ONEIOS_ENCODER_BINDER_POOL_H
#define ONEIOS_ENCODER_BINDER_POOL_H
int oneios_encoder_start_binder_pool(void);
#endif
