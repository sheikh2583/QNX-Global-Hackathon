/*
 * Z3 - Sensor fusion server pair.
 *
 *   fusion_a  owns the IMU estimate; sends camera-fusion requests to fusion_b
 *   fusion_b  owns the camera estimate; sends IMU-sync requests to fusion_a
 *
 * Each server sits in MsgReceive() serving the other. Once per run each side
 * recalibrates: both sides meet at a shared epoch (a process-shared barrier) and
 * each asks its peer for its current estimate.
 */
#include <signal.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include "tl.h"

struct fusion_msg { uint32_t kind; float value; };

static uint64_t t0;
/* Recalibration epoch, shared by both processes: each side stops serving, snapshots its
 * own estimate, then asks the peer for its estimate at the same epoch. */
static pthread_barrier_t *epoch;
static unsigned run_s;

/* Request the peer's current estimate. */
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

static void serve(const char *name, int chid, int peer_coid, uint64_t recalibrate_at)
{
    tl_thread_init(name, 30, TL_ALL_CPUS);
    const uint64_t end = t0 + (uint64_t)run_s * TL_NS_PER_S;
    int recalibrated = 0;

    while (tl_now_ns() < end) {
        if (!recalibrated && tl_now_ns() >= recalibrate_at) {
            recalibrated = 1;
            pthread_barrier_wait(epoch);
            float peer_state;
            tl_mark("TL_NOTE recalibrate from=%s", name);
            if (request(peer_coid, 1, &peer_state) == -1)
                fprintf(stderr, "%s: recalibration request failed: %s\n", name, strerror(errno));
            continue;
        }
        struct fusion_msg msg;
        uint64_t poll = 5 * TL_NS_PER_MS;
        TimerTimeout(CLOCK_MONOTONIC, _NTO_TIMEOUT_RECEIVE, NULL, &poll, NULL);
        rcvid_t rcvid = MsgReceive(chid, &msg, sizeof msg, NULL);
        if (rcvid > 0) {
            struct fusion_msg reply = { msg.kind, 1.0f };
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

    epoch = mmap(NULL, sizeof *epoch, PROT_READ | PROT_WRITE, MAP_SHARED | MAP_ANON, NOFD, 0);
    if (epoch == MAP_FAILED)
        tl_die("mmap");
    pthread_barrierattr_t ba;
    pthread_barrierattr_init(&ba);
    pthread_barrierattr_setpshared(&ba, PTHREAD_PROCESS_SHARED);
    if ((errno = pthread_barrier_init(epoch, &ba, 2)) != 0)
        tl_die("pthread_barrier_init");
    pthread_barrierattr_destroy(&ba);

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
        serve("fusion_b", chid_b, coid_a, recalibrate_at);
        return 0;
    }

    int chid_b;
    if (read(pipefd[0], &chid_b, sizeof chid_b) != sizeof chid_b)
        tl_die("read chid");
    int coid_b = ConnectAttach(0, child, chid_b, _NTO_SIDE_CHANNEL, 0);
    if (coid_b == -1)
        tl_die("ConnectAttach(b)");
    serve("fusion_a", chid_a, coid_b, recalibrate_at);
    waitpid(child, NULL, 0);
    return 0;
}
