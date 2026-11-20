/*
 * Passive, single-process watchdog FD inventory for Android/SM8850.
 * Read only: opendir(/proc), readlinkat(/proc/PID/fd/FD), fstatat/fdinfo.
 * No open(), write(), ioctl(), or close() of /dev/watchdog*.
 * Optional proc root argument is for local regression fixtures only.
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <time.h>
#include <unistd.h>

static int numeric(const char *p) {
    if (!*p) return 0;
    for (; *p; p++) if (!isdigit((unsigned char)*p)) return 0;
    return 1;
}

static int matches(const char *target) {
    const char *prefix[] = {
        "/dev/watchdog", "/dev/softdog",
        "/dev/char/10:130", "/dev/char/242:0"
    };
    size_t i;
    for (i = 0; i < sizeof(prefix) / sizeof(prefix[0]); i++) {
        size_t len = strlen(prefix[i]);
        if (strncmp(target, prefix[i], len) != 0) continue;
        char suffix = target[len];
        if (!suffix || isdigit((unsigned char)suffix) ||
            suffix == ' ' || suffix == '/' || suffix == '(')
            return 1;
    }
    return 0;
}

static double monotonic_ms(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

static void read_comm(const char *root, const char *pid, char *out, size_t size) {
    char path[PATH_MAX];
    if (snprintf(path, sizeof(path), "%s/%s/comm", root, pid) >= (int)sizeof(path)) return;
    FILE *f = fopen(path, "r");
    if (!f) return;
    if (fgets(out, (int)size, f)) {
        out[strcspn(out, "\r\n")] = '\0';
    }
    fclose(f);
}

static void show_fdinfo(const char *root, const char *pid, const char *fd) {
    char path[PATH_MAX], line[256];
    if (snprintf(path, sizeof(path), "%s/%s/fdinfo/%s", root, pid, fd) >= (int)sizeof(path)) return;
    FILE *f = fopen(path, "r");
    if (!f) return;
    while (fgets(line, sizeof(line), f)) {
        if (strncmp(line, "flags:", 6) == 0 ||
            strncmp(line, "mnt_id:", 7) == 0 ||
            strncmp(line, "ino:", 4) == 0) {
            printf("  %s", line);
        }
    }
    fclose(f);
}

int main(int argc, char **argv) {
    const char *root = "/proc";
    if (argc == 2) root = argv[1];
    else if (argc != 1) {
        fprintf(stderr, "usage: %s [fixture-proc-root]\n", argv[0]);
        return 2;
    }

    double start = monotonic_ms();
    DIR *proc = opendir(root);
    if (!proc) {
        perror("opendir proc");
        return 2;
    }

    unsigned long processes = 0, dirs_read = 0, links = 0, owners = 0;
    unsigned long denied = 0, vanished = 0, readlink_errors = 0;
    struct dirent *pid_entry;
    puts("=== NATIVE READ-ONLY WATCHDOG FD INVENTORY ===");
    while ((pid_entry = readdir(proc)) != NULL) {
        if (!numeric(pid_entry->d_name)) continue;
        processes++;

        char fdpath[PATH_MAX];
        if (snprintf(fdpath, sizeof(fdpath), "%s/%s/fd",
                     root, pid_entry->d_name) >= (int)sizeof(fdpath)) {
            denied++;
            continue;
        }
        DIR *fds = opendir(fdpath);
        if (!fds) {
            if (errno == EACCES || errno == EPERM) denied++;
            else vanished++;
            continue;
        }
        dirs_read++;

        struct dirent *entry;
        int dfd = dirfd(fds);
        while ((entry = readdir(fds)) != NULL) {
            if (!numeric(entry->d_name)) continue;
            char target[1024];
            ssize_t n = readlinkat(dfd, entry->d_name,
                                   target, sizeof(target) - 1);
            if (n < 0) {
                readlink_errors++;
                continue;
            }
            target[n] = '\0';
            links++;
            if (!matches(target)) continue;

            owners++;
            char comm[128] = "unknown";
            read_comm(root, pid_entry->d_name, comm, sizeof(comm));
            struct stat st;
            if (fstatat(dfd, entry->d_name, &st, 0) == 0 &&
                S_ISCHR(st.st_mode)) {
                printf("holder=%s comm=%s fd=%s target=%s rdev=%x:%x\n",
                       pid_entry->d_name, comm, entry->d_name, target,
                       (unsigned int)major(st.st_rdev),
                       (unsigned int)minor(st.st_rdev));
            } else {
                printf("holder=%s comm=%s fd=%s target=%s rdev=UNAVAILABLE\n",
                       pid_entry->d_name, comm, entry->d_name, target);
            }
            show_fdinfo(root, pid_entry->d_name, entry->d_name);
        }
        closedir(fds);
    }
    closedir(proc);

    puts("=== INVENTORY SUMMARY ===");
    printf("WATCHDOG_FDS=%lu\n", owners);
    printf("PROCESSES_SEEN=%lu\n", processes);
    printf("FD_DIRECTORIES_SCANNED=%lu\n", dirs_read);
    printf("FD_LINKS_SCANNED=%lu\n", links);
    printf("FD_DIR_PERMISSION_ERRORS=%lu\n", denied);
    printf("FD_DIR_RACE_ERRORS=%lu\n", vanished);
    printf("FD_READLINK_RACE_ERRORS=%lu\n", readlink_errors);
    printf("SCAN_DURATION_MS=%.0f\n", monotonic_ms() - start);
    printf("SCAN_COVERAGE=%s\n", denied ? "PARTIAL_PERMISSION_DENIED" :
           "COMPLETE_FOR_VISIBLE_PROCESSES");
    puts("WATCHDOG_DEVICE_OPEN_ATTEMPTED=NO");
    puts("FRAMEWORK_STOP_ATTEMPTED=NO");
    fflush(stdout);
    return denied ? 3 : 0;
}
