/* Host-only stub of <sys/neutrino.h> for `make hostcheck`. Not for QNX builds. */
#ifndef TL_STUB_NEUTRINO_H
#define TL_STUB_NEUTRINO_H

#include <pthread.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <time.h>

typedef long rcvid_t;

struct _msg_info {
    uint32_t nd, srcnd;
    pid_t pid;
    int32_t tid, chid, scoid, coid;
    int16_t priority, flags;
    size_t msglen, srcmsglen, dstmsglen;
};

struct _pulse {
    uint16_t type, subtype;
    int8_t code;
    uint8_t zero[3];
    union sigval value;
    int32_t scoid;
};

#define _NTO_CHF_FIXED_PRIORITY 0x0001u
#define _NTO_SIDE_CHANNEL 0x40000000u
#define _NTO_TCTL_IO 14
#define _NTO_TCTL_RUNMASK 4
#define _NTO_TIMEOUT_RECEIVE (1 << 2)
#define _NTO_TIMEOUT_SEND (1 << 3)
#define _NTO_TIMEOUT_REPLY (1 << 4)
#define _NTO_INTR_FLAGS_TRK_MSK 0x08u
#define _PULSE_CODE_MINAVAIL 0

#define SIGEV_INTR_INIT(e) ((void)((e)->sigev_notify = 0))

int ChannelCreate(unsigned flags);
int ChannelDestroy(int chid);
int ConnectAttach(uint32_t nd, pid_t pid, int chid, unsigned index, int flags);
int ConnectDetach(int coid);
rcvid_t MsgReceive(int chid, void *msg, size_t bytes, struct _msg_info *info);
int MsgReceivePulse(int chid, void *pulse, size_t bytes, struct _msg_info *info);
int MsgReply(rcvid_t rcvid, long status, const void *msg, size_t bytes);
long MsgSend(int coid, const void *smsg, size_t sbytes, void *rmsg, size_t rbytes);
int MsgSendPulse(int coid, int priority, int code, int value);
int TimerTimeout(clockid_t id, int flags, const struct sigevent *notify,
                 const uint64_t *ntime, uint64_t *otime);
int ThreadCtl(int cmd, void *data);
int InterruptAttachEvent(int intr, const struct sigevent *event, unsigned flags);
int InterruptDetach(int id);
int InterruptUnmask(int intr, int id);
int InterruptWait(int flags, const uint64_t *timeout);
uint64_t ClockCycles(void);
int pthread_setname_np(pthread_t thread, const char *name);

#endif
