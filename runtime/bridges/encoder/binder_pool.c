// SPDX-License-Identifier: MIT
// Qualcomm Codec2 uses incoming Binder callbacks. A native executable that
// is not bootstrapped by Android's app runtime must create its own pool.
// The process-level start functions are Android platform symbols, not NDK
// public headers, so resolve them dynamically; fail closed if unavailable.
#include "binder_pool.h"
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

int oneios_encoder_start_binder_pool(void) {
  void *lib = dlopen("libbinder_ndk.so", RTLD_NOW | RTLD_LOCAL);
  if (!lib) {
    fprintf(stderr, "error: encoder Binder pool: libbinder_ndk.so unavailable: %s\n", dlerror());
    return -1;
  }

  bool (*set_max)(uint32_t) = (bool (*)(uint32_t))dlsym(lib, "ABinderProcess_setThreadPoolMaxThreadCount");
  void (*start_pool)(void) = (void (*)(void))dlsym(lib, "ABinderProcess_startThreadPool");
  if (!set_max || !start_pool) {
    fprintf(stderr, "error: encoder Binder pool: required platform symbols unavailable\n");
    dlclose(lib);
    return -1;
  }
  if (!set_max(2)) {
    fprintf(stderr, "error: encoder Binder pool: cannot set max lazy threads to 2\n");
    dlclose(lib);
    return -1;
  }
  // Intentionally hold the libbinder_ndk handle for the entire process:
  // newly spawned Binder threads may still execute code in that library.
  start_pool();
  fprintf(stderr, "oneios-encoder: Binder callback threadpool started (1 initial + up to 2 lazy)\n");
  return 0;
}
