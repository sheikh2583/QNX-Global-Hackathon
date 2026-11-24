/* SPDX-License-Identifier: MIT
 * TraceLens driver for memcached's logger thread (memcached/memcached#1348), our code, not upstream's.
 *
 * It links memcached 1.6.45's own logger.c, bipbuffer.c, globals.c and util.c, unedited, and replaces
 * only the four functions that live in the rest of the daemon (thread.c / memcached.c). It then does
 * what the issue's reproducer does through the logger's public API:
 *
 *   1. start the logger thread                        (logger_init)
 *   2. hand it one watcher, as the "watch" command does (logger_add_watcher)
 *   3. leave the watcher idle so the logger's poll sleep backs off to ~1 s
 *   4. disconnect the watcher; the logger reaps it, the last one, and starts its next sleep
 *   5. 0.3 s later stop the logger, as stop_threads() does on a graceful shutdown (logger_stop)
 *
 * mode "stop-while-waiting" is the healthy control: no watcher at all, so the logger parks in
 * pthread_cond_wait() and the stop signal finds it there.
 *
 * A watchdog thread gives the join 4 s; if it never returns that is the hang from the issue.
 */
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/trace.h>
#include <unistd.h>

#include "memcached.h"

extern int watcher_count; /* logger.c, not static */

/* ---- what the rest of memcached would provide ------------------------------------------------ */
static pthread_mutex_t stats_mutex = PTHREAD_MUTEX_INITIALIZER;
void STATS_LOCK(void) { pthread_mutex_lock(&stats_mutex); }
void STATS_UNLOCK(void) { pthread_mutex_unlock(&stats_mutex); }
void thread_setname(pthread_t thread, const char *name) { (void)pthread_setname_np(thread, name); }

static int g_closed; /* fd closed by sidethread_conn_close */
void sidethread_conn_close(conn *c) { (void)c; g_closed = 1; }

/* ---- a watcher "connection": read()/write() on a socket ---------------------------------------- */
static int g_sfd;
static ssize_t my_read(struct conn *c, void *buf, size_t n) { (void)c; return read(g_sfd, buf, n); }
static ssize_t my_write(struct conn *c, void *buf, size_t n) { (void)c; return write(g_sfd, buf, n); }

/* ---- markers (the verdict needs a job to measure) ---------------------------------------------- */
static void mark(const char *what, const char *name)
{
    char buf[64];
    snprintf(buf, sizeof buf, "%s name=%s", what, name);
    (void)TraceEvent(_NTO_TRACE_INSERTUSRSTREVENT, _NTO_TRACE_USERFIRST + 1, buf);
}

static volatile int joined;
static void *watchdog(void *arg)
{
    (void)arg;
    for (int i = 0; i < 400 && !joined; i++)
        usleep(10000);
    if (!joined) {
        fprintf(stderr, "HANG: logger_stop() did not return in 4 s (memcached/memcached#1348)\n");
        _exit(3);
    }
    return NULL;
}

int main(int argc, char **argv)
{
    int wait_s = 8; /* seconds the watcher idles: the logger's sleep backs off towards 1 s by then */
    int healthy = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-w") && i + 1 < argc) wait_s = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--healthy")) healthy = 1;
    }
    memset(&settings, 0, sizeof settings);
    settings.logger_watcher_buf_size = 8192;
    settings.logger_buf_size = 8192;

    logger_init();
    static conn c;
    c.read = my_read;
    c.write = my_write;
    int sv[2] = {-1, -1};

    if (!healthy) {
        if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) != 0) { perror("socketpair"); return 1; }
        g_sfd = sv[0];
        if (logger_add_watcher(&c, sv[0], LOG_SYSEVENTS) != LOGGER_ADD_WATCHER_OK) {
            fprintf(stderr, "add_watcher failed\n");
            return 1;
        }
        sleep(wait_s);
        close(sv[1]);                         /* the client disconnects */
        while (watcher_count != 0)            /* the logger reaps it: the last watcher */
            usleep(5000);
        usleep(300000);                       /* it is now in the sleep that follows the reap */
    } else {
        sleep(1);                             /* no watcher: the logger is parked in pthread_cond_wait */
    }

    pthread_t wd;
    pthread_create(&wd, NULL, watchdog, NULL);
    mark("TL_JOB_START", "logger_stop");
    logger_stop();                            /* what stop_threads() calls */
    joined = 1;
    mark("TL_JOB_END", "logger_stop");
    pthread_join(wd, NULL);
    printf("logger stopped cleanly\n");
    return 0;
}
