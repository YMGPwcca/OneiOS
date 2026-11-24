// SPDX-License-Identifier: MIT
// Freestanding, exact, non-overlapping signal-state copy. No SIMD register
// use, libc, unaligned scalar accesses, or reads/writes outside [0,n).
#ifndef XNUHOST_STUB_COPY_H
#define XNUHOST_STUB_COPY_H
#include <stdint.h>
#include <stddef.h>

// The source/destination may be register structs, uint64_t arrays, or raw
// kernel signal-frame bytes. These alias types keep strict-aliasing valid.
typedef uint64_t xs_copy_u64 __attribute__((__may_alias__));
typedef uint32_t xs_copy_u32 __attribute__((__may_alias__));

static inline void xs_copy_state(void *to, const void *from, size_t n)
{
  volatile unsigned char *d = to;
  const volatile unsigned char *s = from;
  if (!(((uintptr_t)d | (uintptr_t)s) & 7u)) {
    while (n >= 8) {
      *(volatile xs_copy_u64 *)d = *(const volatile xs_copy_u64 *)s;
      d += 8; s += 8; n -= 8;
    }
  }
  if (!(((uintptr_t)d | (uintptr_t)s) & 3u)) {
    while (n >= 4) {
      *(volatile xs_copy_u32 *)d = *(const volatile xs_copy_u32 *)s;
      d += 4; s += 4; n -= 4;
    }
  }
  while (n) { *d++ = *s++; --n; }
}
#endif
