/* SPDX-License-Identifier: MIT
 * TraceLens driver for NNG's nng_close() deadlock (nanomsg/nng#1543, #1813), our code, not upstream's.
 *
 * It follows the reporter's description of #1813: a REQ socket dials a REP server over ipc://, sends a
 * request, and just before nng_recv() a second thread calls nng_close() on the same socket. Repeated.
 * Usage:  nng_repro server <url>      REP server, runs until killed
 *         nng_repro client <url> [n]  n close cycles (default 400); exits 3 if one cycle takes over 6 s
 */
#include <nng/nng.h>
#include <nng/protocol/reqrep0/rep.h>
#include <nng/protocol/reqrep0/req.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/trace.h>
#include <unistd.h>

static void mark(const char *what)
{
    char buf[64];
    snprintf(buf, sizeof buf, "%s name=close_cycle", what);
    (void)TraceEvent(_NTO_TRACE_INSERTUSRSTREVENT, _NTO_TRACE_USERFIRST + 1, buf);
}

static int server(const char *url)
{
    nng_socket s;
    nng_listener l;
    if (nng_rep0_open(&s) != 0 || nng_listener_create(&l, s, url) != 0 || nng_listener_start(l, 0) != 0) {
        fprintf(stderr, "server: cannot listen on %s\n", url);
        return 1;
    }
    for (;;) {
        char *buf = NULL;
        size_t sz;
        if (nng_recv(s, &buf, &sz, NNG_FLAG_ALLOC) != 0)
            continue;
        (void)nng_send(s, buf, sz, NNG_FLAG_ALLOC);
    }
}

static void *closer(void *arg)
{
    nng_close(*(nng_socket *)arg);
    return NULL;
}

static volatile int cycle_done;
static volatile int cycle_no;

static void *watchdog(void *arg)
{
    (void)arg;
    int seen = -1, waited = 0;
    for (;;) {
        usleep(100000);
        if (cycle_no != seen) { seen = cycle_no; waited = 0; continue; }
        if (++waited > 60) {
            fprintf(stderr, "HANG: close cycle %d did not finish in 6 s (nanomsg/nng#1813)\n", seen);
            _exit(3);
        }
    }
}

static int client(const char *url, int n)
{
    pthread_t wd;
    sleep(3); /* the capture starts client and server together; the report's setup has the server up first */
    pthread_create(&wd, NULL, watchdog, NULL);
    for (int i = 0; i < n; i++) {
        cycle_no = i;
        mark("TL_JOB_START");
        nng_socket s;
        nng_dialer d;
        if (nng_req0_open(&s) != 0 || nng_dialer_create(&d, s, url) != 0) {
            fprintf(stderr, "client: open/dial failed\n");
            return 1;
        }
        nng_dialer_start(d, NNG_FLAG_NONBLOCK);
        uint64_t cmd = 1;
        (void)nng_send(s, &cmd, sizeof cmd, 0);
        pthread_t t;
        pthread_create(&t, NULL, closer, &s);
        char *buf = NULL;
        size_t sz;
        if (nng_recv(s, &buf, &sz, NNG_FLAG_ALLOC) == 0)
            nng_free(buf, sz);
        pthread_join(t, NULL);
        mark("TL_JOB_END");
        usleep(20000); /* pace the loop: a tight loop overruns the kernel trace buffers */
    }
    printf("client: %d close cycles finished\n", n);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc >= 3 && !strcmp(argv[1], "server"))
        return server(argv[2]);
    if (argc >= 3 && !strcmp(argv[1], "client"))
        return client(argv[2], argc > 3 ? atoi(argv[3]) : 400);
    fprintf(stderr, "usage: nng_repro server|client <url> [cycles]\n");
    return 2;
}
