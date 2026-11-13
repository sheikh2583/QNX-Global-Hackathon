"""Query functions behind the MCP server (and usable from Python directly).

Each returns plain JSON-able data. Analyses are cached per (trace, mtime, config),
so an assistant can ask many questions about one trace cheaply.
"""

from __future__ import annotations

import os
from pathlib import Path

from .analyze import Analysis, analyze_file
from .config import load_config
from .model.trace import BLOCKED_STATES

_CACHE: dict[tuple, Analysis] = {}
MAX_ROWS = 200


def _analysis(trace_path: str, config_path: str | None = None) -> Analysis:
    p = Path(trace_path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"no such trace: {p}")
    cfg_m = os.path.getmtime(config_path) if config_path else None
    key = (str(p.resolve()), p.stat().st_mtime, config_path, cfg_m)
    if key not in _CACHE:
        _CACHE[key] = analyze_file(p, load_config(config_path))
    return _CACHE[key]


def _finding_row(f) -> dict:
    return {"id": f.id, "kind": f.kind, "severity": f.severity, "title": f.title, "summary": f.summary,
            "t_start_ms": round(f.t_start / 1e6, 3), "t_end_ms": round(f.t_end / 1e6, 3),
            "metrics": f.metrics}


def analyze_trace(trace_path: str, config_path: str | None = None) -> dict:
    a = _analysis(trace_path, config_path)
    m = a.model
    return {
        "trace": m.trace.source,
        "events": len(m.events),
        "threads": len(m.threads),
        "duration_ms": round((m.t_end - m.t_start) / 1e6, 3),
        "lossy": m.lossy,
        "integrity_issues": m.integrity,
        "parse_notes": m.trace.issues,
        "findings": [_finding_row(f) for f in a.findings],
        "detector_errors": a.errors,
    }


def get_finding(trace_path: str, finding_id: str, config_path: str | None = None) -> dict:
    a = _analysis(trace_path, config_path)
    f = next((f for f in a.findings if f.id == finding_id), None)
    if f is None:
        raise KeyError(f"no finding {finding_id}; known: {[x.id for x in a.findings]}")
    m = a.model
    evidence = [{"event": e.id, "line": e.line, "t_ms": round((e.t_ns - m.t_start) / 1e6, 6), "cpu": e.cpu,
                 "thread": m.describe(e.key) if e.key else None, "raw": e.raw}
                for i in f.evidence if (e := m.by_id.get(i)) is not None]
    return {**_finding_row(f), "threads": f.threads, "qnx_note": f.qnx_note, "evidence": evidence}


def list_threads(trace_path: str) -> list[dict]:
    m = _analysis(trace_path).model
    span = max(1, m.t_end - m.t_start)
    rows = []
    for key, th in sorted(m.threads.items()):
        rows.append({
            "thread": m.label(key), "pid": key[0], "tid": key[1],
            "base_prio": th.prio, "prio_source": th.prio_source,
            "prio_changes": max(0, len(th.prio_hist) - 1), "cpus": sorted(th.cpus),
            "running_pct": round(100 * m.overlap(th, {"RUNNING"}, m.t_start, m.t_end) / span, 2),
            "ready_pct": round(100 * m.overlap(th, {"READY"}, m.t_start, m.t_end) / span, 2),
            "blocked_pct": round(100 * m.overlap(th, BLOCKED_STATES, m.t_start, m.t_end) / span, 2),
        })
    return rows


def _resolve_thread(m, thread: str):
    for key, th in m.threads.items():
        if thread in (m.label(key), f"{key[0]}/{key[1]}", f"{key[0]}:{key[1]}"):
            return th
    raise KeyError(f"no thread {thread!r}; use a name from list_threads or 'pid/tid'")


def thread_states(trace_path: str, thread: str, start_ms: float = 0, end_ms: float | None = None) -> list[dict]:
    m = _analysis(trace_path).model
    th = _resolve_thread(m, thread)
    a = m.t_start + int(start_ms * 1e6)
    b = m.t_end if end_ms is None else m.t_start + int(end_ms * 1e6)
    rows = []
    for iv in th.intervals:
        if iv.end <= a or iv.start >= b:
            continue
        rows.append({"state": iv.state, "start_ms": round((iv.start - m.t_start) / 1e6, 6),
                     "dur_ms": round(iv.duration / 1e6, 6), "cpu": iv.cpu, "event": iv.event_id,
                     "prio": th.prio_at(iv.start)})
        if len(rows) >= MAX_ROWS:
            break
    return rows


def events(trace_path: str, start_ms: float = 0, end_ms: float | None = None, thread: str | None = None,
           event_class: str | None = None, limit: int = 100) -> list[dict]:
    m = _analysis(trace_path).model
    a = m.t_start + int(start_ms * 1e6)
    b = m.t_end if end_ms is None else m.t_start + int(end_ms * 1e6)
    key = _resolve_thread(m, thread).key if thread else None
    rows = []
    for e in m.events:
        if e.t_ns < a or e.t_ns > b or (key and e.key != key) or (event_class and e.cls != event_class):
            continue
        rows.append({"event": e.id, "t_ms": round((e.t_ns - m.t_start) / 1e6, 6), "cpu": e.cpu,
                     "class": e.cls, "kind": e.kind, "thread": m.label(e.key) if e.key else None,
                     "line": e.line, "raw": e.raw})
        if len(rows) >= min(limit, MAX_ROWS):
            break
    return rows


def compare_traces(before: list[str], after: list[str], config_path: str | None = None,
                   min_runs: int = 5) -> dict:
    from .verdict import compare_files
    return compare_files(before, after, load_config(config_path), min_runs=min_runs).to_dict()
