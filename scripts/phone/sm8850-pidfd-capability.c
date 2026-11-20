/*
 * Benign-only pidfd_getfd capability probe for SM8850 recovery research.
 *
 * This NEVER duplicates, opens, ioctls or writes any watchdog device.
 * The sole eligible remote descriptor is an already-open /dev/null FD
 * (character device 1:3) in system_server. After duplication, fstat()
 * checks 1:3; it is closed without I/O. No stop/kill/signal operations.
 *
 * argv: --system-server PID (real device) or --selftest (host CI only).
 * Results do NOT authorize a live takeover or watchdog FD handback.
 */
#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef SYS_pidfd_open
#define SYS_pidfd_open 434
#endif
#ifndef SYS_pidfd_getfd
#define SYS_pidfd_getfd 438
#endif

static int parse_pid(const char *text, pid_t *pid) {
    char *end = NULL;
    errno = 0;
    long v = strtol(text, &end, 10);
    if (errno || !text[0] || !end || *end || v < 2 || v > 9999999)
        return -1;
    *pid = (pid_t)v;
    return 0;
}

static int benign_fd(pid_t pid) {
    char path[64];
    if (snprintf(path, sizeof(path), "/proc/%ld/fd", (long)pid) >= (int)sizeof(path))
        return -1;
    DIR *dir = opendir(path);
    if (!dir) return -1;
    int found = -1;
    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        char *end = NULL;
        errno = 0;
        long fd = strtol(entry->d_name, &end, 10);
        if (errno || end == entry->d_name || *end || fd < 0 || fd > 1048576)
            continue;

        char target[128];
        ssize_t length = readlinkat(dirfd(dir), entry->d_name,
                                    target, sizeof(target) - 1);
        if (length <= 0 || length >= (ssize_t)sizeof(target)) continue;
        target[length] = '\0';
        if (strcmp(target, "/dev/null") != 0) continue;

        struct stat st;
        if (fstatat(dirfd(dir), entry->d_name, &st, 0) != 0 ||
            !S_ISCHR(st.st_mode) || major(st.st_rdev) != 1 ||
            minor(st.st_rdev) != 3)
            continue;
        found = (int)fd;
        break;
    }
    closedir(dir);
    return found;
}

static int target_comm(pid_t pid, const char *want) {
    char path[64], comm[128] = "";
    if (snprintf(path, sizeof(path), "/proc/%ld/comm", (long)pid) >= (int)sizeof(path))
        return -1;
    FILE *fp = fopen(path, "r");
    if (!fp) return -1;
    if (!fgets(comm, sizeof(comm), fp)) {
        fclose(fp);
        return -1;
    }
    fclose(fp);
    comm[strcspn(comm, "\r\n")] = '\0';
    return strcmp(comm, want) == 0 ? 0 : -1;
}

int main(int argc, char **argv) {
    pid_t pid = 0;
    int selftest = 0;
    int owned_null = -1;

    if (argc == 2 && strcmp(argv[1], "--selftest") == 0) {
        selftest = 1;
        pid = getpid();
        /* Only selftest may open its OWN harmless /dev/null. */
        FILE *f = fopen("/dev/null", "r");
        if (!f) { perror("selftest /dev/null"); return 2; }
        owned_null = fileno(f);
        /* Keep f alive until after the pidfd_getfd check. */
        (void)owned_null;
        int probe_fd = benign_fd(pid);
        if (probe_fd < 0) {
            puts("PIDFD_PROBE=NO_BENIGN_FD");
            fclose(f);
            return 4;
        }

        int pidfd = (int)syscall(SYS_pidfd_open, pid, 0);
        if (pidfd < 0) {
            printf("PIDFD_PROBE=BLOCKED_PIDFD_OPEN errno=%d\n", errno);
            fclose(f);
            return 3;
        }
        int clone = (int)syscall(SYS_pidfd_getfd, pidfd, probe_fd, 0);
        if (clone < 0) {
            printf("PIDFD_PROBE=BLOCKED_GETFD errno=%d\n", errno);
            close(pidfd);
            fclose(f);
            return 3;
        }
        struct stat st;
        int safe = fstat(clone, &st) == 0 && S_ISCHR(st.st_mode) &&
                   major(st.st_rdev) == 1 && minor(st.st_rdev) == 3;
        close(clone);
        close(pidfd);
        fclose(f);
        puts(safe ? "PIDFD_PROBE=SUPPORTED_BENIGN_FD_ONLY"
                  : "PIDFD_PROBE=MISMATCH_ABORT");
        return safe ? 0 : 5;
    }
    if (argc != 3 || strcmp(argv[1], "--system-server") != 0 ||
        parse_pid(argv[2], &pid) != 0) {
        fprintf(stderr, "usage: %s --system-server PID | --selftest\n", argv[0]);
        return 2;
    }
    if (target_comm(pid, "system_server") != 0) {
        puts("PIDFD_PROBE=BLOCKED_TARGET_NOT_SYSTEM_SERVER");
        return 2;
    }

    int fd = benign_fd(pid);
    if (fd < 0) {
        puts("PIDFD_PROBE=NO_BENIGN_FD");
        puts("WATCHDOG_FD_DUPLICATED=NO");
        return 4;
    }
    printf("TARGET_PID=%ld\n", (long)pid);
    printf("BENIGN_FD=%d target=/dev/null rdev=1:3\n", fd);
    int pidfd = (int)syscall(SYS_pidfd_open, pid, 0);
    if (pidfd < 0) {
        printf("PIDFD_PROBE=BLOCKED_PIDFD_OPEN errno=%d (%s)\n", errno, strerror(errno));
        puts("WATCHDOG_FD_DUPLICATED=NO");
        return 3;
    }
    int dup = (int)syscall(SYS_pidfd_getfd, pidfd, fd, 0);
    if (dup < 0) {
        printf("PIDFD_PROBE=BLOCKED_GETFD errno=%d (%s)\n", errno, strerror(errno));
        close(pidfd);
        puts("WATCHDOG_FD_DUPLICATED=NO");
        return 3;
    }
    struct stat st;
    int safe = fstat(dup, &st) == 0 && S_ISCHR(st.st_mode) &&
               major(st.st_rdev) == 1 && minor(st.st_rdev) == 3;
    close(dup);
    close(pidfd);
    puts(safe ? "PIDFD_PROBE=SUPPORTED_BENIGN_FD_ONLY" : "PIDFD_PROBE=MISMATCH_ABORT");
    puts("WATCHDOG_FD_DUPLICATED=NO");
    puts("WATCHDOG_DEVICE_OPEN_ATTEMPTED=NO");
    puts("FRAMEWORK_STOP_ATTEMPTED=NO");
    return safe ? 0 : 5;
}
