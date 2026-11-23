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
import math

from ..config import Config
from ..events import parse_kv
from ..findings import Finding
from ..model.trace import TraceModel
from ._util import fmt_ms, ms, percentile


def _releases(items: list, period: int | None, markers: list) -> list[int]:
    """Release time of each job.

    1. ``TL_RELEASE name=<job>`` markers, when the workload emits them (exact).
    2. Otherwise a period grid fitted to the data: ``release_k = a + k * p``. The configured period
       numbers the jobs (k); the effective period p is the Theil-Sen slope of start times over k
       (robust to late outliers), and a is the lower envelope, so the earliest starts sit on the
       grid. Fitting p matters on real targets: the trace clock and the workload's clock drift
       apart (0.05% on QEMU/KVM, i.e. ~1 ms over 200 periods), and a rigid grid turns that drift
       into false deadline misses. Delay before TL_JOB_START still shows as release jitter.
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

    def fit(ks):
        p = _theil_sen(ks, starts) or period
        return p if 0.9 * period <= p <= 1.1 * period else period  # implausible fit: configured period

    # Number the jobs. Rounding alone puts a job that starts more than half a period late into the
    # next period, and the lower envelope then drags the whole grid early (found on real QNX: one
    # 5.3 ms late wake-up turned into 199/200 false misses). A job never starts before its release,
    # so floor each start relative to the typical (median) phase instead: correct for lateness up
    # to 80% of a period.
    ks = [round((st - s0) / period) for st in starts]
    p = fit(ks)
    phase = sorted(st - s0 - k * p for k, st in zip(ks, starts, strict=False))[len(starts) // 2]
    ks = [math.floor((st - s0 - phase + 0.2 * p) / p) for st in starts]
    p = fit(ks)
    a = min(st - k * p for k, st in zip(ks, starts, strict=False))
    return [int(a + k * p) for k in ks]


def _theil_sen(xs: list[int], ys: list[int], max_points: int = 400) -> float | None:
    """Median of pairwise slopes; robust to a minority of outliers (late jobs)."""
    n = len(xs)
    if n < 3:
        return None
    step = max(1, n // max_points)
    pts = list(zip(xs, ys, strict=False))[::step]
    slopes = sorted((y2 - y1) / (x2 - x1) for i, (x1, y1) in enumerate(pts)
                    for x2, y2 in pts[i + 1:] if x2 != x1)
    return slopes[len(slopes) // 2] if slopes else None


def _jobs(model: TraceModel) -> tuple[dict[str, list], dict[str, list]]:
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
                open_jobs[(name, th.key)] = e
            elif (name, th.key) in open_jobs:
                start = open_jobs.pop((name, th.key))
                jobs.setdefault(name, []).append((start, e))
    return jobs, releases


def _stream_releases(items: list, period: int | None, markers: list) -> list[int]:
    """Releases per job stream. Several threads can run the same job name (Z4's four workers, each
    with its own phase); every (name, thread) stream gets its own grid, then results are merged
    back in the order of ``items``. One grid over interleaved streams is wrong (seen on QNX)."""
    by_thread: dict = {}
    for i, (start, _) in enumerate(items):
        by_thread.setdefault(start.key, []).append(i)
    out = [0] * len(items)
    for key, idx in by_thread.items():
        mk = [e for e in markers if e.key == key] or ([] if len(by_thread) > 1 else markers)
        rel = _releases([items[i] for i in idx], period, mk)
        for i, r in zip(idx, rel, strict=False):
            out[i] = r
    return out


def response_streams(model: TraceModel, cfg: Config) -> dict[str, dict[str, list[int]]]:
    """Per declared deadline, per job stream: each job's response time in ns, measured from release.

    A "stream" is the thread that ran the job. Several threads can serve one deadline name (Z4's
    four tile workers all emit ``frame``), and each has its own phase and its own release grid, so
    the regression gate can see one worker slow down while the pooled distribution barely moves.
    Shares ``_jobs`` and ``_stream_releases`` with :func:`responses`, which pools the streams.
    """
    jobs, releases = _jobs(model)
    out: dict[str, dict[str, list[int]]] = {}
    for name, dl in cfg.deadlines.items():
        items = sorted(jobs.get(name, []), key=lambda x: x[0].t_ns)
        if not items:
            continue
        period = int(dl.period_us * 1000) if dl.period_us else None
        rel = _stream_releases(items, period, releases.get(name, []))
        per: dict[str, list[int]] = {}
        for (start, end), r in zip(items, rel, strict=True):
            per.setdefault(model.label(start.key), []).append(end.t_ns - r)
        out[name] = per
    return out


def responses(model: TraceModel, cfg: Config) -> dict[str, list[int]]:
    """Per declared deadline: each job's response time in ns, measured from its release."""
    jobs, releases = _jobs(model)
    out: dict[str, list[int]] = {}
    for name, dl in cfg.deadlines.items():
        items = sorted(jobs.get(name, []), key=lambda x: x[0].t_ns)
        if not items:
            continue
        period = int(dl.period_us * 1000) if dl.period_us else None
        rel = _stream_releases(items, period, releases.get(name, []))
        out[name] = [end.t_ns - r for (_, end), r in zip(items, rel, strict=False)]
    return out


SLEEP_STATES = {"NANOSLEEP", "SIGWAITINFO", "INTR", "RECEIVE", "CONDVAR", "SEM"}


def _idle(model: TraceModel, key) -> bool:
    th = model.threads.get(key)
    name = (th.kernel_name or th.name or "") if th else ""
    return name.startswith("idle") or (th is not None and th.prio == 0 and key[0] == 1)


def _breakdown(model: TraceModel, job_key, release: int, end: int) -> dict[str, int]:
    """Where a job's response time went, from release to TL_JOB_END."""
    out = {"late_wakeup": 0, "ready": 0, "blocked": 0, "running": 0, "late_wakeup_cpu_free": 0}
    th = model.threads.get(job_key)
    if th is None:
        return out
    for iv in th.intervals:
        if iv.end <= release or iv.start >= end:
            continue
        a, b = max(iv.start, release), min(iv.end, end)
        if iv.state == "RUNNING":
            out["running"] += b - a
        elif iv.state == "READY":
            out["ready"] += b - a
        elif iv.state in ("NANOSLEEP",) or (iv.state in SLEEP_STATES and iv.start < release):
            out["late_wakeup"] += b - a
            cpu = iv.cpu
            mine = th.prio_at(a) if th.prio_at(a) is not None else th.prio
            # While it overslept, was its CPU held only by threads that cannot delay its wake-up
            # (idle, or lower priority: they are preempted the moment the timer fires)? Then the
            # lateness is the platform's timer path, not the application. Real QNX/QEMU: a 5.3 ms
            # late wake-up of a prio-60 thread while a prio-30 thread ran and the kernel's
            # clock thread itself was stalled.
            for k, other in model.threads.items():
                for o in other.intervals:
                    if o.state != "RUNNING" or o.cpu != cpu or o.end <= a or o.start >= b:
                        continue
                    op = other.prio_at(o.start)
                    op = other.prio if op is None else op
                    if _idle(model, k) or (mine is not None and op is not None and op < mine):
                        out["late_wakeup_cpu_free"] += min(o.end, b) - max(o.start, a)
        else:
            out["blocked"] += b - a
    return out


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    if not cfg.deadlines:
        return []
    jobs, releases = _jobs(model)
    findings = []
    for name, dl in cfg.deadlines.items():
        items = sorted(jobs.get(name, []), key=lambda x: x[0].t_ns)
        if not items:
            continue
        budget = dl.budget_us * 1000
        period = int(dl.period_us * 1000) if dl.period_us else None
        rel = _stream_releases(items, period, releases.get(name, []))
        resp = [end.t_ns - r for (_, end), r in zip(items, rel, strict=False)]
        jitter = [start.t_ns - r for (start, _), r in zip(items, rel, strict=False)]
        misses = [i for i, r in enumerate(resp) if r > budget]
        overruns = sum(1 for r in resp if period and r > period)
        skipped = 0
        if period:
            for key in {s.key for s, _ in items}:  # per stream: a period with no job from that thread
                rs = sorted(r for (s, _), r in zip(items, rel, strict=False) if s.key == key)
                if len(rs) > 1:
                    slots = {round((r - rs[0]) / period) for r in rs}
                    skipped += (max(slots) - min(slots) + 1) - len(slots)
        if not misses and not skipped:
            continue
        w = max(range(len(items)), key=lambda i: resp[i])
        worst_ns = resp[w]
        rate = len(misses) / len(items)
        # Why was each late job late? A late wake-up while nothing of equal or higher priority held
        # the CPU is platform timer latency (seen on QEMU/KVM: ~1.3 ms, about 1 in 200 periods,
        # and rare multi-ms host stalls), not the application.
        parts = [_breakdown(model, items[i][0].key, rel[i], items[i][1].t_ns) for i in misses]
        platform = [p for p in parts if p["late_wakeup"] > 0 and
                    p["late_wakeup"] >= 0.5 * sum(p[k] for k in ("late_wakeup", "ready", "blocked", "running"))
                    and p["late_wakeup_cpu_free"] >= 0.5 * p["late_wakeup"]]
        platform_only = bool(misses) and len(platform) == len(misses) and not skipped
        # Real QNX/QEMU: a reference build missed a 4 ms budget by 94 us in 1 of 800 jobs. Report
        # it, but a rare, small overshoot is not the same defect as a systematic miss.
        th = cfg.thresholds
        marginal = (not platform_only and not skipped and rate < th.deadline_marginal_rate
                    and worst_ns <= budget * (1 + th.deadline_marginal_overshoot))
        wb = _breakdown(model, items[w][0].key, rel[w], items[w][1].t_ns)
        extra = []
        if period:
            extra.append(f"p99 release jitter {fmt_ms(percentile(jitter, 99))}")
        if overruns:
            extra.append(f"{overruns} ran into the next period")
        if skipped:
            extra.append(f"{skipped} periods had no job at all")
        extra.append(f"worst job: {fmt_ms(wb['late_wakeup'])} late wake-up, {fmt_ms(wb['ready'])} waiting for "
                     f"the CPU, {fmt_ms(wb['blocked'])} blocked, {fmt_ms(wb['running'])} running")
        if platform_only:
            extra.append("every miss was a late wake-up while nothing of equal or higher priority held the "
                         "CPU: platform timer latency "
                         "(e.g. virtualization), not this program; confirm with `tracelens compare` over several runs")
        if marginal:
            extra.append(f"marginal: under {th.deadline_marginal_rate:.0%} of jobs and within "
                         f"{th.deadline_marginal_overshoot:.0%} of the budget (set deadline_marginal_rate = 0 "
                         f"to treat every miss as HIGH)")
        findings.append(Finding(
            kind="deadline_miss",
            severity="medium" if platform_only or marginal else ("critical" if rate >= 0.5 or skipped else "high"),
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
                "misses_from_platform_latency": len(platform),
                "worst_late_wakeup_ms": round(ms(wb["late_wakeup"]), 3),
                "worst_ready_ms": round(ms(wb["ready"]), 3),
                "worst_blocked_ms": round(ms(wb["blocked"]), 3),
                "worst_running_ms": round(ms(wb["running"]), 3),
                "release_source": "TL_RELEASE" if releases.get(name) else ("period grid" if period else "job start"),
            },
            qnx_note=("Response measured from the job's release (TL_RELEASE marker or the period grid) to "
                      "TL_JOB_END, so wake-up latency before the job starts counts against the budget."),
        ))
    return findings
