from __future__ import annotations

import json

from .. import __version__
from ..analyze import Analysis


def to_dict(a: Analysis, explanations: dict | None = None) -> dict:
    m = a.model
    explanations = explanations or {}
    return {
        "tool": "tracelens",
        "version": __version__,
        "trace": {
            "source": m.trace.source,
            "events": len(m.events),
            "duration_ms": round((m.t_end - m.t_start) / 1e6, 3),
            "cycles_per_sec": m.trace.cycles_per_sec,
            "threads": len(m.threads),
            "unparsed_lines": m.trace.unparsed_lines,
        },
        "summary": {
            sev: sum(1 for f in a.findings if f.severity == sev)
            for sev in ("critical", "high", "medium", "low")
        },
        "findings": [
            {**f.to_dict(),
             "evidence_events": [_ev(m.by_id[i]) for i in f.evidence if i in m.by_id],
             **({"explanation": explanations[f.id].to_dict()} if f.id in explanations else {})}
            for f in a.findings
        ],
        "errors": a.errors,
    }


def _ev(e) -> dict:
    return {"id": e.id, "t_ms": round(e.t_ns / 1e6, 6), "cpu": e.cpu, "line": e.line,
            "pid": e.pid, "tid": e.tid, "raw": e.raw}


def dumps(a: Analysis, explanations: dict | None = None) -> str:
    return json.dumps(to_dict(a, explanations), indent=2)
