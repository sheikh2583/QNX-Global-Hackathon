/*
 * Z4 - Camera frame pipeline.
 *
 * Four worker threads (prio 20, CPUs 0-1) each process one tile of a frame
 * every 4 ms (releases staggered by 100 us) and publish it into a shared frame
 * store. Frame budget: 1.5 ms per worker.
 */
#include "tl.h"

#define PERIOD_US 4000
#define WORKERS 4
#define TILE_BYTES (256 * 1024)

static pthread_mutex_t store_lock = PTHREAD_MUTEX_INITIALIZER;
static unsigned char frame_store[WORKERS][TILE_BYTES];
static uint64_t t0;
static unsigned run_s;

static void *worker(void *arg)
{
    const unsigned id = (unsigned)(uintptr_t)arg;
    char name[16];
    snprintf(name, sizeof name, "worker%u", id + 1);
    tl_thread_init(name, 20, 0x3);

    unsigned char *tile = malloc(TILE_BYTES);
    if (tile == NULL)
        tl_die("malloc");
    const unsigned periods = run_s * 1000000U / PERIOD_US;

    for (unsigned k = 0; k < periods; k++) {
        tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US + id * 100 * TL_NS_PER_US);
        tl_job_start("frame");
        pthread_mutex_lock(&store_lock);
        /* Demosaic + colour-correct the tile, then publish it. */
        memset(tile, (int)(k + id), TILE_BYTES);
        tl_spin_us(600);
        memcpy(frame_store[id], tile, TILE_BYTES);
        pthread_mutex_unlock(&store_lock);
        tl_job_end("frame");
    }
    free(tile);
    return NULL;
}

int main(int argc, char **argv)
{
    t0 = tl_parse_args(argc, argv, &run_s);
    pthread_t th[WORKERS];
    for (unsigned i = 0; i < WORKERS; i++)
        th[i] = tl_spawn(worker, (void *)(uintptr_t)i);
    for (unsigned i = 0; i < WORKERS; i++)
        pthread_join(th[i], NULL);
    return 0;
}
