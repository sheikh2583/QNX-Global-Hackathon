"""Synthetic twins of the bug-zoo workloads (see PLAN.md Â§5).

Each function returns traceprinter-format text. They encode the *expected*
kernel behaviour of the real C workloads in ``bugzoo/`` and double as
regression fixtures once real QNX captures replace them.
"""

from __future__ import annotations

from .synth import TraceBuilder

DEADLINES_TOML = """\
fail_on = "high"

[deadlines.control]
budget_us = 1000
period_us = 10000

[deadlines.brake]
budget_us = 2000
period_us = 10000
"""


def z0_clean() -> str:
    """Infusion pump done right: a priority-inheriting mutex, short critical section."""
    b = TraceBuilder(name="z0_clean.kev")
    L, M, H = (100, 1), (100, 2), (100, 3)
    b.proc(0, 100, "infusion_pump")
    b.meta(0, 0, L, "logger", 10)
    b.meta(1, 0, M, "telemetry", 20)
    b.meta(2, 0, H, "control", 50)
    b.state(3, M, "NANOSLEEP")
    b.block(3, 0, "NANOSLEEP", next_key=L)
    for k in range(3):
        base = 1000 + k * 10_000
        b.run(base + 500, 0, H)
        b.user(base + 505, 0, "TL_JOB_START name=control")
        b.call(base + 505, 0, "SYNC_MUTEX_LOCK", sync="0x00008040", count=0)
        b.set_prio(L, 50)                                     # priority inheritance boost
        b.block(base + 505, 0, "MUTEX", next_key=L)          # L inherits prio 50, runs
        b.call(base + 700, 0, "SYNC_MUTEX_UNLOCK", sync="0x00008040")
        b.set_prio(L, 10)                                     # boost ends at unlock
        b.run(base + 701, 0, H)
        b.user(base + 800, 0, "TL_JOB_END name=control")
        b.block(base + 850, 0, "NANOSLEEP", next_key=M)
        b.block(base + 8850, 0, "NANOSLEEP", next_key=L)
    return b.text()


def z1_prio_inversion() -> str:
    """Infusion pump with a semaphore guarding the sensor buffer: no inheritance."""
    b = TraceBuilder(name="z1_prio_inversion.kev")
    L, M, H = (100, 1), (100, 2), (100, 3)
    b.proc(0, 100, "infusion_pump")
    b.meta(0, 0, L, "logger", 10)
    b.meta(1, 0, M, "telemetry", 20)
    b.meta(2, 0, H, "control", 50)
    b.state(3, M, "NANOSLEEP")
    b.block(3, 0, "NANOSLEEP", next_key=L)
    for k in range(3):
        base = 1000 + k * 10_000
        b.call(base + 100, 0, "SYNC_SEM_WAIT", sync="0x00008040")   # L takes the buffer
        b.run(base + 500, 0, H)                                            # control period fires
        b.user(base + 505, 0, "TL_JOB_START name=control")
        b.call(base + 505, 0, "SYNC_SEM_WAIT", sync="0x00008040")
        b.block(base + 505, 0, "SEM", next_key=M)                           # telemetry preempts logger
        b.block(base + 8505, 0, "NANOSLEEP", next_key=L)
        b.call(base + 8700, 0, "SYNC_SEM_POST", sync="0x00008040")
        b.run(base + 8701, 0, H)
        b.call(base + 8890, 0, "SYNC_SEM_POST", sync="0x00008040")
        b.user(base + 8900, 0, "TL_JOB_END name=control")
        b.block(base + 8950, 0, "NANOSLEEP", next_key=L)
    return b.text()


def z2_fixed_prio_channel() -> str:
    """Brake-by-wire: arbiter channel created with _NTO_CHF_FIXED_PRIORITY at low prio."""
    b = TraceBuilder(name="z2_fixed_prio_channel.kev")
    C, A, D = (210, 1), (220, 1), (230, 1)  # controller (60), arbiter (10), diagnostics (30)
    b.proc(0, 210, "brake_ctrl")
    b.proc(0, 220, "arbiter")
    b.proc(0, 230, "diagnostics")
    b.meta(0, 0, A, "arbiter", 10)
    b.set_prio(D, 30)
    b.set_prio(C, 60)
    b.call(1, 0, "CHANNEL_CREATE", flags="0x00000010")  # _NTO_CHF_FIXED_PRIORITY (verify value)
    b.block(1, 0, "RECEIVE", next_key=D)
    b.user(2, 0, "TL_META name=diagnostics")
    b.block(3, 0, "NANOSLEEP", next_key=C)
    b.user(3, 0, "TL_META name=brake_ctrl")
    b.call(4, 0, "CONNECT_ATTACH", nd=0, pid=220, chid=1, index=0, flags=0)
    b.ret(5, 0, "CONNECT_ATTACH", ret_val=3)
    b.block(6, 0, "NANOSLEEP")
    for k in range(3):
        base = 1000 + k * 10_000
        b.run(base, 0, C)
        b.user(base + 1, 0, "TL_JOB_START name=brake")
        b.call(base + 2, 0, "MSG_SENDV", coid="0x00000003", sparts=1, rparts=1)
        b.block(base + 2, 0, "SEND", next_key=A)       # arbiter (prio 10, fixed) receives
        b.ret(base + 3, 0, "MSG_RECEIVEV", ret_val=1)
        b.state(base + 3, C, "REPLY")
        b.run(base + 50, 0, D)                          # diagnostics (30) preempts arbiter (10)
        b.block(base + 6050, 0, "NANOSLEEP", next_key=A)
        b.call(base + 6200, 0, "MSG_REPLYV", rcvid=1, status=0)
        b.run(base + 6201, 0, C)
        b.user(base + 6250, 0, "TL_JOB_END name=brake")
        b.block(base + 6300, 0, "NANOSLEEP", next_key=A)
        b.block(base + 6301, 0, "RECEIVE")
    return b.text()


def lost_wakeup(signal_after_wait: bool = False) -> str:
    """memcached's logger_stop(), reduced to its kernel events (memcached/memcached#1348).

    The stopper signals a condition variable while the logger thread is still in its sleep, then joins it.
    The logger wakes later and waits on the condition variable; nothing signals it again, so both hang.
    With ``signal_after_wait`` the signal comes after the wait: the healthy ordering.
    """
    b = TraceBuilder(name="lost_wakeup.kev")
    S, L = (100, 1), (100, 2)
    cv = "0x00000051cd514018"
    b.proc(0, 100, "memd")
    b.meta(0, 0, S, "stopper", 10)
    b.meta(0, 1, L, "mc-log", 10)
    b.run(1000, 1, L)
    b.block(1100, 1, "NANOSLEEP")
    b.run(1500, 0, S)
    if not signal_after_wait:
        b.call(2000, 0, "SYNC_CONDVAR_SIGNAL", 83, sync=cv, all=0)
        b.ret(2001, 0, "SYNC_CONDVAR_SIG", 83, ret_val=0)
        b.call(2100, 0, "THREAD_JOIN", 50, tid=2)
        b.block(2101, 0, "JOIN")
    b.run(700_000, 1, L)
    b.call(700_010, 1, "SYNC_CONDVAR_WAIT", 82, sync=cv, mutex_p="0x00000051cd514020")
    b.block(700_011, 1, "CONDVAR")
    if signal_after_wait:
        b.run(800_000, 0, S)
        b.call(800_001, 0, "SYNC_CONDVAR_SIGNAL", 83, sync=cv, all=0)
        b.ret(800_002, 0, "SYNC_CONDVAR_SIG", 83, ret_val=0)
        b.run(800_003, 1, L)
        b.ret(800_004, 1, "SYNC_CONDVAR_WAIT", 82, ret_val=0)
        b.block(800_010, 1, "NANOSLEEP")
    b.user(3_000_000, 0, "TL_NOTE end")
    return b.text()


def stuck_job(finish: bool = False) -> str:
    """One job whose START is never followed by an END: the program hangs inside it (NNG's nng_close()).

    The worker waits on one condition variable and the main thread on another; nothing signals either.
    With ``finish`` the END marker arrives and nothing is wrong.
    """
    b = TraceBuilder(name="stuck_job.kev")
    M, W = (100, 1), (100, 2)
    b.proc(0, 100, "app")
    b.meta(0, 0, M, "main", 10)
    b.meta(0, 1, W, "worker", 10)
    b.run(1000, 0, M)
    b.user(1100, 0, "TL_JOB_START name=cycle")
    b.run(1200, 1, W)
    b.call(1300, 1, "SYNC_CONDVAR_WAIT", 82, sync="0x1000", mutex_p="0x1008")
    b.block(1301, 1, "CONDVAR")
    if finish:
        b.user(2000, 0, "TL_JOB_END name=cycle")
    b.call(2100, 0, "SYNC_CONDVAR_WAIT", 82, sync="0x2000", mutex_p="0x2008")
    b.block(2101, 0, "CONDVAR")
    b.user(3_000_000, 0, "TL_NOTE end")
    return b.text()


def z3_ipc_deadlock(resolve_after_us: float | None = 1_000_000) -> str:
    """Two sensor-fusion servers that MsgSend() to each other.

    Like the real workload, a 1 s TimerTimeout() breaks the deadlock; pass
    ``resolve_after_us=None`` for a deadlock that lasts to the end of the trace.
    """
    b = TraceBuilder(name="z3_ipc_deadlock.kev")
    A, B, W = (200, 1), (300, 1), (600, 1)
    b.proc(0, 200, "fusion_a")
    b.proc(0, 300, "fusion_b")
    b.proc(0, 600, "watchdog")
    b.meta(0, 0, A, "fusion_a", 30)
    b.meta(0, 1, B, "fusion_b", 30)
    b.call(10, 0, "CONNECT_ATTACH", nd=0, pid=300, chid=1, index=0, flags=0)
    b.ret(11, 0, "CONNECT_ATTACH", ret_val=3)
    b.call(10, 1, "CONNECT_ATTACH", nd=0, pid=200, chid=1, index=0, flags=0)
    b.ret(11, 1, "CONNECT_ATTACH", ret_val=3)
    # Normal operation: both sides serve each other.
    b.block(20, 0, "RECEIVE")
    b.block(20, 1, "RECEIVE")
    b.run(1000, 0, A)
    b.run(1000, 1, B)
    b.user(1000, 0, "TL_NOTE recalibrate from=fusion_a")
    b.user(1000, 1, "TL_NOTE recalibrate from=fusion_b")
    b.call(1001, 0, "TIMER_TIMEOUT", flags="0x00000006")
    b.call(1002, 0, "MSG_SENDV", coid="0x00000003", sparts=1, rparts=1)
    b.block(1002, 0, "SEND")
    b.call(1001, 1, "TIMER_TIMEOUT", flags="0x00000006")
    b.call(1002, 1, "MSG_SENDV", coid="0x00000003", sparts=1, rparts=1)
    b.block(1002, 1, "SEND")
    if resolve_after_us is None:
        b.meta(200_000, 0, W, "watchdog", 5)
        return b.text()
    t = 1002 + resolve_after_us
    b.run(t, 0, A)
    b.ret(t, 0, "MSG_SENDV", ret_val=-1, errno="ETIMEDOUT")
    b.run(t, 1, B)
    b.ret(t, 1, "MSG_SENDV", ret_val=-1, errno="ETIMEDOUT")
    b.block(t + 50, 0, "RECEIVE")
    b.block(t + 50, 1, "RECEIVE")
    b.meta(t + 200_000, 0, W, "watchdog", 5)
    return b.text()


def z4_mutex_contention() -> str:
    """Camera pipeline: workers serialize on one global mutex around a slow copy."""
    b = TraceBuilder(name="z4_mutex_contention.kev")
    W1, W2, W3, W4 = (400, 1), (400, 2), (400, 3), (400, 4)
    b.proc(0, 400, "camera_pipeline")
    b.meta(0, 0, W1, "worker1", 20)
    b.meta(1, 0, W3, "worker3", 20)
    b.state(2, W1, "NANOSLEEP")
    b.block(2, 0, "NANOSLEEP")
    b.meta(0, 1, W2, "worker2", 20)
    b.meta(1, 1, W4, "worker4", 20)
    b.state(2, W2, "NANOSLEEP")
    b.block(2, 1, "NANOSLEEP")
    for f in range(15):
        t0 = 100 + f * 4000
        b.run(t0, 0, W1)
        b.run(t0 + 100, 1, W2)
        b.call(t0 + 100, 1, "SYNC_MUTEX_LOCK", sync="0x00009000", count=0)
        b.block(t0 + 100, 1, "MUTEX")
        b.call(t0 + 1500, 0, "SYNC_MUTEX_UNLOCK", sync="0x00009000")
        b.run(t0 + 1501, 1, W2)
        b.block(t0 + 1510, 0, "NANOSLEEP", next_key=W3)
        b.call(t0 + 1520, 0, "SYNC_MUTEX_LOCK", sync="0x00009000", count=0)
        b.block(t0 + 1520, 0, "MUTEX")
        b.call(t0 + 3000, 1, "SYNC_MUTEX_UNLOCK", sync="0x00009000")
        b.run(t0 + 3001, 0, W3)
        b.block(t0 + 3010, 1, "NANOSLEEP")
        b.call(t0 + 3500, 0, "SYNC_MUTEX_UNLOCK", sync="0x00009000")
        b.block(t0 + 3510, 0, "NANOSLEEP")
    return b.text()


def z5_irq_overrun(work_us: list[int] | None = None) -> str:
    """Motor encoder: the interrupt service thread does heavy work before unmasking.

    ``work_us``: handler time per interrupt (default: ten interrupts of 2 ms each)."""
    work_us = work_us if work_us is not None else [2000] * 10
    b = TraceBuilder(name="z5_irq_overrun.kev")
    H = (500, 1)
    b.proc(0, 500, "motor_ctrl")
    b.meta(0, 0, H, "encoder_ist", 60)
    b.call(10, 0, "INTERRUPT_ATTACH_EVENT", intr=9, event_p="0x0804a000", flags=0)
    b.ret(11, 0, "INTERRUPT_ATTACH_EVENT", ret_val=1)
    b.call(20, 0, "INTERRUPT_WAIT", flags=0)
    b.block(20, 0, "INTR")
    for k, w in enumerate(work_us):
        t = 1000 + k * 5000
        b.irq(t, 0, 9)
        b.run(t + 30, 0, H)
        b.ret(t + 31, 0, "INTERRUPT_WAIT", ret_val=0)
        b.call(t + 31 + w, 0, "INTERRUPT_UNMASK", intr=9, id=1)
        b.call(t + 40 + w, 0, "INTERRUPT_WAIT", flags=0)
        b.block(t + 40 + w, 0, "INTR")
    return b.text()


SCENARIOS = {
    "z0_clean": z0_clean,
    "z1_prio_inversion": z1_prio_inversion,
    "z2_fixed_prio_channel": z2_fixed_prio_channel,
    "z3_ipc_deadlock": z3_ipc_deadlock,
    "z4_mutex_contention": z4_mutex_contention,
    "z5_irq_overrun": z5_irq_overrun,
}
