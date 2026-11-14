"""Evaluation harness: the numbers that go in the README, the Devpost text and the video.

``eval_detect``  For every bug-zoo workload, capture the buggy and the reference build N times
                 on the target. Report how often each expected finding appears (recall), whether
                 the reference fix stays clean (false positives), and the before/after verdict.
                 Healthy system commands from the manifest form a negative set that must stay clean.
``eval_fix``     Run the fix agent on every workload with the full context and with source only,
                 reusing one set of "before" captures per workload: the ablation table.

Results are written as Markdown and JSON. Lossy runs are counted and excluded, never scored, and
replaced by a fresh capture (at most ``runs`` extra per build) so every row has ``runs`` clean runs.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .analyze import analyze_file
from .config import Config
from .findings import at_least
from .verdict import compare_runs, summarize

# (label, run index, binary or None, shell command or None, args, out dir, background) -> trace path
EvalCapturer = Callable[..., Path]


@dataclass
class ZooEntry:
    name: str
    expect: list[str]
    args: list[str] = field(default_factory=list)
    needs_irq: bool = False
    background: str | None = None


@dataclass
class NegativeEntry:
    name: str
    command: str


def load_zoo(path: str | Path) -> tuple[list[ZooEntry], list[NegativeEntry]]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    neg = [NegativeEntry(k, v["command"]) for k, v in data.pop("negative", {}).items()]
    zoo = [ZooEntry(k, list(v.get("expect", [])), [str(a) for a in v.get("args", [])], bool(v.get("needs_irq")),
                    v.get("background")) for k, v in data.items()]
    return zoo, neg


@dataclass
class WorkloadResult:
    name: str
    expect: list[str]
    runs: int = 0
    skipped: str = ""
    lossy: int = 0
    buggy_clean_runs: int = 0
    detected_runs: int = 0  # clean buggy runs where every expected kind appeared
    kind_rates: dict[str, float] = field(default_factory=dict)
    unexpected_kinds: list[str] = field(default_factory=list)
    reference_runs_with_findings: int = 0
    reference_clean_runs: int = 0
    reference_kinds: list[str] = field(default_factory=list)
    reference_verdict: str = ""


@dataclass
class NegativeResult:
    name: str
    command: str
    runs: int = 0
    lossy: int = 0
    runs_with_findings: int = 0
    kinds: list[str] = field(default_factory=list)


def _runs(capture: EvalCapturer, label: str, n: int, binary, command, args, out, cfg: Config,
          background: str | None = None):
    summaries, kinds_per_run = [], []
    clean, i = 0, 0
    while clean < n and i < 2 * n:  # a lossy capture is excluded and replaced, up to n extra
        trace = capture(label, i, binary, command, args, out, background=background)
        i += 1
        a = analyze_file(trace, cfg)
        s = summarize(a, cfg, str(trace))
        summaries.append(s)
        kinds_per_run.append(None if s.lossy else {f.kind for f in a.findings if at_least(f.severity, cfg.fail_on)})
        clean += not s.lossy
    return summaries, kinds_per_run


def eval_detect(zoo_dir: str | Path, cfg: Config, capture: EvalCapturer, out_dir: str | Path,
                runs: int = 5, irq: int | None = None, only: list[str] | None = None) -> dict:
    zoo_dir, out = Path(zoo_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    zoo, negatives = load_zoo(zoo_dir / "zoo.toml")
    results: list[WorkloadResult] = []
    for z in zoo:
        if only and z.name not in only:
            continue
        r = WorkloadResult(z.name, z.expect)
        results.append(r)
        if z.needs_irq and irq is None:
            r.skipped = "needs --irq (interrupt source)"
            continue
        args = [a.replace("{irq}", str(irq)) for a in z.args]
        tdir = out / "traces" / z.name
        buggy, buggy_kinds = _runs(capture, f"{z.name}-buggy", runs, zoo_dir / "out" / z.name, None, args, tdir,
                                   cfg, z.background)
        fixed, fixed_kinds = _runs(capture, f"{z.name}-fixed", runs, zoo_dir / "out" / f"{z.name}_fixed", None,
                                   args, tdir, cfg, z.background)
        clean_b = [k for k in buggy_kinds if k is not None]
        clean_f = [k for k in fixed_kinds if k is not None]
        r.runs = runs
        r.lossy = (len(buggy_kinds) - len(clean_b)) + (len(fixed_kinds) - len(clean_f))
        r.buggy_clean_runs = len(clean_b)
        r.detected_runs = sum(1 for k in clean_b if set(z.expect) <= k)
        r.kind_rates = {k: round(sum(1 for ks in clean_b if k in ks) / len(clean_b), 3) if clean_b else 0.0
                        for k in z.expect}
        r.unexpected_kinds = sorted(set().union(*clean_b) - set(z.expect)) if clean_b else []
        r.reference_clean_runs = len(clean_f)
        r.reference_runs_with_findings = sum(1 for k in clean_f if k)
        r.reference_kinds = sorted(set().union(*clean_f)) if clean_f else []
        r.reference_verdict = compare_runs(buggy, fixed, cfg, target_kinds=z.expect, min_runs=min(5, runs)).verdict

    neg_results: list[NegativeResult] = []
    for n in negatives:
        if only and n.name not in only:
            continue
        nr = NegativeResult(n.name, n.command)
        neg_results.append(nr)
        _, kinds = _runs(capture, f"negative-{n.name}", runs, None, n.command, [], out / "traces" / "negative", cfg)
        clean = [k for k in kinds if k is not None]
        nr.runs, nr.lossy = len(kinds), len(kinds) - len(clean)
        nr.runs_with_findings = sum(1 for k in clean if k)
        nr.kinds = sorted(set().union(*clean)) if clean else []

    report = {"runs_per_build": runs, "fail_on": cfg.fail_on,
              "workloads": [asdict(r) for r in results], "negatives": [asdict(n) for n in neg_results]}
    (out / "detect.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "detect.md").write_text(detect_markdown(report), encoding="utf-8")
    return report


def detect_markdown(report: dict) -> str:
    n = report["runs_per_build"]
    lines = [f"## Detection on QNX ({n} runs per build, findings at or above `{report['fail_on']}`)", "",
             "| Workload | Expected findings | Buggy build: detected | Reference fix: runs with findings "
             "| Lossy runs excluded | Before/after verdict |", "|---|---|---|---|---|---|"]
    for w in report["workloads"]:
        if w["skipped"]:
            lines.append(f"| `{w['name']}` | {', '.join(w['expect'])} | skipped: {w['skipped']} | | | |")
            continue
        clean_b = w["buggy_clean_runs"]
        extra = f" (also: {', '.join(w['unexpected_kinds'])})" if w["unexpected_kinds"] else ""
        ref = f"{w['reference_runs_with_findings']}/{w['reference_clean_runs']}"
        if w["reference_kinds"]:
            ref += f" ({', '.join(w['reference_kinds'])})"
        lines.append(f"| `{w['name']}` | {', '.join(w['expect'])} | {w['detected_runs']}/{clean_b}{extra} "
                     f"| {ref} | {w['lossy']} | {w['reference_verdict']} |")
    if report["negatives"]:
        lines += ["", "### Healthy programs (must stay clean)", "",
                  "| Program | Command | Runs with findings | Lossy runs excluded |", "|---|---|---|---|"]
        for g in report["negatives"]:
            kinds = f" ({', '.join(g['kinds'])})" if g["kinds"] else ""
            lines.append(f"| {g['name']} | `{g['command']}` | {g['runs_with_findings']}/{g['runs'] - g['lossy']}"
                         f"{kinds} | {g['lossy']} |")
    return "\n".join(lines) + "\n"


def eval_fix(zoo_dir: str | Path, cfg: Config, make_agent: Callable[..., Any], capture: EvalCapturer,
             out_dir: str | Path, runs: int = 5, contexts: tuple[str, ...] = ("full", "source-only"),
             irq: int | None = None, only: list[str] | None = None) -> dict:
    """``make_agent(workload_dir, context, out_dir) -> FixAgent`` builds a configured agent."""
    zoo_dir, out = Path(zoo_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    zoo, _ = load_zoo(zoo_dir / "zoo.toml")
    rows = []
    for z in zoo:
        if only and z.name not in only:
            continue
        if z.needs_irq and irq is None:
            rows.append({"workload": z.name, "skipped": "needs --irq"})
            continue
        args = [a.replace("{irq}", str(irq)) for a in z.args]
        before = [capture(f"{z.name}-before", i, zoo_dir / "out" / z.name, None, args, out / z.name / "before",
                          background=z.background) for i in range(runs)]
        row: dict[str, Any] = {"workload": z.name, "skipped": ""}
        for ctx in contexts:
            res = make_agent(zoo_dir / z.name, ctx, out / z.name / ctx).run(before_traces=before)
            row[ctx] = {"status": res.status, "attempts": len(res.attempts), "bundle": res.bundle}
        rows.append(row)
    report = {"runs_per_side": runs, "contexts": list(contexts), "rows": rows}
    (out / "fix.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out / "fix.md").write_text(fix_markdown(report), encoding="utf-8")
    return report


def fix_markdown(report: dict) -> str:
    ctx = report["contexts"]
    head = " | ".join(f"{'Source + findings + trace' if c == 'full' else 'Source only'}" for c in ctx)
    lines = [f"## Autonomous fixes on QNX ({report['runs_per_side']} runs per side)", "",
             f"| Workload | {head} |", "|---|" + "---|" * len(ctx)]
    totals = {c: 0 for c in ctx}
    counted = 0
    for r in report["rows"]:
        if r.get("skipped"):
            lines.append(f"| `{r['workload']}` | " + " | ".join(f"skipped: {r['skipped']}" for _ in ctx) + " |")
            continue
        counted += 1
        cells = []
        for c in ctx:
            st = r[c]["status"]
            totals[c] += st == "VERIFIED"
            cells.append(f"{st} ({r[c]['attempts']} attempt{'s' if r[c]['attempts'] != 1 else ''})")
        lines.append(f"| `{r['workload']}` | " + " | ".join(cells) + " |")
    lines.append("| **Verified** | " + " | ".join(f"**{totals[c]}/{counted}**" for c in ctx) + " |")
    return "\n".join(lines) + "\n"
