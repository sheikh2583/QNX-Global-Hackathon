"""Before/after fix report: one self-contained HTML page per fix.

The same zoomed window of the workload's threads before and after the patch, on the same time
scale, with the verdict numbers, the remedy and why, and the patch itself.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .. import __version__
from ..analyze import Analysis, analyze_file
from ..config import Config
from .html import CSS, STATE_COLORS

WINDOW_NS = 25_000_000  # 2.5 periods of a 10 ms loop: enough to see the pattern repeat

FIX_CSS = """
.verdict{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:700;margin-left:8px}
.v-ok{background:rgba(47,158,68,.15);color:var(--run)}.v-bad{background:rgba(224,49,49,.14);color:var(--block)}
.v-guide{background:rgba(28,126,214,.14);color:var(--intr)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.kpi b{display:block;font-size:20px}.kpi .arrow{color:var(--muted)}.kpi small{color:var(--muted)}
.pair{display:grid;grid-template-columns:minmax(0,1fr);gap:6px}.pair h3{margin:10px 0 4px}
pre.diff{font-size:12px;overflow:auto;background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:10px}
.add{color:var(--run)}.del{color:var(--block)}.hunk{color:var(--intr)}
.rem{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:10px 0}
.rem code{font-size:12px}.tag{display:inline-block;font-size:11px;padding:1px 8px;border-radius:999px;
border:1px solid var(--line);margin-left:6px;color:var(--muted)}
"""


def _workload_threads(m, workload: str, findings=()) -> list:
    pids = {pid for pid, name in m.proc_names.items() if name.startswith(workload)}
    if not pids:  # process named differently: use the processes of the threads the findings name
        named = {n for f in findings for n in f.threads}
        pids = {k[0] for k in m.threads if m.label(k) in named and k[0] != 1}
    rows = [th for k, th in m.threads.items() if k[0] in pids]
    return sorted(rows, key=lambda th: (-(th.prio or 0), th.key))


def _middle(m, rows) -> int:
    """Start of a window in the middle of the workload's activity: steady state, away from the
    program's startup and teardown (the planted bugs recur every period, so the middle shows them)."""
    keys = {th.key for th in rows}
    ts = [e.t_ns for e in m.events if (e.pid, e.tid) in keys]
    if not ts:
        return m.t_start
    return max(min(ts), (min(ts) + max(ts)) // 2 - WINDOW_NS // 2)


def _timeline(m, rows, t0: int, t1: int, findings, width: int = 960) -> str:
    left, row_h = 170, 22
    height = 30 + row_h * max(1, len(rows))
    span = max(1, t1 - t0)
    x = lambda t: left + (min(max(t, t0), t1) - t0) / span * (width - left - 10)  # noqa: E731
    parts = [f'<svg class="tl" viewBox="0 0 {width} {height}" role="img" aria-label="Thread timeline">']
    for f in findings:
        if f.t_end < t0 or f.t_start > t1:
            continue
        x0, x1 = x(f.t_start), x(f.t_end)
        parts.append(f'<rect x="{x0:.1f}" y="0" width="{max(2, x1 - x0):.1f}" height="{height}" '
                     f'fill="var(--band)"><title>{escape(f.title)}</title></rect>')
    for ms in range(0, int(span / 1e6) + 1, 5):  # 5 ms grid
        gx = x(t0 + ms * 1_000_000)
        parts.append(f'<line x1="{gx:.1f}" y1="14" x2="{gx:.1f}" y2="{height}" stroke="var(--line)"/>'
                     f'<text x="{gx + 2:.1f}" y="11" class="muted">{ms} ms</text>')
    for i, th in enumerate(rows):
        y = 20 + i * row_h
        parts.append(f'<text x="4" y="{y + 12}">{escape(m.describe(th.key))}</text>')
        for iv in th.intervals:
            color = STATE_COLORS.get(iv.state)
            if color is None or iv.end <= t0 or iv.start >= t1:
                continue
            x0, x1 = x(iv.start), x(iv.end)
            parts.append(f'<rect x="{x0:.2f}" y="{y}" width="{max(0.8, x1 - x0):.2f}" height="15" rx="2" '
                         f'fill="{color}"><title>{escape(iv.state)} {iv.duration / 1e6:.3f} ms</title></rect>')
    parts.append("</svg>")
    return "".join(parts)


def _diff_html(diff: str) -> str:
    out = []
    for line in diff.splitlines():
        cls = ("add" if line.startswith("+") and not line.startswith("+++") else
               "del" if line.startswith("-") and not line.startswith("---") else
               "hunk" if line.startswith("@@") else "")
        out.append(f'<span class="{cls}">{escape(line)}</span>' if cls else escape(line))
    return "\n".join(out)


def _kpis(result: dict) -> str:
    v = result.get("verdict") or {}
    cards = []
    for k, t in v.get("targets", {}).items():
        cards.append(f'<div class=kpi><small>{escape(k.replace("_", " "))}: runs with the finding</small>'
                     f'<b>{t["before_rate"]:.0%} <span class=arrow>→</span> {t["after_rate"]:.0%}</b></div>')
    for d in v.get("deadlines", []):
        cards.append(f'<div class=kpi><small>\'{escape(d["name"])}\' p99 response (budget '
                     f'{d["budget_ns"] / 1e6:.1f} ms)</small><b>{d["before_p99"] / 1e6:.2f} '
                     f'<span class=arrow>→</span> {d["after_p99"] / 1e6:.2f} ms</b>'
                     f'<small>misses {d["before_misses"]} → {d["after_misses"]}; {escape(d["reason"])}</small></div>')
    for extra in result.get("extra_kpis", []):
        cards.append(f'<div class=kpi><small>{escape(extra["label"])}</small><b>{escape(extra["before"])} '
                     f'<span class=arrow>→</span> {escape(extra["after"])}</b></div>')
    return f'<div class=kpis>{"".join(cards)}</div>' if cards else ""


def render_fix(result: dict, diff: str, before: Analysis, after: Analysis | None) -> str:
    status = result["status"]
    rounds = result.get("rounds") or 0
    rounds_txt = f", {rounds} round{'s' if rounds != 1 else ''}" if rounds else ""
    vcls = "v-ok" if status == "VERIFIED" else ("v-guide" if status == "GUIDED" else "v-bad")
    w = result["workload"]
    rows_b = _workload_threads(before.model, w, before.findings)
    t0b = _middle(before.model, rows_b)
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        '<meta name=viewport content="width=device-width,initial-scale=1">',
        f"<title>TraceLens fix: {escape(w)}</title><style>{CSS}{FIX_CSS}</style></head><body><main>",
        f'<h1>{escape(w)}<span class="verdict {vcls}">{escape(status)}</span></h1>',
        f'<div class=muted>Found in the trace, fixed in the source, proven on QNX: {result["runs"]} runs before, '
        f'{result["runs"]} after{rounds_txt}. '
        f'The patch is written by fixed rules, not a model. TraceLens {escape(__version__.split(".dev")[0])}.</div>',
        _kpis(result),
        "<h2>What TraceLens changed, and why</h2>",
    ]
    for r in result.get("remedies", []):
        if r["rule"] == "symptom":
            continue
        locs = "".join(f"<li><code>{escape(p)}:{n}</code> <code>{escape(c)}</code></li>" for p, n, c in r["locations"])
        guide = "".join(f"<li>{escape(g)}</li>" for g in r["guidance"])
        notes = "".join(f"<li>{escape(n)}</li>" for n in r["notes"])
        parts.append(
            f'<div class=rem><b>{escape(r["title"])}</b><span class=tag>{"automatic" if r["automatic"] else "guided"}'
            f'</span><span class=tag>rule {escape(r["rule"])}</span>'
            + (f'<span class=tag>round {r["round"]}</span>' if r.get("round") else "")
            + f'<p>{escape(r["rationale"])}</p>'
            + (f"<div class=muted>Source locations</div><ul>{locs}</ul>" if locs else "")
            + (f"<div class=muted>What to do</div><ul>{guide}</ul>" if guide else "")
            + (f"<div class=muted>Why not automatic</div><ul>{notes}</ul>" if notes and not r["automatic"] else "")
            + "</div>")
    parts.append("<h2>The workload's threads, before and after</h2>")
    parts.append('<div class=legend><span><i style="background:var(--run)"></i>running</span>'
                 '<span><i style="background:var(--ready)"></i>ready (preempted)</span>'
                 '<span><i style="background:var(--block)"></i>blocked on sync</span>'
                 '<span><i style="background:var(--ipc)"></i>send/reply blocked</span>'
                 '<span><i style="background:var(--intr)"></i>waiting for interrupt</span>'
                 '<span><i style="background:var(--band)"></i>finding</span></div>')
    parts.append(f"<div class=pair><h3>Before the fix <span class=muted>({escape(Path(before.model.trace.source).name)}, 25 ms from the middle of the run)</span></h3>"
                 + _timeline(before.model, rows_b, t0b, t0b + WINDOW_NS, before.findings))
    if after is not None:
        rows_a = _workload_threads(after.model, w, before.findings)
        t0a = _middle(after.model, rows_a)
        parts.append(f"<h3>After the fix <span class=muted>({escape(Path(after.model.trace.source).name)}, 25 ms from the middle of the run)</span></h3>"
                     + _timeline(after.model, rows_a, t0a, t0a + WINDOW_NS,
                                 after.findings))
    parts.append("</div>")
    if diff:
        parts.append(f"<h2>The patch</h2><pre class=diff>{_diff_html(diff)}</pre>")
    v = result.get("verdict") or {}
    if v.get("reasons"):
        parts.append("<h2>Verdict notes</h2><ul>" + "".join(f"<li>{escape(x)}</li>" for x in v["reasons"]) + "</ul>")
    parts.append("</main></body></html>")
    return "\n".join(parts)


def write_fix_report(bundle: str | Path, before: list[str | Path], after: list[str | Path], cfg: Config,
                     out: str | Path | None = None, extra_kpis: list[dict] | None = None) -> Path:
    """Render ``report.html`` for a fix bundle from its result.json and patch.diff."""
    bundle = Path(bundle)
    result = json.loads((bundle / "result.json").read_text(encoding="utf-8"))
    if extra_kpis:
        result["extra_kpis"] = extra_kpis
    diff = (bundle / "patch.diff").read_text(encoding="utf-8") if (bundle / "patch.diff").exists() else ""
    targets = result.get("targets", [])

    def pick(paths, worst: bool):
        an = [analyze_file(p, cfg) for p in paths]
        an = [a for a in an if not a.model.lossy] or an
        score = lambda a: sum(1 for f in a.findings if f.kind in targets)  # noqa: E731
        return (max if worst else min)(an, key=score) if an else None

    b = pick(before, worst=True)
    a = pick(after, worst=True) if after else None
    path = Path(out or bundle / "report.html")
    path.write_text(render_fix(result, diff, b, a), encoding="utf-8")
    return path
