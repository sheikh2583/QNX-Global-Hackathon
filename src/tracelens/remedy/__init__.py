"""Deterministic remedies: from a finding proven in the trace to a QNX-specific source change.

``plan(findings, sources)`` returns one ``Remedy`` per root cause, applying the automatic ones
in order to a working copy of the sources (each rule sees the previous rules' edits), and the
final sources. No model, no network: the same trace and source always give the same patch.
"""

from __future__ import annotations

from ..findings import SEVERITY_RANK, Finding
from .rules import RULES, Remedy

CAUSES = {"priority_inversion", "ipc_deadlock", "mutex_contention", "irq_handler_overrun"}
SYMPTOMS = {"deadline_miss", "irq_latency"}


def plan(findings: list[Finding], sources: dict[str, str]) -> tuple[list[Remedy], dict[str, str]]:
    current = dict(sources)
    remedies: list[Remedy] = []
    seen: set[tuple[str, str]] = set()
    ordered = sorted(findings, key=lambda f: -SEVERITY_RANK.get(f.severity, 0))
    for f in ordered:
        for rule in RULES:
            r = rule(f, current)
            if r is None:
                continue
            key = (r.rule, f.kind)
            if key in seen:
                break
            seen.add(key)
            remedies.append(r)
            if r.automatic:
                current.update(r.changes)
            break
    causes = {f.kind for f in findings} & CAUSES
    for f in ordered:
        if f.kind in SYMPTOMS and ("symptom", f.kind) not in seen:
            seen.add(("symptom", f.kind))
            remedies.append(_symptom(f, causes))
    return remedies, current


def _symptom(f: Finding, causes: set[str]) -> Remedy:
    r = Remedy("symptom", f.id, f.kind, f"{f.title}: a symptom", False, "")
    if causes:
        r.rationale = (f"{f.kind.replace('_', ' ')} is the visible effect; the trace also shows its cause "
                       f"({', '.join(sorted(causes))}). It is expected to clear with that fix, and the "
                       "re-trace checks that it does.")
    else:
        m = f.metrics
        parts = {k: m.get(f"worst_{k}_ms") for k in ("late_wakeup", "ready", "blocked", "running")}
        top = max((k for k in parts if parts[k] is not None), key=lambda k: parts[k], default=None)
        advice = {
            "late_wakeup": "the thread woke late: check timer resolution (QNX 8.0 fires timers on 1 ms "
                           "ticks) and whether its release is closer than a tick to another thread's",
            "ready": "the thread was ready but another thread had the CPU: raise its priority or move the "
                     "competing work to another CPU",
            "blocked": "the thread was blocked: find what it waits on (mutex, semaphore, message) in the "
                       "evidence events",
            "running": "the job itself runs too long: shorten the work or raise the budget",
        }
        r.rationale = f"No root-cause detector fired. The worst job's time went mostly to {top}: " \
                      f"{advice.get(top, 'see the breakdown')}." if top else "See the late-job breakdown."
        r.guidance.append(f.summary)
    return r


__all__ = ["Remedy", "plan"]
