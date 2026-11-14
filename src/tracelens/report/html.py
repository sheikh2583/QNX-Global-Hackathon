"""Self-contained HTML report: findings with evidence, plus a thread state timeline."""

from __future__ import annotations

import re
from html import escape
from typing import Any

from .. import __version__
from ..analyze import Analysis
from ..model.trace import TraceModel

STATE_COLORS = {
    "RUNNING": "var(--run)",
    "READY": "var(--ready)",
    "SEM": "var(--block)",
    "MUTEX": "var(--block)",
    "CONDVAR": "var(--block)",
    "SEND": "var(--ipc)",
    "REPLY": "var(--ipc)",
    "INTR": "var(--intr)",
}
SEV_CLASS = {"critical": "sev-crit", "high": "sev-high", "medium": "sev-med", "low": "sev-low"}

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1b;--muted:#6b6b66;--line:#e3e2dd;
--run:#2f9e44;--ready:#f2b33d;--block:#e03131;--ipc:#7048e8;--intr:#1c7ed6;
--crit:#c92a2a;--high:#e8590c;--med:#f08c00;--low:#868e96;--band:rgba(224,49,49,.10)}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141413;--card:#1e1e1c;
--fg:#ecebe6;--muted:#a3a29b;--line:#33332f;--band:rgba(255,107,107,.14)}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 12px}
.muted{color:var(--muted)}.stats{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:120px}
.stat b{display:block;font-size:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0}
.card h3{margin:0 0 6px;font-size:16px}.badge{display:inline-block;border-radius:6px;padding:1px 8px;
font-size:12px;font-weight:600;color:#fff;margin-right:8px;text-transform:uppercase;letter-spacing:.03em}
.sev-crit{background:var(--crit)}.sev-high{background:var(--high)}.sev-med{background:var(--med)}.sev-low{background:var(--low)}
.qnx{border-left:3px solid var(--intr);padding:6px 12px;margin:10px 0;color:var(--muted)}
table{border-collapse:collapse;font-size:13px;margin:8px 0}td{padding:2px 14px 2px 0;vertical-align:top}
details{margin-top:8px}summary{cursor:pointer;color:var(--muted)}
pre{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;overflow-x:auto;font-size:12px}
.tl{width:100%;box-sizing:border-box;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px}
.tl text{fill:var(--fg);font-size:11px}.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted)}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.cite{font:12px ui-monospace,Consolas,monospace;color:var(--intr);text-decoration:none;white-space:nowrap}
.tag{font-size:12px;border-radius:6px;padding:1px 7px;margin-left:6px;border:1px solid var(--line)}
.tag.ok2{color:var(--run)}.tag.bad{color:var(--crit)}
.warnbox{border:1px solid var(--crit);border-radius:10px;padding:10px 14px;margin:12px 0}
.warnbox b{color:var(--crit)}.notebox{border:1px solid var(--line);border-radius:10px;padding:8px 14px;margin:12px 0;font-size:13px}
.ok{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;color:var(--run);font-weight:600}
"""


def _timeline(m: TraceModel, a: Analysis, max_threads: int = 14) -> str:
    span = max(1, m.t_end - m.t_start)
    involved = []
    for f in a.findings:
        for name in f.threads:
            if name not in involved:
                involved.append(name)
    by_label = {m.label(k): th for k, th in m.threads.items() if th.pid != 1}
    rows = [by_label[n] for n in involved if n in by_label]
    rest = sorted((th for n, th in by_label.items() if n not in involved),
                  key=lambda th: -m.overlap(th, {"RUNNING"}, m.t_start, m.t_end))
    rows = (rows + rest)[:max_threads]

    left, width, row_h = 150, 960, 22
    height = 24 + row_h * len(rows)
    x = lambda t: left + (t - m.t_start) / span * (width - left - 10)  # noqa: E731
    parts = [f'<svg class="tl" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="Thread state timeline">']
    for f in a.findings:
        x0, x1 = x(f.t_start), x(f.t_end)
        parts.append(f'<rect x="{x0:.1f}" y="0" width="{max(2, x1 - x0):.1f}" height="{height}" '
                     f'fill="var(--band)"><title>{escape(f.id)} {escape(f.title)}</title></rect>')
        parts.append(f'<text x="{x0 + 2:.1f}" y="11">{escape(f.id)}</text>')
    for i, th in enumerate(rows):
        y = 18 + i * row_h
        label = escape(m.describe(th.key))
        parts.append(f'<text x="4" y="{y + 12}">{label}</text>')
        for iv in th.intervals:
            color = STATE_COLORS.get(iv.state)
            if color is None or iv.duration <= 0:
                continue
            x0, x1 = x(iv.start), x(iv.end)
            parts.append(f'<rect x="{x0:.2f}" y="{y}" width="{max(0.6, x1 - x0):.2f}" height="15" '
                         f'rx="2" fill="{color}"><title>{escape(iv.state)} '
                         f'{iv.duration / 1e6:.3f} ms (event {iv.event_id})</title></rect>')
    parts.append("</svg>")
    return "".join(parts)


_CITE = re.compile(r"\bE(\d+)\b")


def _link(fid: str, eid: int) -> str:
    return f'<a class=cite href="#{escape(fid)}-E{eid}">E{eid}</a>'


def _cite(text: str, fid: str) -> str:
    return _CITE.sub(lambda m: _link(fid, int(m.group(1))), escape(str(text)))


def _integrity(a: Analysis) -> str:
    m = a.model
    out = []
    if m.integrity:
        items = "".join(f"<li>{escape(i)}</li>" for i in m.integrity)
        out.append(f'<div class=warnbox><b>Lossy trace: verdict withheld.</b> The scheduler state machine is '
                   f'broken, which usually means the capture dropped events. Findings below may be artefacts; '
                   f'recapture with fewer event classes or a larger buffer.<ul>{items}</ul></div>')
    notes = list(m.trace.issues)
    if getattr(a, "snapshot_path", None):
        notes.append(f"base priorities seeded from thread snapshot {a.snapshot_path}")
    if notes:
        out.append('<div class=notebox>' + "<br>".join(escape(n) for n in notes) + "</div>")
    return "".join(out)


def render(a: Analysis) -> str:
    m = a.model
    counts = {s: sum(1 for f in a.findings if f.severity == s) for s in ("critical", "high", "medium", "low")}
    out = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        '<meta name=viewport content="width=device-width,initial-scale=1">',
        f"<title>TraceLens Report</title><style>{CSS}</style></head><body><main>",
        "<h1>TraceLens report</h1>",
        f'<div class=muted>{escape(m.trace.source)} · TraceLens {escape(__version__)}</div>',
        '<div class=stats>',
        f'<div class=stat><b>{len(a.findings)}</b>findings</div>',
        f'<div class=stat><b>{counts["critical"]}</b>critical</div>',
        f'<div class=stat><b>{counts["high"]}</b>high</div>',
        f'<div class=stat><b>{(m.t_end - m.t_start) / 1e6:.1f} ms</b>traced</div>',
        f'<div class=stat><b>{len(m.events):,}</b>events</div>',
        f'<div class=stat><b>{len(m.threads)}</b>threads</div>',
        "</div>",
        _integrity(a),
        "<h2>Timeline</h2>",
        _timeline(m, a),
        '<div class=legend><span><i style="background:var(--run)"></i>running</span>'
        '<span><i style="background:var(--ready)"></i>ready (preempted)</span>'
        '<span><i style="background:var(--block)"></i>blocked on sync</span>'
        '<span><i style="background:var(--ipc)"></i>send/reply blocked</span>'
        '<span><i style="background:var(--intr)"></i>waiting for interrupt</span>'
        '<span><i style="background:var(--band)"></i>finding window</span></div>',
        "<h2>Findings</h2>",
    ]
    if not a.findings:
        out.append('<div class=ok>No real-time issues detected.</div>')
    for f in a.findings:
        rows = "".join(f"<tr><td class=muted>{escape(k)}</td><td>{escape(str(v))}</td></tr>"
                       for k, v in f.metrics.items())
        core = set(f.evidence)
        ev = "\n".join(
            f'<span id="{escape(f.id)}-E{e.id}">'
            + escape(f"{'*' if e.id in core else ' '}E{e.id:<6} L{e.line:<6} {e.raw}") + "</span>"
            for i in f.evidence if (e := m.by_id.get(i)) is not None)
        out.append(
            f'<div class=card><h3><span class="badge {SEV_CLASS.get(f.severity, "sev-low")}">'
            f'{escape(f.severity)}</span>{escape(f.id)} · {escape(f.title)}</h3>'
            f"<div>{escape(f.summary)}</div>"
            f'<div class=qnx>{escape(f.qnx_note)}</div>'
            f"<table>{rows}</table>"
            f"<details><summary>Evidence ({len(f.evidence)} trace events, * = detector evidence)</summary>"
            f"<pre>{ev}</pre></details>"
            "</div>"
        )
    if a.errors:
        out.append("<h2>Detector errors</h2><pre>" + escape("\n".join(a.errors)) + "</pre>")
    out.append("</main></body></html>")
    return "\n".join(out)
