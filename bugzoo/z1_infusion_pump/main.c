/*
 * Z1 - Infusion pump control loop.
 *
 * Three threads share a sensor buffer, all pinned to CPU 0:
 *   control    prio 50  every 10 ms: read the buffer, compute the dose (deadline 1 ms)
 *   telemetry  prio 20  every 10 ms: compress and upload readings (8 ms of CPU)
 *   logger     prio 10  every 10 ms: append the buffer to the black-box log
 */
#include <semaphore.h>
#include "tl.h"

#define PERIOD_US 10000

static struct {
    double samples[64];
    unsigned n;
} sensor_buf;

static sem_t buf_lock;
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
        sem_wait(&buf_lock);
        double dose = 0;
        for (unsigned i = 0; i < sensor_buf.n; i++)
            dose += sensor_buf.samples[i];
        tl_spin_us(100); /* dose computation */
        sem_post(&buf_lock);
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
        tl_spin_us(8000); /* compression + upload */
    }
    return NULL;
}

static void *logger(void *arg)
{
    (void)arg;
    tl_thread_init("logger", 10, 0x1);
    for (unsigned k = 0; k < periods(); k++) {
        tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US - 300 * TL_NS_PER_US);
        sem_wait(&buf_lock);
        sensor_buf.n = 64;
        for (unsigned i = 0; i < sensor_buf.n; i++)
            sensor_buf.samples[i] = (double)(k + i);
        tl_spin_us(600); /* write to flash */
        sem_post(&buf_lock);
    }
    return NULL;
}

int main(int argc, char **argv)
{
    t0 = tl_parse_args(argc, argv, &run_s);
    if (sem_init(&buf_lock, 0, 1) == -1)
        tl_die("sem_init");

    pthread_t th[3] = { tl_spawn(logger, NULL), tl_spawn(telemetry, NULL), tl_spawn(control, NULL) };
    for (int i = 0; i < 3; i++)
        pthread_join(th[i], NULL);
    sem_destroy(&buf_lock);
    return 0;
}
