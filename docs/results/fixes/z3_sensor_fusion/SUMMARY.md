# TraceLens fix: z3_sensor_fusion

- Status: **GUIDED**
- Runs per side: 5
- Findings in most 'before' runs: ipc_deadlock
- Note: no root cause here has a safe automatic transform; apply the guidance, then compare

## Guided: Break the Send/Reply cycle with a send hierarchy

_Rule `ipc-cycle`, for finding TL-001 (ipc_deadlock)._

QNX message passing is synchronous: a thread blocked in MsgSend() cannot receive. If two servers send to each other, each waits for the other to receive. QNX designs avoid this with a send hierarchy: messages only flow one way; the other direction uses non-blocking notifications (MsgSendPulse()/MsgDeliverEvent()) and the notified side pulls the data.

Source locations:
- `main.c:31` `if (MsgSend(coid, &msg, sizeof msg, &reply, sizeof reply) == -1)`

What to do:
- The trace shows the cycle fusion_a -> fusion_b -> fusion_a; these MsgSend() calls are where it closes.
- Pick a direction (usually: the more central server never sends to its clients). On the other side, replace MsgSend() with MsgSendPulse() (or MsgDeliverEvent() from a reply), and let the receiver fetch what it needs with its own MsgSend() down the hierarchy.
- Not automated: the reply carries data, so the new protocol is a design decision.
