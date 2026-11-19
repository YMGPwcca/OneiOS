// Link-time test double. No real watchdog node is ever opened.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/watchdog.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

int __real_open(const char *, int, ...);
int __real_fstat(int, struct stat *);
int __real_lstat(const char *, struct stat *);
ssize_t __real_write(int, const void *, size_t);
int __real_close(int);
static int endpoint = -1, root = -1, opens, pings, queries;

static bool fault(const char *name) {
    const char *value = getenv("WD_FAKE_FAULT");
    return value && !strcmp(value, name);
}

static void trace(char event) {
    int fd = openat(root, "fake.trace", O_WRONLY | O_CREAT | O_APPEND, 0600);
    if (fd >= 0) {
        __real_write(fd, &event, 1);
        __real_close(fd);
    }
}

int __wrap_open(const char *path, int flags, ...) {
    if (strcmp(path, "/dev/watchdog0")) {
        root = __real_open(path, flags);
        return root;
    }
    if (fault("busy") || (fault("busy-three") && ++opens <= 3)) {
        trace('E');
        errno = EBUSY;
        return -1;
    }
    if (!(flags & O_CLOEXEC) || endpoint != -1) {
        errno = EINVAL;
        return -1;
    }
    endpoint = __real_open("/dev/null", flags);
    trace('O');
    return endpoint;
}

int __wrap_lstat(const char *path, struct stat *stat) {
    if (strcmp(path, "/dev/watchdog0"))
        return __real_lstat(path, stat);
    if (fault("unavailable")) {
        errno = ENODEV;
        return -1;
    }
    *stat = (struct stat){.st_mode = S_IFCHR, .st_rdev = makedev(242, 0)};
    return 0;
}

int __wrap_fstat(int fd, struct stat *stat) {
    if (fd != endpoint)
        return __real_fstat(fd, stat);
    *stat = (struct stat){.st_mode = S_IFCHR, .st_rdev = makedev(242, fault("bad-device") ? 1 : 0)};
    return 0;
}

int __wrap_ioctl(int fd, unsigned long action, ...) {
    if (fd != endpoint)
        abort();
    va_list ap;
    va_start(ap, action);
    void *out = va_arg(ap, void *);
    va_end(ap);
    switch (action) {
    case WDIOC_GETSUPPORT: {
        struct watchdog_info *info = out;
        info->options = WDIOF_KEEPALIVEPING | WDIOF_MAGICCLOSE;
        strcpy((char *)info->identity, fault("bad-identity") ? "Hardware WD" : "Software Watchdog");
        return 0;
    }
    case WDIOC_GETTIMEOUT: *(int *)out = fault("bad-timeout") ? 60 : 120; return 0;
    case WDIOC_GETPRETIMEOUT: *(int *)out = fault("pretimeout") ? 5 : 0; return 0;
    case WDIOC_GETTIMELEFT: *(int *)out = (++queries > 1 && fault("short-handback")) ? 7 : 110; return 0;
    default: abort();
    }
}

ssize_t __wrap_write(int fd, const void *data, size_t length) {
    if (fd != endpoint)
        return __real_write(fd, data, length);
    if (length != 1)
        abort();
    char byte = *(const char *)data;
    if (byte != '.' && byte != 'V')
        abort();
    if (++pings > 1 && fault("ping-error")) {
        trace('F');
        errno = EIO;
        return -1;
    }
    trace(byte == '.' ? 'P' : 'V');
    return 1;
}

int __wrap_close(int fd) {
    if (fd == endpoint) {
        if (fault("delay-close")) {
            trace('B');
            sleep(1);
        }
        trace('C');
        endpoint = -1;
    }
    return __real_close(fd);
}
