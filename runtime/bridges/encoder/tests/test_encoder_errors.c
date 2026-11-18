// SPDX-License-Identifier: MIT
// Fault-inject the REAL socket helper path with a host-only stub backend.
// One case per process because backend_helper.c starts one child per parent.
// No phone, Android HAL, guest kernel or Apple files are involved.
#define _GNU_SOURCE
#include "encoder.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static void nap(void) {
  const struct timespec delay = { .tv_sec = 0, .tv_nsec = 3000000 };
  nanosleep(&delay, NULL);
}

int main(int argc, char **argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: %s HOST_HELPER feed|drain|poll|timeout|crash\n", argv[0]);
    return 2;
  }
  const char *fault = argv[2];
  int expect = !strcmp(fault, "feed") ? EINVAL :
               !strcmp(fault, "drain") ? EIO :
               !strcmp(fault, "poll") ? EIO :
               !strcmp(fault, "timeout") ? ETIMEDOUT :
               !strcmp(fault, "crash") ? EPIPE : 0;
  if (!expect) return 2;
  if (setenv("ONEIOS_ENCODER_TEST_FAULT", fault, 1)) return 2;
  const br_encoder_backend *backend = br_encoder_backend_helper(argv[1]);
  br_enc_session *sess = backend->open(MEDIA_PIXFMT_HEVC, 256, 256);
  if (!sess) { fprintf(stderr, "FAIL %s: open failed\n", fault); return 1; }

  const uint8_t frame[256 * 256 * 3 / 2] = { 0 };
  // The socket layer acknowledges sending; the child reports actual failures
  // asynchronously via ENC_MSG_ERROR, never via a fabricated EOS.
  (void)backend->feed(sess, frame, sizeof frame, 1000000, 1);
  (void)backend->drain(sess);

  uint8_t bitstream[4096];
  int got = 0, eos = 0, error = 0;
  for (unsigned i = 0; i < 1500; i++) { // 4.5 s max; helper timeout is ~2 s
    int key = 0, end = 0;
    int64_t pts = 0;
    int n = backend->poll(sess, bitstream, sizeof bitstream, &key, &pts, &end);
    if (n < 0) { error = -n; break; }
    if (end) { eos = 1; break; }
    if (n > 0) got++;
    nap();
  }
  backend->close(sess);
  if (error != expect || eos) {
    fprintf(stderr, "FAIL %s: expected errno %d, got errno %d, eos %d, coded %d\n",
            fault, expect, error, eos, got);
    return 1;
  }
  printf("PASS %s: errno %d, no fabricated EOS (coded %d)\n", fault, error, got);
  return 0;
}
