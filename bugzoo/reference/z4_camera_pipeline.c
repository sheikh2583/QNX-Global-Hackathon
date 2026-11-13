/*
 * Z4 reference fix: do the work on a private tile outside the lock; the lock
 * only protects publishing (a pointer swap), so hold times drop from ~0.6 ms
 * to well under a microsecond.
 */
#include "tl.h"

#define PERIOD_US 4000
#define WORKERS 4
#define TILE_BYTES (256 * 1024)

static pthread_mutex_t store_lock = PTHREAD_MUTEX_INITIALIZER;
static unsigned char *frame_store[WORKERS]; /* published tiles */
static uint64_t t0;
static unsigned run_s;

static void *worker(void *arg)
{
    const unsigned id = (unsigned)(uintptr_t)arg;
    char name[16];
    snprintf(name, sizeof name, "worker%u", id + 1);
    tl_thread_init(name, 20, 0x3);

    /* Double buffer: fill one tile while the other is published. */
    unsigned char *tiles[2] = { malloc(TILE_BYTES), malloc(TILE_BYTES) };
    if (tiles[0] == NULL || tiles[1] == NULL)
        tl_die("malloc");
    const unsigned periods = run_s * 1000000U / PERIOD_US;

    for (unsigned k = 0; k < periods; k++) {
        tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US + id * 100 * TL_NS_PER_US);
        tl_job_start("frame");
        unsigned char *tile = tiles[k & 1];
        memset(tile, (int)(k + id), TILE_BYTES);
        tl_spin_us(600);
        pthread_mutex_lock(&store_lock);
        frame_store[id] = tile; /* publish */
        pthread_mutex_unlock(&store_lock);
        tl_job_end("frame");
    }
    pthread_mutex_lock(&store_lock);
    frame_store[id] = NULL;
    pthread_mutex_unlock(&store_lock);
    free(tiles[0]);
    free(tiles[1]);
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
