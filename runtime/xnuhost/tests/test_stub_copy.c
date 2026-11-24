// SPDX-License-Identifier: MIT
#include "stub_copy.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

static unsigned checks, failed;
#define CHECK(c) do { ++checks; if (!(c)) { if (failed < 8) fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #c); ++failed; } } while (0)

int main(void)
{
  _Alignas(16) unsigned char src[640], saved[640], dst[640], want[640];
  static const unsigned sizes[] = {
    0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,
    24,25,26,27,28,29,30,31,32,33,63,64,65,247,248,249,511,512,513
  };
  for (size_t i = 0; i < sizeof src; ++i) src[i] = (unsigned char)(i * 29u + i / 7u);
  memcpy(saved, src, sizeof saved);
  for (unsigned a = 0; a < 16; ++a) for (unsigned b = 0; b < 16; ++b)
    for (unsigned k = 0; k < sizeof sizes / sizeof sizes[0]; ++k) {
      unsigned n = sizes[k];
      memset(dst, 0xa5, sizeof dst);
      memset(want, 0xa5, sizeof want);
      memcpy(want + b, src + a, n);
      xs_copy_state(dst + b, src + a, n);
      CHECK(!memcmp(dst, want, sizeof dst) && !memcmp(src, saved, sizeof src));
    }
  // Guard pages detect even a single over-read or over-write at an exact end.
  long ps = sysconf(_SC_PAGESIZE);
  if (ps < 1024) return 2;
  size_t page = (size_t)ps;
  unsigned char *a = mmap(NULL, 2 * page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  unsigned char *b = mmap(NULL, 2 * page, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
  if (a == MAP_FAILED || b == MAP_FAILED) return 2;
  if (mprotect(a + page, page, PROT_NONE) || mprotect(b + page, page, PROT_NONE)) return 2;
  for (unsigned k = 0; k < sizeof sizes / sizeof sizes[0]; ++k) {
    size_t n = sizes[k];
    memcpy(a + page - n, src, n);
    memset(b, 0xa5, page);
    xs_copy_state(b + page - n, a + page - n, n);
    CHECK(!memcmp(b + page - n, src, n) && b[page - n - 1] == 0xa5);
  }
  munmap(a, 2 * page); munmap(b, 2 * page);
  printf("stub state copy: %u checks, %u failed\n", checks, failed);
  return failed ? 1 : 0;
}
