/* SPDX-License-Identifier: MIT
 *
 * busy_medium - a LABELLED NEGATIVE/POSITIVE CONTROL for third_party/rt-tests.  Not upstream
 * code, not a TraceLens bug-zoo workload, and carries no TraceLens markers.
 *
 * Why it exists.  pi_stress (the upstream program) cannot test the priority-inversion rule: its
 * barriers make the inversion transient, so even without priority inheritance the high thread
 * waits only briefly (docs/results/third_party/README.md, section 6).  This program builds the
 * classic Mars-Pathfinder shape on purpose, with one knob that decides whether the inversion is
 * sustained, and it MEASURES the high thread's wait itself, so the ground truth does not depend
 * on TraceLens at all.
 *
 * All three threads share ONE cpu (so the medium thread really does keep the low one off it):
 *
 *   t = 0     low  (prio 10) takes the lock and holds it for -c us of work
 *   t = 1 tick  high (prio 30) wants the lock and blocks;  medium (prio 20) becomes ready and
 *               spins for -b us.  Without inheritance the low thread is starved for the whole
 *               of -b, so the high thread's wait is about -b.  With inheritance low is boosted
 *               above medium, finishes its -c us of work, and the high thread's wait is about -c.
 *
 *   -m pi    PTHREAD_PRIO_INHERIT mutex          (the fix)         expected wait ~ -c
 *   -m none  PTHREAD_PRIO_NONE mutex             (QNX: verify it really disables inheritance)
 *   -m sem   sem_t used as a lock                (ownerless: never inherits)  expected wait ~ -b
 *
 * Each round reports the high thread's measured wait; the run prints min / median / max.  The
 * program decides nothing about what a tool should say; it only states what happened.
 *
 * Build: see ../Makefile (`make busy`).  Run: busy_medium -m none -d 2
 */
#include <errno.h>
#include <pthread.h>
#include <sched.h>
#include <semaphore.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/neutrino.h>
#include <sys/syspage.h>

#define NS_PER_US 1000ULL
#define NS_PER_S 1000000000ULL

static struct {
    const char *mode;
    unsigned seconds, period_us, cs_us, busy_us, cpu;
} A = { "none", 2, 50000, 4000, 20000, 1 };

static pthread_mutex_t mtx;
static sem_t sem;
static int use_sem;
static uint64_t t0;
static unsigned rounds;
static uint64_t *waits; /* high thread's measured wait, per round (ns) */

static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * NS_PER_S + (uint64_t)ts.tv_nsec;
}

static void sleep_until(uint64_t abs_ns)
{
    struct timespec ts = { .tv_sec = (time_t)(abs_ns / NS_PER_S), .tv_nsec = (long)(abs_ns % NS_PER_S) };
    while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &ts, NULL) == EINTR) {
    }
}

static void spin_us(unsigned us)
{
    const uint64_t cps = SYSPAGE_ENTRY(qtime)->cycles_per_sec;
    const uint64_t end = ClockCycles() + cps * us / 1000000ULL;
    while (ClockCycles() < end) {
    }
}

static void die(const char *what)
{
    fprintf(stderr, "busy_medium: %s: %s\n", what, strerror(errno));
    exit(EXIT_FAILURE);
}

static void lock(void)
{
    if (use_sem ? sem_wait(&sem) : pthread_mutex_lock(&mtx))
        die("lock");
}

static void unlock(void)
{
    if (use_sem ? sem_post(&sem) : pthread_mutex_unlock(&mtx))
        die("unlock");
}

struct role {
    const char *name;
    int prio;
    int which; /* 0 low, 1 medium, 2 high */
};

static void *role_thread(void *arg)
{
    const struct role *r = arg;
    struct sched_param sp = { .sched_priority = r->prio };

    if (ThreadCtl(_NTO_TCTL_RUNMASK, (void *)(uintptr_t)(1u << A.cpu)) == -1)
        die("ThreadCtl(RUNMASK)");
    if ((errno = pthread_setschedparam(pthread_self(), SCHED_FIFO, &sp)) != 0)
        die("pthread_setschedparam");
    (void)pthread_setname_np(pthread_self(), r->name);

    for (unsigned k = 0; k < rounds; k++) {
        const uint64_t base = t0 + (uint64_t)k * A.period_us * NS_PER_US;
        /* low goes first; medium and high are released one 1 ms tick later (QNX timers fire on
         * tick boundaries, so a sub-tick offset would be unreliable). */
        sleep_until(r->which == 0 ? base : base + 1000 * NS_PER_US);
        switch (r->which) {
        case 0:
            lock();
            spin_us(A.cs_us);
            unlock();
            break;
        case 1:
            spin_us(A.busy_us);
            break;
        case 2: {
            const uint64_t a = now_ns();
            lock();
            waits[k] = now_ns() - a;
            unlock();
            break;
        }
        }
    }
    return NULL;
}

static int cmp_u64(const void *a, const void *b)
{
    const uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
    return x < y ? -1 : x > y;
}

int main(int argc, char **argv)
{
    int c;
    while ((c = getopt(argc, argv, "m:d:c:b:P:a:")) != -1) {
        switch (c) {
        case 'm': A.mode = optarg; break;
        case 'd': A.seconds = (unsigned)atoi(optarg); break;
        case 'c': A.cs_us = (unsigned)atoi(optarg); break;
        case 'b': A.busy_us = (unsigned)atoi(optarg); break;
        case 'P': A.period_us = (unsigned)atoi(optarg); break;
        case 'a': A.cpu = (unsigned)atoi(optarg); break;
        default:
            fprintf(stderr, "usage: busy_medium [-m pi|none|sem] [-d s] [-c cs_us] [-b busy_us] [-P period_us] [-a cpu]\n");
            return EXIT_FAILURE;
        }
    }
    use_sem = !strcmp(A.mode, "sem");
    if (use_sem) {
        if (sem_init(&sem, 0, 1) == -1)
            die("sem_init");
    } else if (!strcmp(A.mode, "pi") || !strcmp(A.mode, "none")) {
        pthread_mutexattr_t at;
        int want = !strcmp(A.mode, "pi") ? PTHREAD_PRIO_INHERIT : PTHREAD_PRIO_NONE, got = -1;
        pthread_mutexattr_init(&at);
        if ((errno = pthread_mutexattr_setprotocol(&at, want)) != 0)
            die("pthread_mutexattr_setprotocol");
        (void)pthread_mutexattr_getprotocol(&at, &got);
        if ((errno = pthread_mutex_init(&mtx, &at)) != 0)
            die("pthread_mutex_init");
        pthread_mutexattr_destroy(&at);
        printf("busy_medium: mutex protocol requested=%d read back=%d (PRIO_NONE=%d PRIO_INHERIT=%d)\n", want, got,
               PTHREAD_PRIO_NONE, PTHREAD_PRIO_INHERIT);
    } else {
        fprintf(stderr, "busy_medium: -m must be pi, none or sem\n");
        return EXIT_FAILURE;
    }
    if (A.busy_us + 1000 + A.cs_us >= A.period_us) {
        fprintf(stderr, "busy_medium: -P must exceed 1 ms + -c + -b so each round finishes inside its period\n");
        return EXIT_FAILURE;
    }

    rounds = A.seconds * 1000000U / A.period_us;
    waits = calloc(rounds, sizeof *waits);
    if (!waits)
        die("calloc");
    t0 = now_ns() + 100 * 1000000ULL;

    struct role roles[3] = { { "bm_low", 10, 0 }, { "bm_med", 20, 1 }, { "bm_high", 30, 2 } };
    pthread_t th[3];
    for (int i = 0; i < 3; i++) {
        pthread_attr_t at;
        pthread_attr_init(&at);
        pthread_attr_setinheritsched(&at, PTHREAD_EXPLICIT_SCHED);
        pthread_attr_setschedpolicy(&at, SCHED_FIFO);
        if ((errno = pthread_create(&th[i], &at, role_thread, &roles[i])) != 0)
            die("pthread_create");
    }
    for (int i = 0; i < 3; i++)
        pthread_join(th[i], NULL);

    qsort(waits, rounds, sizeof *waits, cmp_u64);
    printf("busy_medium: mode=%s rounds=%u cs_us=%u busy_us=%u | high-thread wait us: min=%.0f median=%.0f max=%.0f\n",
           A.mode, rounds, A.cs_us, A.busy_us, (double)waits[0] / 1e3, (double)waits[rounds / 2] / 1e3,
           (double)waits[rounds - 1] / 1e3);
    return EXIT_SUCCESS;
}
