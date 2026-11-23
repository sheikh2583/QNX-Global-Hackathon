/*
 * irqprobe - does this interrupt actually arrive on this machine?
 *
 *   irqprobe <irq> [seconds]
 *
 * The interrupt workloads (tlgen's healthy_irq / irq_overrun / healthy_irq_deferred and bug-zoo z5)
 * attach to an interrupt and block in InterruptWait() with no timeout. On a machine where the chosen
 * interrupt never fires they hang forever, which looks like a TraceLens failure and is not. This
 * program attaches the same way (InterruptAttachEvent with _NTO_INTR_FLAGS_TRK_MSK, unmask after each
 * event), but gives up each wait after 250 ms, so it reports "0 interrupts" instead of hanging.
 *
 * Use it to pick an interrupt source on a new board or emulated machine, with the load that is meant to
 * drive it running in the background (docs/results/aarch64.md section 6).
 */
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/neutrino.h>
#include <sys/siginfo.h>

static uint64_t now_ns(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <irq> [seconds]\n", argv[0]);
        return 2;
    }
    const int irq = atoi(argv[1]);
    const int secs = argc > 2 ? atoi(argv[2]) : 3;

    if (ThreadCtl(_NTO_TCTL_IO, 0) == -1) {
        perror("ThreadCtl(_NTO_TCTL_IO)");
        return 1;
    }
    struct sigevent ev;
    SIGEV_INTR_INIT(&ev);
    const int id = InterruptAttachEvent(irq, &ev, _NTO_INTR_FLAGS_TRK_MSK);
    if (id == -1) {
        printf("irq %d: InterruptAttachEvent failed: %s\n", irq, strerror(errno));
        return 1;
    }
    const uint64_t end = now_ns() + (uint64_t)secs * 1000000000ull;
    unsigned long count = 0, timeouts = 0;
    while (now_ns() < end) {
        struct sigevent tev;
        SIGEV_UNBLOCK_INIT(&tev);
        uint64_t wait_ns = 250000000ull;
        TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_INTR, &tev, &wait_ns, NULL);
        if (InterruptWait(0, NULL) == -1) {
            if (errno == ETIMEDOUT) {
                timeouts++;
                continue;
            }
            perror("InterruptWait");
            break;
        }
        count++;
        InterruptUnmask(irq, id);
    }
    InterruptDetach(id);
    printf("irq %d: %lu interrupts in %d s (%.0f/s), %lu quiet 250 ms waits\n", irq, count, secs,
           (double)count / (secs ? secs : 1), timeouts);
    return 0;
}
