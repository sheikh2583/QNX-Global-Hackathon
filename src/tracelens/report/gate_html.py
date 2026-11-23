"""Self-contained HTML page for a ``tracelens gate`` run: what moved, by how much, how certain.

Reuses the report stylesheet and the fix page's KPI/verdict components, so a gate page looks like
the rest of the tool and there is one place to change the design.
"""

from __future__ import annotations

from html import escape

from .. import __version__
from ..gate import BETTER, PASS, REGRESSION, UNKNOWN, WORSE, GateResult, fmt_delta
from .fix_html import FIX_CSS
from .html import CSS

GATE_CSS = """
table.gate{width:100%;border-collapse:collapse;font-size:13px;margin:8px 0}
table.gate th{text-align:left;font-weight:600;color:var(--muted);font-size:12px;
border-bottom:1px solid var(--line);padding:6px 10px 6px 0}
table.gate td{padding:6px 10px 6px 0;border-bottom:1px solid var(--line);vertical-align:top}
table.gate td.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.st{font-size:11px;font-weight:700;border-radius:999px;padding:1px 9px;white-space:nowrap}
.st-worse{background:rgba(224,49,49,.14);color:var(--block)}
.st-better{background:rgba(47,158,68,.15);color:var(--run)}
.st-same{border:1px solid var(--line);color:var(--muted)}
.st-inconclusive{background:rgba(240,140,0,.16);color:var(--med)}
ul.why{margin:6px 0 0 18px;padding:0}ul.why li{margin:3px 0}
"""

_ST_CLASS = {WORSE: "st-worse", BETTER: "st-better", UNKNOWN: "st-inconclusive"}


def _rows(r: GateResult) -> str:
    out = []
    for m in r.metrics:
        if m.status == UNKNOWN and not m.new_p99_ms:
            cells = f'<td class="num muted" colspan=3>{escape(m.reason)}</td>'
        else:
            p = "-" if m.p_value is None else (f"{m.p_value:.3g}"
                                               + (f" <span class=muted>(adj {m.p_adjusted:.3g})</span>"
                                                  if m.p_adjusted is not None else ""))
            cells = (f'<td class=num>{m.base_p99_ms:.2f} ms</td>'
                     f'<td class=num>{m.new_p99_ms:.2f} ms <span class=muted>({fmt_delta(m)})</span></td>'
                     f'<td class=num>{p}</td>')
        budget = f"{m.budget_ms:.2f} ms" if m.budget_ms else "-"
        out.append(f'<tr><td><code>{escape(m.key)}</code></td>{cells}<td class=num>{budget}</td>'
                   f'<td class=num>{m.runs_base}+{m.runs_new} runs<br>'
                   f'<span class=muted>{m.jobs_base}+{m.jobs_new} jobs</span></td>'
                   f'<td><span class="st {_ST_CLASS.get(m.status, "st-same")}">{escape(m.status)}</span><br>'
                   f'<span class=muted>{escape(m.reason)}</span></td></tr>')
    return "".join(out)


def _kinds(r: GateResult) -> str:
    if not r.kind_rates:
        return '<div class=notebox>No finding at or above the gate severity on either side.</div>'
    rows = []
    for kind, (base, new) in r.kind_rates.items():
        tag = ("<span class='st st-worse'>new</span>" if kind in r.new_kinds
               else "<span class='st st-better'>gone</span>" if kind in r.gone_kinds else "")
        rows.append(f'<tr><td><code>{escape(kind)}</code></td><td class=num>{base:.0%} of runs</td>'
                    f'<td class=num>{new:.0%} of runs</td><td>{tag}</td></tr>')
    return ('<table class=gate><tr><th>Finding kind</th><th>Baseline</th><th>This build</th><th></th></tr>'
            + "".join(rows) + "</table>")


def render_gate(r: GateResult) -> str:
    b = r.baseline
    vcls = {PASS: "v-ok", REGRESSION: "v-bad"}.get(r.verdict, "v-guide")
    evidence = ("run-level Mann-Whitney U, Holm-adjusted across "
                f"{sum(1 for m in r.metrics if m.p_value is not None)} metric(s), alpha {r.alpha:g}"
                if r.statistical else
                "threshold rule: too few captures for a p-value"
                + (f" (a build that did not change clears the baseline's worst p99 about "
                   f"{r.false_alarm_bound:.0%} of the time by chance)" if r.false_alarm_bound else ""))
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>",
        '<meta name=viewport content="width=device-width,initial-scale=1">',
        f"<title>TraceLens gate: {escape(r.name or 'baseline')}</title>",
        f"<style>{CSS}{FIX_CSS}{GATE_CSS}</style></head><body><main>",
        f'<h1>{escape(r.name or "regression gate")}'
        f'<span class="verdict {vcls}">{escape(r.verdict)}</span></h1>',
        f'<div class=muted>Baseline <code>{escape(str(b.get("name", "")))}</code> recorded '
        f'{escape(str(b.get("created", "?")))} by TraceLens {escape(str(b.get("tool_version", "?")))} from '
        f'{r.runs_base} capture(s); this build: {r.runs_new} clean capture(s)'
        + (f", {r.lossy_excluded} lossy excluded" if r.lossy_excluded else "")
        + f'. TraceLens {escape(__version__)}.</div>',
        f'<div class=notebox><b>Evidence:</b> {escape(evidence)}</div>',
    ]
    if r.reasons:
        cls = "warnbox" if r.verdict == REGRESSION else "notebox"
        head = ("<b>Why this build is blocked</b>" if r.verdict == REGRESSION
                else "<b>Why no verdict could be given</b>")
        items = "".join(f"<li>{escape(x)}</li>" for x in r.reasons)
        parts.append(f'<div class={cls}>{head}<ul class=why>{items}</ul></div>')
    if r.verdict == PASS:
        faster = "; ".join(f"{m.key} {fmt_delta(m)}" for m in r.improvements)
        parts.append('<div class=ok>No regression: no new finding kind, and no declared deadline is '
                     'significantly slower.' + (f" Faster: {escape(faster)}." if faster else "") + "</div>")
    parts += ["<h2>Deadline response times (p99)</h2>"]
    if r.metrics:
        parts.append('<table class=gate><tr><th>Metric</th><th>Baseline p99</th><th>This build p99</th>'
                     '<th>p (slower)</th><th>Budget</th><th>Samples</th><th>Verdict</th></tr>'
                     + _rows(r) + "</table>")
    else:
        parts.append('<div class=notebox>The baseline recorded no deadline response times: declare a '
                     '<code>[deadlines.&lt;job&gt;]</code> budget to gate timing as well as finding kinds.</div>')
    parts += ["<h2>Finding kinds</h2>", _kinds(r)]
    if r.warnings:
        items = "".join(f"<li>{escape(w)}</li>" for w in r.warnings)
        parts.append(f'<h2>Caveats</h2><div class=notebox><ul class=why>{items}</ul></div>')
    parts.append("</main></body></html>")
    return "\n".join(parts)
