"""Lost wake-ups: a condition-variable signal that woke nobody, then a wait that never ends.

``pthread_cond_signal()`` only wakes a thread that is already waiting; if no thread waits, the signal
is dropped. A waiter that checks its condition, then waits *without re-checking under the lock* can
therefore sleep forever once the signal has come and gone.

The rule reads four kinds of kernel event and nothing else:

* a ``SYNC_CONDVAR_SIGNAL`` on condition variable ``S`` while no thread was in CONDVAR state on ``S``
  (the signal woke nobody),
* a later ``SYNC_CONDVAR_WAIT`` on the same ``S`` that stays blocked for at least ``lost_wakeup_min_stuck_us``,
* no signal on ``S`` at all after that wait began (so nothing could have woken it),
* another thread of the same process in JOIN state on the waiter (``THREAD_JOIN tid``) from before the wait
  ended: somebody is waiting for the stuck thread, so the program is hung, not idle.

The wait may end with the trace or with the process being torn down (a watchdog killing a hung program).

Without the last condition the same pattern is an idle worker that parked after its last item, which is
normal, so it is not reported.
"""

from __future__ import annotations

from collections import defaultdict

from ..config import Config
from ..findings import Finding
from ..model.trace import TraceModel
from ._util import fmt_ms, ms

QNX_NOTE = ("pthread_cond_signal() wakes a thread that is already waiting; with no waiter the signal is "
            "lost. Wait in a loop that re-checks the condition while holding the mutex (the thread that "
            "sets the condition must also hold the mutex), and test the stop flag before every wait.")


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    min_ns = int(cfg.thresholds.lost_wakeup_min_stuck_us * 1000)
    signals: dict[str, list] = defaultdict(list)  # sync address -> SYNC_CONDVAR_SIGNAL call events
    waits = []  # (thread, interval, wait call, sync)
    for th in model.threads.values():
        for e in th.calls:
            if e.kind == "SYNC_CONDVAR_SIGNAL" and e.args.get("sync"):
                signals[e.args["sync"]].append(e)
        for iv in th.intervals:
            if iv.state != "CONDVAR":
                continue
            call = model.last_call_before(th, iv.start, ("SYNC_CONDVAR_WAIT",))
            if call is not None and call.args.get("sync"):
                waits.append((th, iv, call, call.args["sync"]))

    findings: list[Finding] = []
    for th, iv, call, sync in waits:
        if iv.duration < min_ns:
            continue
        sigs = sorted(signals.get(sync, ()), key=lambda e: e.t_ns)
        if not sigs or sigs[-1].t_ns > iv.start:
            continue  # signalled again after the wait began: the waiter was not left behind
        last = sigs[-1]
        if any(o_iv.start <= last.t_ns < o_iv.end and o_call.args.get("sync") == sync and o_iv is not iv
               for _o, o_iv, o_call, _s in waits):
            continue  # somebody was waiting when it fired: the signal was not lost
        joiner = None
        for other in model.threads.values():
            if other.pid != th.pid or other.tid == th.tid:
                continue
            for jv in other.intervals:
                if jv.state != "JOIN" or jv.start > iv.end or jv.end < iv.end - 1_000_000:
                    continue  # the joiner must still be joined on the waiter when the wait ends
                jc = model.last_call_before(other, jv.start, ("THREAD_JOIN",))
                if jc is not None and jc.arg_int("tid") == th.tid:
                    joiner = (other, jv, jc)
        if joiner is None:
            continue
        other, jv, jc = joiner
        stuck = iv.duration
        until = "until the end of the trace" if iv.end >= model.t_end - 1_000_000 else "until the process was torn down"
        findings.append(Finding(
            kind="lost_wakeup",
            severity="high",
            title=f"Lost wake-up: {model.label(th.key)} waits on a signal that already came",
            summary=(f"{model.label(other.key)} signalled condition variable {sync} at "
                     f"{fmt_ms(last.t_ns - model.t_start)} when no thread was waiting on it, then "
                     f"joined {model.label(th.key)}. {model.label(th.key)} only began its wait "
                     f"{fmt_ms(iv.start - last.t_ns)} later and was still blocked "
                     f"{fmt_ms(stuck)} on, {until}, with no further signal: "
                     "the program is hung."),
            t_start=last.t_ns,
            t_end=iv.end,
            threads=[model.label(other.key), model.label(th.key)],
            evidence=[last.id, call.id, iv.event_id, jc.id, jv.event_id],
            metrics={"condvar": sync, "signal_to_wait_ms": round(ms(iv.start - last.t_ns), 3),
                     "stuck_ms": round(ms(stuck), 3), "waiter": model.label(th.key),
                     "signaller": model.label(other.key)},
            qnx_note=QNX_NOTE,
        ))
    return findings
