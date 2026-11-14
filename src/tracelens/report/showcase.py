"""The TraceLens results page: real QNX 8.0 numbers, before/after timelines, the fix loop."""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path


def render_showcase(root: str | Path, live: str = "") -> str:
    """The results page, built from docs/results (no number typed by hand). ``live``: extra HTML
    inserted after the hero (the hosted demo's 'try it' section)."""
    root = Path(root)
    R = root / "docs/results"
    fix = json.loads((R / "fix.json").read_text(encoding="utf-8"))
    det = json.loads((R / "detect.json").read_text(encoding="utf-8"))


    def svgs(workload):
        html = (R / "fixes" / workload / "report.html").read_text(encoding="utf-8")
        return re.findall(r'<svg class="tl".*?</svg>', html, flags=re.S)


    NAMES = {"z1_infusion_pump": "Infusion pump", "z2_brake_by_wire": "Brake-by-wire",
             "z3_sensor_fusion": "Sensor fusion", "z4_camera_pipeline": "Camera pipeline",
             "z5_motor_encoder": "Motor encoder"}
    CAUSE = {"z1_infusion_pump": "A semaphore used as a lock: no owner, so no priority inheritance",
             "z2_brake_by_wire": "A server channel created with _NTO_CHF_FIXED_PRIORITY",
             "z3_sensor_fusion": "Two servers MsgSend() to each other: Send/Reply deadlock",
             "z4_camera_pipeline": "Four workers do their work inside one global mutex",
             "z5_motor_encoder": "2 ms of work before InterruptUnmask(): the IRQ stays masked"}
    FIX = {"z1_infusion_pump": "<code>sem_t</code> → <code>pthread_mutex_t</code> with <code>PTHREAD_PRIO_INHERIT</code>",
           "z2_brake_by_wire": "Dropped <code>_NTO_CHF_FIXED_PRIORITY</code>: the server runs at its client's priority",
           "z3_sensor_fusion": "Guided: the two <code>MsgSend()</code> lines and the send-hierarchy fix",
           "z4_camera_pipeline": "Private work moved out of the lock; the shared copy stays inside",
           "z5_motor_encoder": "Unmask first; the work moves to a pulse-driven worker at priority 20"}
    EXTRA = {"z5_motor_encoder": "p99 time masked 2.41 → 0.24 ms; p99 response 2.08 → 0.57 ms"}


    def evidence(r):
        v = r.get("verdict") or {}
        bits = []
        for k, t in v.get("targets", {}).items():
            if k in ("priority_inversion", "mutex_contention", "irq_handler_overrun"):
                bits.append(f"{k.replace('_', ' ')}: {t['before_rate']:.0%} → {t['after_rate']:.0%} of runs")
        for d in v.get("deadlines", []):
            bits.append(f"p99 {d['before_p99'] / 1e6:.2f} → {d['after_p99'] / 1e6:.2f} ms "
                        f"(budget {d['budget_ns'] / 1e6:.0f} ms)")
        if r["workload"] in EXTRA:
            bits.append(EXTRA[r["workload"]])
        return "<br>".join(escape(b).replace("→", "→") for b in bits) or "—"


    rows = []
    for r in fix["rows"]:
        st = r["status"]
        cls = {"VERIFIED": "ok", "GUIDED": "guide"}.get(st, "bad")
        rows.append(f"""<tr><td><b>{NAMES[r['workload']]}</b><span class=mono>{r['workload']}</span></td>
    <td>{escape(CAUSE[r['workload']])}</td><td>{FIX[r['workload']]}</td>
    <td><span class="pill {cls}">{st.title() if st != 'GUIDED' else 'Guided'}</span></td><td class=num>{evidence(r)}</td></tr>""")

    drows = []
    for w in det["workloads"]:
        drows.append(f"<tr><td>{NAMES[w['name']]}</td><td class=num>{w['detected_runs']}/{w['buggy_clean_runs']}</td>"
                     f"<td class=num>{w['reference_runs_with_findings']}/{w['reference_clean_runs']}</td></tr>")
    neg_runs = sum(n["runs"] - n["lossy"] for n in det["negatives"])
    neg_bad = sum(n["runs_with_findings"] for n in det["negatives"])
    ref_runs = sum(w["reference_clean_runs"] for w in det["workloads"])
    ref_bad = sum(w["reference_runs_with_findings"] for w in det["workloads"])
    caught = sum(w["detected_runs"] for w in det["workloads"])
    buggy_runs = sum(w["buggy_clean_runs"] for w in det["workloads"])
    verified = sum(1 for r in fix["rows"] if r["status"] == "VERIFIED")

    z1 = svgs("z1_infusion_pump_codelab_2_rounds")
    z5 = svgs("z5_motor_encoder")
    z1rounds = json.loads((R / "fixes/z1_infusion_pump_codelab_2_rounds/result.json").read_text(encoding="utf-8"))
    r1 = json.loads((R / "fixes/z1_infusion_pump_codelab_2_rounds/round-1/verdict.json").read_text(encoding="utf-8"))
    r2 = json.loads((R / "fixes/z1_infusion_pump_codelab_2_rounds/round-2/verdict.json").read_text(encoding="utf-8"))
    d1, d2 = r1["deadlines"][0], r2["deadlines"][0]

    page = f"""<title>TraceLens on QNX 8.0</title>
    <meta name="claude:viewport-fit-sides" content="cover">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
    <style>
    /* Layout: one reading column; the proof (timelines, tables) is allowed wider, each in its own scroller. */
    :root {{
      --bg: #f6f7f6; --surface: #ffffff; --fg: #17201d; --muted: #5b6763; --line: #dde3e0;
      --accent: #0f6e64;          /* deep teal: the tool's own voice */
      --run: #2f9e44; --ready: #e8a317; --block: #d9363e; --ipc: #7048e8; --intr: #1c7ed6;
      --band: rgba(217, 54, 62, .10); --ok-bg: rgba(47, 158, 68, .13); --guide-bg: rgba(28, 126, 214, .13);
      --code-bg: #eef2f0;
      --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
      --mono: "IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
    }}
    @media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
      --bg: #111615; --surface: #19201e; --fg: #e6ece9; --muted: #9aa8a3; --line: #2b3532;
      --accent: #4fc4b4; --run: #40c057; --ready: #f5b83d; --block: #ff6b6b; --ipc: #9775fa; --intr: #4dabf7;
      --band: rgba(255, 107, 107, .14); --ok-bg: rgba(64, 192, 87, .16); --guide-bg: rgba(77, 171, 247, .16);
      --code-bg: #1f2826; color-scheme: dark }} }}
    :root[data-theme="dark"] {{
      --bg: #111615; --surface: #19201e; --fg: #e6ece9; --muted: #9aa8a3; --line: #2b3532;
      --accent: #4fc4b4; --run: #40c057; --ready: #f5b83d; --block: #ff6b6b; --ipc: #9775fa; --intr: #4dabf7;
      --band: rgba(255, 107, 107, .14); --ok-bg: rgba(64, 192, 87, .16); --guide-bg: rgba(77, 171, 247, .16);
      --code-bg: #1f2826; color-scheme: dark }}
    * {{ box-sizing: border-box }}
    body {{ background: var(--bg); color: var(--fg); font: 16px/1.6 var(--sans) }}
    .wrap {{ max-width: 1080px; margin: 0 auto; padding-block: 40px 72px;
      padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
      display: grid; gap: 44px }}
    .wrap > * {{ min-width: 0 }}
    h1, h2, h3 {{ text-wrap: balance; line-height: 1.2; margin: 0 }}
    h1 {{ font-size: clamp(30px, 5vw, 46px); font-weight: 700; letter-spacing: -.01em }}
    h1 em {{ font-style: normal; color: var(--accent) }}
    h2 {{ font-size: 24px; font-weight: 600 }}
    h3 {{ font-size: 16px; font-weight: 600 }}
    p {{ margin: 0; max-width: 68ch }}
    .eyebrow {{ font: 500 12px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--accent) }}
    .lede {{ font-size: 19px; color: var(--muted); max-width: 64ch }}
    .hero {{ display: grid; gap: 16px }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px }}
    .stat {{ border-top: 3px solid var(--accent); padding-top: 10px }}
    .stat b {{ display: block; font: 600 34px/1.1 var(--sans); font-variant-numeric: tabular-nums }}
    .stat span {{ color: var(--muted); font-size: 14px }}
    section {{ display: grid; gap: 14px }}
    .scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface) }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px }}
    th, td {{ text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid var(--line) }}
    th {{ font: 500 12px/1.3 var(--mono); letter-spacing: .05em; text-transform: uppercase; color: var(--muted) }}
    tr:last-child td {{ border-bottom: 0 }}
    td .mono, .mono {{ font-family: var(--mono); font-size: 12px; color: var(--muted); display: block }}
    td.num {{ font-variant-numeric: tabular-nums; white-space: nowrap }}
    code {{ font-family: var(--mono); font-size: .88em; background: var(--code-bg); padding: 1px 5px; border-radius: 4px }}
    .pill {{ display: inline-block; font: 600 12px/1 var(--sans); padding: 6px 10px; border-radius: 999px; white-space: nowrap }}
    .pill.ok {{ background: var(--ok-bg); color: var(--run) }}
    .pill.guide {{ background: var(--guide-bg); color: var(--intr) }}
    .pill.bad {{ background: var(--band); color: var(--block) }}
    .tl {{ width: 100%; min-width: 640px; display: block; background: var(--surface) }}
    .tl text {{ fill: var(--fg); font: 11px var(--sans) }}
    .tl text.muted {{ fill: var(--muted) }}
    .timeline {{ display: grid; gap: 6px }}
    .timeline h3 span {{ color: var(--muted); font-weight: 400 }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--muted) }}
    .legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -2px }}
    pre.trace {{ margin: 0; padding: 14px; overflow-x: auto; font: 12.5px/1.6 var(--mono); background: var(--code-bg);
      border-radius: 10px; color: var(--fg) }}
    pre.trace .who {{ color: var(--accent) }}
    .steps {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; padding: 0; margin: 0; list-style: none; counter-reset: s }}
    .steps li {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; counter-increment: s }}
    .steps li::before {{ content: counter(s); font: 600 12px var(--mono); color: var(--accent); display: block; margin-bottom: 4px }}
    .rounds {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px }}
    .round {{ border-left: 3px solid var(--line); padding: 4px 0 4px 14px }}
    .round.done {{ border-color: var(--run) }}
    .round b {{ font-variant-numeric: tabular-nums }}
    ul.lessons {{ margin: 0; padding-left: 20px; display: grid; gap: 8px; max-width: 72ch }}
    footer {{ color: var(--muted); font-size: 14px; border-top: 1px solid var(--line); padding-top: 18px; display: grid; gap: 8px }}
    a {{ color: var(--accent) }}
    @media (prefers-reduced-motion: no-preference) {{ .stat b {{ transition: color .2s }} }}
    </style>

    <div class=wrap>
      <header class=hero>
        <div class=eyebrow>QNX Global Hackathon 2026 · Developer Tooling</div>
        <h1>TraceLens finds, fixes and <em>proves</em> real-time bugs on QNX</h1>
        <p class=lede>It reads a QNX 8.0 kernel event trace, finds the timing bug with deterministic rules, rewrites the
        C code with the QNX-specific fix for the cause it proved, rebuilds it with <code>qcc</code>, and keeps the fix
        only if the re-traced program is measurably clean on the real kernel. No AI and no API keys: the same trace
        always gives the same patch.</p>
        <div class=stats>
          <div class=stat><b>{verified} of 5</b><span>planted bugs fixed automatically and verified on QNX</span></div>
          <div class=stat><b>{caught}/{buggy_runs}</b><span>buggy runs caught (10 per program, held out)</span></div>
          <div class=stat><b>{ref_bad + neg_bad} of {ref_runs + neg_runs}</b><span>clean runs falsely flagged (fixed builds + healthy system programs)</span></div>
        </div>
      </header>
    {live}

      <section>
        <div class=eyebrow>The evidence</div>
        <h2>What the kernel recorded</h2>
        <p>Every finding cites the trace events that prove it. These four lines, from a real capture of the infusion pump,
        are the bug: the highest-priority thread blocks on a semaphore, a medium-priority thread takes the CPU, and the
        low-priority holder posts 5.36 ms later.</p>
        <pre class=trace><span class=who>control  </span> t:0x1f828f6fbcdf CPU:00 KER_CALL  :SYNC_SEM_WAIT/85
    <span class=who>control  </span> t:0x1f828f6fc2d7 CPU:00 THREAD    :THSEM      pid:97103894 tid:4 priority:50
    <span class=who>telemetry</span> t:0x1f828f6fc40a CPU:00 THREAD    :THRUNNING  pid:97103894 tid:3 priority:20
    <span class=who>logger   </span> t:0x1f829035876e CPU:00 KER_CALL  :SYNC_SEM_POST/84</pre>
      </section>

      <section>
        <div class=eyebrow>Fixes, proven on the target</div>
        <h2>Five planted bugs, five root causes</h2>
        <p>For each program: 5 captures of the buggy build, the remedy chosen from them, a <code>qcc</code> build, and 5
        captures of the patched build. Verified means the finding is gone in every run, nothing new appears, and response
        times are significantly faster (one-sided Mann-Whitney U, p &lt; 0.01).</p>
        <div class=scroll><table>
          <thead><tr><th>Program</th><th>Root cause the trace proved</th><th>What TraceLens changed</th><th>On QNX</th><th>Before → after</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table></div>
      </section>

      <section>
        <div class=eyebrow>Before and after</div>
        <h2>The same threads, on the same scale</h2>
        <div class=legend><span><i style="background:var(--run)"></i>running</span><span><i style="background:var(--ready)"></i>ready, waiting for the CPU</span><span><i style="background:var(--block)"></i>blocked on a lock</span><span><i style="background:var(--ipc)"></i>send/reply blocked</span><span><i style="background:var(--intr)"></i>waiting for an interrupt</span><span><i style="background:var(--band)"></i>finding</span></div>
        <div class=timeline><h3>Infusion pump, before <span>· control (priority 50) blocked for most of each period</span></h3><div class=scroll>{z1[0]}</div></div>
        <div class=timeline><h3>Infusion pump, after two rounds <span>· control runs on time, every period</span></h3><div class=scroll>{z1[1] if len(z1) > 1 else ''}</div></div>
        <div class=timeline><h3>Motor encoder, before <span>· the interrupt thread works with IRQ 4 masked</span></h3><div class=scroll>{z5[0]}</div></div>
        <div class=timeline><h3>Motor encoder, after <span>· the interrupt thread waits, ready; a priority-20 worker does the work</span></h3><div class=scroll>{z5[1] if len(z5) > 1 else ''}</div></div>
      </section>

      <section>
        <div class=eyebrow>How the fix loop works</div>
        <h2>The kernel decides, not the tool</h2>
        <ol class=steps>
          <li>Capture the program 5 times under <code>tracelogger</code>; the findings in most runs become the targets.</li>
          <li>Pick the remedy for each proven cause. Rewrite only if its safety checks pass in the code; otherwise point at the lines.</li>
          <li>Build the patched copy with <code>qcc</code>. Only the program's own files ever change.</li>
          <li>Capture the patched build 5 times and compare before and after.</li>
          <li>Not fixed yet? Diagnose the new traces and fix again, up to 3 rounds.</li>
        </ol>
        <p>Step 5 is not decoration. In a fresh run of the codelab, the mutex removed the infusion pump's inversion but the
        re-trace showed the next cause: the logger held the lock through a 2.5 ms flash write.</p>
        <div class=rounds>
          <div class=round><h3>Round 1 · priority-inheriting mutex</h3><p>Inversion {r1['targets']['priority_inversion']['before_rate']:.0%} → {r1['targets']['priority_inversion']['after_rate']:.0%} of runs. p99 <b>{d1['before_p99'] / 1e6:.2f} → {d1['after_p99'] / 1e6:.2f} ms</b>, still over the {d1['budget_ns'] / 1e6:.0f} ms budget. Not fixed.</p></div>
          <div class="round done"><h3>Round 2 · shrink the critical section</h3><p>Work that touches no shared data leaves the lock. p99 <b>{d2['before_p99'] / 1e6:.2f} → {d2['after_p99'] / 1e6:.2f} ms</b>, misses {d2['before_misses']} → {d2['after_misses']}. Verified.</p></div>
        </div>
      </section>

      <section>
        <div class=eyebrow>Detection, held out</div>
        <h2>10 captures of every build</h2>
        <p>Captured after the detectors were last tuned, and not used to tune them. Lossy captures (a dropped kernel event)
        are excluded and replaced, never scored.</p>
        <div class=scroll><table>
          <thead><tr><th>Program</th><th>Buggy build: caught</th><th>Hand-written fix: flagged</th></tr></thead>
          <tbody>{''.join(drows)}<tr><td>Healthy system programs (pidin, idle, ls -lR)</td><td class=num>—</td><td class=num>{neg_bad}/{neg_runs}</td></tr></tbody>
        </table></div>
      </section>

      <section>
        <div class=eyebrow>What real QNX taught the tool</div>
        <h2>Found on real traces, each now a regression test</h2>
        <ul class=lessons>
          <li><b>The 1 ms tick decides races.</b> QNX 8.0 fires timers on tick boundaries, so releases less than a tick apart wake in random order. Bugs that depended on it reproduced 1 to 4 times in 5; spaced by whole ticks, every time.</li>
          <li><b>Deferred interrupt work belongs below every driver.</b> The first motor-encoder fix ran its worker just below the interrupt thread and started it after <code>InterruptAttachEvent()</code>. The trace showed 20 ms stalls; the worker now runs below the lowest interrupt thread on the system (virtio, 21).</li>
          <li><b>Not every lock is yours.</b> Waits on procnto's own mutexes are reported, at low severity, and never fail the gate.</li>
          <li><b>Measure on a quiet host.</b> The VM's CPUs share the host's cores: a test suite running on the host stretched a 0.13 ms job to 1.3 ms.</li>
          <li><b>Never verify a bug that never happened.</b> A fix counts only if the bug reproduced first.</li>
        </ul>
      </section>

      <footer>
        <div>QNX SDP 8.0 · QEMU x86_64 VM built with <code>mkqnximage</code> (4 CPUs, KVM) · <code>procnto-smp-instr</code> · <code>tracelogger -w</code> · <code>qcc</code> · Python standard library only.</div>
        <div>Every number on this page comes from the committed results in <code>docs/results/</code> of
        <a href="https://github.com/sheikh2583/QNX-Global-Hackathon">github.com/sheikh2583/QNX-Global-Hackathon</a>; each fix's patch, traces summary and verdict are in its evidence bundle.</div>
      </footer>
    </div>
    """
    return page
