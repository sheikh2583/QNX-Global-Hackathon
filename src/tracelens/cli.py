"""``tracelens`` command line.

Exit codes (CI contract):
  0  no findings at or above --fail-on
  1  findings at or above --fail-on
  2  usage or input error (including a trace without a clock rate)
  3  inconclusive: the trace is lossy (scheduler state machine broken, usually dropped
     events), so no verdict is given; rerun the capture or pass --allow-lossy.
     For `compare` and `gate`: too few clean runs to decide.
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
    if args.radar is not None:
        from .ml import model as ml_model
        from .ml.radar import annotate
        path = Path(args.radar) if args.radar else ml_model.DEFAULT_RADAR
        if not path.exists():
            print(f"tracelens analyze: no radar model at {path} (train one: tracelens ml train-radar)", file=sys.stderr)
            return 2
        annotate(a, path)

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
    host, host_port = _split_host(host)
    target = Target(host=host, user=args.user or cfg_target.get("user", "root"),
                    port=args.port or host_port or int(cfg_target.get("port", 22)),
                    key=args.key or cfg_target.get("key"))
    wargs = args.workload_args
    try:
        res = capture(target, args.binary, wargs, args.out, seconds=args.seconds, name=args.name,
                      snapshot=not args.no_snapshot, traceprinter=args.traceprinter, command=args.command,
                      background=args.background)
    except (TargetError, FileNotFoundError, ValueError) as exc:
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
                            cycles_per_sec=None, allow_lossy=False, snapshot="auto", sarif=None)
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


def _cmd_baseline(args: argparse.Namespace) -> int:
    """Record a timing baseline that a later `tracelens gate` run can be measured against."""
    from .gate import build_baseline, load_baseline, save_baseline, stats_of

    if args.baseline_cmd == "show":
        try:
            doc = load_baseline(args.baseline)
        except ValueError as exc:
            print(f"tracelens baseline show: {exc}", file=sys.stderr)
            return 2
        print(f"TraceLens baseline '{doc['name']}' | {doc['runs']} clean capture(s) | recorded {doc['created']} "
              f"by TraceLens {doc['tool_version']}")
        print(f"  config: {doc['config'].get('path') or '(defaults)'}  fail_on={doc['config'].get('fail_on')}")
        for t in doc["traces"]:
            print(f"  {'LOSSY ' if t['lossy'] else '      '}{t['name']}  {t['jobs']} jobs  {t['sha256'][:12]}")
        for kind, rate in doc["finding_rates"].items():
            print(f"  finding {kind:<24} {rate:.0%} of runs")
        if not doc["finding_rates"]:
            print("  no finding at or above the gate severity in any capture")
        for key, m in doc["metrics"].items():
            budget = f", budget {m['budget_ms']:.2f} ms" if m.get("budget_ms") else ""
            print(f"  {key:<24} p99 {min(m['p99_ms']):.2f}-{max(m['p99_ms']):.2f} ms over "
                  f"{len(m['p99_ms'])} run(s){budget}")
        for key in doc.get("metrics_not_in_every_run", []):
            print(f"  note: '{key}' was not in every capture, so it is not part of the baseline", file=sys.stderr)
        return 0

    cfg = load_config(args.config)
    if args.fail_on:
        cfg.fail_on = args.fail_on
    caps = [stats_of(t, cfg) for t in args.trace]
    doc = build_baseline(caps, cfg, args.name or Path(args.out).stem, args.config)
    if not doc["runs"]:
        print(f"tracelens baseline save: all {len(caps)} captures are lossy, so there is nothing to base a gate "
              f"on. Recapture (keep the host idle) and try again.", file=sys.stderr)
        return EXIT_LOSSY
    out = save_baseline(args.out, doc)
    print(f"TraceLens {__version__} | baseline '{doc['name']}' -> {out}")
    print(f"  {doc['runs']} clean capture(s)"
          + (f", {doc['lossy_excluded']} lossy excluded" if doc["lossy_excluded"] else ""))
    for key, m in doc["metrics"].items():
        print(f"  {key:<24} p99 {min(m['p99_ms']):.2f}-{max(m['p99_ms']):.2f} ms, {sum(m['jobs_per_run'])} jobs")
    if doc["finding_rates"]:
        print("  findings already in the baseline (the gate reports what *changes*): "
              + ", ".join(f"{k} {v:.0%}" for k, v in doc["finding_rates"].items()))
    if doc["runs"] < 5:
        print(f"  note: {doc['runs']} capture(s) is too few for a rank test; `tracelens gate` will fall back to a "
              f"threshold rule and say so. 5+ captures per build make the verdict statistical.", file=sys.stderr)
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    """Fail a build whose timing or findings got worse than a recorded baseline."""
    from .gate import BETTER, PASS, REGRESSION, UNKNOWN, WORSE, gate_files

    cfg = load_config(args.config)
    if args.fail_on:
        cfg.fail_on = args.fail_on
    try:
        r = gate_files(args.trace, args.baseline, cfg, min_runs=args.min_runs, alpha=args.alpha,
                       min_regression_pct=args.min_regression_pct, min_regression_us=args.min_regression_us,
                       strict=args.strict)
    except ValueError as exc:
        print(f"tracelens gate: {exc}", file=sys.stderr)
        return 2

    tag = {WORSE: "WORSE", BETTER: "faster", UNKNOWN: "NO ANSWER"}
    if not args.quiet:
        created = r.baseline.get("created")
        print(f"TraceLens {__version__} | gate '{r.name}' vs baseline from {created} "
              f"({r.runs_base} capture(s)) | this build: {r.runs_new} clean capture(s)"
              + (f", {r.lossy_excluded} LOSSY EXCLUDED" if r.lossy_excluded else ""))
        tested = sum(1 for m in r.metrics if m.p_value is not None)
        if r.statistical:
            print(f"  evidence: one-sided Mann-Whitney U on per-capture p99, Holm-adjusted across {tested} "
                  f"metric(s), alpha {args.alpha:g}")
        else:
            print(f"  evidence: threshold rule - {r.runs_base}+{r.runs_new} captures is too few for a p-value")
        print()
        for kind, (rb, ra) in r.kind_rates.items():
            mark = "   NEW: a finding kind the baseline never had" if kind in r.new_kinds else (
                "   gone" if kind in r.gone_kinds else "")
            print(f"  {kind:<22} baseline {rb:>4.0%} of runs  ->  now {ra:>4.0%}{mark}")
        for m in r.metrics:
            print(f"  {m.key:<22} p99 {m.base_p99_ms:>7.2f} -> {m.new_p99_ms:>7.2f} ms  "
                  f"{tag.get(m.status, 'same'):<9} {m.reason}")
        for x in r.reasons:
            print(f"  - {x}")
        for w in r.warnings:
            print(f"  warning: {w}")
        print(f"  VERDICT: {r.verdict}")

    if args.json:
        Path(args.json).write_text(json.dumps(r.to_dict(), indent=2) + "\n", encoding="utf-8")
    if args.html:
        from .report.gate_html import render_gate
        Path(args.html).write_text(render_gate(r), encoding="utf-8")
    return {PASS: 0, REGRESSION: 1}.get(r.verdict, EXIT_LOSSY)


def _cmd_remedy(args: argparse.Namespace) -> int:
    """Plan fixes from a trace and the workload source. No target, no network."""
    from .remedy import plan

    cfg = load_config(args.config)
    a = analyze_file(args.trace, cfg, cycles_per_sec=args.cycles_per_sec, snapshot=args.snapshot)
    src_dir = Path(args.source)
    files = [src_dir] if src_dir.is_file() else sorted([*src_dir.glob("*.c"), *src_dir.glob("*.h")])
    if not files:
        print(f"tracelens remedy: no .c/.h files in {src_dir}", file=sys.stderr)
        return 2
    root = src_dir if src_dir.is_dir() else src_dir.parent
    sources = {f.relative_to(root).as_posix(): f.read_text(encoding="utf-8", errors="replace") for f in files}
    findings = [f for f in a.findings if at_least(f.severity, cfg.fail_on)] or a.findings
    remedies, fixed = plan(findings, sources)
    print(f"TraceLens {__version__} | remedies for {Path(args.trace).name} ({len(findings)} findings)")
    if not remedies:
        print("  nothing to fix")
        return 0
    for r in remedies:
        tag = "SYMPTOM" if r.rule == "symptom" else ("AUTO" if r.automatic else "GUIDED")
        print(f"\n  [{tag}] {r.title}")
        print(f"      {r.rationale}")
        for path, line, code in r.locations[:8]:
            print(f"      {path}:{line}  {code}")
        for g in r.guidance:
            print(f"      - {g}")
        for n in r.notes:
            print(f"      (not automatic: {n})")
    import difflib
    diff = "".join(
        line for path in sorted(sources) if fixed[path] != sources[path]
        for line in difflib.unified_diff(sources[path].splitlines(True), fixed[path].splitlines(True),
                                         f"a/{path}", f"b/{path}"))
    if diff:
        out = Path(args.patch or "tracelens-fix.patch")
        out.write_text(diff, encoding="utf-8")
        print(f"\n  patch: {out} ({diff.count(chr(10))} lines). Prove it on the target: tracelens fix "
              f"{root} --host <qnx>")
    return 0


def _zoo_background(workload: Path) -> str | None:
    """The load a workload needs while it is captured, from its bug-zoo entry.

    Z5's interrupt-handler bug only appears while something drives the serial line, so running
    `tracelens fix bugzoo/z5_motor_encoder` without the flag reported "nothing to fix" on a workload
    that is genuinely broken (measured 2026-11-16). The zoo already records the command; use it.
    """
    zoo = workload.parent / "zoo.toml"
    if not zoo.is_file():
        return None
    try:
        import tomllib
        return tomllib.loads(zoo.read_text(encoding="utf-8")).get(workload.name, {}).get("background")
    except (OSError, ValueError):
        return None


def _cmd_fix(args: argparse.Namespace) -> int:
    import os
    from .fix import FixEngine, QccBuilder
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
    host, host_port = _split_host(host)
    target = Target(host=host, user=args.user or cfg.target.get("user", "root"),
                    port=args.port or host_port or int(cfg.target.get("port", 22)),
                    key=args.key or cfg.target.get("key"))
    wargs = args.workload_args
    background = args.background or _zoo_background(workload)

    def capturer(binary, _ws, label, i, out):
        res = capture(target, binary, wargs, Path(out), seconds=args.seconds, name=f"{label}-{i}",
                      background=background)
        return res.text

    includes = [Path(d) for d in args.include] or [d for d in [workload.parent / "common"] if d.is_dir()]
    out = Path(args.out or f"fixes/{workload.name}")
    on_event = None
    if args.watch:
        from .live import LiveFeed, start_live_view
        feed = LiveFeed()
        url = start_live_view(feed, args.watch_port, f"Fixing {workload.name}", open_browser=not args.no_browser)
        print(f"  live view: {url}  (it updates as the fix runs)", flush=True)
        on_event = feed.publish
    engine = FixEngine(workload, includes, cfg, QccBuilder(), capturer, out, runs=args.runs,
                       target_kinds=args.kind or None, on_event=on_event)
    res = engine.run(before_traces=args.before or None)
    if args.watch:
        import time
        time.sleep(3)  # let the browser receive the last events before the server goes away
    print(f"TraceLens {__version__} | fix {res.workload} ({res.runs} runs per side)")
    for r in res.remedies:
        if r["rule"] != "symptom":
            print(f"  [{'AUTO' if r['automatic'] else 'GUIDED'}] {r['title']}")
    if res.verdict:
        for k, t in res.verdict["targets"].items():
            print(f"  {k:<22} before {t['before_rate']:>4.0%} of runs  ->  after {t['after_rate']:>4.0%}")
    print(f"  STATUS: {res.status}" + (" (quick check: fewer than 5 runs)" if res.quick else ""))
    print(f"  evidence bundle: {res.bundle} (report.html, SUMMARY.md, patch.diff, round-N/)")
    return {"VERIFIED": 0, "NOTHING TO FIX": 0, "GUIDED": 0, "INCONCLUSIVE": EXIT_LOSSY}.get(res.status, 1)


def _cmd_fix_report(args: argparse.Namespace) -> int:
    from .report.fix_html import write_fix_report
    out = write_fix_report(args.bundle, args.before, args.after or [], load_config(args.config), args.out)
    print(f"wrote {out}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import os
    from .web import prebuild, serve
    if args.prebuild:
        print("rendering the committed traces' pages into .site/ (one trace per process)")
        return prebuild(args.root)
    port = args.port or int(os.environ.get("PORT", "8000"))
    serve(args.host, port, args.root)
    return 0


def _split_host(host: str) -> tuple[str, int | None]:
    """``host`` may carry a port, as ``127.0.0.1:2222`` (QEMU's own NAT forwards ssh to one)."""
    name, _, port = str(host).partition(":")
    return name, (int(port) if port.isdigit() else None)


def _cmd_simulate(args: argparse.Namespace) -> int:
    from .ml.dataset import SCENARIOS
    from .sim import simulate, write_trace
    if args.scenario not in SCENARIOS:
        print(f"tracelens simulate: unknown scenario {args.scenario} (one of {', '.join(SCENARIOS)})", file=sys.stderr)
        return 2
    params = {}
    for kv in args.param:
        k, _, v = kv.partition("=")
        params[k.strip()] = int(v)
    path = write_trace(args.out, simulate(args.scenario, params, seed=args.seed, seconds=args.seconds))
    print(f"wrote {path} (simulated QNX 8.0 trace: {args.scenario}, seed {args.seed}); "
          f"analyze it with: tracelens analyze {path} -c bugzoo/gen/tlgen.toml")
    return 0


def _cmd_data(args: argparse.Namespace) -> int:
    from .ml import dataset
    if args.data_cmd == "plan":
        plan = dataset.make_plan(args.per_scenario, args.seed, args.scenario or None)
        dataset.write_jsonl(args.out, plan)
        by = {}
        for item in plan:
            by[item["split"]] = by.get(item["split"], 0) + 1
        print(f"wrote {len(plan)} planned runs to {args.out}: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
        print(f"  about {len(plan) * 10 / 3600:.1f} h on the QNX target (keep the host idle)")
        return 0
    if args.data_cmd == "collect":
        import os
        from .target import Target, capture
        cfg = load_config(args.config)
        host = args.host or os.environ.get("TRACELENS_TARGET") or cfg.target.get("host")
        if not host:
            print("tracelens data collect: no target host (--host or TRACELENS_TARGET)", file=sys.stderr)
            return 2
        host, host_port = _split_host(host)
        target = Target(host=host, user=args.user or "root", port=host_port or 22, key=args.key)

        def cap(item, out):
            return capture(target, args.binary, item["args"], out, seconds=args.seconds, name=item["id"],
                           background=item.get("background"), snapshot=False).text

        rows = dataset.collect(dataset.read_jsonl(args.plan), cap, args.out, cfg, limit=args.limit)
        ok = [r for r in rows if r.get("status") == "ok"]
        print(f"manifest: {len(ok)} collected, {sum(1 for r in ok if r.get('triggered'))} with the planted "
              f"problem showing, {sum(1 for r in ok if r.get('lossy'))} lossy")
        return 0
    if args.data_cmd == "simulate":
        from .sim.dataset import generate
        plan = dataset.make_plan(args.per_scenario, args.seed, args.scenario or None)
        rows = [r for r in generate(plan, args.out, args.config, plan_seed=args.seed, workers=args.workers,
                                    keep_traces=not args.no_traces) if r.get("status") == "ok"]
        by: dict[str, list[int]] = {}
        for r in rows:
            by.setdefault(r["scenario"], [0, 0])[0] += 1
            by[r["scenario"]][1] += bool(r.get("triggered"))
        print(f"{len(rows)} simulated traces in {args.out} (features: {Path(args.out) / 'features.jsonl'})")
        for name, (n, t) in by.items():
            print(f"  {name:18s} planted problem showed up in {t}/{n}")
        return 0
    from .ml.train import features_from_manifest
    n = features_from_manifest(args.data, args.out, load_config(args.config), workers=args.workers,
                               config_path=args.config, resume=args.resume)
    print(f"wrote {n} feature rows to {args.out}")
    return 0


def _cmd_ml(args: argparse.Namespace) -> int:
    from .ml import dataset, evaluate, model as ml_model, train
    rows = dataset.read_jsonl(args.features)
    if args.ml_cmd == "train-radar":
        radar = train.train_radar(rows)
        ml_model.save(radar, args.out)
        print(f"radar: threshold {radar['threshold']:.2f}; {radar['note']} -> {args.out}")
        return 0
    if args.ml_cmd == "train-classifier":
        clf = train.train_classifier(rows)
        ml_model.save(clf, args.out)
        print(f"classifier: {clf['note']} -> {args.out}")
        return 0
    radar = ml_model.load(args.radar)
    clf = ml_model.load(args.classifier) if args.classifier else None
    md = evaluate.markdown(evaluate.evaluate_radar(rows, radar), evaluate.evaluate_classifier(rows, clf) if clf else None)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    print(md)
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from .export.perfetto import dumps
    a = analyze_file(args.trace, load_config(args.config), cycles_per_sec=args.cycles_per_sec,
                     snapshot=args.snapshot)
    out = Path(args.out or Path(args.trace).with_suffix(".perfetto.json"))
    out.write_text(dumps(a, include_calls=not args.no_calls), encoding="utf-8")
    print(f"wrote {out} ({len(a.findings)} findings) - open it at https://ui.perfetto.dev")
    return 0


def _cmd_target(args: argparse.Namespace) -> int:
    import os
    from .target import Target
    from .target.check import FAIL, preflight, summary_status
    from .target.qemu import QemuImage

    qemu = QemuImage(args.image_dir)
    try:
        if args.action == "up":
            ip = qemu.up(timeout=args.timeout, user_net=args.user_net)
            for line in qemu.log:
                print(f"  {line}")
            where = ip if qemu.ssh_port == 22 else f"{ip}:{qemu.ssh_port}"
            print(f"  export TRACELENS_TARGET={where}")
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
    host, host_port = _split_host(host)
    t = Target(host=host, user=args.user or cfg_target.get("user", "root"), port=host_port or 22,
               key=args.key or cfg_target.get("key"))
    checks = preflight(t)
    for c in checks:
        print(f"  [{c.status}] {c.name:<20} {c.detail}")
        if c.hint and c.status != "PASS":
            print(f"         -> {c.hint}")
    status = summary_status(checks)
    print(f"  target {host}: {status}")
    return 1 if status == FAIL else 0


def _cmd_eval(args: argparse.Namespace) -> int:
    import os
    from .evaluation import eval_detect, eval_fix
    from .target import Target, capture

    cfg = load_config(args.config)
    host = args.host or os.environ.get("TRACELENS_TARGET") or cfg.target.get("host")
    if not host:
        print("tracelens eval: no target host (--host, TRACELENS_TARGET or [target] host)", file=sys.stderr)
        return 2
    host, host_port = _split_host(host)
    target = Target(host=host, user=args.user or cfg.target.get("user", "root"), port=host_port or 22,
                    key=args.key or cfg.target.get("key"))

    def cap(label, i, binary, command, wargs, out, background=None):
        if binary is not None and not Path(binary).exists():
            raise FileNotFoundError(f"{binary} not built: run `make -C {args.zoo}` with the SDP environment")
        return capture(target, binary, wargs, out, seconds=args.seconds, name=f"{label}-{i}", command=command,
                       background=background).text

    only = args.only.split(",") if args.only else None
    out = Path(args.out)
    try:
        if args.eval_cmd == "detect":
            eval_detect(args.zoo, cfg, cap, out, runs=args.runs, irq=args.irq, only=only)
            print((out / "detect.md").read_text(encoding="utf-8"))
            return 0
        from .fix import FixEngine, QccBuilder

        def make_engine(workload_dir, engine_out):
            def fix_cap(binary, _ws, label, i, o):
                entry = _zoo_entry(args.zoo, Path(workload_dir).name)
                wargs = [a.replace("{irq}", str(args.irq)) for a in entry.args]
                return cap(label, i, binary, None, wargs, o, background=entry.background)
            return FixEngine(workload_dir, [Path(args.zoo) / "common"], cfg, QccBuilder(), fix_cap, engine_out,
                             runs=args.runs)

        eval_fix(args.zoo, cfg, make_engine, cap, out, runs=args.runs, irq=args.irq, only=only)
        print((out / "fix.md").read_text(encoding="utf-8"))
        return 0
    except (FileNotFoundError, ImportError) as exc:
        print(f"tracelens eval: {exc}", file=sys.stderr)
        return 2


def _zoo_entry(zoo: str, name: str):
    from .evaluation import load_zoo
    return next(z for z in load_zoo(Path(zoo) / "zoo.toml")[0] if z.name == name)


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
    a.add_argument("--radar", nargs="?", const="", default=None, metavar="MODEL",
                   help="also report behaviour unlike healthy QNX traces (learned model; default: the bundled one)")
    a.set_defaults(func=_cmd_analyze)

    c = sub.add_parser("capture", help="run a workload on the QNX target under a kernel trace and fetch it")
    c.add_argument("binary", nargs="?", help="workload built with qcc (e.g. bugzoo/out/z1_infusion_pump)")
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
    c.add_argument("--command", help="trace a shell command already on the target instead of a binary")
    c.add_argument("--background", help="shell command run on the target during the workload (e.g. an interrupt load)")
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

    bl = sub.add_parser("baseline", help="record a timing baseline for `tracelens gate` (save | show)")
    bls = bl.add_subparsers(dest="baseline_cmd", required=True)
    b1 = bls.add_parser("save", help="per deadline and per job stream, the response-time distribution of N captures")
    b1.add_argument("trace", nargs="+", help="captures of ONE build (several runs of the same binary)")
    b1.add_argument("--name", help="what this baseline is of (default: the --out file stem)")
    b1.add_argument("--out", required=True, help="where to write the baseline JSON (commit it)")
    b1.add_argument("-c", "--config", help="tracelens.toml (thresholds, deadlines); fingerprinted in the baseline")
    b1.add_argument("--fail-on", choices=["critical", "high", "medium", "low"])
    b1.set_defaults(func=_cmd_baseline)
    b2 = bls.add_parser("show", help="print a baseline file")
    b2.add_argument("baseline")
    b2.set_defaults(func=_cmd_baseline)

    g = sub.add_parser("gate", help="fail a build that is statistically slower than a recorded baseline")
    g.add_argument("trace", nargs="+", help="captures of the build under test")
    g.add_argument("--baseline", required=True, help="baseline JSON from `tracelens baseline save`")
    g.add_argument("-c", "--config", help="tracelens.toml (thresholds, deadlines)")
    g.add_argument("--min-runs", type=int, default=5,
                   help="clean captures needed on each side for a p-value (default 5; below it, a stated "
                        "threshold rule and a loud caveat)")
    g.add_argument("--alpha", type=float, default=0.05,
                   help="family-wise significance level across every metric tested (default 0.05)")
    g.add_argument("--min-regression-pct", type=float, default=10.0,
                   help="a regression must also be this much worse in percent (default 10; 0 disables)")
    g.add_argument("--min-regression-us", type=float, default=50.0,
                   help="...and this much worse in absolute microseconds (default 50; 0 disables)")
    g.add_argument("--strict", action="store_true",
                   help="withhold a verdict (exit 3) rather than decide without a p-value, or with any lossy "
                        "capture in the set")
    g.add_argument("--fail-on", choices=["critical", "high", "medium", "low"])
    g.add_argument("--json", help="write the gate result as JSON here")
    g.add_argument("--html", help="write an HTML gate report here")
    g.add_argument("-q", "--quiet", action="store_true")
    g.set_defaults(func=_cmd_gate)

    r = sub.add_parser("remedy", help="plan QNX fixes from a trace + source (no target needed); writes a patch")
    r.add_argument("trace")
    r.add_argument("--source", required=True, help="workload directory (or one .c file)")
    r.add_argument("-c", "--config", help="tracelens.toml (thresholds, deadlines)")
    r.add_argument("--patch", help="write the patch here (default: tracelens-fix.patch)")
    r.add_argument("--snapshot", default="auto")
    r.add_argument("--cycles-per-sec", type=int)
    r.set_defaults(func=_cmd_remedy)

    f = sub.add_parser("fix", help="find, fix and prove: trace, apply the remedy, qcc, re-trace, verdict")
    f.add_argument("workload", help="workload directory, e.g. bugzoo/z1_infusion_pump")
    f.add_argument("-c", "--config", help="tracelens.toml (deadlines, [target])")
    f.add_argument("--host")
    f.add_argument("--user")
    f.add_argument("--port", type=int)
    f.add_argument("--key")
    f.add_argument("--runs", type=int, default=5, help="captures per side (>= 5 for a verified claim)")
    f.add_argument("--seconds", type=int, default=4)
    f.add_argument("--background", help="shell command run on the target during each capture "
                   "(default: the workload's bug-zoo entry, e.g. z5's serial load)")
    f.add_argument("--kind", action="append", help="finding kind the fix must remove")
    f.add_argument("--before", nargs="+", metavar="TRACE", help="reuse existing 'before' traces")
    f.add_argument("--include", action="append", default=[], help="read-only include dir (default: ../common)")
    f.add_argument("--out", help="evidence bundle folder (default: fixes/<workload>)")
    f.add_argument("--watch", action="store_true", help="open a live view of the fix in your browser")
    f.add_argument("--watch-port", type=int, default=8777, help="port for --watch (default 8777)")
    f.add_argument("--no-browser", action="store_true", help="with --watch: print the URL, do not open a browser")
    f.set_defaults(func=_cmd_fix)

    fr = sub.add_parser("fix-report", help="before/after HTML page for a fix bundle (from its traces)")
    fr.add_argument("bundle", help="fix bundle folder (result.json, patch.diff)")
    fr.add_argument("--before", nargs="+", required=True, metavar="TRACE")
    fr.add_argument("--after", nargs="+", metavar="TRACE")
    fr.add_argument("-c", "--config", help="tracelens.toml (deadlines)")
    fr.add_argument("-o", "--out", help="output file (default: <bundle>/report.html)")
    fr.set_defaults(func=_cmd_fix_report)

    sv = sub.add_parser("serve", help="run the web demo: results, live analysis and fix planning, uploads")
    sv.add_argument("--host", default="127.0.0.1", help="bind address (0.0.0.0 on a hosting provider)")
    sv.add_argument("--port", type=int, help="port (default: $PORT, else 8000)")
    sv.add_argument("--root", default=".", help="repository checkout with fixtures/real and docs/results")
    sv.add_argument("--prebuild", action="store_true",
                    help="render the committed traces' pages into <root>/.site and exit (run at deploy time)")
    sv.set_defaults(func=_cmd_serve)

    e = sub.add_parser("export", help="write Chrome Trace JSON for ui.perfetto.dev (states, markers, findings)")
    e.add_argument("trace")
    e.add_argument("-o", "--out", help="output file (default: <trace>.perfetto.json)")
    e.add_argument("-c", "--config", help="tracelens.toml (so findings use your deadlines)")
    e.add_argument("--snapshot", default="auto")
    e.add_argument("--cycles-per-sec", type=int)
    e.add_argument("--no-calls", action="store_true", help="leave out kernel-call instants (smaller file)")
    e.set_defaults(func=_cmd_export)

    sm = sub.add_parser("simulate", help="write one simulated QNX 8.0 trace of a tlgen scenario (no target needed)")
    sm.add_argument("scenario", help="healthy_periodic, sem_inversion, ... (tracelens data plan lists them all)")
    sm.add_argument("-o", "--out", required=True, help="trace file (.txt or .txt.gz)")
    sm.add_argument("--seed", type=int, default=0)
    sm.add_argument("--seconds", type=int, default=2)
    sm.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                    help="scenario parameter, e.g. cs_us=2500 (repeatable)")
    sm.set_defaults(func=_cmd_simulate)

    tg = sub.add_parser("target", help="QNX QEMU target: up | ip | check | down")
    tg.add_argument("action", choices=["up", "ip", "check", "down"])
    tg.add_argument("--image-dir", default="~/qnx-vm", help="folder of a mkqnximage-built VM")
    tg.add_argument("--timeout", type=float, default=180, help="seconds to wait for an IP (up)")
    tg.add_argument("--user-net", dest="user_net", action="store_true", default=None,
                    help="up: run the VM on QEMU's own network with ssh forwarded to 127.0.0.1:2222 "
                         "(no bridge, no DHCP server, no sudo; the default when libvirt's DHCP is not serving)")
    tg.add_argument("--bridge", dest="user_net", action="store_false",
                    help="up: use libvirt's bridge even if its DHCP looks down")
    tg.add_argument("--host", help="target address for check (default: TRACELENS_TARGET or mkqnximage --getip)")
    tg.add_argument("--user")
    tg.add_argument("--key")
    tg.add_argument("-c", "--config")
    tg.set_defaults(func=_cmd_target)

    dp = sub.add_parser("data", help="ML data engine: plan, collect and featurize labelled QNX traces")
    dps = dp.add_subparsers(dest="data_cmd", required=True)
    d1 = dps.add_parser("plan", help="seeded scenario/parameter plan with the evaluation split fixed in advance")
    d1.add_argument("--per-scenario", type=int, default=150)
    d1.add_argument("--seed", type=int, default=7)
    d1.add_argument("--scenario", action="append", help="only these scenarios (repeatable)")
    d1.add_argument("--out", default="data/plan.jsonl")
    d2 = dps.add_parser("collect", help="run the plan on the QNX target (resumable; keep the host idle)")
    d2.add_argument("--plan", default="data/plan.jsonl")
    d2.add_argument("--binary", default="bugzoo/out/tlgen")
    d2.add_argument("--out", default="data")
    d2.add_argument("--limit", type=int)
    d2.add_argument("--seconds", type=int, default=4)
    d2.add_argument("--host")
    d2.add_argument("--user")
    d2.add_argument("--key")
    d2.add_argument("-c", "--config", default="bugzoo/gen/tlgen.toml")
    d4 = dps.add_parser("simulate", help="run the plan through the QNX scheduling simulator (no target; parallel)")
    d4.add_argument("--per-scenario", type=int, default=40)
    d4.add_argument("--seed", type=int, default=7)
    d4.add_argument("--scenario", action="append", help="only these scenarios (repeatable)")
    d4.add_argument("--out", default="data/sim")
    d4.add_argument("--workers", type=int, default=0, help="processes (default: all CPUs)")
    d4.add_argument("--no-traces", action="store_true", help="keep manifest and features only")
    d4.add_argument("-c", "--config", default="bugzoo/gen/tlgen.toml")
    d3 = dps.add_parser("features", help="one feature row per (thread, 20 ms window) of every collected trace")
    d3.add_argument("--data", default="data")
    d3.add_argument("--out", default="data/features.jsonl")
    d3.add_argument("-c", "--config", default="bugzoo/gen/tlgen.toml")
    d3.add_argument("--workers", type=int, default=0,
                    help="processes to parse traces in (default: one per CPU; 1 = no parallelism)")
    d3.add_argument("--resume", action="store_true", help="keep the rows already written and add the missing traces")
    for d in (d1, d2, d3, d4):
        d.set_defaults(func=_cmd_data)

    mp = sub.add_parser("ml", help="train and evaluate the radar and the classifier")
    mps = mp.add_subparsers(dest="ml_cmd", required=True)
    m1 = mps.add_parser("train-radar", help="fit the radar on healthy training windows (pure Python)")
    m1.add_argument("--out", default="src/tracelens/ml/radar.json")
    m2 = mps.add_parser("train-classifier", help="fit the root-cause classifier (needs .[ml])")
    m2.add_argument("--out", default="src/tracelens/ml/classifier.json")
    m3 = mps.add_parser("eval", help="the evaluation protocol on held-out data (docs/ml/DESIGN.md)")
    m3.add_argument("--radar", default="src/tracelens/ml/radar.json")
    m3.add_argument("--classifier")
    m3.add_argument("--out", help="write the markdown report here")
    for m in (m1, m2, m3):
        m.add_argument("--features", default="data/features.jsonl")
        m.set_defaults(func=_cmd_ml)

    ev = sub.add_parser("eval", help="bug-zoo evaluation on the QNX target: detection table, fix ablation")
    evs = ev.add_subparsers(dest="eval_cmd", required=True)
    for name, desc in (("detect", "capture buggy + reference builds N times; detection and false-positive table"),
                       ("fix", "run the fix engine on every workload; proven-fix table")):
        e2 = evs.add_parser(name, help=desc)
        e2.add_argument("--zoo", default="bugzoo", help="bug-zoo folder with zoo.toml and out/ binaries")
        e2.add_argument("-c", "--config", default="bugzoo/tracelens.toml")
        e2.add_argument("--runs", type=int, default=5)
        e2.add_argument("--seconds", type=int, default=4)
        e2.add_argument("--irq", type=int, help="interrupt for z5 (skipped without it)")
        e2.add_argument("--only", help="comma-separated workload names")
        e2.add_argument("--out", default="docs/results")
        e2.add_argument("--host")
        e2.add_argument("--user")
        e2.add_argument("--key")
        e2.set_defaults(func=_cmd_eval)

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
    # Everything after a bare "--" belongs to the workload (capture, fix), never to TraceLens,
    # so TraceLens options may appear anywhere before it.
    argv = list(sys.argv[1:] if argv is None else argv)
    workload_args: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, workload_args = argv[:i], argv[i + 1:]
    args = build_parser().parse_args(argv)
    args.workload_args = workload_args
    try:
        return args.func(args)
    except (FileNotFoundError, TraceFormatError) as exc:
        print(f"tracelens: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
