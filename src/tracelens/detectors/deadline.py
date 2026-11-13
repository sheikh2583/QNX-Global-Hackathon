"""Deadline misses, measured from TraceLens job markers.

Workloads emit user string events (QNX ``TraceEvent()`` with
``_NTO_TRACE_INSERTUSRSTREVENT``)::

    TL_JOB_START name=control
    TL_JOB_END   name=control

and ``tracelens.toml`` declares ``[deadlines.control] budget_us = 1000, period_us = 10000``.
An optional ``TL_RELEASE name=control`` marker pins the release time exactly.
"""

from __future__ import annotations

import bisect

from ..config import Config
from ..events import parse_kv
from ..findings import Finding
from ..model.trace import TraceModel
from ._util import fmt_ms, ms, percentile


def _releases(items: list, period: int | None, markers: list) -> list[int]:
    """Release time of each job.

    1. ``TL_RELEASE name=<job>`` markers, when the workload emits them (exact).
    2. Otherwise the period grid: releases are ``anchor + k * period``, anchored at the earliest
       start phase seen (so delay before TL_JOB_START, i.e. release jitter, becomes visible).
    3. Without a period, the job's own start marker.
    """
    starts = [s.t_ns for s, _ in items]
    if markers:
        times = sorted(e.t_ns for e in markers)
        out = []
        for st in starts:
            i = bisect.bisect_right(times, st) - 1
            out.append(times[i] if i >= 0 else st)
        return out
    if not period:
        return starts
    s0 = starts[0]
    phase = min((st - s0) % period for st in starts)
    return [s0 + phase + ((st - s0 - phase) // period) * period for st in starts]


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    if not cfg.deadlines:
        return []
    jobs: dict[str, list] = {}
    releases: dict[str, list] = {}
    open_jobs: dict[str, object] = {}
    for th in model.threads.values():
        for e in th.user:
            if not e.text.startswith(("TL_JOB_START", "TL_JOB_END", "TL_RELEASE")):
                continue
            name = parse_kv(e.text).get("name") or model.label(th.key)
            if e.text.startswith("TL_RELEASE"):
                releases.setdefault(name, []).append(e)
            elif e.text.startswith("TL_JOB_START"):
                open_jobs[name] = e
            elif name in open_jobs:
                start = open_jobs.pop(name)
                jobs.setdefault(name, []).append((start, e))

    findings = []
    for name, dl in cfg.deadlines.items():
        items = sorted(jobs.get(name, []), key=lambda x: x[0].t_ns)
        if not items:
            continue
        budget = dl.budget_us * 1000
        period = int(dl.period_us * 1000) if dl.period_us else None
        rel = _releases(items, period, releases.get(name, []))
        resp = [end.t_ns - r for (_, end), r in zip(items, rel)]
        jitter = [start.t_ns - r for (start, _), r in zip(items, rel)]
        misses = [i for i, r in enumerate(resp) if r > budget]
        overruns = sum(1 for r in resp if period and r > period)
        skipped = 0
        if period and len(rel) > 1:
            slots = {round((r - rel[0]) / period) for r in rel}
            skipped = (max(slots) - min(slots) + 1) - len(slots)
        if not misses and not skipped:
            continue
        w = max(range(len(items)), key=lambda i: resp[i])
        worst_ns = resp[w]
        rate = len(misses) / len(items)
        extra = []
        if period:
            extra.append(f"p99 release jitter {fmt_ms(percentile(jitter, 99))}")
        if overruns:
            extra.append(f"{overruns} ran into the next period")
        if skipped:
            extra.append(f"{skipped} periods had no job at all")
        findings.append(Finding(
            kind="deadline_miss",
            severity="critical" if rate >= 0.5 or skipped else "high",
            title=f"Deadline misses in '{name}'",
            summary=(f"'{name}' missed its {dl.budget_us:.0f} us budget in {len(misses)} of "
                     f"{len(items)} jobs (measured from release); worst response {fmt_ms(worst_ns)} "
                     f"({worst_ns / budget:.1f}x budget)" + ("; " + ", ".join(extra) if extra else "") + "."),
            t_start=rel[w],
            t_end=items[w][1].t_ns,
            threads=[name],
            evidence=[items[w][0].id, items[w][1].id],
            metrics={
                "jobs": len(items),
                "misses": len(misses),
                "miss_rate": round(rate, 3),
                "budget_ms": round(budget / 1e6, 3),
                "period_ms": round(period / 1e6, 3) if period else "",
                "p99_response_ms": round(ms(percentile(resp, 99)), 3),
                "worst_response_ms": round(ms(worst_ns), 3),
                "p99_release_jitter_ms": round(ms(percentile(jitter, 99)), 3),
                "overruns": overruns,
                "skipped_periods": skipped,
                "release_source": "TL_RELEASE" if releases.get(name) else ("period grid" if period else "job start"),
            },
            qnx_note=("Response measured from the job's release (TL_RELEASE marker or the period grid) to "
                      "TL_JOB_END, so wake-up latency before the job starts counts against the budget."),
        ))
    return findings
