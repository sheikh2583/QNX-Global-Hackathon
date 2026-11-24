"""A job that started and never finished.

``deadline.py`` measures jobs that have both a ``TL_JOB_START`` and a ``TL_JOB_END`` marker. A program
that hangs inside a job emits the START and never the END, so it falls through that check. This
detector reports every declared job whose latest START has no END, once more than its budget has
passed since the START, up to the end of the trace.

It also writes down what every other thread of the same process was doing at the end: its state,
the condition variable it waits on, the thread it is joined to. For a hang that is the thread dump a
developer would otherwise have to attach a debugger to get.
"""

from __future__ import annotations

import re

from ..config import Config
from ..findings import Finding
from ..model.trace import TraceModel
from ._util import fmt_ms, ms

QNX_NOTE = ("Every thread of the process is listed with what it was blocked on when the trace ended. A "
            "cycle of CONDVAR and JOIN waits with no thread left running means each thread waits for "
            "another one to make progress: find which of them has to signal, complete or cancel first.")

_MARK = re.compile(r"TL_JOB_(START|END)\s+name=(\S+)")


def _snapshot(model: TraceModel, pid: int) -> list[dict]:
    out = []
    for th in sorted((t for t in model.threads.values() if t.pid == pid), key=lambda t: t.tid):
        if not th.intervals:
            continue
        iv = th.intervals[-1]
        row = {"thread": f"{model.label(th.key)}", "tid": th.tid, "state": iv.state,
               "since_ms": round(ms(iv.start - model.t_start), 1), "event": iv.event_id}
        if iv.state == "CONDVAR":
            c = model.last_call_before(th, iv.start, ("SYNC_CONDVAR_WAIT",))
            row["on"] = c.args.get("sync") if c else None
        elif iv.state == "JOIN":
            c = model.last_call_before(th, iv.start, ("THREAD_JOIN",))
            row["on"] = f"thread {c.arg_int('tid')}" if c else None
        out.append(row)
    return out


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    findings: list[Finding] = []
    for th in model.threads.values():
        state: dict[str, tuple] = {}  # job name -> its latest START event, or None once ended
        for e in th.user:
            m = _MARK.search(e.text or "")
            if not m or m.group(2) not in cfg.deadlines:
                continue
            state[m.group(2)] = e if m.group(1) == "START" else None
        for name, start in state.items():
            if start is None:
                continue
            budget = cfg.deadlines[name].budget_us * 1000
            stuck = model.t_end - start.t_ns
            if stuck <= budget:
                continue
            snap = _snapshot(model, th.pid)
            blocked = [r for r in snap if r["state"] in ("CONDVAR", "JOIN", "MUTEX", "SEM", "REPLY", "SEND")]
            lines = "; ".join(
                f"{r['thread']} {r['state']}" + (f" on {r['on']}" if r.get("on") else "") for r in blocked[:8])
            findings.append(Finding(
                kind="stuck_job",
                severity="critical",
                title=f"Job '{name}' started and never finished",
                summary=(f"'{name}' started on {model.label(th.key)} at {fmt_ms(start.t_ns - model.t_start)} and had "
                         f"not finished {fmt_ms(stuck)} later, until the end of the trace (budget "
                         f"{fmt_ms(budget)}). The process's threads were blocked: {lines}."),
                t_start=start.t_ns,
                t_end=model.t_end,
                threads=[model.label(th.key)],
                evidence=[start.id] + [r["event"] for r in blocked[:8]],
                metrics={"job": name, "stuck_ms": round(ms(stuck), 3), "budget_ms": round(ms(budget), 3),
                         "blocked_threads": len(blocked), "threads": len(snap), "waiting": lines},
                qnx_note=QNX_NOTE,
            ))
    return findings
