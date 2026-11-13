"""SARIF 2.1.0 output, so GitHub code scanning shows findings as alerts.

Each finding becomes a result located at the first evidence line of the trace
file (traces are committed as fixtures, so the location resolves in the repo).
Upload with ``github/codeql-action/upload-sarif``.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import __version__
from ..analyze import Analysis

LEVEL = {"critical": "error", "high": "error", "medium": "warning", "low": "note", "info": "note"}
RULE_TEXT = {
    "priority_inversion": "A high-priority thread waited on a lower-priority one while medium-priority work held its CPU.",
    "ipc_deadlock": "Processes were SEND/REPLY-blocked on each other in a cycle; none could receive.",
    "ipc_chain": "A request was blocked through a long chain of message-passing servers.",
    "mutex_contention": "Threads spent a large share of time waiting for one mutex.",
    "irq_latency": "The interrupt handler thread started too late after the interrupt.",
    "irq_handler_overrun": "The interrupt stayed masked too long while its handler worked.",
    "deadline_miss": "Periodic jobs finished after their budget, measured from release.",
}


def to_sarif(a: Analysis, trace_uri: str | None = None) -> dict:
    m = a.model
    uri = (trace_uri or m.trace.source).replace("\\", "/")
    rules, seen = [], set()
    results = []
    for f in a.findings:
        if f.kind not in seen:
            seen.add(f.kind)
            rules.append({
                "id": f.kind,
                "name": "".join(w.capitalize() for w in f.kind.split("_")),
                "shortDescription": {"text": RULE_TEXT.get(f.kind, f.kind)},
                "help": {"text": f.qnx_note or RULE_TEXT.get(f.kind, f.kind)},
                "properties": {"tags": ["real-time", "qnx"]},
            })
        lines = sorted(e.line for i in f.evidence if (e := m.by_id.get(i)) is not None and e.line)
        loc = {"physicalLocation": {"artifactLocation": {"uri": uri},
                                    "region": {"startLine": lines[0] if lines else 1}}}
        results.append({
            "ruleId": f.kind,
            "level": LEVEL.get(f.severity, "warning"),
            "message": {"text": f"{f.id} {f.title}: {f.summary}"},
            "locations": [loc],
            "relatedLocations": [
                {"id": n, "physicalLocation": {"artifactLocation": {"uri": uri}, "region": {"startLine": ln}},
                 "message": {"text": f"evidence event on trace line {ln}"}}
                for n, ln in enumerate(lines[1:6], start=1)],
            "partialFingerprints": {"tracelensFinding": f"{f.kind}:{':'.join(sorted(f.threads))}"},
            "properties": {"severity": f.severity, "metrics": f.metrics, "evidence_events": f.evidence},
        })
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "TraceLens", "version": __version__,
                                "informationUri": "https://github.com/sheikh2583/QNX-Global-Hackathon",
                                "rules": rules}},
            "results": results,
        }],
    }


def dumps(a: Analysis, trace_uri: str | None = None) -> str:
    return json.dumps(to_sarif(a, trace_uri), indent=2)


def relative_uri(trace: str | Path, root: str | Path = ".") -> str:
    try:
        return Path(trace).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return Path(trace).as_posix()
