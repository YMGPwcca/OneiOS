#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "hosted_own_presence.h"

#define PAGE 4096ull
#define N (256u * 64u)
static uint64_t tags[HOSTED_PRESENCE_SETS], bits[HOSTED_PRESENCE_SETS];
static unsigned char attempted[N];
static uint32_t seed = 0x2e31ba6d;
static uint32_t rng(void) {
    seed ^= seed << 13; seed ^= seed >> 17; seed ^= seed << 5;
    return seed;
}
static bool skip(uint64_t first, uint64_t end) {
    return hosted_own_presence_skip(true, true, tags, bits, first * PAGE,
        (end - first) * PAGE, PAGE);
}
int main(void) {
    assert(skip(1, 2));
    assert(!hosted_own_presence_skip(false, true, tags, bits, PAGE, PAGE, PAGE));
    assert(!hosted_own_presence_skip(true, false, tags, bits, PAGE, PAGE, PAGE));
    assert(!hosted_own_presence_skip(true, true, tags, bits, 1, PAGE, PAGE));
    assert(!hosted_own_presence_skip(true, true, tags, bits, PAGE, 1, PAGE));
    assert(!hosted_own_presence_skip(true, true, tags, bits, PAGE, 0, PAGE));
    assert(!hosted_own_presence_skip(true, true, tags, bits, PAGE, PAGE, 0));
    assert(!hosted_own_presence_skip(true, true, tags, bits, PAGE, PAGE, 3));
    assert(!hosted_own_presence_skip(true, true, tags, bits, UINT64_MAX - PAGE + 1, PAGE, PAGE));
    assert(!skip(0, 8192));
    hosted_presence_mark(tags, bits, 63);
    hosted_presence_mark(tags, bits, 64);
    assert(!skip(63, 65));
    assert(skip(65, 66));
    assert(!skip(63, 64)); /* late failed unmap: history cannot clear */
    unsigned coll = 1;
    while (hosted_presence_index(coll) != hosted_presence_index(0)) ++coll;
    hosted_presence_mark(tags, bits, (uint64_t)coll * 64);
    assert(!skip(0, 1)); /* collision is unknown, not empty */
    unsigned skipped = 0;
    for (unsigned i = 0; i < 200000; ++i) {
        if (i % 1024 == 0) { memset(tags, 0, sizeof tags); memset(bits, 0, sizeof bits); memset(attempted, 0, sizeof attempted); }
        uint64_t first = rng() % N, end = first + 1 + rng() % 96;
        if (end > N) end = N;
        if (rng() % 3 == 0) { hosted_presence_mark(tags, bits, first); attempted[first] = 1; }
        if (skip(first, end)) {
            ++skipped;
            for (uint64_t p = first; p < end; ++p) assert(!attempted[p]);
        }
    }
    assert(skipped != 0);
    printf("G22B_OWN_PRESENCE_MODEL=PASS operations=200000 skipped=%u\n", skipped);
}
