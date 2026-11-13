"""Deadline misses, measured from TraceLens job markers.

Workloads emit user string events (QNX ``TraceEvent()`` with
``_NTO_TRACE_INSERTUSRSTREVENT``)::

    TL_JOB_START name=control
    TL_JOB_END   name=control

and ``tracelens.toml`` declares ``[deadlines.control] budget_us = 1000``.
"""

from __future__ import annotations

from ..config import Config
from ..events import parse_kv
from ..findings import Finding
from ..model.trace import TraceModel
from ._util import fmt_ms, ms, percentile


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    if not cfg.deadlines:
        return []
    jobs: dict[str, list] = {}
    open_jobs: dict[str, object] = {}
    for th in model.threads.values():
        for e in th.user:
            if not e.text.startswith(("TL_JOB_START", "TL_JOB_END")):
                continue
            name = parse_kv(e.text).get("name") or model.label(th.key)
            if e.text.startswith("TL_JOB_START"):
                open_jobs[name] = e
            elif name in open_jobs:
                start = open_jobs.pop(name)
                jobs.setdefault(name, []).append((start, e))

    findings = []
    for name, dl in cfg.deadlines.items():
        items = jobs.get(name, [])
        if not items:
            continue
        budget = dl.budget_us * 1000
        resp = [end.t_ns - start.t_ns for start, end in items]
        misses = [(s, e) for (s, e), r in zip(items, resp) if r > budget]
        if not misses:
            continue
        worst = max(items, key=lambda x: x[1].t_ns - x[0].t_ns)
        worst_ns = worst[1].t_ns - worst[0].t_ns
        rate = len(misses) / len(items)
        findings.append(Finding(
            kind="deadline_miss",
            severity="critical" if rate >= 0.5 else "high",
            title=f"Deadline misses in '{name}'",
            summary=(f"'{name}' missed its {dl.budget_us:.0f} us budget in {len(misses)} of "
                     f"{len(items)} jobs; worst response {fmt_ms(worst_ns)} "
                     f"({worst_ns / budget:.1f}x budget)."),
            t_start=worst[0].t_ns,
            t_end=worst[1].t_ns,
            threads=[name],
            evidence=[worst[0].id, worst[1].id],
            metrics={
                "jobs": len(items),
                "misses": len(misses),
                "miss_rate": round(rate, 3),
                "budget_ms": round(budget / 1e6, 3),
                "p99_response_ms": round(ms(percentile(resp, 99)), 3),
                "worst_response_ms": round(ms(worst_ns), 3),
            },
            qnx_note="Deadline measured from TraceEvent() job markers emitted by the workload.",
        ))
    return findings
