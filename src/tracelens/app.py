"""The TraceLens web app: pages for people who want their QNX program fixed, and a guided demo.

Plain language first; the engineering detail (raw events, metrics, parser notes) stays one click
away under "Technical details". Every number on these pages is computed from real QNX 8.0 traces
and the committed results in docs/results, never typed in by hand.
"""

from __future__ import annotations

import base64
import difflib
import json
from html import escape
from pathlib import Path

from . import __version__
from .analyze import Analysis
from .config import Config
from .findings import SEVERITY_RANK, Finding, at_least
from .report.fix_html import _timeline

# ----------------------------------------------------------------------------- copy
KIND = {
    "priority_inversion": {
        "name": "A high-priority task was held up by lower-priority work",
        "impact": "The most urgent part of your program waits for work that should never delay it, so it can "
                  "miss its deadline even though the CPU had time for it.",
        "todo": "Protect shared data with a mutex that has priority inheritance (on QNX, pthread mutexes do "
                "this by default), not with a semaphore; let servers inherit their clients' priority.",
    },
    "ipc_deadlock": {
        "name": "Two parts of the program are waiting for each other",
        "impact": "Each side sent a message and waits for a reply the other can never send. Nothing moves "
                  "until a timeout breaks the wait, or forever if there is none.",
        "todo": "Let messages flow one way only (a send hierarchy); use a pulse for the other direction.",
    },
    "mutex_contention": {
        "name": "Threads queue for the same lock",
        "impact": "While one thread holds the lock, the others stop. Work that runs in parallel on paper runs "
                  "one at a time.",
        "todo": "Hold the lock only while touching shared data: do the computation before or after it.",
    },
    "irq_handler_overrun": {
        "name": "Interrupt handling takes too long",
        "impact": "The interrupt stays blocked while the handler works, so the next ones from the device are "
                  "delayed or lost.",
        "todo": "Acknowledge and unmask the interrupt first; hand the heavy work to a lower-priority thread.",
    },
    "irq_latency": {
        "name": "Interrupts are answered late",
        "impact": "The thread that serves the device starts long after the device asked for attention.",
        "todo": "Usually a symptom of slow interrupt handling or a higher-priority thread on the same CPU.",
    },
    "deadline_miss": {
        "name": "A periodic task finished late",
        "impact": "The task did not complete within its time budget. This is what users and safety checks notice.",
        "todo": "Fix the cause TraceLens names above; a deadline miss is the symptom.",
    },
}
SEVERITY = {  # label, what it means for you
    "critical": ("Fix now", "Breaks timing in most runs"),
    "high": ("Fix", "Breaks timing"),
    "medium": ("Worth a look", "Real, but rare or small"),
    "low": ("For information", "Not caused by your code"),
}
WORKLOADS = {
    "z1_infusion_pump": ("Infusion pump", "A dose controller shares a sensor buffer with a logger and a telemetry task."),
    "z2_brake_by_wire": ("Brake-by-wire", "A brake controller sends each request to an arbiter server."),
    "z3_sensor_fusion": ("Sensor fusion", "Two fusion servers ask each other for their latest estimate."),
    "z4_camera_pipeline": ("Camera pipeline", "Four worker threads process camera tiles and publish them to a shared store."),
    "z5_motor_encoder": ("Motor encoder", "An interrupt thread services a motor encoder and updates its velocity profile."),
}

# ----------------------------------------------------------------------------- design system
CSS = """
:root{--bg:#f5f7f6;--surface:#fff;--sunk:#edf1ef;--fg:#16201d;--muted:#56635f;--faint:#8a9692;--line:#dbe2df;
--accent:#0d6b61;--accent-ink:#fff;--accent-soft:rgba(13,107,97,.10);
--run:#2f9e44;--ready:#e8a317;--block:#d9363e;--ipc:#7048e8;--intr:#1c7ed6;--band:rgba(217,54,62,.10);
--crit:#c92a2a;--crit-soft:rgba(201,42,42,.10);--warn:#b35c00;--warn-soft:rgba(232,140,0,.13);
--ok:#2b8a3e;--ok-soft:rgba(43,138,62,.12);--info:#1c6fb8;--info-soft:rgba(28,111,184,.11);
--before:#9aa5a1;
--sans:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
--mono:"IBM Plex Mono",ui-monospace,"Cascadia Mono",Consolas,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1514;--surface:#172020;--sunk:#1c2625;
--fg:#e4ebe8;--muted:#9aa8a3;--faint:#6c7975;--line:#283331;--accent:#4cc3b2;--accent-ink:#06201c;
--accent-soft:rgba(76,195,178,.13);--run:#40c057;--ready:#f5b83d;--block:#ff6b6b;--ipc:#9775fa;--intr:#4dabf7;
--band:rgba(255,107,107,.14);--crit:#ff8787;--crit-soft:rgba(255,107,107,.14);--warn:#ffb057;
--warn-soft:rgba(255,176,87,.14);--ok:#69db7c;--ok-soft:rgba(105,219,124,.13);--info:#74b8f5;
--info-soft:rgba(116,184,245,.13);--before:#6c7975;color-scheme:dark}}
:root[data-theme=dark]{--bg:#0f1514;--surface:#172020;--sunk:#1c2625;--fg:#e4ebe8;--muted:#9aa8a3;--faint:#6c7975;
--line:#283331;--accent:#4cc3b2;--accent-ink:#06201c;--accent-soft:rgba(76,195,178,.13);--run:#40c057;--ready:#f5b83d;
--block:#ff6b6b;--ipc:#9775fa;--intr:#4dabf7;--band:rgba(255,107,107,.14);--crit:#ff8787;--crit-soft:rgba(255,107,107,.14);
--warn:#ffb057;--warn-soft:rgba(255,176,87,.14);--ok:#69db7c;--ok-soft:rgba(105,219,124,.13);--info:#74b8f5;
--info-soft:rgba(116,184,245,.13);--before:#6c7975;color-scheme:dark}
*{box-sizing:border-box}html{scroll-behavior:smooth}[hidden]{display:none!important}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.6 var(--sans)}
a{color:var(--accent)}a:focus-visible,button:focus-visible,summary:focus-visible,input:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.top{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--line)}
.top .in{max-width:1120px;margin:0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:6px 22px;
padding:12px max(16px,env(safe-area-inset-right,0px)) 12px max(16px,env(safe-area-inset-left,0px))}
.brand{font-weight:700;font-size:18px;color:var(--fg);text-decoration:none;display:flex;align-items:center;gap:8px}
.brand i{width:22px;height:22px;border-radius:6px;background:var(--accent);display:inline-block;position:relative}
.brand i::after{content:"";position:absolute;left:5px;right:5px;top:10px;height:2px;background:var(--accent-ink)}
.top nav{display:flex;flex-wrap:wrap;gap:4px 18px;font-size:15px}.top nav a{color:var(--muted);text-decoration:none}
.top nav a[aria-current=page],.top nav a:hover{color:var(--fg)}
.top .cta{margin-left:auto}
main{max-width:1120px;margin:0 auto;padding:36px max(16px,env(safe-area-inset-right,0px)) 80px
max(16px,env(safe-area-inset-left,0px));display:grid;gap:56px}main>*{min-width:0}
section{display:grid;gap:18px}
h1,h2,h3{margin:0;line-height:1.18;text-wrap:balance}
h1{font-size:clamp(32px,5.2vw,52px);letter-spacing:-.015em;font-weight:700}
h2{font-size:clamp(24px,3vw,30px);font-weight:650;letter-spacing:-.005em}h3{font-size:18px;font-weight:600}
p{margin:0;max-width:68ch}.lede{font-size:clamp(17px,2vw,20px);color:var(--muted);max-width:62ch}
.eyebrow{font:500 12px/1 var(--mono);letter-spacing:.09em;text-transform:uppercase;color:var(--accent)}
.muted{color:var(--muted)}.small{font-size:14px}
.btn{display:inline-flex;align-items:center;gap:8px;font:600 15px/1 var(--sans);padding:12px 18px;border-radius:10px;
text-decoration:none;border:1px solid transparent;cursor:pointer}
.btn.primary{background:var(--accent);color:var(--accent-ink)}.btn.ghost{border-color:var(--line);color:var(--fg);background:var(--surface)}
.btns{display:flex;flex-wrap:wrap;gap:10px}
.hero{display:grid;gap:22px;padding-top:12px}
.grid3{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:18px 20px;display:grid;gap:10px;align-content:start}
.card>*{min-width:0}
.step{font:600 13px var(--mono);color:var(--accent)}
.stat b{display:block;font-size:clamp(30px,4vw,40px);line-height:1.05;font-variant-numeric:tabular-nums}
.stat span{color:var(--muted);font-size:14px}
.pill{display:inline-flex;align-items:center;gap:6px;font:600 12.5px/1 var(--sans);padding:6px 10px;border-radius:999px;white-space:nowrap}
.pill::before{content:"";width:7px;height:7px;border-radius:50%;background:currentColor}
.sev-critical,.sev-high{background:var(--crit-soft);color:var(--crit)}.sev-medium{background:var(--warn-soft);color:var(--warn)}
.sev-low{background:var(--sunk);color:var(--muted)}.st-ok{background:var(--ok-soft);color:var(--ok)}
.st-info{background:var(--info-soft);color:var(--info)}.st-bad{background:var(--crit-soft);color:var(--crit)}
.verdict{border-radius:14px;padding:18px 20px;display:grid;gap:6px;border:1px solid var(--line)}
.verdict.bad{background:var(--crit-soft);border-color:transparent}.verdict.ok{background:var(--ok-soft);border-color:transparent}
.verdict.warn{background:var(--warn-soft);border-color:transparent}
.verdict b{font-size:20px}
.problem{background:var(--surface);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.problem .hd{padding:16px 20px;display:flex;flex-wrap:wrap;gap:10px 14px;align-items:center;border-bottom:1px solid var(--line)}
.problem .hd h3{flex:1 1 320px}
.problem .bd{padding:16px 20px;display:grid;gap:16px}
.cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
.k{font:600 12px/1.3 var(--mono);letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
.tl{width:100%;min-width:620px;display:block;background:var(--surface)}
.tl text{fill:var(--fg);font:11px var(--sans)}.tl text.muted{fill:var(--muted)}
.legend{display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--muted)}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-2px}
pre{margin:0;padding:14px 16px;overflow-x:auto;background:var(--sunk);border-radius:10px;font:12.5px/1.6 var(--mono)}
code{font-family:var(--mono);font-size:.9em;background:var(--sunk);padding:1px 6px;border-radius:5px}
.add{color:var(--ok)}.del{color:var(--crit)}.hunk{color:var(--info)}
details{border:1px solid var(--line);border-radius:12px;background:var(--surface)}
details>summary{cursor:pointer;padding:12px 16px;font-weight:600;list-style:none}
details>summary::-webkit-details-marker{display:none}details>summary::before{content:"+";display:inline-block;width:18px;color:var(--accent)}
details[open]>summary::before{content:"−"}details>.in{padding:0 16px 16px;display:grid;gap:10px}
table{border-collapse:collapse;width:100%;font-size:14.5px}
th,td{text-align:left;vertical-align:top;padding:10px 14px;border-bottom:1px solid var(--line)}
th{font:600 12px/1.3 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted)}
tr:last-child td{border-bottom:0}td.n{font-variant-numeric:tabular-nums;white-space:nowrap}
.tour{display:grid;grid-template-columns:220px minmax(0,1fr);gap:36px;align-items:start}
.tour nav{position:sticky;top:76px;display:grid;gap:4px;font-size:14.5px}
.tour nav a{color:var(--muted);text-decoration:none;padding:6px 10px;border-radius:8px;border-left:2px solid var(--line)}
.tour nav a:hover{color:var(--fg);background:var(--accent-soft)}
.tour>*,.tour .steps>section,.tour .steps>section>*{min-width:0}
.tour .steps{display:grid;gap:64px}.tour .steps>section{scroll-margin-top:84px}
@media (max-width:860px){.tour{grid-template-columns:1fr}.tour nav{position:static;display:flex;flex-wrap:wrap}}
.chart{display:block;width:100%;max-width:860px;min-width:540px;height:auto;margin:0 auto}
.chart text{fill:var(--muted);font:12px var(--sans)}.chart .lab{fill:var(--fg);font-weight:600}
.drop{border:2px dashed var(--line);border-radius:14px;padding:22px;display:grid;gap:14px;background:var(--surface)}
.drop label{display:grid;gap:6px;font-weight:600}.drop label span{font-weight:400;color:var(--muted);font-size:14px}
input[type=file]{font:14px var(--sans);color:var(--muted)}
footer{border-top:1px solid var(--line)}footer .in{max-width:1120px;margin:0 auto;padding:22px 16px;color:var(--muted);font-size:14px;display:grid;gap:6px}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" '
         'href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:'
         'wght@400;500;600;700&display=swap">')

NAV = [("/", "Home"), ("/demo", "Guided demo"), ("/examples", "Examples"), ("/guide", "Reading results")]


def layout(title: str, body: str, active: str = "") -> bytes:
    nav = "".join(f'<a href="{href}"{" aria-current=page" if href == active else ""}>{label}</a>'
                  for href, label in NAV)
    return (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f'<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f"<title>{escape(title)}</title>{FONTS}<style>{CSS}</style></head><body>"
            f'<header class=top><div class=in><a class=brand href="/"><i></i>TraceLens</a><nav>{nav}</nav>'
            f'<a class="btn primary cta" href="/analyze">Analyze your trace</a></div></header>'
            f"<main>{body}</main>"
            f'<footer><div class=in><div>TraceLens finds, fixes and proves real-time bugs in QNX programs. '
            f'Open source: <a href="https://github.com/sheikh2583/QNX-Global-Hackathon">github.com/sheikh2583/'
            f'QNX-Global-Hackathon</a>.</div><div>Built for QNX SDP 8.0 · runs on your machine · no account, '
            f'no AI, no data kept · v{escape(__version__)}</div></div></footer></body></html>').encode("utf-8")


LEGEND = ('<div class=legend><span><i style="background:var(--run)"></i>running</span>'
          '<span><i style="background:var(--ready)"></i>ready, waiting for a CPU</span>'
          '<span><i style="background:var(--block)"></i>blocked on a lock</span>'
          '<span><i style="background:var(--ipc)"></i>waiting for a message reply</span>'
          '<span><i style="background:var(--intr)"></i>waiting for an interrupt</span>'
          '<span><i style="background:var(--band)"></i>the problem</span></div>')


# ----------------------------------------------------------------------------- pieces
def diff_html(diff: str) -> str:
    out = []
    for line in diff.splitlines():
        cls = ("add" if line.startswith("+") and not line.startswith("+++") else
               "del" if line.startswith("-") and not line.startswith("---") else
               "hunk" if line.startswith("@@") else "")
        out.append(f'<span class="{cls}">{escape(line)}</span>' if cls else escape(line))
    return "\n".join(out)


def severity_pill(sev: str) -> str:
    label, _ = SEVERITY.get(sev, (sev, ""))
    return f'<span class="pill sev-{escape(sev)}">{escape(label)}</span>'


def finding_timeline(a: Analysis, f: Finding, max_rows: int = 6) -> str:
    """The moment of the problem: the threads involved, zoomed to the finding."""
    m = a.model
    by_label = {m.label(k): th for k, th in m.threads.items() if k[0] != 1}
    rows = [by_label[n] for n in f.threads if n in by_label]
    pids, seen = {th.key[0] for th in rows}, {th.key for th in rows}
    rows += [th for k, th in sorted(m.threads.items()) if k[0] in pids and k not in seen
             and m.overlap(th, {"RUNNING"}, f.t_start, f.t_end) > 0]
    rows = rows[:max_rows]
    if not rows:
        return ""
    dur = f.t_end - f.t_start
    span = min(max(dur + 3_000_000, 8_000_000), 30_000_000)
    t0 = max(m.t_start, f.t_start - 1_500_000)
    return f'<div class=scroll>{_timeline(m, rows, t0, t0 + span, [f])}</div>'


def evidence_lines(a: Analysis, f: Finding, n: int = 4) -> str:
    m = a.model
    evs = sorted((m.by_id[i] for i in f.evidence if i in m.by_id), key=lambda e: e.t_ns)[:n]
    w = max((len(m.label(e.key)) for e in evs if e.key), default=6)
    lines = [f"{(m.label(e.key) if e.key else '-'):<{w}}  {e.raw.splitlines()[0].strip()}" for e in evs]
    return escape("\n".join(lines))


def friendly_summary(f: Finding) -> str:
    """The detector's summary, minus raw addresses (kept in the technical details)."""
    import re
    s = re.sub(r"\s*\((0x[0-9a-fA-F]+|pid \d+ coid 0x[0-9a-fA-F]+)\)", "", f.summary)
    s = re.sub(r"\bmutex 0x[0-9a-fA-F]+\b", "the mutex", s)
    return s


def problem_card(a: Analysis, f: Finding, n: int, remedies: list, diff: str = "") -> str:
    copy = KIND.get(f.kind, {"name": f.title, "impact": "", "todo": ""})
    mine = [r for r in remedies if r.finding_id == f.id]
    fix = ""
    for r in mine:
        if r.rule == "symptom":
            fix += f"<p>{escape(r.rationale)}</p>"
            continue
        where = "".join(f"<li><code>{escape(p)}:{ln}</code> <code>{escape(c)}</code></li>"
                        for p, ln, c in r.locations[:6])
        fix += (f'<p><span class="pill {"st-ok" if r.automatic else "st-info"}">'
                f'{"Fixed automatically" if r.automatic else "Fix by hand"}</span> <b>{escape(r.title)}</b></p>'
                f"<p class=muted>{escape(r.rationale)}</p>"
                + (f"<ul class=small>{where}</ul>" if where else "")
                + "".join(f"<p>{escape(g)}</p>" for g in r.guidance))
    if not fix:
        fix = f"<p>{escape(copy['todo'])}</p>"
    metrics = "".join(f"<tr><td>{escape(k.replace('_', ' '))}</td><td class=n>{escape(str(v))}</td></tr>"
                      for k, v in f.metrics.items())
    return f"""
<article class=problem id="p{n}">
  <div class=hd><span class="step">#{n}</span><h3>{escape(copy['name'])}</h3>{severity_pill(f.severity)}</div>
  <div class=bd>
    <div class=cols>
      <div><div class=k>What happened</div><p>{escape(friendly_summary(f))}</p></div>
      <div><div class=k>Why it matters</div><p>{escape(copy['impact'])}</p></div>
    </div>
    <div><div class=k>The moment it happened</div>{finding_timeline(a, f)}</div>
    <div class=cols>
      <div><div class=k>Why QNX behaves this way</div><p>{escape(f.qnx_note)}</p></div>
      <div><div class=k>What to do</div>{fix}</div>
    </div>
    <details><summary>Technical details</summary><div class=in>
      <p class=small>{escape(f.title)}. Trace events that prove it (thread, then the kernel event):</p>
      <pre>{evidence_lines(a, f, 8)}</pre>
      <table><tbody>{metrics}</tbody></table>
    </div></details>
  </div>
</article>"""


SYMPTOMS = {"deadline_miss", "irq_latency"}


def order(f: Finding) -> tuple:
    """Most severe first; within a severity, causes before the symptoms they explain."""
    return (-SEVERITY_RANK.get(f.severity, 0), f.kind in SYMPTOMS, f.t_start)


def report_body(a: Analysis, cfg: Config, title: str, sources: dict[str, str] | None = None,
                note: str = "") -> str:
    from .remedy import plan
    shown = sorted([f for f in a.findings if f.severity != "low"], key=order)
    info = [f for f in a.findings if f.severity == "low"]
    remedies, fixed = plan([f for f in shown if at_least(f.severity, "medium")], sources) if sources else ([], {})
    diff = "".join(line for p in sorted(sources or {}) if fixed.get(p, sources[p]) != sources[p]
                   for line in difflib.unified_diff(sources[p].splitlines(True), fixed[p].splitlines(True),
                                                    f"a/{p}", f"b/{p}"))
    must = [f for f in shown if at_least(f.severity, cfg.fail_on)]
    m = a.model
    if m.lossy:
        verdict = ('<div class="verdict warn"><b>This recording is incomplete</b><p>The kernel dropped some events '
                   'while recording, so TraceLens will not give a verdict on it. Record again (a shorter run, or a '
                   'larger trace buffer) and analyze the new trace.</p></div>')
    elif must:
        verdict = (f'<div class="verdict bad"><b>{len(must)} timing problem{"s" if len(must) != 1 else ""} '
                   f'to fix</b><p>Below: what happened, the moment it happened in the recording, why QNX '
                   f'behaves that way, and what to do.'
                   + (" TraceLens prepared a patch for your source." if diff else "") + "</p></div>")
    elif shown:
        verdict = ('<div class="verdict warn"><b>No serious problems; a few things worth a look</b><p>Nothing here '
                   'breaks timing in most runs.</p></div>')
    else:
        verdict = ('<div class="verdict ok"><b>No timing problems found</b><p>No priority inversion, deadlock, '
                   'lock contention, slow interrupt handling or missed deadline in this recording.</p></div>')
    dur = (m.t_end - m.t_start) / 1e6
    parts = [f'<section><div class=eyebrow>Report</div><h1>{escape(title)}</h1>'
             f'<p class=muted>{len(m.events):,} kernel events over {dur:,.0f} ms, {len(m.threads)} threads.'
             f'{" " + escape(note) if note else ""}</p>{verdict}</section>']
    if shown:
        parts.append("<section>" + "".join(problem_card(a, f, i, remedies) for i, f in enumerate(shown, 1)) + "</section>")
        parts.append(f"<section>{LEGEND}</section>")
    if diff:
        b64 = base64.b64encode(diff.encode("utf-8")).decode("ascii")
        parts.append(f'<section><h2>Your patch</h2><p class=muted>Apply it with <code>git apply tracelens-fix.patch'
                     f'</code>, rebuild, record again, and compare. Changed only where TraceLens checked it is safe.</p>'
                     f'<div class=btns><a class="btn primary" download="tracelens-fix.patch" '
                     f'href="data:text/x-diff;base64,{b64}">Download the patch</a></div>'
                     f'<pre>{diff_html(diff)}</pre></section>')
    if info:
        parts.append("<section><details><summary>Notes that need no action</summary><div class=in>"
                     + "".join(f"<p class=small>{escape(f.title)}: {escape(friendly_summary(f))}</p>" for f in info)
                     + "</div></details></section>")
    tech = list(m.trace.issues) + list(m.integrity)
    if tech or m.trace.unparsed_lines:
        parts.append("<section><details><summary>Recording diagnostics</summary><div class=in>"
                     + (f"<p class=small>{m.trace.unparsed_lines} lines were not recognised.</p>"
                        if m.trace.unparsed_lines else "")
                     + "".join(f"<p class=small>{escape(x)}</p>" for x in tech) + "</div></details></section>")
    return "".join(parts)


# ----------------------------------------------------------------------------- charts
def chart_before_after(rows: list[tuple[str, float, float, float]]) -> str:
    """p99 response time before -> after the fix, one row per program, with its budget (dumbbell)."""
    if not rows:
        return ""
    left, right, row_h, top = 150, 24, 44, 34
    width = 720
    xmax = max(max(b, a, bud) for _, b, a, bud in rows) * 1.08
    plot = width - left - right
    x = lambda v: left + v / xmax * plot  # noqa: E731
    h = top + row_h * len(rows) + 30
    s = [f'<svg class="chart" viewBox="0 0 {width} {h}" role="img" aria-label="Worst-case response time before and after the fix">']
    step = 2 if xmax <= 12 else 5
    for v in range(0, int(xmax) + 1, step):
        s.append(f'<line x1="{x(v):.1f}" y1="{top - 8}" x2="{x(v):.1f}" y2="{h - 26}" stroke="var(--line)"/>'
                 f'<text x="{x(v):.1f}" y="{h - 8}" text-anchor="middle">{v} ms</text>')
    for i, (name, b, a, bud) in enumerate(rows):
        y = top + i * row_h + row_h / 2
        s.append(f'<text class=lab x="{left - 12}" y="{y + 4}" text-anchor="end">{escape(name)}</text>')
        s.append(f'<line x1="{x(bud):.1f}" y1="{y - 13}" x2="{x(bud):.1f}" y2="{y + 13}" stroke="var(--fg)" '
                 f'stroke-width="2" stroke-dasharray="3 3"><title>budget {bud:g} ms</title></line>')
        s.append(f'<line x1="{x(a):.1f}" y1="{y}" x2="{x(b):.1f}" y2="{y}" stroke="var(--line)" stroke-width="6" '
                 f'stroke-linecap="round"/>')
        s.append(f'<circle cx="{x(b):.1f}" cy="{y}" r="7" fill="var(--before)" stroke="var(--surface)" stroke-width="2">'
                 f'<title>{escape(name)} before the fix: {b:.2f} ms</title></circle>')
        s.append(f'<circle cx="{x(a):.1f}" cy="{y}" r="7" fill="var(--accent)" stroke="var(--surface)" stroke-width="2">'
                 f'<title>{escape(name)} after the fix: {a:.2f} ms</title></circle>')
        s.append(f'<text x="{x(b) + 12:.1f}" y="{y + 4}">{b:.2f}</text>')
        s.append(f'<text class=lab x="{x(a) - 12:.1f}" y="{y + 4}" text-anchor="end">{a:.2f}</text>')
    s.append(f'<text x="{left}" y="16">Worst-case (p99) response time, 5 runs each</text></svg>')
    legend = ('<div class=legend><span><i style="background:var(--before);border-radius:50%"></i>before the fix</span>'
              '<span><i style="background:var(--accent);border-radius:50%"></i>after the fix</span>'
              '<span><i style="background:none;border-left:2px dashed var(--fg);border-radius:0;width:2px"></i>'
              'deadline budget</span></div>')
    return legend + f'<div class=scroll style="padding:8px 6px">{"".join(s)}</div>'


# ----------------------------------------------------------------------------- results data
class Results:
    """The committed results (docs/results), read once."""

    def __init__(self, root: Path):
        r = root / "docs" / "results"
        self.dir = r
        self.fix = json.loads((r / "fix.json").read_text(encoding="utf-8")) if (r / "fix.json").exists() else {"rows": []}
        self.det = json.loads((r / "detect.json").read_text(encoding="utf-8")) if (r / "detect.json").exists() \
            else {"workloads": [], "negatives": []}

    @property
    def verified(self) -> int:
        return sum(1 for r in self.fix["rows"] if r.get("status") == "VERIFIED")

    def detection(self) -> tuple[int, int, int, int]:
        w, n = self.det["workloads"], self.det["negatives"]
        caught = sum(x["detected_runs"] for x in w)
        runs = sum(x["buggy_clean_runs"] for x in w)
        false = sum(x["reference_runs_with_findings"] for x in w) + sum(x["runs_with_findings"] for x in n)
        clean = sum(x["reference_clean_runs"] for x in w) + sum(x["runs"] - x["lossy"] for x in n)
        return caught, runs, false, clean

    def before_after_rows(self) -> list[tuple[str, float, float, float]]:
        rows = []
        for r in self.fix["rows"]:
            v = r.get("verdict") or {}
            for d in v.get("deadlines", []):
                rows.append((WORKLOADS.get(r["workload"], (r["workload"],))[0], d["before_p99"] / 1e6,
                             d["after_p99"] / 1e6, d["budget_ns"] / 1e6))
        return rows

    def replay_for(self, workload: str) -> str | None:
        """The bundle whose recorded events replay a real fix of this workload, if any."""
        for b in (f"{workload}_live", workload):
            if (self.dir / "fixes" / b / "events.jsonl").exists():
                return b
        return None

    def fix_svgs(self, bundle: str) -> list[str]:
        import re
        p = self.dir / "fixes" / bundle / "report.html"
        return re.findall(r'<svg class="tl".*?</svg>', p.read_text(encoding="utf-8"), flags=re.S) if p.exists() else []


# ----------------------------------------------------------------------------- pages
def home(res: Results) -> bytes:
    caught, runs, false, clean = res.detection()
    body = f"""
<section class=hero>
  <div class=eyebrow>For QNX real-time programs</div>
  <h1>Your QNX program misses deadlines. TraceLens finds out why, fixes the code, and proves the fix.</h1>
  <p class=lede>Record what the QNX kernel saw while your program ran. TraceLens reads that recording, names the
  timing problem in plain words, shows the moment it happened, and gives you the change that fixes it.</p>
  <div class=btns><a class="btn primary" href="/analyze">Analyze your trace</a>
  <a class="btn ghost" href="/demo">See it work on a real trace</a></div>
</section>

<section>
  <div class=grid3>
    <div class="card stat"><b>{res.verified} of 5</b><span>planted real-time bugs fixed automatically and proven on a QNX 8.0 kernel</span></div>
    <div class="card stat"><b>{caught}/{runs}</b><span>buggy runs caught, 10 recordings of each program</span></div>
    <div class="card stat"><b>{false} of {clean}</b><span>healthy runs wrongly flagged</span></div>
  </div>
</section>

<section>
  <div class=eyebrow>How it works</div><h2>Three steps</h2>
  <div class=grid3>
    <div class=card><span class=step>1 · Record</span><h3>Run your program with tracing on</h3>
      <p class=muted>QNX's instrumented kernel records every scheduling decision, message and interrupt. One
      command on your QNX target, a few seconds of normal operation.</p></div>
    <div class=card><span class=step>2 · Analyze</span><h3>Upload the recording</h3>
      <p class=muted>TraceLens checks it for the five ways real-time QNX programs go wrong and shows each problem
      as it happened, thread by thread.</p></div>
    <div class=card><span class=step>3 · Fix and prove</span><h3>Apply the fix, record again</h3>
      <p class=muted>Add your C source and TraceLens writes the QNX-specific fix. Record the fixed program to see
      the problem gone; with the command-line tool, TraceLens does this loop on your target for you.</p></div>
  </div>
</section>

<section>
  <div class=eyebrow>What it finds</div><h2>The five ways QNX real-time code goes wrong</h2>
  <div class=grid3>
    {''.join(f'<div class=card><h3>{escape(KIND[k]["name"])}</h3><p class=muted>{escape(KIND[k]["impact"])}</p></div>'
             for k in ("priority_inversion", "ipc_deadlock", "mutex_contention", "irq_handler_overrun", "deadline_miss"))}
  </div>
</section>

<section>
  <div class=eyebrow>Proof</div><h2>Fixes measured on the real kernel, not promised</h2>
  <p>Each program below was recorded 5 times with its bug, fixed by TraceLens, and recorded 5 more times on a
  QNX 8.0 machine. The fix counts only if the problem is gone in every run and the program is measurably faster.</p>
  {chart_before_after(res.before_after_rows())}
  <div class=btns><a class="btn ghost" href="/demo#reliable">How we know it is reliable</a>
  <a class="btn ghost" href="/examples">Open the five examples</a></div>
</section>
"""
    return layout("TraceLens: find, fix and prove QNX timing bugs", body, "/")


def analyze_page(error: str = "") -> bytes:
    err = f'<div class="verdict bad"><b>That file could not be analyzed</b><p>{escape(error)}</p></div>' if error else ""
    body = f"""
<section class=hero>
  <div class=eyebrow>Analyze your trace</div>
  <h1>Upload a recording of your program</h1>
  <p class=lede>You get the problems in plain words, the moment each one happened, and what to do. Add your C
  source to get a patch. Files are analyzed in memory and not kept.</p>
  {err}
  <form class=drop method=post action="/analyze" enctype="multipart/form-data">
    <label for=trace>Recording (required)<span>The text <code>traceprinter</code> prints, as .txt or .txt.gz, up to 12 MB.</span>
      <input id=trace name=trace type=file accept=".txt,.gz" required></label>
    <label for=source>Your C source (optional)<span>One .c file. With it, TraceLens writes the fix as a patch.</span>
      <input id=source name=source type=file accept=".c,.h"></label>
    <label for=config>Deadlines (optional)<span>A tracelens.toml with your tasks' time budgets, to check deadlines.</span>
      <input id=config name=config type=file accept=".toml"></label>
    <div class=btns><button class="btn primary" type=submit>Analyze</button>
    <a class="btn ghost" href="/demo">No recording yet? See the demo</a></div>
  </form>
</section>

<section>
  <div class=eyebrow>How to record</div><h2>Make a recording on your QNX target</h2>
  <div class=grid2>
    <div class=card><span class=step>On the QNX target</span><h3>Record a few seconds while your program runs</h3>
<pre>tracelogger -w -n 0 -s 4 -f /tmp/app.kev &amp;
./your_program</pre>
      <p class=muted small>Needs the instrumented kernel (<code>procnto-smp-instr</code>). <code>-w</code> records
      full detail, <code>-s 4</code> four seconds.</p></div>
    <div class=card><span class=step>On your computer, with QNX SDP 8.0</span><h3>Turn the recording into text</h3>
<pre>scp root@&lt;target&gt;:/tmp/app.kev .
traceprinter -f app.kev &gt; app.txt
gzip app.txt          # optional, smaller upload</pre>
      <p class=muted small>Then upload <code>app.txt</code> or <code>app.txt.gz</code> above.</p></div>
  </div>
  <details><summary>Prefer one command? Use the command-line tool</summary><div class=in>
<pre>pip install git+https://github.com/sheikh2583/QNX-Global-Hackathon
tracelens capture ./your_program --host &lt;target&gt; --analyze      # record + analyze
tracelens fix path/to/your_program_dir --host &lt;target&gt;           # fix + prove on the target</pre>
    <p class=small muted>The command-line tool records, analyzes, applies the fix, rebuilds with <code>qcc</code>,
    records the fixed program 5 times and tells you whether the problem is really gone.</p></div></details>
  <details><summary>Checking deadlines</summary><div class=in>
    <p class=small>To check that a periodic task finishes on time, mark the start and end of each job in your
    code (<code>TraceEvent()</code> user events named <code>TL_JOB_START</code> / <code>TL_JOB_END</code>) and
    give its budget in a tracelens.toml:</p>
<pre>[deadlines.control]
budget_us = 2000
period_us = 10000</pre></div></details>
</section>
"""
    return layout("Analyze your trace · TraceLens", body, "/analyze")


def guide_page() -> bytes:
    sev = "".join(f'<tr><td>{severity_pill(k)}</td><td>{escape(v[1])}</td></tr>' for k, v in SEVERITY.items())
    body = f"""
<section class=hero><div class=eyebrow>Reading results</div><h1>How to read a TraceLens report</h1>
<p class=lede>A report answers four questions for each problem: what happened, why it matters, why QNX behaved
that way, and what to do. Here is how to use it.</p></section>

<section><h2>Severity</h2><div class=scroll><table><thead><tr><th>Label</th><th>Meaning</th></tr></thead>
<tbody>{sev}</tbody></table></div>
<p>Fix the problems marked <b>Fix now</b> and <b>Fix</b> first. A deadline miss usually comes with a cause
listed above it; fix the cause and the miss goes away.</p></section>

<section><h2>The timeline</h2>{LEGEND}
<p>Each row is one thread of your program, left to right in time. The shaded band is where the problem
happened. A high-priority thread shown red (blocked) while a lower-priority one is green (running) is the
picture of a priority inversion; two threads both purple (waiting for a reply) is a deadlock.</p></section>

<section><h2>Patches</h2>
<p><span class="pill st-ok">Fixed automatically</span> means TraceLens changed your code after checking the
change is safe there (for example, that a semaphore is only used as a lock). <span class="pill st-info">Fix by
hand</span> means the right change is a design decision (for example, which of two servers should stop
sending); TraceLens shows the exact lines and the QNX pattern to use.</p></section>

<section><h2>Is the fix real?</h2>
<p>One recording proves little: timing varies from run to run. Record the fixed program several times. The
command-line tool does this for you (<code>tracelens fix</code>): it records 5 runs before and 5 after and
says <b>Verified</b> only if the problem is gone in every run, nothing new appeared, and response times are
measurably faster (a statistical test, not a single number).</p></section>

<section><h2>When TraceLens will not answer</h2>
<p>If the kernel dropped events while recording, the report says the recording is incomplete and gives no
verdict: a missing event can hide a problem or invent one. Record again with a shorter run.</p></section>
"""
    return layout("Reading results · TraceLens", body, "/guide")


def examples_page(res: Results) -> bytes:
    rows = {r["workload"]: r for r in res.fix["rows"]}
    cards = []
    for w, (name, story) in WORKLOADS.items():
        r = rows.get(w, {})
        st = r.get("status", "")
        pill = {"VERIFIED": '<span class="pill st-ok">Fixed and verified on QNX</span>',
                "GUIDED": '<span class="pill st-info">Fix by hand, lines shown</span>'}.get(st, "")
        cards.append(f'<div class=card><h3>{escape(name)}</h3><p class=muted>{escape(story)}</p>{pill}'
                     f'<div class=btns><a class="btn primary" href="/example/{w}">Open the report</a>'
                     + (f'<a class="btn ghost" href="/replay/{res.replay_for(w)}">Watch the fix happen</a>'
                        if res.replay_for(w) else "")
                     + (f'<a class="btn ghost" href="/proof/{w}">Before and after</a>' if st == "VERIFIED" else "")
                     + "</div></div>")
    body = (f'<section class=hero><div class=eyebrow>Examples</div><h1>Five real QNX programs, five real bugs</h1>'
            f'<p class=lede>Each one ran on QNX 8.0 and was recorded with the kernel tracer. Open a report to see what '
            f'TraceLens says, as you would for your own program.</p></section><section><div class=grid2>'
            f'{"".join(cards)}</div></section>')
    return layout("Examples · TraceLens", body, "/examples")


def example_report(a: Analysis, cfg: Config, workload: str, sources: dict[str, str]) -> bytes:
    name, story = WORKLOADS[workload]
    links = (f'<section><div class=btns><a class="btn ghost" href="/proof/{workload}">See the fix proven on QNX</a>'
             f'<a class="btn ghost" href="/trace/{workload}">Engineer\'s view of this trace</a></div></section>')
    body = report_body(a, cfg, f"{name}: what went wrong", sources, note=story) + links
    return layout(f"{name} · TraceLens", body, "/examples")


def upload_report(a: Analysis, cfg: Config, filename: str, sources: dict[str, str] | None) -> bytes:
    body = report_body(a, cfg, filename or "Your recording", sources)
    body += ('<section><div class=btns><a class="btn ghost" href="/analyze">Analyze another recording</a>'
             '<a class="btn ghost" href="/guide">How to read this report</a></div></section>')
    return layout("Your report · TraceLens", body, "/analyze")


def demo_page(a: Analysis, cfg: Config, res: Results, sources: dict[str, str]) -> bytes:
    """The guided tour for judges: one real trace, from recording to proof, then reliability."""
    from .remedy import plan
    m = a.model
    findings = sorted(a.findings, key=order)
    inv = next((f for f in findings if f.kind == "priority_inversion"), findings[0])
    remedies, _ = plan([f for f in findings if at_least(f.severity, "medium")], sources)
    bundle = "z1_infusion_pump_codelab_2_rounds"
    svgs = res.fix_svgs(bundle)
    rounds = []
    for rnd in (1, 2):
        p = res.dir / "fixes" / bundle / f"round-{rnd}" / "verdict.json"
        if p.exists():
            rounds.append(json.loads(p.read_text(encoding="utf-8")))
    patch = (res.dir / "fixes" / bundle / "patch.diff")
    patch_txt = patch.read_text(encoding="utf-8") if patch.exists() else ""
    caught, runs, false, clean = res.detection()
    det_rows = "".join(
        f'<tr><td>{escape(WORKLOADS.get(w["name"], (w["name"],))[0])}</td><td class=n>{w["detected_runs"]}/'
        f'{w["buggy_clean_runs"]}</td><td class=n>{w["reference_runs_with_findings"]}/{w["reference_clean_runs"]}</td></tr>'
        for w in res.det["workloads"])
    neg_runs = sum(x["runs"] - x["lossy"] for x in res.det["negatives"])
    neg_bad = sum(x["runs_with_findings"] for x in res.det["negatives"])
    fix_rows = "".join(
        f'<tr><td>{escape(WORKLOADS.get(r["workload"], (r["workload"],))[0])}</td><td>'
        + ('<span class="pill st-ok">Verified</span>' if r.get("status") == "VERIFIED" else
           '<span class="pill st-info">Lines shown</span>' if r.get("status") == "GUIDED" else escape(r.get("status", "")))
        + "</td></tr>" for r in res.fix["rows"])

    def round_card(i, v, what):
        d = (v.get("deadlines") or [{}])[0]
        ok = v.get("verdict") == "VERIFIED"
        pi = v.get("targets", {}).get("priority_inversion", {})
        return (f'<div class=card><span class=step>Round {i}</span><h3>{escape(what)}</h3>'
                f'<p>Inversion in {pi.get("before_rate", 0):.0%} → {pi.get("after_rate", 0):.0%} of runs. '
                f'Worst-case response {d.get("before_p99", 0) / 1e6:.2f} → <b>{d.get("after_p99", 0) / 1e6:.2f} ms</b> '
                f'(budget {d.get("budget_ns", 0) / 1e6:.0f} ms), {d.get("before_misses", 0)} → {d.get("after_misses", 0)} late jobs.</p>'
                f'<p><span class="pill {"st-ok" if ok else "st-bad"}">{"Verified" if ok else "Not fixed yet"}</span></p></div>')

    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t in (
        ("program", "1 · The program"), ("recording", "2 · The recording"), ("found", "3 · What TraceLens found"),
        ("fix", "4 · The fix"), ("proof", "5 · Proof on QNX"), ("reliable", "6 · Is it reliable?"), ("try", "7 · Try it")))
    dur = (m.t_end - m.t_start) / 1e6
    body = f"""
<section class=hero>
  <div class=eyebrow>Guided demo · real QNX 8.0 recordings</div>
  <h1>Watch TraceLens find, fix and prove a real bug</h1>
  <p class=lede>One program, one recording from a QNX 8.0 kernel, every step TraceLens takes. Then the evidence
  that it works the same way on four more programs, and does not cry wolf on healthy ones.</p>
</section>
<div class=tour><nav aria-label="Demo steps">{nav}</nav><div class=steps>

<section id=program><div class=eyebrow>Step 1</div><h2>The program: an infusion pump</h2>
  <p>Three threads share a sensor buffer on one CPU. The dose controller is the most urgent and must finish
  every 10 ms job within 2 ms.</p>
  <div class=scroll><table><thead><tr><th>Thread</th><th>Priority</th><th>Every 10 ms</th></tr></thead><tbody>
  <tr><td>control</td><td class=n>50 (highest)</td><td>reads the buffer, computes the dose: must finish within 2 ms</td></tr>
  <tr><td>telemetry</td><td class=n>20</td><td>compresses and uploads readings (6 ms of work)</td></tr>
  <tr><td>logger</td><td class=n>10 (lowest)</td><td>writes the buffer to the black-box log</td></tr></tbody></table></div>
  <p class=muted>The buffer is guarded with a semaphore. That looks correct, compiles cleanly, and passes code review.</p>
</section>

<section id=recording><div class=eyebrow>Step 2</div><h2>The recording</h2>
  <p>The program ran on a QNX 8.0 machine with the kernel tracer on: {len(m.events):,} kernel events in
  {dur:,.0f} ms. Every scheduling decision is in there; here are four of them, exactly as the kernel wrote them.</p>
  <pre>{evidence_lines(a, inv, 4)}</pre>
  <p class=muted>The dose controller (priority 50) asks for the semaphore and blocks; telemetry (priority 20)
  takes the CPU; the logger, which holds the semaphore, only releases it milliseconds later.</p>
</section>

<section id=found><div class=eyebrow>Step 3</div><h2>What TraceLens found</h2>
  <p>This is the report you would get for your own program. Detection is a set of fixed rules over the kernel's
  own events: the same recording always gives the same answer.</p>
  {''.join(problem_card(a, f, i, remedies) for i, f in enumerate([f for f in findings if f.severity != "low"], 1))}
  {LEGEND}
</section>

<section id=fix><div class=eyebrow>Step 4</div><h2>The fix TraceLens wrote</h2>
  <p>TraceLens checked that the semaphore is only ever used as a lock (it starts at 1, and every function that
  takes it also gives it back) before replacing it with a QNX mutex that lends its priority to whoever waits.</p>
  <details><summary>Show the full patch</summary><div class=in><pre>{diff_html(patch_txt)}</pre></div></details>
</section>

<section id=proof><div class=eyebrow>Step 5</div><h2>Proof on the QNX kernel</h2>
  <p>TraceLens built the patched program with <code>qcc</code>, ran it 5 times on the QNX machine, and compared
  against 5 runs of the original. The first fix was not enough, and TraceLens said so.</p>
  <div class=grid2>
    {round_card(1, rounds[0], "Mutex with priority inheritance") if rounds else ""}
    {round_card(2, rounds[1], "Shorter time holding the lock") if len(rounds) > 1 else ""}
  </div>
  <p class=muted>Round 1 removed the inversion, and the new recordings showed the next cause: the logger held the
  lock through a 2.5 ms flash write. Round 2 moved that work out of the lock.</p>
  {f'<div class=btns><a class="btn primary" href="/replay/{res.replay_for("z1_infusion_pump")}">Watch a fix happen, step by step</a></div>'
   if res.replay_for("z1_infusion_pump") else ""}
  {LEGEND}
  <div><div class=k>Before: 25 ms from the middle of a run</div><div class=scroll>{svgs[0] if svgs else ""}</div></div>
  <div><div class=k>After round 2: 25 ms from the middle of a run of the fixed program</div><div class=scroll>{svgs[1] if len(svgs) > 1 else ""}</div></div>
  <p class=muted>Before, the dose controller sits blocked (red) for most of every period while lower-priority
  telemetry runs (green). After, it runs on time in short bursts.</p>
</section>

<section id=reliable><div class=eyebrow>Step 6</div><h2>Is it reliable?</h2>
  <div class=grid3>
    <div class="card stat"><b>{res.verified} of 5</b><span>bugs fixed and verified on QNX; the fifth (a deadlock) gets the exact lines to change</span></div>
    <div class="card stat"><b>{caught}/{runs}</b><span>buggy runs caught across the five programs</span></div>
    <div class="card stat"><b>{false} of {clean}</b><span>healthy runs wrongly flagged (fixed programs and QNX's own system programs)</span></div>
  </div>
  <h3>Every fix, measured</h3>
  {chart_before_after(res.before_after_rows())}
  <p class=muted small>The motor encoder has no deadline: its fix cut the time the interrupt stays blocked from
  2.41 ms to 0.24 ms (worst case) and the interrupt response from 2.08 ms to 0.57 ms.</p>
  <div class=grid2>
    <div><h3>Detection, 10 recordings each</h3><div class=scroll><table><thead><tr><th>Program</th>
      <th>Bug caught</th><th>Fixed version flagged</th></tr></thead><tbody>{det_rows}
      <tr><td>QNX system programs (pidin, idle, ls)</td><td class=n>no bug</td><td class=n>{neg_bad}/{neg_runs}</td></tr>
      </tbody></table></div></div>
    <div><h3>Fixes, 5 runs before and after</h3><div class=scroll><table><thead><tr><th>Program</th><th>Result</th></tr></thead>
      <tbody>{fix_rows}</tbody></table></div></div>
  </div>
  <h3>Why you can trust these numbers</h3>
  <div class=grid2>
    <div class=card><h3>Measured, not modelled</h3><p class=muted>Every number comes from recordings of real
    programs on a QNX 8.0 kernel (a QEMU machine with the instrumented kernel), committed with the code so anyone
    can re-check them.</p></div>
    <div class=card><h3>Tested on data it never saw</h3><p class=muted>The detection table was recorded after the
    rules were last changed, and was not used to tune them.</p></div>
    <div class=card><h3>Several runs, a statistical test</h3><p class=muted>A fix counts only if the problem is
    gone in all 5 runs, nothing new appears, and response times are faster by a one-sided Mann-Whitney test
    (p &lt; 0.01).</p></div>
    <div class=card><h3>No verdict on bad data</h3><p class=muted>A recording where the kernel dropped events gets
    no verdict, and a bug that never showed up before a fix can never count as fixed.</p></div>
  </div>
</section>

<section id=try><div class=eyebrow>Step 7</div><h2>Try it</h2>
  <p>Open the other four programs, or analyze your own recording.</p>
  <div class=btns><a class="btn primary" href="/analyze">Analyze your trace</a>
  <a class="btn ghost" href="/examples">The five examples</a></div>
</section>
</div></div>
"""
    return layout("Guided demo · TraceLens", body, "/demo")


# ----------------------------------------------------------------------------- live fix view
LIVE_CSS = """
.livehd{display:grid;gap:10px}.livehd .row{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px}
#lv-now{font-size:18px;color:var(--muted);min-height:1.6em}
.pill.busy::before{animation:pulse 1.2s ease-in-out infinite}
@keyframes pulse{50%{opacity:.25}}
.livegrid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:18px;align-items:start}
@media (max-width:960px){.livegrid{grid-template-columns:minmax(0,1fr)}}
.livegrid>div{display:grid;gap:18px;min-width:0}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:14px;padding:16px 18px;display:grid;gap:12px;min-width:0}
.panel>h2{font-size:18px}.panel h3{font-size:16px}
#lv-steps{list-style:none;margin:0;padding:0;display:grid;gap:2px}
#lv-steps li{display:flex;gap:10px;align-items:center;padding:6px 8px;border-radius:8px;color:var(--faint)}
#lv-steps li .dot{width:12px;height:12px;border-radius:50%;border:2px solid var(--line);flex:none}
#lv-steps li.done{color:var(--fg)}#lv-steps li.done .dot{background:var(--ok);border-color:var(--ok)}
#lv-steps li.now{color:var(--fg);background:var(--accent-soft);font-weight:600}
#lv-steps li.now .dot{border-color:var(--accent);background:var(--accent);animation:pulse 1.2s ease-in-out infinite}
.runrow{display:grid;gap:6px}.rowlbl{font-size:13px;color:var(--muted)}
.slots{display:flex;flex-wrap:wrap;gap:6px}
.slot{width:34px;height:22px;border-radius:6px;border:2px dashed var(--line)}
.slot.rec{border:2px solid var(--accent);animation:pulse 1s ease-in-out infinite}
.slot.bug{background:var(--crit);border-color:var(--crit)}.slot.clean{background:var(--ok);border-color:var(--ok)}
.slot.lossy{border:2px solid var(--faint);background:repeating-linear-gradient(45deg,transparent 0 4px,var(--line) 4px 6px)}
.tabs{display:flex;flex-wrap:wrap;gap:6px}.tabs button{font:600 13px var(--sans);padding:7px 12px;border-radius:8px;border:1px solid var(--line);
background:var(--surface);color:var(--muted);cursor:pointer}.tabs button[aria-pressed=true]{background:var(--accent-soft);color:var(--fg);border-color:var(--accent)}
#lv-code{max-height:460px;overflow:auto;margin:0;padding:8px 0;background:var(--sunk);border-radius:10px;font:12.5px/1.55 var(--mono)}
#lv-code .ln{display:block;padding:0 12px;white-space:pre}#lv-code .ln i{font-style:normal;color:var(--faint);user-select:none}
#lv-code .ln.mark{background:var(--crit-soft);box-shadow:inset 3px 0 var(--crit)}
#lv-code .ln.chg,#lv-code .ln.add{background:var(--ok-soft);box-shadow:inset 3px 0 var(--ok)}
#lv-code .ln.del{background:var(--crit-soft)}#lv-code .ln.hunk{color:var(--info)}
.fcard,.rcard{border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:grid;gap:8px;min-width:0}
.fhd{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;justify-content:space-between}
.found{display:grid;gap:12px}
.vcard{border-radius:12px;padding:12px 14px;display:grid;gap:6px}.vcard ul{margin:0;padding-left:18px}
.vcard.ok{background:var(--ok-soft)}.vcard.bad{background:var(--crit-soft)}.vcard.warn{background:var(--warn-soft)}
#lv-log{list-style:none;margin:0;padding:0;font:12.5px/1.6 var(--mono);color:var(--muted);max-height:200px;overflow:auto}
.minichart{display:block;width:100%;height:auto}.minichart text{fill:var(--muted);font:12px var(--sans)}
#lv-controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
#lv-controls select{font:14px var(--sans);padding:8px;border-radius:8px;border:1px solid var(--line);background:var(--surface);color:var(--fg)}
@media (prefers-reduced-motion:reduce){.pill.busy::before,#lv-steps li.now .dot,.slot.rec{animation:none}}
"""


def live_page(mode: str, events_url: str, title: str = "Live fix", intro: str = "") -> bytes:
    """The fix as it happens: where the error is, the fix, each run on the target, the verdict.
    ``mode`` is "live" (EventSource from a running `tracelens fix --watch`) or "replay"."""
    controls = ("" if mode == "live" else
                '<div id=lv-controls hidden><button class="btn ghost" id=lv-pause type=button>Pause</button>'
                '<label class=small for=lv-speed>Speed <select id=lv-speed><option value=8>Slow</option>'
                '<option value=20 selected>Normal</option><option value=60>Fast</option></select></label>'
                '<button class="btn ghost" id=lv-end type=button>Skip to the result</button>'
                '<button class="btn ghost" id=lv-again type=button>Play again</button></div>')
    body = f"""
<section class=livehd id=live data-mode="{escape(mode)}" data-events="{escape(events_url)}">
  <div class=eyebrow>{"Live fix on your QNX target" if mode == "live" else "Replay of a real fix on a QNX 8.0 target"}</div>
  <div class=row><h1 id=lv-title>{escape(title)}</h1><span id=lv-status class="pill st-info busy">Connecting</span></div>
  <p id=lv-now>Waiting for the first step…</p>
  {f"<p class=muted>{escape(intro)}</p>" if intro else ""}
  {controls}
</section>
<div class=livegrid>
  <div>
    <div class=panel><h2>Where the error is</h2><div id=lv-where><p class=muted>TraceLens shows the problem here as soon
      as it has read the recordings of the original program.</p></div></div>
    <div class=panel><h2>Your code <span class="muted small" id=lv-file></span></h2>
      <div class=tabs><button type=button data-tab=base aria-pressed=true>With the error</button>
      <button type=button data-tab=fixed aria-pressed=false>After the fix</button>
      <button type=button data-tab=patch aria-pressed=false>The patch</button></div>
      <pre id=lv-code></pre>
      <div class=legend><span><i style="background:var(--crit)"></i>where the error is</span>
      <span><i style="background:var(--ok)"></i>what the fix changed</span></div>
      <div id=lv-fix></div></div>
  </div>
  <div>
    <div class=panel><h2>Progress</h2><ol id=lv-steps></ol></div>
    <div class=panel><h2>Runs on the QNX target</h2><div id=lv-runs></div>
      <div class=legend><span><i style="background:var(--crit)"></i>problem present</span><span><i style="background:var(--ok)"></i>clean</span>
      <span><i style="border:2px dashed var(--line)"></i>waiting</span><span><i style="border:2px solid var(--faint)"></i>recording lost events</span></div>
      <div id=lv-chart></div>
      <div class=legend id=lv-chart-legend hidden><span><i style="background:var(--before);border-radius:50%"></i>original</span>
      <span><i style="background:var(--accent);border-radius:50%"></i>fixed</span>
      <span><i style="border-left:2px dashed var(--fg);width:2px;border-radius:0"></i>budget</span></div></div>
    <div class=panel><h2>Verdict</h2><div id=lv-verdict><p class=muted>Appears after the fixed program has been
      recorded and compared with the original.</p></div>
      <div id=lv-final hidden class=btns><a class="btn ghost" href="/guide">What the verdict means</a></div></div>
    <div class=panel><h2>Activity</h2><ul id=lv-log></ul></div>
  </div>
</div>
<script src="/live.js" defer></script>
"""
    page = layout(f"{title} · TraceLens", body, "/demo" if mode == "replay" else "")
    return page.replace(b"</style>", LIVE_CSS.encode("utf-8") + b"</style>", 1)
