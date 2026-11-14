/*
 * Z2 - Brake-by-wire message chain.
 *
 *   brake_ctrl   (process, prio 60)  every 10 ms: MsgSend a brake request to the arbiter
 *   arbiter      (process, prio 10)  receives requests, validates them (200 us), replies
 *   diagnostics  (arbiter process, prio 30)  6 ms of CPU every 10 ms
 *
 * All threads are pinned to CPU 0. diagnostics is released one QNX clock tick (1 ms) before
 * brake_ctrl, so it is already running when the request arrives, on every run.
 */
#include <signal.h>
#include <sys/wait.h>
#include "tl.h"

#define PERIOD_US 10000

struct brake_req { uint32_t seq; int32_t pressure_kpa; };
struct brake_ack { uint32_t seq; int32_t applied_kpa; };

static uint64_t t0;
static unsigned run_s;

static unsigned periods(void) { return run_s * 1000000U / PERIOD_US; }

static void *diagnostics(void *arg)
{
    (void)arg;
    tl_thread_init("diagnostics", 30, 0x1);
    for (unsigned k = 0; k < periods(); k++) {
        tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US - 1000 * TL_NS_PER_US);
        tl_spin_us(6000); /* self-test sweep */
    }
    return NULL;
}

static void arbiter(int chid)
{
    tl_thread_init("arbiter", 10, 0x1);
    pthread_t diag = tl_spawn(diagnostics, NULL);

    for (unsigned k = 0; k < periods(); k++) {
        struct brake_req req;
        struct _msg_info info;
        rcvid_t rcvid = MsgReceive(chid, &req, sizeof req, &info);
        if (rcvid == -1)
            tl_die("MsgReceive");
        if (rcvid == 0)
            continue; /* pulse */
        tl_spin_us(200); /* validate against wheel-speed limits */
        struct brake_ack ack = { req.seq, req.pressure_kpa > 9000 ? 9000 : req.pressure_kpa };
        MsgReply(rcvid, 0, &ack, sizeof ack);
    }
    pthread_join(diag, NULL);
}

static void brake_ctrl(pid_t server, int chid)
{
    tl_thread_init("brake_ctrl", 60, 0x1);
    int coid = ConnectAttach(0, server, chid, _NTO_SIDE_CHANNEL, 0);
    if (coid == -1)
        tl_die("ConnectAttach");

    for (unsigned k = 0; k < periods(); k++) {
        tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US);
        tl_job_start("brake");
        struct brake_req req = { k, 4200 };
        struct brake_ack ack;
        if (MsgSend(coid, &req, sizeof req, &ack, sizeof ack) == -1)
            tl_die("MsgSend");
        tl_job_end("brake");
    }
    ConnectDetach(coid);
}

int main(int argc, char **argv)
{
    t0 = tl_parse_args(argc, argv, &run_s);

    int chid = ChannelCreate(_NTO_CHF_FIXED_PRIORITY);
    if (chid == -1)
        tl_die("ChannelCreate");

    pid_t server = getpid();
    pid_t child = fork();
    if (child == -1)
        tl_die("fork");
    if (child == 0) {
        brake_ctrl(server, chid);
        return 0;
    }
    arbiter(chid);
    waitpid(child, NULL, 0);
    ChannelDestroy(chid);
    return 0;
}
