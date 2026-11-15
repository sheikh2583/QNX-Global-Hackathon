/*
 * tlgen - one QNX program, many real-time scenarios, for TraceLens's ML data engine.
 *
 *   tlgen -s <scenario> [-d seconds] [-P period_us] [-H hi] [-M mid] [-L lo]
 *         [-w work_us] [-c cs_us] [-m mid_us] [-n workers] [-p pin] [-i irq]
 *
 * Each run plants (or does not plant) one known problem, so the trace's label is known without
 * anyone reading it. Built once with qcc; the dataset is many runs with different arguments.
 * Releases are whole QNX ticks (1 ms) apart: QNX 8.0 fires timers on tick boundaries, so sub-tick
 * offsets would make a planted bug trigger only sometimes (measured, PLAN.md section 15).
 *
 * Scenarios (label in brackets; "unseen" = no TraceLens rule exists, used to test the radar):
 *   healthy_periodic   [healthy]              periodic threads, no shared state
 *   healthy_pi_mutex   [healthy]              shared buffer behind a priority-inheriting mutex
 *   healthy_ipc        [healthy]              client -> server with default (inheriting) channel
 *   healthy_mixed      [healthy]              periodic + PI mutex + message passing together
 *   sem_inversion      [priority_inversion]   semaphore used as a lock, medium load in between
 *   chan_inversion     [priority_inversion]   _NTO_CHF_FIXED_PRIORITY server, medium load
 *   ipc_deadlock       [ipc_deadlock]         two processes MsgSend() to each other
 *   lock_contention    [mutex_contention]     N workers do their work inside one mutex
 *   condvar_inversion  [priority_inversion]   high waits on a condvar the low thread must signal
 *   cpu_starvation     [unseen]               a busy higher-priority thread makes a periodic job late
 *   mutex_abba         [unseen]               two mutexes taken in opposite orders (timed out)
 *   lost_wakeup        [unseen]               signal sent before the consumer waits: it sleeps to its timeout (-m)
 *   period_overrun     [unseen]               a periodic job's work exceeds its period; a logger starves
 *   healthy_irq        [healthy]              interrupt thread: acknowledge, unmask, then short work (-i irq)
 *   irq_overrun        [irq_handler_overrun]  interrupt thread works before InterruptUnmask() (-i irq)
 * The interrupt scenarios need a busy interrupt line: on the QEMU VM, IRQ 4 (console UART) while
 * something writes to /dev/ser1 (verified, PLAN.md).
 */
#include <semaphore.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <time.h>
#include "tl.h"

static struct {
    const char *scenario;
    unsigned seconds, period_us, work_us, cs_us, mid_us, workers, pin;
    int hi, mid, lo, irq;
} A = { "healthy_periodic", 2, 10000, 300, 200, 4000, 4, 1, 50, 20, 10, -1 };

static uint64_t t0;
static unsigned cpu_mask(void) { return A.pin ? 0x1u : TL_ALL_CPUS; }
static unsigned periods(void) { return A.seconds * 1000000U / A.period_us; }
static uint64_t release(unsigned k, int tick_offset)
{
    return t0 + (uint64_t)k * A.period_us * TL_NS_PER_US + (int64_t)tick_offset * (int64_t)TL_NS_PER_MS;
}

/* ------------------------------------------------------------------ shared state */
static sem_t sem_lock;
static pthread_mutex_t mtx = PTHREAD_MUTEX_INITIALIZER, mtx_b = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cond = PTHREAD_COND_INITIALIZER;
static unsigned ready_gen;
static volatile double shared_buf[64];

static void pi_mutex_init(pthread_mutex_t *m)
{
    pthread_mutexattr_t a;
    pthread_mutexattr_init(&a);
    pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_INHERIT);
    if ((errno = pthread_mutex_init(m, &a)) != 0)
        tl_die("pthread_mutex_init");
    pthread_mutexattr_destroy(&a);
}

static void touch_buffer(unsigned k)
{
    for (unsigned i = 0; i < 64; i++)
        shared_buf[i] = (double)(k + i);
}

/* ------------------------------------------------------------------ roles */
struct role { const char *name; int prio; int offset_ticks; unsigned work_us; int kind; };
enum { R_PLAIN, R_SEM_HI, R_SEM_LO, R_MTX_HI, R_MTX_LO, R_CV_HI, R_CV_LO, R_BUSY, R_WORKER, R_LW_CONS, R_LW_PROD };

static void *role_thread(void *arg)
{
    struct role *r = arg;
    tl_thread_init(r->name, r->prio, cpu_mask());
    for (unsigned k = 0; k < periods(); k++) {
        tl_sleep_until(release(k, r->offset_ticks));
        switch (r->kind) {
        case R_PLAIN:
        case R_BUSY:
            tl_job_start(r->name);
            tl_spin_us(r->work_us);
            tl_job_end(r->name);
            break;
        case R_SEM_HI:
            tl_job_start("job");
            sem_wait(&sem_lock);
            tl_spin_us(r->work_us);
            sem_post(&sem_lock);
            tl_job_end("job");
            break;
        case R_SEM_LO:
            sem_wait(&sem_lock);
            touch_buffer(k);
            tl_spin_us(A.cs_us);
            sem_post(&sem_lock);
            break;
        case R_MTX_HI:
        case R_WORKER:
            tl_job_start(r->kind == R_MTX_HI ? "job" : "frame");
            pthread_mutex_lock(&mtx);
            touch_buffer(k);
            tl_spin_us(r->work_us);
            pthread_mutex_unlock(&mtx);
            tl_job_end(r->kind == R_MTX_HI ? "job" : "frame");
            break;
        case R_MTX_LO:
            pthread_mutex_lock(&mtx);
            touch_buffer(k);
            tl_spin_us(A.cs_us);
            pthread_mutex_unlock(&mtx);
            break;
        case R_CV_HI: {   /* waits for the low thread's data: no inheritance through a condvar */
            tl_job_start("job");
            pthread_mutex_lock(&mtx);
            unsigned want = k + 1;
            while (ready_gen < want)
                pthread_cond_wait(&cond, &mtx);
            pthread_mutex_unlock(&mtx);
            tl_spin_us(r->work_us);
            tl_job_end("job");
            break;
        }
        case R_CV_LO:     /* produces outside the lock (so no mutex inheritance), then signals */
            tl_spin_us(A.cs_us);
            pthread_mutex_lock(&mtx);
            ready_gen = k + 1;
            pthread_cond_broadcast(&cond);
            pthread_mutex_unlock(&mtx);
            break;
        case R_LW_CONS: { /* no predicate: a signal sent before this wait is lost, so it sleeps to the timeout */
            tl_job_start(r->name);
            pthread_mutex_lock(&mtx);
            struct timespec ts;
            clock_gettime(CLOCK_REALTIME, &ts);
            ts.tv_nsec += (long)A.mid_us * 1000L;
            while (ts.tv_nsec >= 1000000000L) {
                ts.tv_sec++;
                ts.tv_nsec -= 1000000000L;
            }
            (void)pthread_cond_timedwait(&cond, &mtx, &ts);
            pthread_mutex_unlock(&mtx);
            tl_spin_us(r->work_us);
            tl_job_end(r->name);
            break;
        }
        case R_LW_PROD:   /* signals one tick before the consumer waits */
            tl_spin_us(A.cs_us);
            pthread_mutex_lock(&mtx);
            pthread_cond_signal(&cond);
            pthread_mutex_unlock(&mtx);
            break;
        }
    }
    return NULL;
}

static void run_roles(struct role *roles, unsigned n)
{
    pthread_t th[16];
    for (unsigned i = 0; i < n; i++)
        th[i] = tl_spawn(role_thread, &roles[i]);
    for (unsigned i = 0; i < n; i++)
        pthread_join(th[i], NULL);
}

/* ------------------------------------------------------------------ message passing */
struct msg { uint32_t seq; int32_t v; };
static int srv_chid = -1;

static void *server_thread(void *arg)
{
    const char *name = arg;
    tl_thread_init(name, A.lo, cpu_mask());
    for (unsigned k = 0; k < periods(); k++) {
        struct msg m;
        rcvid_t rcvid = MsgReceive(srv_chid, &m, sizeof m, NULL);
        if (rcvid <= 0)
            continue;
        tl_spin_us(A.cs_us);
        MsgReply(rcvid, 0, &m, sizeof m);
    }
    return NULL;
}

static void *client_thread(void *arg)
{
    (void)arg;
    tl_thread_init("client", A.hi, cpu_mask());
    int coid = ConnectAttach(0, 0, srv_chid, _NTO_SIDE_CHANNEL, 0);
    if (coid == -1)
        tl_die("ConnectAttach");
    for (unsigned k = 0; k < periods(); k++) {
        tl_sleep_until(release(k, 0));
        tl_job_start("job");
        struct msg m = { k, 1 }, r;
        if (MsgSend(coid, &m, sizeof m, &r, sizeof r) == -1)
            tl_die("MsgSend");
        tl_spin_us(A.work_us);
        tl_job_end("job");
    }
    return NULL;
}

static void run_ipc(unsigned flags, int with_mid)
{
    if ((srv_chid = ChannelCreate(flags)) == -1)
        tl_die("ChannelCreate");
    struct role mid = { "mid", A.mid, -1, A.mid_us, R_BUSY };
    pthread_t s = tl_spawn(server_thread, (void *)"server"), c = tl_spawn(client_thread, NULL), m;
    if (with_mid)
        m = tl_spawn(role_thread, &mid);
    pthread_join(c, NULL);
    pthread_cancel(s);
    if (with_mid)
        pthread_join(m, NULL);
}

/* ------------------------------------------------------------------ ipc deadlock (two processes) */
static void run_ipc_deadlock(void)
{
    pthread_barrier_t *epoch = mmap(NULL, sizeof *epoch, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, NOFD, 0);
    if (epoch == MAP_FAILED)
        tl_die("mmap");
    pthread_barrierattr_t ba;
    pthread_barrierattr_init(&ba);
    pthread_barrierattr_setpshared(&ba, PTHREAD_PROCESS_SHARED);
    pthread_barrier_init(epoch, &ba, 2);
    int pipefd[2];
    if (pipe(pipefd) == -1)
        tl_die("pipe");
    int chid_a = ChannelCreate(0);
    pid_t pid_a = getpid(), child = fork();
    if (child == -1)
        tl_die("fork");
    int is_b = child == 0, chid = is_b ? ChannelCreate(0) : chid_a, peer;
    if (is_b) {
        if (write(pipefd[1], &chid, sizeof chid) != sizeof chid)
            tl_die("write");
        peer = ConnectAttach(0, pid_a, chid_a, _NTO_SIDE_CHANNEL, 0);
    } else {
        int chid_b;
        if (read(pipefd[0], &chid_b, sizeof chid_b) != sizeof chid_b)
            tl_die("read");
        peer = ConnectAttach(0, child, chid_b, _NTO_SIDE_CHANNEL, 0);
    }
    tl_thread_init(is_b ? "fusion_b" : "fusion_a", A.mid, TL_ALL_CPUS);
    tl_sleep_until(t0 + (uint64_t)A.seconds * TL_NS_PER_S / 4);
    pthread_barrier_wait(epoch);                 /* both stop serving, then ask each other */
    struct msg m = { 1, 0 }, r;
    uint64_t timeout = 1 * TL_NS_PER_S;
    TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_SEND | _NTO_TIMEOUT_REPLY, NULL, &timeout, NULL);
    (void)MsgSend(peer, &m, sizeof m, &r, sizeof r);
    (void)chid;
    if (is_b)
        _exit(0);
    waitpid(child, NULL, 0);
}

/* ------------------------------------------------------------------ lock-order deadlock (unseen) */
static void *abba_thread(void *arg)
{
    int first_a = arg != NULL;
    tl_thread_init(first_a ? "ab" : "ba", A.mid, TL_ALL_CPUS);
    tl_sleep_until(t0 + (uint64_t)A.seconds * TL_NS_PER_S / 4);
    pthread_mutex_t *x = first_a ? &mtx : &mtx_b, *y = first_a ? &mtx_b : &mtx;
    pthread_mutex_lock(x);
    tl_spin_us(2000);                            /* both now hold their first lock */
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    ts.tv_sec += 1;
    if (pthread_mutex_timedlock(y, &ts) == 0)
        pthread_mutex_unlock(y);
    pthread_mutex_unlock(x);
    return NULL;
}

/* ------------------------------------------------------------------ interrupt thread */
static void run_irq(int unmask_first)
{
    if (A.irq < 0) {
        fprintf(stderr, "%s needs -i <irq>\n", A.scenario);
        exit(2);
    }
    if (ThreadCtl(_NTO_TCTL_IO, 0) == -1)
        tl_die("ThreadCtl(_NTO_TCTL_IO)");
    tl_thread_init("ist", A.hi, 0x1);
    struct sigevent ev;
    SIGEV_INTR_INIT(&ev);
    int id = InterruptAttachEvent(A.irq, &ev, _NTO_INTR_FLAGS_TRK_MSK);
    if (id == -1)
        tl_die("InterruptAttachEvent");
    const uint64_t end = tl_now_ns() + (uint64_t)A.seconds * TL_NS_PER_S;
    while (tl_now_ns() < end) {
        if (InterruptWait(0, NULL) == -1)
            tl_die("InterruptWait");
        if (unmask_first) {
            InterruptUnmask(A.irq, id);
            tl_spin_us(A.cs_us);              /* a little bookkeeping, interrupt already unmasked */
        } else {
            tl_spin_us(A.work_us);            /* the heavy work, with the line still masked */
            InterruptUnmask(A.irq, id);
        }
    }
    InterruptDetach(id);
}

/* ------------------------------------------------------------------ main */
int main(int argc, char **argv)
{
    int c;
    while ((c = getopt(argc, argv, "s:d:P:H:M:L:w:c:m:n:p:i:")) != -1) {
        switch (c) {
        case 's': A.scenario = optarg; break;
        case 'd': A.seconds = (unsigned)atoi(optarg); break;
        case 'P': A.period_us = (unsigned)atoi(optarg); break;
        case 'H': A.hi = atoi(optarg); break;
        case 'M': A.mid = atoi(optarg); break;
        case 'L': A.lo = atoi(optarg); break;
        case 'w': A.work_us = (unsigned)atoi(optarg); break;
        case 'c': A.cs_us = (unsigned)atoi(optarg); break;
        case 'm': A.mid_us = (unsigned)atoi(optarg); break;
        case 'n': A.workers = (unsigned)atoi(optarg); break;
        case 'p': A.pin = (unsigned)atoi(optarg); break;
        case 'i': A.irq = atoi(optarg); break;
        default:
            fprintf(stderr, "usage: %s -s scenario [-d s] [-P us] [-H -M -L prio] [-w -c -m us] [-n N] [-p 0|1]\n", argv[0]);
            return 2;
        }
    }
    if (A.workers > 12)
        A.workers = 12;
    t0 = tl_now_ns() + 100 * TL_NS_PER_MS;
    tl_mark("TL_GEN scenario=%s period_us=%u work_us=%u cs_us=%u mid_us=%u workers=%u pin=%u",
            A.scenario, A.period_us, A.work_us, A.cs_us, A.mid_us, A.workers, A.pin);
    const char *s = A.scenario;

    if (!strcmp(s, "healthy_periodic")) {
        struct role r[3] = { { "hi", A.hi, 0, A.work_us, R_PLAIN }, { "mid", A.mid, -1, A.work_us, R_PLAIN },
                             { "lo", A.lo, -2, A.work_us, R_PLAIN } };
        run_roles(r, 3);
    } else if (!strcmp(s, "healthy_pi_mutex") || !strcmp(s, "sem_inversion")) {
        int sem = !strcmp(s, "sem_inversion");
        if (sem && sem_init(&sem_lock, 0, 1) == -1)
            tl_die("sem_init");
        if (!sem)
            pi_mutex_init(&mtx);
        struct role r[3] = { { "hi", A.hi, 0, A.work_us, sem ? R_SEM_HI : R_MTX_HI },
                             { "mid", A.mid, -1, A.mid_us, R_BUSY },
                             { "lo", A.lo, -2, 0, sem ? R_SEM_LO : R_MTX_LO } };
        run_roles(r, 3);
    } else if (!strcmp(s, "healthy_ipc") || !strcmp(s, "chan_inversion")) {
        run_ipc(!strcmp(s, "chan_inversion") ? _NTO_CHF_FIXED_PRIORITY : 0, 1);
    } else if (!strcmp(s, "healthy_mixed")) {
        pi_mutex_init(&mtx);
        struct role r[3] = { { "hi", A.hi, 0, A.work_us, R_MTX_HI }, { "mid", A.mid, -1, A.work_us, R_PLAIN },
                             { "lo", A.lo, -2, 0, R_MTX_LO } };
        pthread_t th[3];
        for (unsigned i = 0; i < 3; i++)
            th[i] = tl_spawn(role_thread, &r[i]);
        run_ipc(0, 0);
        for (unsigned i = 0; i < 3; i++)
            pthread_join(th[i], NULL);
    } else if (!strcmp(s, "ipc_deadlock")) {
        run_ipc_deadlock();
    } else if (!strcmp(s, "lock_contention")) {
        struct role r[12];
        for (unsigned i = 0; i < A.workers; i++) {
            static char names[12][8];
            snprintf(names[i], sizeof names[i], "w%u", i + 1);
            r[i] = (struct role){ names[i], A.mid, 0, A.work_us, R_WORKER };
        }
        run_roles(r, A.workers);
    } else if (!strcmp(s, "condvar_inversion")) {
        struct role r[3] = { { "hi", A.hi, 0, A.work_us, R_CV_HI }, { "mid", A.mid, -1, A.mid_us, R_BUSY },
                             { "lo", A.lo, -2, 0, R_CV_LO } };
        run_roles(r, 3);
    } else if (!strcmp(s, "cpu_starvation")) {
        struct role r[2] = { { "job", A.mid, 0, A.work_us, R_PLAIN }, { "hog", A.hi, -1, A.mid_us, R_BUSY } };
        run_roles(r, 2);
    } else if (!strcmp(s, "lost_wakeup")) {
        struct role r[2] = { { "consumer", A.hi, 0, A.work_us, R_LW_CONS }, { "producer", A.lo, -1, 0, R_LW_PROD } };
        run_roles(r, 2);
    } else if (!strcmp(s, "period_overrun")) {
        struct role r[2] = { { "ctl", A.hi, 0, A.work_us, R_PLAIN }, { "logger", A.lo, -2, A.cs_us, R_PLAIN } };
        run_roles(r, 2);
    } else if (!strcmp(s, "mutex_abba")) {
        pthread_t a = tl_spawn(abba_thread, (void *)1), b = tl_spawn(abba_thread, NULL);
        pthread_join(a, NULL);
        pthread_join(b, NULL);
    } else if (!strcmp(s, "healthy_irq") || !strcmp(s, "irq_overrun")) {
        run_irq(!strcmp(s, "healthy_irq"));
    } else {
        fprintf(stderr, "unknown scenario %s\n", s);
        return 2;
    }
    return 0;
}
