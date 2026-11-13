"""``tracelens`` command line.

Exit codes (CI contract):
  0  no findings at or above --fail-on
  1  findings at or above --fail-on
  2  usage or input error (including a trace without a clock rate)
  3  inconclusive: the trace is lossy (scheduler state machine broken, usually dropped
     events), so no verdict is given; rerun the capture or pass --allow-lossy.
     For `compare`: too few clean runs to decide.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .analyze import analyze_file
from .config import load_config
from .findings import at_least
from .ingest.traceprinter import TraceFormatError

EXIT_LOSSY = 3

SEV_TAG = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}

PLANNED = {
}


def _cmd_analyze(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.fail_on:
        cfg.fail_on = args.fail_on
    a = analyze_file(args.trace, cfg, cycles_per_sec=args.cycles_per_sec, snapshot=args.snapshot)
    m = a.model

    if args.json:
        from .report.json_out import dumps
        Path(args.json).write_text(dumps(a), encoding="utf-8")
    if args.html:
        from .report.html import render
        Path(args.html).write_text(render(a), encoding="utf-8")
    if args.sarif:
        from .report.sarif import dumps as sarif_dumps, relative_uri
        Path(args.sarif).write_text(sarif_dumps(a, relative_uri(args.trace)), encoding="utf-8")

    if not args.quiet:
        dur = (m.t_end - m.t_start) / 1e6
        print(f"TraceLens {__version__} | {m.trace.source}")
        if a.snapshot_path:
            print(f"  thread snapshot: {a.snapshot_path}")
        print(f"  {len(m.events):,} events, {len(m.threads)} threads, {dur:.1f} ms traced")
        if m.trace.unparsed_lines:
            print(f"  warning: {m.trace.unparsed_lines} lines not recognised")
        for issue in m.trace.issues:
            print(f"  note: {issue}")
        for issue in m.integrity:
            print(f"  TRACE INTEGRITY: {issue}")
        print()
        for f in a.findings:
            print(f"  [{SEV_TAG.get(f.severity, f.severity)}] {f.id} {f.title}")
            print(f"      {f.summary}")
        if not a.findings:
            print("  No real-time issues detected.")
        for err in a.errors:
            print(f"  detector error: {err}", file=sys.stderr)
        print()
        failing = sum(1 for f in a.findings if at_least(f.severity, cfg.fail_on))
        print(f"  {len(a.findings)} findings, {failing} at or above '{cfg.fail_on}'"
              + (f" | report: {args.html}" if args.html else ""))

    return _verdict(a, cfg, args.allow_lossy)


def _verdict(a, cfg, allow_lossy: bool) -> int:
    if a.model.lossy and not allow_lossy:
        print("  verdict: INCONCLUSIVE - the trace looks lossy (see TRACE INTEGRITY); findings above "
              "may be artefacts of dropped events. Recapture, or pass --allow-lossy.", file=sys.stderr)
        return EXIT_LOSSY
    return 1 if any(at_least(f.severity, cfg.fail_on) for f in a.findings) else 0


def _cmd_explain(args: argparse.Namespace) -> int:
    try:
        from .explain.claude import Explainer
        explainer = Explainer(model=args.model, effort=args.effort,
                              cache_dir=None if args.no_cache else args.cache_dir)
    except ImportError:
        print("tracelens explain needs the AI extra: pip install 'tracelens[ai]'", file=sys.stderr)
        return 2

    cfg = load_config(args.config)
    if args.fail_on:
        cfg.fail_on = args.fail_on
    a = analyze_file(args.trace, cfg, cycles_per_sec=args.cycles_per_sec, snapshot=args.snapshot)
    sources = {Path(s).name: Path(s).read_text(encoding="utf-8", errors="replace") for s in args.source}

    print(f"TraceLens {__version__} | explaining {min(len(a.findings), args.limit or 10**9)} "
          f"of {len(a.findings)} findings with {args.model}")
    expl = {}
    for f in a.findings[:args.limit]:
        x = explainer.explain(a, f, sources)
        expl[f.id] = x
        if x.data is None:
            state = f"unavailable ({x.error})"
        elif x.verified:
            state = "citations verified" + (" (cached)" if x.cached else f" ({x.attempts} attempt(s))")
        else:
            state = "citations NOT verified: " + "; ".join(x.problems)
        print(f"  {f.id} {f.title}\n      {state}")
        if x.data is not None and not args.quiet:
            print(f"      -> {x.data.get('headline', '')}")

    if any("authentication" in x.error.lower() for x in expl.values()):
        print("  hint: no Claude credentials found - set ANTHROPIC_API_KEY in your shell, then rerun",
              file=sys.stderr)
    if args.json:
        from .report.json_out import dumps
        Path(args.json).write_text(dumps(a, expl), encoding="utf-8")
    if args.html:
        from .report.html import render
        Path(args.html).write_text(render(a, expl), encoding="utf-8")
        print(f"  report: {args.html}")
    return _verdict(a, cfg, args.allow_lossy)


def _cmd_capture(args: argparse.Namespace) -> int:
    import os
    from .target import Target, TargetError, capture

    cfg_target = load_config(args.config).target if args.config else {}
    host = args.host or os.environ.get("TRACELENS_TARGET") or cfg_target.get("host")
    if not host:
        print("tracelens capture: no target host. Pass --host (inside the QEMU image folder, "
              "`mkqnximage --getip` prints it), set TRACELENS_TARGET, or add [target] host to tracelens.toml.",
              file=sys.stderr)
        return 2
    target = Target(host=host, user=args.user or cfg_target.get("user", "root"),
                    port=args.port or int(cfg_target.get("port", 22)), key=args.key or cfg_target.get("key"))
    wargs = args.workload_args[1:] if args.workload_args[:1] == ["--"] else args.workload_args
    try:
        res = capture(target, args.binary, wargs, args.out, seconds=args.seconds, name=args.name,
                      snapshot=not args.no_snapshot, traceprinter=args.traceprinter)
    except (TargetError, FileNotFoundError) as exc:
        print(f"tracelens capture: {exc}", file=sys.stderr)
        return 2
    for line in res.log:
        print(f"  {line}")
    if res.workload_rc not in (0, None):
        print(f"  warning: the workload exited {res.workload_rc}", file=sys.stderr)
    if not args.analyze:
        print(f"  next: tracelens analyze {res.text}" + (f" -c {args.config}" if args.config else ""))
        return 0
    ns = argparse.Namespace(trace=str(res.text), config=args.config, fail_on=None, json=None,
                            html=str(Path(args.out) / f"{res.name}.html"), quiet=False,
                            cycles_per_sec=None, allow_lossy=False, snapshot="auto")
    return _cmd_analyze(ns)


def _cmd_compare(args: argparse.Namespace) -> int:
    from .verdict import INCONCLUSIVE, VERIFIED, compare_files

    cfg = load_config(args.config)
    if args.fail_on:
        cfg.fail_on = args.fail_on
    v = compare_files(args.before, args.after, cfg, target_kinds=args.kind or None,
                      min_runs=args.min_runs, alpha=args.alpha)
    print(f"TraceLens {__version__} | before/after over {v.runs_before} + {v.runs_after} clean runs"
          + (f" ({v.lossy_skipped} lossy skipped)" if v.lossy_skipped else ""))
    for kind, (rb, ra) in v.targets.items():
        print(f"  {kind:<22} before {rb:>4.0%} of runs  ->  after {ra:>4.0%}")
    for d in v.deadlines:
        print(f"  deadline '{d.name}': p99 {d.before_p99 / 1e6:.2f} -> {d.after_p99 / 1e6:.2f} ms "
              f"(budget {d.budget_ns / 1e6:.2f} ms; misses {d.before_misses} -> {d.after_misses}); {d.reason}")
    for r in v.reasons:
        print(f"  - {r}")
    print(f"  VERDICT: {v.verdict}")
    if args.json:
        Path(args.json).write_text(json.dumps(v.to_dict(), indent=2), encoding="utf-8")
    return {VERIFIED: 0, INCONCLUSIVE: EXIT_LOSSY}.get(v.verdict, 1)


def _cmd_fix(args: argparse.Namespace) -> int:
    import os
    from .fix import FixAgent, QccBuilder
    from .target import Target, capture

    workload = Path(args.workload)
    if not workload.is_dir():
        print(f"tracelens fix: {workload} is not a workload directory", file=sys.stderr)
        return 2
    cfg = load_config(args.config)
    host = args.host or os.environ.get("TRACELENS_TARGET") or cfg.target.get("host")
    if not host:
        print("tracelens fix: no target host (--host, TRACELENS_TARGET or [target] host)", file=sys.stderr)
        return 2
    target = Target(host=host, user=args.user or cfg.target.get("user", "root"),
                    port=args.port or int(cfg.target.get("port", 22)), key=args.key or cfg.target.get("key"))
    wargs = args.workload_args[1:] if args.workload_args[:1] == ["--"] else args.workload_args

    def capturer(binary, _ws, label, i, out):
        res = capture(target, binary, wargs, Path(out) / "traces", seconds=args.seconds, name=f"{label}-{i}")
        return res.text

    includes = [Path(d) for d in args.include] or [d for d in [workload.parent / "common"] if d.is_dir()]
    out = Path(args.out or f"fixes/{workload.name}-{args.context}")
    try:
        agent = FixAgent(workload, includes, cfg, QccBuilder(), capturer, out, model=args.model,
                         effort=args.effort, runs=args.runs, max_attempts=args.max_attempts,
                         context=args.context, target_kinds=args.kind or None)
    except ImportError:
        print("tracelens fix needs the AI extra: pip install 'tracelens[ai]'", file=sys.stderr)
        return 2
    res = agent.run(before_traces=args.before or None)
    print(f"TraceLens {__version__} | fix {res.workload} ({res.context}, {res.runs} runs per side)")
    for a in res.attempts:
        print(f"  attempt {a.n}: {a.stage} {'OK' if a.ok else 'failed'}"
              + (f" - {a.verdict['verdict']}" if a.verdict else (f" - {a.detail[:120]}" if a.detail else "")))
    print(f"  STATUS: {res.status}" + (" (quick check: fewer than 5 runs)" if res.quick else ""))
    print(f"  evidence bundle: {res.bundle}")
    return {"VERIFIED": 0, "NOTHING TO FIX": 0, "INCONCLUSIVE": EXIT_LOSSY, "ERROR": 2}.get(res.status, 1)


def _cmd_export(args: argparse.Namespace) -> int:
    from .export.perfetto import dumps
    a = analyze_file(args.trace, load_config(args.config), cycles_per_sec=args.cycles_per_sec,
                     snapshot=args.snapshot)
    out = Path(args.out or Path(args.trace).with_suffix(".perfetto.json"))
    out.write_text(dumps(a, include_calls=not args.no_calls), encoding="utf-8")
    print(f"wrote {out} ({len(a.findings)} findings) - open it at https://ui.perfetto.dev")
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    try:
        from .mcp_server import main as serve
    except ImportError:
        print("tracelens mcp needs the MCP extra: pip install 'tracelens[mcp]'", file=sys.stderr)
        return 2
    try:
        serve()
    except ImportError:
        print("tracelens mcp needs the MCP extra: pip install 'tracelens[mcp]'", file=sys.stderr)
        return 2
    return 0


def _cmd_target(args: argparse.Namespace) -> int:
    import os
    from .target import Target
    from .target.check import FAIL, preflight, summary_status
    from .target.qemu import QemuImage

    qemu = QemuImage(args.image_dir)
    try:
        if args.action == "up":
            ip = qemu.up(timeout=args.timeout)
            for line in qemu.log:
                print(f"  {line}")
            print(f"  export TRACELENS_TARGET={ip}")
            return 0
        if args.action == "ip":
            ip = qemu.ip()
            print(ip or "no running target found")
            return 0 if ip else 1
        if args.action == "down":
            qemu.down()
            print("  target stopped")
            return 0
    except RuntimeError as exc:
        print(f"tracelens target: {exc}", file=sys.stderr)
        return 2

    cfg_target = load_config(args.config).target if args.config else {}
    host = args.host or os.environ.get("TRACELENS_TARGET") or cfg_target.get("host")
    if not host:
        try:
            host = qemu.ip()
        except RuntimeError:
            host = None
    if not host:
        print("tracelens target check: no target (pass --host, set TRACELENS_TARGET, or start one with "
              "`tracelens target up`)", file=sys.stderr)
        return 2
    t = Target(host=host, user=args.user or cfg_target.get("user", "root"), key=args.key or cfg_target.get("key"))
    checks = preflight(t)
    for c in checks:
        print(f"  [{c.status}] {c.name:<20} {c.detail}")
        if c.hint and c.status != "PASS":
            print(f"         -> {c.hint}")
    status = summary_status(checks)
    print(f"  target {host}: {status}")
    return 1 if status == FAIL else 0


def _cmd_dump(args: argparse.Namespace) -> int:
    from .ingest.traceprinter import parse_file
    trace = parse_file(args.trace)
    out = sys.stdout
    for e in trace.events:
        out.write(json.dumps(e.to_dict()) + "\n")
    return 0


def _cmd_threads(args: argparse.Namespace) -> int:
    from .ingest.traceprinter import parse_file
    from .model.trace import TraceModel
    m = TraceModel(parse_file(args.trace))
    span = max(1, m.t_end - m.t_start)
    print(f"{'thread':<28} {'prio':>4} {'running':>9} {'ready':>9} {'blocked':>9}")
    for key, th in sorted(m.threads.items()):
        run = m.overlap(th, {"RUNNING"}, m.t_start, m.t_end)
        ready = m.overlap(th, {"READY"}, m.t_start, m.t_end)
        blk = m.overlap(th, {"SEM", "MUTEX", "CONDVAR", "SEND", "REPLY", "INTR"}, m.t_start, m.t_end)
        print(f"{m.label(key):<28} {th.prio if th.prio is not None else '-':>4} "
              f"{run / span:>8.1%} {ready / span:>8.1%} {blk / span:>8.1%}")
    return 0


def _cmd_synth(args: argparse.Namespace) -> int:
    from .testing.scenarios import DEADLINES_TOML, SCENARIOS
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # newline="\n": fixtures must be byte-identical on every OS (CI diffs them).
    for name, make in SCENARIOS.items():
        (out / f"{name}.txt").write_text(make(), encoding="utf-8", newline="\n")
    (out / "tracelens.toml").write_text(DEADLINES_TOML, encoding="utf-8", newline="\n")
    print(f"wrote {len(SCENARIOS)} synthetic traces + tracelens.toml to {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tracelens", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=f"tracelens {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="detect real-time issues in a traceprinter dump")
    a.add_argument("trace")
    a.add_argument("--snapshot", default="auto",
                       help="pidin listing from capture start (default: <trace>.pidin.txt if present)")
    a.add_argument("--cycles-per-sec", type=int, help="clock rate if the trace header lacks CYCLES_PER_SEC")
    a.add_argument("--allow-lossy", action="store_true", help="give a verdict even on a lossy trace")
    a.add_argument("-c", "--config", help="tracelens.toml (thresholds, deadlines)")
    a.add_argument("--json", help="write JSON findings here")
    a.add_argument("--html", help="write the HTML report here")
    a.add_argument("--sarif", help="write SARIF 2.1.0 here (GitHub code scanning)")
    a.add_argument("--fail-on", choices=["critical", "high", "medium", "low"])
    a.add_argument("-q", "--quiet", action="store_true")
    a.set_defaults(func=_cmd_analyze)

    x = sub.add_parser("explain", help="analyze, then explain each finding with Claude (validated citations)")
    x.add_argument("trace")
    x.add_argument("--snapshot", default="auto",
                       help="pidin listing from capture start (default: <trace>.pidin.txt if present)")
    x.add_argument("--cycles-per-sec", type=int, help="clock rate if the trace header lacks CYCLES_PER_SEC")
    x.add_argument("--allow-lossy", action="store_true", help="give a verdict even on a lossy trace")
    x.add_argument("-c", "--config", help="tracelens.toml (thresholds, deadlines)")
    x.add_argument("--source", action="append", default=[], metavar="FILE",
                   help="workload source to show Claude (repeatable)")
    x.add_argument("--model", default="claude-opus-5-5")
    x.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    x.add_argument("--limit", type=int, help="explain at most N findings (highest severity first)")
    x.add_argument("--json", help="write JSON findings + explanations here")
    x.add_argument("--html", help="write the HTML report with explanations here")
    x.add_argument("--cache-dir", default=".tracelens-cache/explain")
    x.add_argument("--no-cache", action="store_true")
    x.add_argument("--fail-on", choices=["critical", "high", "medium", "low"])
    x.add_argument("-q", "--quiet", action="store_true")
    x.set_defaults(func=_cmd_explain)

    c = sub.add_parser("capture", help="run a workload on the QNX target under a kernel trace and fetch it")
    c.add_argument("binary", help="workload built with qcc (e.g. bugzoo/out/z1_infusion_pump)")
    c.add_argument("workload_args", nargs=argparse.REMAINDER, help="arguments for the workload, after --")
    c.add_argument("--host", help="target address (or TRACELENS_TARGET, or [target] host in the config)")
    c.add_argument("--user")
    c.add_argument("--port", type=int)
    c.add_argument("--key", help="ssh private key")
    c.add_argument("--seconds", type=int, default=4, help="trace length (the workload must finish inside it)")
    c.add_argument("--out", default="captures", help="local folder for .kev, .txt, .pidin.txt")
    c.add_argument("--name", help="base name for the output files (default: binary name)")
    c.add_argument("--no-snapshot", action="store_true", help="skip the pidin thread snapshot")
    c.add_argument("--traceprinter", choices=["auto", "host", "target"], default="auto")
    c.add_argument("-c", "--config", help="tracelens.toml ([target] section, deadlines)")
    c.add_argument("--analyze", action="store_true", help="analyze the trace right after capture")
    c.set_defaults(func=_cmd_capture)

    v = sub.add_parser("compare", help="before/after verdict over several captures (is the fix real?)")
    v.add_argument("--before", nargs="+", required=True, metavar="TRACE")
    v.add_argument("--after", nargs="+", required=True, metavar="TRACE")
    v.add_argument("-c", "--config", help="tracelens.toml (thresholds, deadlines)")
    v.add_argument("--kind", action="append", help="finding kind that must disappear (default: those in most before-runs)")
    v.add_argument("--min-runs", type=int, default=5, help="clean runs needed on each side (default 5)")
    v.add_argument("--alpha", type=float, default=0.01, help="significance level for timing improvement")
    v.add_argument("--fail-on", choices=["critical", "high", "medium", "low"])
    v.add_argument("--json", help="write the verdict as JSON here")
    v.set_defaults(func=_cmd_compare)

    f = sub.add_parser("fix", help="Claude patches a workload; qcc, run on QNX, re-trace, verdict")
    f.add_argument("workload", help="workload directory, e.g. bugzoo/z1_infusion_pump")
    f.add_argument("workload_args", nargs=argparse.REMAINDER, help="arguments for the workload, after --")
    f.add_argument("-c", "--config", help="tracelens.toml (deadlines, [target])")
    f.add_argument("--host")
    f.add_argument("--user")
    f.add_argument("--port", type=int)
    f.add_argument("--key")
    f.add_argument("--runs", type=int, default=5, help="captures per side (>= 5 for a verified claim)")
    f.add_argument("--seconds", type=int, default=4)
    f.add_argument("--max-attempts", type=int, default=4)
    f.add_argument("--context", choices=["full", "source-only"], default="full",
                   help="source-only hides findings and traces from the model (ablation)")
    f.add_argument("--kind", action="append", help="finding kind the fix must remove")
    f.add_argument("--before", nargs="+", metavar="TRACE", help="reuse existing 'before' traces")
    f.add_argument("--include", action="append", default=[], help="read-only include dir (default: ../common)")
    f.add_argument("--model", default="claude-opus-5-5")
    f.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    f.add_argument("--out", help="evidence bundle folder (default: fixes/<workload>-<context>)")
    f.set_defaults(func=_cmd_fix)

    e = sub.add_parser("export", help="write Chrome Trace JSON for ui.perfetto.dev (states, markers, findings)")
    e.add_argument("trace")
    e.add_argument("-o", "--out", help="output file (default: <trace>.perfetto.json)")
    e.add_argument("-c", "--config", help="tracelens.toml (so findings use your deadlines)")
    e.add_argument("--snapshot", default="auto")
    e.add_argument("--cycles-per-sec", type=int)
    e.add_argument("--no-calls", action="store_true", help="leave out kernel-call instants (smaller file)")
    e.set_defaults(func=_cmd_export)

    tg = sub.add_parser("target", help="QNX QEMU target: up | ip | check | down")
    tg.add_argument("action", choices=["up", "ip", "check", "down"])
    tg.add_argument("--image-dir", default="~/qnx800/images/qemu/qemu", help="QEMU quick-start image folder")
    tg.add_argument("--timeout", type=float, default=180, help="seconds to wait for an IP (up)")
    tg.add_argument("--host", help="target address for check (default: TRACELENS_TARGET or mkqnximage --getip)")
    tg.add_argument("--user")
    tg.add_argument("--key")
    tg.add_argument("-c", "--config")
    tg.set_defaults(func=_cmd_target)

    sp = sub.add_parser("mcp", help="run the MCP server on stdio (claude mcp add tracelens -- tracelens mcp)")
    sp.set_defaults(func=_cmd_mcp)

    d = sub.add_parser("dump", help="print the normalized event stream as JSONL")
    d.add_argument("trace")
    d.set_defaults(func=_cmd_dump)

    t = sub.add_parser("threads", help="per-thread CPU / ready / blocked summary")
    t.add_argument("trace")
    t.set_defaults(func=_cmd_threads)

    s = sub.add_parser("synth", help="write the synthetic bug-zoo traces (for demos and tests)")
    s.add_argument("--out", default="fixtures/synthetic")
    s.set_defaults(func=_cmd_synth)

    for name, desc in PLANNED.items():
        sp = sub.add_parser(name, help=f"[planned] {desc}")
        sp.set_defaults(func=lambda _a, d=desc: (print(f"not implemented yet: {d}"), 2)[1])
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, TraceFormatError) as exc:
        print(f"tracelens: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
