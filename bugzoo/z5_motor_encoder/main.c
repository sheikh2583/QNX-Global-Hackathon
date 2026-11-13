/*
 * Z5 - Motor encoder interrupt service thread.
 *
 * Attaches to an interrupt with InterruptAttachEvent() and services it from a
 * high-priority thread (prio 60, CPU 0). For each interrupt the thread reads
 * the encoder and updates the motor velocity profile.
 *
 * Usage: z5_motor_encoder -i <irq> [-d seconds]
 *   <irq> is the encoder's interrupt line (see bugzoo/README.md for the QEMU setup).
 */
#include "tl.h"

static unsigned run_s = 2;
static int irq = -1;

static void recompute_velocity_profile(void) { tl_spin_us(2000); }

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

    if (ThreadCtl(_NTO_TCTL_IO, 0) == -1) /* I/O privity for interrupt calls (verify on 8.0) */
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
        count++; /* read + ack the encoder */
        recompute_velocity_profile();
        InterruptUnmask(irq, id);
    }
    InterruptDetach(id);
    printf("encoder_ist: %lu interrupts\n", count);
    return 0;
}
