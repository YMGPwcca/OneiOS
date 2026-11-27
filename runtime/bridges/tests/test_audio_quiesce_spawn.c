// SPDX-License-Identifier: MIT
#define _GNU_SOURCE
#include "bridges/bridges.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
void br_log(int level, const char *fmt, ...)
{
  (void)level;
  va_list ap;
  va_start(ap, fmt); vfprintf(stderr, fmt, ap); va_end(ap); fputc('\n', stderr);
}
static int wait_receipt(const br_audio_backend *b, void *ctx, uint64_t t, bool resume)
{
  for (unsigned i = 0; i < 5000; i++) {
    int r = resume ? br_audio_quiesce_resume(b, ctx, t) : br_audio_quiesce_poll(b, ctx, t);
    if (r != -EAGAIN) return r;
    usleep(1000);
  }
  return -ETIMEDOUT;
}
int main(int argc, char **argv)
{
  if (argc != 2) return 2; // path to test_audio_helper (fake HAL), never phone helper
  alarm(30);
  CHECK(setenv("ONEIOS_AUDIO_LINGER_S", "1", 1) == 0);
  void *ctx = NULL;
  const br_audio_backend *b = br_audio_helper(argv[1], &ctx);
  CHECK(b && ctx);
  CHECK(br_audio_quiesce_close(b, ctx, 1) == 0);
  CHECK(br_audio_quiesce_poll(b, ctx, 2) == -ESTALE);
  CHECK(wait_receipt(b, ctx, 1, false) == 0);
  CHECK(wait_receipt(b, ctx, 1, true) == 0);
  CHECK(br_audio_quiesce_close(b, ctx, 1) == -ESTALE);
  // FIFO STOP followed by close, but the real helper still has its
  // ordinary lingering speaker until the stream and writer are gone.
  CHECK(b->start(ctx, true, 48000, 2) == 0);
  CHECK(b->stop(ctx, true) == 0);
  CHECK(br_audio_quiesce_close(b, ctx, 2) == 0);
  CHECK(wait_receipt(b, ctx, 2, false) == 0);
  CHECK(wait_receipt(b, ctx, 2, true) == 0);
  CHECK(b->start(ctx, false, 48000, 1) == 0);
  usleep(50000);
  CHECK(b->stop(ctx, false) == 0);
  CHECK(br_audio_quiesce_close(b, ctx, 3) == 0);
  CHECK(wait_receipt(b, ctx, 3, false) == 0);
  CHECK(wait_receipt(b, ctx, 3, true) == 0);
  CHECK(b->start(ctx, true, 48000, 2) == 0);
  int16_t pcm[146];
  for (unsigned i=0;i<146;i++) pcm[i]=1234;
  CHECK(b->write(ctx, pcm, 73) == 73);
  CHECK(br_audio_quiesce_close_playback(b, ctx, 4) == 0);
  CHECK(wait_receipt(b, ctx, 4, false) == 0);
  CHECK(wait_receipt(b, ctx, 4, true) == 0);
  CHECK(b->write(ctx, pcm, 73) == 73); // no synthetic logical START
  CHECK(br_audio_quiesce_close_playback(b, ctx, 5) == 0);
  CHECK(wait_receipt(b, ctx, 5, false) == 0);
  CHECK(wait_receipt(b, ctx, 5, true) == 0);
  CHECK(b->stop(ctx, true) == 0);
  b->close(ctx);
  int status;
  CHECK(waitpid(-1, &status, 0) > 0 && WIFEXITED(status) && !WEXITSTATUS(status));
  printf("audio spawned helper: %u checks, 0 failed\n", checks);
  return 0;
}
