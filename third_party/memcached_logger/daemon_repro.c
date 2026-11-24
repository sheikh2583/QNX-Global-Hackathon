/* SPDX-License-Identifier: MIT
 * TraceLens driver for the whole memcached daemon (memcached/memcached#1348), our code, not upstream's.
 *
 * memcached's own sources are compiled with -Dmain=memcached_main, so the real main() runs here in a
 * thread, with the real worker, logger and LRU threads. This file's main() then does what the issue's
 * reproducer does:
 *
 *   1. connect to the daemon and send "watch"            (a log watcher is handed to the logger thread)
 *   2. leave it idle ~8 s, so the logger's poll sleep backs off towards 1 s
 *   3. disconnect; wait until the logger has reaped the last watcher (watcher_count == 0)
 *   4. send SIGUSR1, which memcached treats as "stop gracefully": stop_threads() -> logger_stop()
 *
 * --healthy skips steps 1-3: no watcher, the logger is parked in pthread_cond_wait(), shutdown is clean.
 * If the daemon has not exited 6 s after the signal, that is the hang from the issue.
 */
#undef main
#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/trace.h>
#include <unistd.h>

extern int memcached_main(int argc, char **argv);
extern int watcher_count; /* logger.c, not static */
static volatile int exited;

static void mark(const char *what)
{
    char buf[64];
    snprintf(buf, sizeof buf, "%s name=graceful_shutdown", what);
    (void)TraceEvent(_NTO_TRACE_INSERTUSRSTREVENT, _NTO_TRACE_USERFIRST + 1, buf);
}

static void *daemon_thread(void *arg)
{
    (void)arg;
    char *av[] = {"memcached", "-u", "root", "-p", "22211", "-U", "0", "-t", "2", "-m", "16", NULL};
    memcached_main(11, av);
    exited = 1;
    return NULL;
}

static int connect_local(void)
{
    for (int i = 0; i < 100; i++) {
        int fd = socket(AF_INET, SOCK_STREAM, 0);
        struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(22211)};
        a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        if (fd >= 0 && connect(fd, (struct sockaddr *)&a, sizeof a) == 0)
            return fd;
        if (fd >= 0)
            close(fd);
        usleep(100000);
    }
    return -1;
}

int main(int argc, char **argv)
{
    int healthy = argc > 1 && !strcmp(argv[1], "--healthy");
    pthread_t d;
    pthread_create(&d, NULL, daemon_thread, NULL);
    int fd = connect_local();
    if (fd < 0) {
        fprintf(stderr, "daemon did not come up\n");
        return 1;
    }
    if (healthy) {
        close(fd);
        sleep(1);
    } else {
        char buf[64];
        if (write(fd, "watch\r\n", 7) != 7 || read(fd, buf, sizeof buf) <= 0) {
            fprintf(stderr, "watch failed\n");
            return 1;
        }
        sleep(8);
        close(fd);
        for (int i = 0; i < 400 && watcher_count != 0; i++)
            usleep(5000);
        usleep(50000);
    }
    mark("TL_JOB_START");
    kill(getpid(), SIGUSR1);
    for (int i = 0; i < 600 && !exited; i++)
        usleep(10000);
    if (!exited) {
        fprintf(stderr, "HANG: the daemon did not exit 6 s after SIGUSR1 (memcached/memcached#1348)\n");
        _exit(3);
    }
    mark("TL_JOB_END");
    printf("memcached exited cleanly\n");
    return 0;
}
