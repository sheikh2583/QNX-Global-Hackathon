/* Z1 reference fix: the sensor buffer is guarded by a priority-inheriting mutex. */
#include "tl.h"

#define PERIOD_US 10000

static struct {
    double samples[64];
    unsigned n;
} sensor_buf;

static pthread_mutex_t buf_lock; /* QNX default protocol: PTHREAD_PRIO_INHERIT */
static uint64_t t0;
static unsigned run_s;

static unsigned periods(void) { return run_s * 1000000U / PERIOD_US; }

static void *control(void *arg)
{
    (void)arg;
    tl_thread_init("control", 50, 0x1);
    for (unsigned k = 0; k < periods(); k++) {
        tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US);
        tl_job_start("control");
        pthread_mutex_lock(&buf_lock);
        double dose = 0;
        for (unsigned i = 0; i < sensor_buf.n; i++)
            dose += sensor_buf.samples[i];
        tl_spin_us(100);
        pthread_mutex_unlock(&buf_lock);
        (void)dose;
        tl_job_end("control");
    }
    return NULL;
}

static void *telemetry(void *arg)
{
    (void)arg;
    tl_thread_init("telemetry", 20, 0x1);
    for (unsigned k = 0; k < periods(); k++) {
        tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US + 20 * TL_NS_PER_US);
        tl_spin_us(8000);
    }
    return NULL;
}

static void *logger(void *arg)
{
    (void)arg;
    tl_thread_init("logger", 10, 0x1);
    double snapshot[64];
    for (unsigned k = 0; k < periods(); k++) {
        tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US - 300 * TL_NS_PER_US);
        pthread_mutex_lock(&buf_lock);
        sensor_buf.n = 64;
        for (unsigned i = 0; i < sensor_buf.n; i++)
            sensor_buf.samples[i] = (double)(k + i);
        memcpy(snapshot, sensor_buf.samples, sizeof snapshot);
        pthread_mutex_unlock(&buf_lock);
        /* Flash write happens on the snapshot, outside the lock: holding the
         * mutex for 600 us would make control wait ~300 us every period, which
         * TraceLens (correctly) reports as mutex contention. */
        tl_spin_us(600);
        (void)snapshot;
    }
    return NULL;
}

int main(int argc, char **argv)
{
    t0 = tl_parse_args(argc, argv, &run_s);

    pthread_mutexattr_t ma;
    pthread_mutexattr_init(&ma);
    pthread_mutexattr_setprotocol(&ma, PTHREAD_PRIO_INHERIT); /* explicit, though default */
    if ((errno = pthread_mutex_init(&buf_lock, &ma)) != 0)
        tl_die("pthread_mutex_init");
    pthread_mutexattr_destroy(&ma);

    pthread_t th[3] = { tl_spawn(logger, NULL), tl_spawn(telemetry, NULL), tl_spawn(control, NULL) };
    for (int i = 0; i < 3; i++)
        pthread_join(th[i], NULL);
    pthread_mutex_destroy(&buf_lock);
    return 0;
}
