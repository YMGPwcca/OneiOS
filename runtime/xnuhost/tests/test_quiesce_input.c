// SPDX-License-Identifier: MIT
#define _GNU_SOURCE
#include "quiesce_input.h"
#include <errno.h>
#include <poll.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/wait.h>
#include <unistd.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)
static int work[2], reported[2], entering[2];
static void *reader(void *arg)
{
  (void)arg;
  char c;
  while (xhqi_reader_checkpoint()) {
    if (write(entering[1], "r", 1) != 1 || read(work[0], &c, 1) != 1) abort();
    if (write(reported[1], &c, 1) != 1) abort();
  }
  xhqi_finish(XHQI_READER, false);
  return NULL;
}
static int wait_rc(int (*f)(uint64_t), uint64_t ticket)
{
  for (unsigned n = 0; n < 5000; n++) {
    int r = f(ticket);
    if (r != -EAGAIN) return r;
    usleep(1000);
  }
  return -ETIMEDOUT;
}
static void entered(void)
{
  struct pollfd p = { .fd = entering[0], .events = POLLIN };
  char c;
  CHECK(poll(&p, 1, 5000) == 1 && read(entering[0], &c, 1) == 1 && c == 'r');
}
static void exchange(char c)
{
  struct pollfd p = { .fd = reported[0], .events = POLLIN };
  char got = 0;
  CHECK(write(work[1], &c, 1) == 1);
  CHECK(poll(&p, 1, 5000) == 1 && read(reported[0], &got, 1) == 1 && got == c);
}
static void live(int late)
{
  pthread_t th;
  CHECK(pipe(work) == 0 && pipe(reported) == 0 && pipe(entering) == 0);
  CHECK(xhqi_start(XHQI_READER) == 0);
  CHECK(xhqi_start(XHQI_SCRIPT) == 0);
  CHECK(xhqi_seal() == 0);
  uint64_t t = 0, old = 0;
  CHECK(xhqi_close(&t) == -EBUSY && !t); // active script: no park or timing change
  xhqi_finish(XHQI_SCRIPT, false);
  CHECK(pthread_create(&th, NULL, reader, NULL) == 0);
  entered(); exchange('s');
  for (int n = 0; n < 3; n++) {
    // Ensure the reader has entered its next in-flight operation by waiting
    // for a distinct readiness report in that operation, not scheduling luck.
    entered();
    CHECK(xhqi_close(&t) == 0 && t > old);
    CHECK(wait_rc(xhqi_poll, t+1) == -ESTALE && wait_rc(xhqi_resume, t+1) == -ESTALE);
    CHECK(xhqi_poll(t) == -EAGAIN && xhqi_resume(t) == -EAGAIN);
    exchange('f'); // prior operation finishes before acknowledgement
    CHECK(wait_rc(xhqi_poll, t) == 0);
    struct pollfd p = { .fd = reported[0], .events = POLLIN };
    CHECK(write(work[1], "q", 1) == 1);
    CHECK(poll(&p, 1, 20) == 0); // queued source work stays unread while parked
    if (late && n == 2) {
      CHECK(xhqi_start(XHQI_SCRIPT) == -EPERM);
      CHECK(wait_rc(xhqi_poll, t) == -ESTALE && wait_rc(xhqi_resume, t) == -ESTALE);
      CHECK(poll(&p, 1, 20) == 0);
      xhqi_reader_stop();
      CHECK(pthread_join(th, NULL) == 0);
      CHECK(poll(&p, 1, 0) == 0); // stop did not deliver queued work
      CHECK(xhqi_close(&old) == -ESTALE);
      return;
    }
    CHECK(wait_rc(xhqi_resume, t) == 0);
    entered();
    char c;
    CHECK(poll(&p, 1, 5000) == 1 && read(reported[0], &c, 1) == 1 && c == 'q');
    CHECK(wait_rc(xhqi_poll, t) == -ESTALE);
    old = t;
  }
  // Terminal shutdown on an otherwise valid park, independent of resume.
  entered();
  CHECK(xhqi_close(&t) == 0); exchange('f'); CHECK(wait_rc(xhqi_poll, t) == 0);
  xhqi_reader_stop(); CHECK(pthread_join(th, NULL) == 0);
  CHECK(wait_rc(xhqi_poll, t) == -ESTALE && wait_rc(xhqi_resume, t) == -ESTALE);
}
static void simple(int kind)
{
  uint64_t t = 0;
  CHECK(xhqi_close(NULL) == -EINVAL);
  CHECK(xhqi_close(&t) == -EBUSY);
  if (kind == 0) {
    CHECK(xhqi_seal() == 0 && xhqi_close(&t) == 0 && t);
    CHECK(xhqi_resume(t) == -EBUSY && xhqi_poll(t) == 0 && xhqi_resume(t) == 0);
    CHECK(xhqi_poll(t) == -ESTALE && xhqi_seal() == -EBUSY);
    CHECK(xhqi_start(XHQI_READER) == -EPERM && xhqi_close(&t) == -ESTALE);
  } else if (kind == 1) {
    CHECK(xhqi_start(XHQI_READER) == 0);
    xhqi_finish(XHQI_READER, false); // startup found no sources
    CHECK(xhqi_seal() == 0 && xhqi_close(&t) == 0 && xhqi_poll(t) == 0 && xhqi_resume(t) == 0);
  } else if (kind == 2) {
    CHECK(xhqi_start(XHQI_READER) == 0 && xhqi_start(XHQI_READER) == -EPERM);
    CHECK(xhqi_seal() == -ESTALE && xhqi_close(&t) == -ESTALE);
  } else if (kind == 3) {
    CHECK(xhqi_start(XHQI_SCRIPT) == 0);
    xhqi_finish(XHQI_SCRIPT, true);
    CHECK(xhqi_seal() == -ESTALE && xhqi_close(&t) == -ESTALE);
  } else {
    CHECK(xhqi_start(XHQI_READER) == 0 && xhqi_seal() == 0 && xhqi_close(&t) == 0);
    xhqi_finish(XHQI_READER, false); // unexpected retirement while closing
    CHECK(xhqi_poll(t) == -ESTALE && xhqi_resume(t) == -ESTALE);
  }
}
int main(void)
{
  alarm(30);
  for (int i = 0; i < 7; i++) {
    int p[2]; CHECK(pipe(p) == 0);
    pid_t pid = fork(); CHECK(pid >= 0);
    if (!pid) {
      close(p[0]); checks = 0;
      if (i < 2) live(i); else simple(i-2);
      if (write(p[1], &checks, sizeof checks) != sizeof checks) _exit(2);
      _exit(0);
    }
    close(p[1]); unsigned n = 0;
    CHECK(read(p[0], &n, sizeof n) == sizeof n); close(p[0]);
    int status; CHECK(waitpid(pid, &status, 0) == pid && WIFEXITED(status) && !WEXITSTATUS(status));
    checks += n;
  }
  printf("input source lifecycle: %u checks, 0 failed\n", checks);
  return 0;
}
