/*
 * Z3 reference fix: strict send hierarchy.
 *
 * fusion_a may MsgSend() to fusion_b (down the hierarchy). fusion_b never
 * sends to fusion_a; it notifies "up" with MsgSendPulse(), which never blocks,
 * and fusion_a pulls the data on its next request.
 */
#include <signal.h>
#include <sys/wait.h>
#include "tl.h"

#define PULSE_RECALIBRATE (_PULSE_CODE_MINAVAIL + 1)

struct fusion_msg { uint32_t kind; float value; };

static uint64_t t0;
static unsigned run_s;

static int request(int coid, uint32_t kind, float *out)
{
    struct fusion_msg msg = { kind, 0.0f };
    struct fusion_msg reply;
    uint64_t timeout = 1 * TL_NS_PER_S;
    TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_SEND | _NTO_TIMEOUT_REPLY, NULL, &timeout, NULL);
    if (MsgSend(coid, &msg, sizeof msg, &reply, sizeof reply) == -1)
        return -1;
    *out = reply.value;
    return 0;
}

/* is_upper: fusion_a (sends requests down); otherwise fusion_b (pulses up). */
static void serve(const char *name, int is_upper, int chid, int peer_coid, uint64_t recalibrate_at)
{
    tl_thread_init(name, 30, 0x1 | 0x2);
    const uint64_t end = t0 + (uint64_t)run_s * TL_NS_PER_S;
    int recalibrated = 0;

    while (tl_now_ns() < end) {
        if (!recalibrated && tl_now_ns() >= recalibrate_at) {
            recalibrated = 1;
            tl_mark("TL_NOTE recalibrate from=%s", name);
            if (is_upper) {
                float peer_state;
                if (request(peer_coid, 1, &peer_state) == -1)
                    fprintf(stderr, "%s: request failed: %s\n", name, strerror(errno));
            } else if (MsgSendPulse(peer_coid, -1, PULSE_RECALIBRATE, 0) == -1) {
                fprintf(stderr, "%s: pulse failed: %s\n", name, strerror(errno));
            }
            continue;
        }
        union { struct fusion_msg msg; struct _pulse pulse; } in;
        uint64_t poll = 5 * TL_NS_PER_MS;
        TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_RECEIVE, NULL, &poll, NULL);
        rcvid_t rcvid = MsgReceive(chid, &in, sizeof in, NULL);
        if (rcvid == 0 && in.pulse.code == PULSE_RECALIBRATE && is_upper) {
            float peer_state; /* pull the camera estimate from fusion_b */
            (void)request(peer_coid, 2, &peer_state);
        } else if (rcvid > 0) {
            struct fusion_msg reply = { in.msg.kind, 1.0f };
            tl_spin_us(100);
            MsgReply(rcvid, 0, &reply, sizeof reply);
        }
    }
}

int main(int argc, char **argv)
{
    t0 = tl_parse_args(argc, argv, &run_s);
    const uint64_t recalibrate_at = t0 + 500 * TL_NS_PER_MS;

    int pipefd[2];
    if (pipe(pipefd) == -1)
        tl_die("pipe");

    int chid_a = ChannelCreate(0);
    if (chid_a == -1)
        tl_die("ChannelCreate(a)");
    pid_t pid_a = getpid();

    pid_t child = fork();
    if (child == -1)
        tl_die("fork");

    if (child == 0) { /* fusion_b */
        int chid_b = ChannelCreate(0);
        if (chid_b == -1)
            tl_die("ChannelCreate(b)");
        if (write(pipefd[1], &chid_b, sizeof chid_b) != sizeof chid_b)
            tl_die("write chid");
        int coid_a = ConnectAttach(0, pid_a, chid_a, _NTO_SIDE_CHANNEL, 0);
        if (coid_a == -1)
            tl_die("ConnectAttach(a)");
        serve("fusion_b", 0, chid_b, coid_a, recalibrate_at);
        return 0;
    }

    int chid_b;
    if (read(pipefd[0], &chid_b, sizeof chid_b) != sizeof chid_b)
        tl_die("read chid");
    int coid_b = ConnectAttach(0, child, chid_b, _NTO_SIDE_CHANNEL, 0);
    if (coid_b == -1)
        tl_die("ConnectAttach(b)");
    serve("fusion_a", 1, chid_a, coid_b, recalibrate_at);
    waitpid(child, NULL, 0);
    return 0;
}
