// Clone a regular file into a privately created empty inode. Sparse copy
// uses positional writes and preserves the logical size and trailing holes.
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64

#include <errno.h>
#include <fcntl.h>
#include <linux/fs.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
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

int main(int argc, char **argv) {
    if (argc != 4 || (strcmp(argv[1], "reflink") && strcmp(argv[1], "sparse")))
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
