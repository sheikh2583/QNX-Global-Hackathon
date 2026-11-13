/*
 * Z5 reference fix: the interrupt service thread only reads/acks the encoder
 * and unmasks the interrupt immediately; the heavy velocity-profile work runs
 * in a lower-priority worker thread on another CPU, triggered by a pulse.
 *
 * The pulse carries an explicit priority (20): a pulse sent with -1 would carry
 * the IST's priority (60) and the worker would run its 2 ms recompute at 60,
 * delaying the next interrupt anyway. (verify pulse-priority semantics on 8.0)
 * Interrupts that arrive while a recompute is pending coalesce into it.
 *
 * Usage: z5_motor_encoder_fixed -i <irq> [-d seconds]
 */
#include <stdatomic.h>
#include "tl.h"

#define PULSE_ENCODER (_PULSE_CODE_MINAVAIL + 1)
#define WORKER_PRIO 20

static unsigned run_s = 2;
static int irq = -1;
static int chid = -1;
static atomic_int running = 1;
static atomic_int recompute_pending;

static void recompute_velocity_profile(void) { tl_spin_us(2000); }

static void *velocity_worker(void *arg)
{
    (void)arg;
    tl_thread_init("velocity_worker", WORKER_PRIO, 0x2);
    while (atomic_load(&running)) {
        struct _pulse p;
        uint64_t poll = 50 * TL_NS_PER_MS;
        TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_RECEIVE, NULL, &poll, NULL);
        if (MsgReceive(chid, &p, sizeof p, NULL) == 0 && p.code == PULSE_ENCODER) {
            atomic_store(&recompute_pending, 0);
            recompute_velocity_profile();
        }
    }
    return NULL;
}

int main(int argc, char **argv)
{
    int c;
    while ((c = getopt(argc, argv, "i:d:")) != -1) {
        if (c == 'i')
            irq = atoi(optarg);
        else if (c == 'd')
            run_s = (unsigned)atoi(optarg);
    }
    if (irq < 0) {
        fprintf(stderr, "usage: %s -i <irq> [-d seconds]\n", argv[0]);
        return EXIT_FAILURE;
    }

    if ((chid = ChannelCreate(0)) == -1)
        tl_die("ChannelCreate");
    int self_coid = ConnectAttach(0, 0, chid, _NTO_SIDE_CHANNEL, 0);
    if (self_coid == -1)
        tl_die("ConnectAttach");
    pthread_t worker = tl_spawn(velocity_worker, NULL);

    if (ThreadCtl(_NTO_TCTL_IO, 0) == -1) /* (verify on 8.0) */
        tl_die("ThreadCtl(_NTO_TCTL_IO)");
    tl_thread_init("encoder_ist", 60, 0x1);

    struct sigevent ev;
    SIGEV_INTR_INIT(&ev);
    int id = InterruptAttachEvent(irq, &ev, _NTO_INTR_FLAGS_TRK_MSK);
    if (id == -1)
        tl_die("InterruptAttachEvent");

    const uint64_t end = tl_now_ns() + (uint64_t)run_s * TL_NS_PER_S;
    unsigned long count = 0;
    while (tl_now_ns() < end) {
        if (InterruptWait(0, NULL) == -1)
            tl_die("InterruptWait");
        count++;                       /* read + ack the encoder (fast) */
        InterruptUnmask(irq, id);      /* unmask first */
        if (atomic_exchange(&recompute_pending, 1) == 0)  /* defer the heavy work */
            MsgSendPulse(self_coid, WORKER_PRIO, PULSE_ENCODER, 0);
    }
    InterruptDetach(id);
    atomic_store(&running, 0);
    pthread_join(worker, NULL);
    printf("encoder_ist: %lu interrupts\n", count);
    return 0;
}
