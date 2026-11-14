/*
 * tl.h - shared helpers for the TraceLens bug zoo (QNX SDP 8.0).
 *
 * Every workload:
 *   - pins its threads to explicit CPUs (ThreadCtl _NTO_TCTL_RUNMASK) so the
 *     scheduling behaviour is reproducible on the 4-CPU QEMU guest (mkqnximage --cpu=4),
 *   - runs its threads SCHED_FIFO at fixed priorities,
 *   - emits TraceLens markers as user string events (TraceEvent with
 *     _NTO_TRACE_INSERTUSRSTREVENT) that the analyzer reads:
 *         TL_META name=<thread> prio=<n>
 *         TL_JOB_START name=<job>      TL_JOB_END name=<job>
 *
 * Items marked (verify) have not yet been checked on a real QNX 8.0 target.
 */
#ifndef TL_H
#define TL_H

#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/neutrino.h>
#include <sys/syspage.h>
#include <sys/trace.h>

#define TL_USER_EVENT (_NTO_TRACE_USERFIRST + 1)
#define TL_NS_PER_US 1000ULL
#define TL_NS_PER_MS 1000000ULL
#define TL_NS_PER_S 1000000000ULL

static inline void tl_die(const char *what)
{
    fprintf(stderr, "tracelens bugzoo: %s: %s\n", what, strerror(errno));
    exit(EXIT_FAILURE);
}

/* User string event; visible in traceprinter output as a USREVENT. */
static inline void tl_mark(const char *fmt, ...)
{
    char buf[128];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    (void)TraceEvent(_NTO_TRACE_INSERTUSRSTREVENT, TL_USER_EVENT, buf);
}

static inline void tl_job_start(const char *job) { tl_mark("TL_JOB_START name=%s", job); }
static inline void tl_job_end(const char *job) { tl_mark("TL_JOB_END name=%s", job); }

/* Pin the calling thread, set SCHED_FIFO priority, name it and announce it. */
static inline void tl_thread_init(const char *name, int prio, unsigned cpu_mask)
{
    struct sched_param sp = { .sched_priority = prio };

    if (ThreadCtl(_NTO_TCTL_RUNMASK, (void *)(uintptr_t)cpu_mask) == -1)
        tl_die("ThreadCtl(_NTO_TCTL_RUNMASK)");
    if ((errno = pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp)) != 0)
        tl_die("pthread_setschedparam");
    (void)pthread_setname_np(pthread_self(), name);
    tl_mark("TL_META name=%s prio=%d", name, prio);
}

static inline uint64_t tl_now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * TL_NS_PER_S + (uint64_t)ts.tv_nsec;
}

static inline void tl_sleep_until(uint64_t abs_ns)
{
    struct timespec ts = { .tv_sec = (time_t)(abs_ns / TL_NS_PER_S),
                           .tv_nsec = (long)(abs_ns % TL_NS_PER_S) };
    while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL) == EINTR) {
    }
}

/* Burn CPU for `us` microseconds (models real computation; stays RUNNING). */
static inline void tl_spin_us(unsigned us)
{
    const uint64_t cps = SYSPAGE_ENTRY(qtime)->cycles_per_sec;
    const uint64_t end = ClockCycles() + cps * us / 1000000ULL;
    while (ClockCycles() < end) {
    }
}

/* Common CLI: -d <seconds> run time (default 2). Returns the absolute start time. */
static inline uint64_t tl_parse_args(int argc, char **argv, unsigned *seconds)
{
    int c;
    *seconds = 2;
    while ((c = getopt(argc, argv, "d:")) != -1) {
        if (c == 'd')
            *seconds = (unsigned)atoi(optarg);
    }
    /* Start everyone on a common, slightly delayed, period boundary. */
    return tl_now_ns() + 100 * TL_NS_PER_MS;
}

static inline pthread_t tl_spawn(void *(*fn)(void *), void *arg)
{
    pthread_t t;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setinheritsched(&attr, PTHREAD_EXPLICIT_SCHED);
    pthread_attr_setschedpolicy(&attr, SCHED_FIFO);
    if ((errno = pthread_create(&t, &attr, fn, arg)) != 0)
        tl_die("pthread_create");
    pthread_attr_destroy(&attr);
    return t;
}

#endif /* TL_H */
