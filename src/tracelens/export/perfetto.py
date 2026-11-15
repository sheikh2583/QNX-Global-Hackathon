"""Export a trace (and its findings) as Chrome Trace Event JSON for ui.perfetto.dev.

Layout in Perfetto:
  * one process per QNX process, one track per thread, a slice per thread state
    (RUNNING, READY, SEM, MUTEX, SEND, REPLY, INTR ...);
  * TraceLens markers (TL_JOB_START/END, TL_RELEASE, notes) and kernel calls as
    instant events on the thread that issued them;
  * interrupts as instants on a per-CPU "IRQs" track;
  * a "TraceLens findings" process with one slice per finding over its time window,
    carrying severity, summary, metrics and evidence event IDs as args.
Open the file at https://ui.perfetto.dev (Open trace file); nothing is uploaded.
"""

from __future__ import annotations

import json

from .. import __version__
from ..analyze import Analysis

FINDINGS_PID = 0x7FFF0000
IRQ_PID = 0x7FFF0001
IDLE_STATES = {"DEAD"}


def _us(ns: int) -> float:
    return ns / 1000.0


def to_chrome_trace(a: Analysis, include_calls: bool = True) -> dict:
    m = a.model
    t0 = m.t_start
    ev: list[dict] = []

    def meta(pid: int, tid: int | None, kind: str, name: str) -> None:
        e = {"ph": "M", "pid": pid, "name": kind, "args": {"name": name}}
        if tid is not None:
            e["tid"] = tid
        ev.append(e)

    for pid in sorted({k[0] for k in m.threads}):
        meta(pid, None, "process_name", m.proc_names.get(pid, f"pid {pid}"))
    for key, th in sorted(m.threads.items()):
        meta(key[0], key[1], "thread_name", m.describe(key))
        for iv in th.intervals:
            if iv.state in IDLE_STATES or iv.duration <= 0:
                continue
            ev.append({"ph": "X", "pid": key[0], "tid": key[1], "name": iv.state, "cat": "state",
                       "ts": _us(iv.start - t0), "dur": _us(iv.duration),
                       "args": {"event": iv.event_id, "cpu": iv.cpu,
                                "prio": th.prio_at(iv.start)}})
        for e in th.user:
            ev.append({"ph": "i", "s": "t", "pid": key[0], "tid": key[1], "name": e.text or e.kind,
                       "cat": "marker", "ts": _us(e.t_ns - t0), "args": {"event": e.id}})
        if include_calls:
            for e in th.calls:
                ev.append({"ph": "i", "s": "t", "pid": key[0], "tid": key[1], "name": e.kind,
                           "cat": "kernel_call", "ts": _us(e.t_ns - t0),
                           "args": {"event": e.id, **dict(e.args.items())}})

    if m.irq_entries:
        meta(IRQ_PID, None, "process_name", "IRQs")
        for cpu in sorted({e.cpu for e in m.irq_entries}):
            meta(IRQ_PID, cpu + 1, "thread_name", f"CPU {cpu}")
        for e in m.irq_entries:
            ev.append({"ph": "i", "s": "t", "pid": IRQ_PID, "tid": e.cpu + 1, "name": f"IRQ {e.kind}",
                       "cat": "irq", "ts": _us(e.t_ns - t0), "args": {"event": e.id}})

    if a.findings:
        meta(FINDINGS_PID, None, "process_name", "TraceLens findings")
        for i, f in enumerate(a.findings, start=1):
            meta(FINDINGS_PID, i, "thread_name", f"{f.id} [{f.severity}]")
            ev.append({"ph": "X", "pid": FINDINGS_PID, "tid": i, "name": f"{f.id} {f.title}",
                       "cat": "finding", "ts": _us(f.t_start - t0), "dur": max(_us(f.t_end - f.t_start), 1.0),
                       "args": {"severity": f.severity, "summary": f.summary, "kind": f.kind,
                                "evidence_events": f.evidence, "metrics": f.metrics,
                                "qnx_note": f.qnx_note}})

    return {"traceEvents": ev, "displayTimeUnit": "ns",
            "metadata": {"tool": f"tracelens {__version__}", "source": m.trace.source,
                         "cycles_per_sec": m.trace.cycles_per_sec}}


def dumps(a: Analysis, include_calls: bool = True) -> str:
    return json.dumps(to_chrome_trace(a, include_calls), separators=(",", ":"))
