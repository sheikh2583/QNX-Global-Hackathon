/* SPDX-License-Identifier: MIT -- TraceLens QNX shim: QNX's <pthread.h> plus the Linux extras the
 * NTNU exercise uses, and job markers around thread start routines. */
#ifndef QNXRT_SHIM_PTHREAD_H
#define QNXRT_SHIM_PTHREAD_H
#include_next <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/trace.h>
#include "qnxrt_compat.h"

static inline int pthread_setaffinity_np(pthread_t t, size_t sz, const cpu_set_t *set)
{
    return t == pthread_self() ? qnxrt_setaffinity_self(sz, set) : -1;
}

/* ---- 3. job markers -------------------------------------------------------------------------
 * TraceLens measures timing from user string events. Upstream has none, so every thread created
 * through pthread_create() reports its whole run as one job named after its SCHED priority:
 *     TL_JOB_START name=task_p<prio>   ...start routine runs...   TL_JOB_END name=task_p<prio>
 * Nothing about upstream's logic changes; the markers only say when each thread started and ended.
 */
struct qnxrt_boot { void *(*fn)(void *); void *arg; int prio; };

static void qnxrt_mark(const char *what, int prio)
{
    char buf[64];
    snprintf(buf, sizeof buf, "%s name=task_p%d", what, prio);
    (void)TraceEvent(_NTO_TRACE_INSERTUSRSTREVENT, _NTO_TRACE_USERFIRST + 1, buf);
}

static void *qnxrt_trampoline(void *p)
{
    struct qnxrt_boot b = *(struct qnxrt_boot *)p;
    char name[16];
    free(p);
    snprintf(name, sizeof name, "task_p%d", b.prio);
    (void)pthread_setname_np(pthread_self(), name);
    qnxrt_mark("TL_JOB_START", b.prio);
    void *r = b.fn(b.arg);
    qnxrt_mark("TL_JOB_END", b.prio);
    return r;
}

static inline int qnxrt_pthread_create(pthread_t *t, const pthread_attr_t *attr, void *(*fn)(void *), void *arg)
{
    struct sched_param sp = { .sched_priority = 0 };
    struct qnxrt_boot *b = malloc(sizeof *b);
    if (b == NULL)
        return -1;
    if (attr != NULL)
        (void)pthread_attr_getschedparam(attr, &sp);
    b->fn = fn;
    b->arg = arg;
    b->prio = sp.sched_priority;
    int rc = pthread_create(t, attr, qnxrt_trampoline, b);
    if (rc != 0)
        free(b);
    return rc;
}
#define pthread_create qnxrt_pthread_create
#endif
