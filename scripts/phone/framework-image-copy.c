// Clone a regular file into a privately created empty inode. Sparse copy
// uses positional writes and preserves the logical size and trailing holes.
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64

#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

static int copy_sparse(int source, int dest, off_t size) {
    static unsigned char buffer[64 * 1024], zeros[sizeof buffer];

    for (off_t offset = 0; offset < size;) {
        off_t remaining = size - offset;
        size_t count = remaining < (off_t)sizeof buffer ? (size_t)remaining : sizeof buffer;
        ssize_t length = pread(source, buffer, count, offset);
        if (length < 0 && errno == EINTR)
            continue;
        if (length <= 0) {
            if (!length)
                errno = EIO;
            return -1;
        }
        if (memcmp(buffer, zeros, (size_t)length)) {
            for (ssize_t written = 0; written < length;) {
                ssize_t amount = pwrite(dest, buffer + written, (size_t)(length - written), offset + written);
                if (amount < 0 && errno == EINTR)
                    continue;
                if (amount <= 0) {
                    if (!amount)
                        errno = EIO;
                    return -1;
                }
                written += amount;
            }
        }
        offset += length;
    }
    return ftruncate(dest, size);
}

// Optional compact clone for the GPU preview. Keep the established 30 GiB
// reserve + 64 MiB and 2 GiB copy margin. Estimate the exact 4 KiB nonzero
// payload, rather than using st_blocks (which can undercount compressed
// source extents) or charging every byte of the logical 8 GiB image.
// No allocation of Data contents until the pre-scan fits the budget.
#define COMPACT_PAGE 4096u
#define COMPACT_CHUNK (64u * 1024u)
#define RESERVE_BYTES (UINT64_C(30) * 1024 * 1024 * 1024 + UINT64_C(64) * 1024 * 1024)
#define MARGIN_BYTES (UINT64_C(2) * 1024 * 1024 * 1024)

static int compact_free(int dest, uint64_t required) {
    struct statvfs v;
    if (fstatvfs(dest, &v)) return -1;
    // Require compatible allocation units; do not assume a sparse copy
    // consumes exactly 4 KiB per page on an unknown filesystem.
    if (!v.f_frsize || v.f_frsize > COMPACT_PAGE || COMPACT_PAGE % v.f_frsize) {
        errno = EOPNOTSUPP;
        return -1;
    }
    uint64_t avail = (uint64_t)v.f_bavail;
    if (avail < required / v.f_frsize + (required % v.f_frsize != 0)) {
        errno = ENOSPC;
        return -1;
    }
    return 0;
}

static int exact_read(int source, unsigned char *buf, size_t size, off_t offset) {
    size_t got = 0;
    while (got < size) {
        ssize_t n = pread(source, buf + got, size - got, offset + (off_t)got);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { if (!n) errno = EIO; return -1; }
        got += (size_t)n;
    }
    return 0;
}

static int exact_write(int dest, const unsigned char *buf, size_t size, off_t offset) {
    size_t put = 0;
    while (put < size) {
        ssize_t n = pwrite(dest, buf + put, size - put, offset + (off_t)put);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { if (!n) errno = EIO; return -1; }
        put += (size_t)n;
    }
    return 0;
}

static int copy_compact(int source, int dest, off_t size) {
    static unsigned char buf[COMPACT_CHUNK], zero[COMPACT_PAGE];
    uint64_t planned = 0, written = 0;
    if (size <= 0 || size % COMPACT_PAGE) { errno = EINVAL; return -1; }
    if (compact_free(dest, RESERVE_BYTES + MARGIN_BYTES)) return -1;
    for (unsigned pass = 0; pass < 2; pass++) {
        for (off_t off = 0; off < size;) {
            size_t count = size - off < (off_t)sizeof buf ? (size_t)(size - off) : sizeof buf;
            if (pass && off % (64 * 1024 * 1024) == 0 &&
                compact_free(dest, RESERVE_BYTES + MARGIN_BYTES)) return -1;
            if (exact_read(source, buf, count, off)) return -1;
            for (size_t i = 0; i < count;) {
                if (!memcmp(buf + i, zero, COMPACT_PAGE)) { i += COMPACT_PAGE; continue; }
                size_t begin = i;
                do i += COMPACT_PAGE;
                while (i < count && memcmp(buf + i, zero, COMPACT_PAGE));
                size_t length = i - begin;
                if (!pass) planned += length;
                else {
                    if (written > planned || length > planned - written) { errno = EIO; return -1; }
                    if (exact_write(dest, buf + begin, length, off + (off_t)begin)) return -1;
                    written += length;
                }
            }
            off += (off_t)count;
        }
        if (!pass) {
            printf("COMPACT_NONZERO_BYTES=%" PRIu64 "\nCOMPACT_REQUIRED_FREE_BYTES=%" PRIu64 "\n",
                   planned, RESERVE_BYTES + MARGIN_BYTES + planned);
            fflush(stdout);
            if (compact_free(dest, RESERVE_BYTES + MARGIN_BYTES + planned)) return -1;
        }
    }
    if (written != planned) { errno = EIO; return -1; }
    if (ftruncate(dest, size) || fsync(dest) || compact_free(dest, RESERVE_BYTES)) return -1;
    printf("COMPACT_WRITTEN_BYTES=%" PRIu64 "\n", written);
    return 0;
}

int main(int argc, char **argv) {
    if (argc != 4 || (strcmp(argv[1], "reflink") && strcmp(argv[1], "sparse") && strcmp(argv[1], "compact")))
        return 2;

    int source = open(argv[2], O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    int dest = open(argv[3], O_WRONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    struct stat from, to;
    if (source < 0 || dest < 0 || fstat(source, &from) || fstat(dest, &to) ||
        !S_ISREG(from.st_mode) || !S_ISREG(to.st_mode) || to.st_size ||
        to.st_nlink != 1 || (from.st_dev == to.st_dev && from.st_ino == to.st_ino)) {
        fprintf(stderr, "clone: expected an independent empty destination and regular source\n");
        return 2;
    }
    if (!strcmp(argv[1], "reflink")) {
        if (ioctl(dest, FICLONE, source)) {
            int error = errno;
            perror("FICLONE");
            return error == EOPNOTSUPP || error == ENOTTY || error == EXDEV || error == EINVAL ? 3 : 2;
        }
    } else if (!strcmp(argv[1], "compact")) {
        if (copy_compact(source, dest, from.st_size)) {
            perror("compact copy");
            return 2;
        }
    } else if (copy_sparse(source, dest, from.st_size)) {
        perror("sparse copy");
        return 2;
    }
    if (fsync(dest) || close(dest)) {
        perror("clone destination");
        return 2;
    }
    return 0;
}
