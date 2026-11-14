"""Find -> fix -> prove, with no model anywhere.

  before runs  -> findings (deterministic detectors, N captures on the target)
  remedies     -> QNX-specific source transforms chosen by the proven root cause (tracelens.remedy)
  guardrails   -> only existing .c/.h files of this workload change (Workspace)
  build        -> qcc
  after runs   -> N captures of the patched build
  verdict      -> tracelens compare: VERIFIED / NOT FIXED / INCONCLUSIVE
  next round   -> if NOT FIXED: diagnose the patched build's traces, fix again (up to 3 rounds)

Root causes without a safe automatic transform get GUIDED: exact source locations and the QNX
remedy, so a developer applies it and reruns ``tracelens compare``. Everything lands in an
evidence bundle: before/after traces, the patch, build log, verdict, and SUMMARY.md.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..analyze import Analysis, analyze_file
from ..config import Config
from ..remedy import Remedy, plan
from ..verdict import INCONCLUSIVE, RunSummary, compare_runs, summarize
from .scope import Workspace

# (binary or None, workspace dir, label, run index, output dir) -> path of the decoded trace text
Capturer = Callable[[Path | None, Path, str, int, Path], Path]

GUIDED = "GUIDED"
NOTHING = "NOTHING TO FIX"
BUILD_FAILED = "BUILD FAILED"


@dataclass
class FixResult:
    status: str  # VERIFIED | NOT FIXED | INCONCLUSIVE | GUIDED | NOTHING TO FIX | BUILD FAILED
    workload: str
    runs: int
    targets: list[str] = field(default_factory=list)
    remedies: list[dict] = field(default_factory=list)
    diff: str = ""
    verdict: dict | None = None
    bundle: str = ""
    note: str = ""
    rounds: int = 0  # fix -> re-trace rounds used
    quick: bool = False  # fewer than 5 runs per side: a smoke test, not a verified claim

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class FixEngine:
    def __init__(self, workload_dir: str | Path, include_dirs: list[str | Path], cfg: Config,
                 builder: Any, capturer: Capturer, out_dir: str | Path, runs: int = 5,
                 target_kinds: list[str] | None = None, alpha: float = 0.01, max_rounds: int = 3):
        self.workload_dir = Path(workload_dir)
        self.include_dirs = [Path(d) for d in include_dirs]
        self.cfg, self.builder, self.capturer = cfg, builder, capturer
        self.out = Path(out_dir)
        self.runs, self.target_kinds, self.alpha, self.max_rounds = runs, target_kinds, alpha, max_rounds

    def run(self, before_traces: list[str | Path] | None = None) -> FixResult:
        name = self.workload_dir.name
        self.out.mkdir(parents=True, exist_ok=True)
        res = FixResult(status=INCONCLUSIVE, workload=name, runs=self.runs, bundle=str(self.out),
                        quick=self.runs < 5)
        original = Workspace.create(self.workload_dir, self.out / "original", self.include_dirs).files()

        before, analyses = self._before(name, before_traces)
        clean = [a for s, a in zip(before, analyses) if not s.lossy]
        if not clean:
            res.note = "every 'before' trace is lossy; recapture"
            return self._finish(res, [])
        targets = self.target_kinds or _majority_kinds(before)
        res.targets = targets
        if not targets:
            res.status, res.note = NOTHING, "the detectors find no consistent problem in the 'before' runs"
            return self._finish(res, [])

        # Rounds: fix what the trace proves, re-trace, and if the verdict is NOT FIXED, diagnose the
        # *new* traces of the patched build (a first fix often uncovers the next cause: removing an
        # inversion leaves a long critical section) and fix again. Every round is judged against
        # the original 'before' runs.
        findings = _representative_findings(clean, targets)
        current, all_remedies = dict(original), []
        for rnd in range(1, self.max_rounds + 1):
            remedies, fixed = plan(findings, current)
            all_remedies += remedies
            res.remedies += [r.to_dict() | {"round": rnd} for r in remedies]
            if fixed == current:
                if rnd == 1:
                    res.status = GUIDED
                    res.note = "no root cause here has a safe automatic transform; apply the guidance, then compare"
                else:
                    res.note = f"round {rnd}: the remaining findings have no further automatic remedy"
                break
            current = fixed
            rdir = self.out / f"round-{rnd}"
            ws = Workspace.create(self.workload_dir, rdir / "src", self.include_dirs)
            ws.apply([{"path": p, "content": t} for p, t in sorted(current.items()) if t != original.get(p)])
            res.diff = _diff(original, ws.files())
            (rdir / "patch.diff").write_text(res.diff, encoding="utf-8")
            (self.out / "patch.diff").write_text(res.diff, encoding="utf-8")

            build = self.builder.build(sorted(ws.root.glob("*.c")), [ws.root, *self.include_dirs], rdir / name)
            (rdir / "build.log").write_text(build.log, encoding="utf-8")
            if not build.ok:
                res.status, res.note = BUILD_FAILED, build.log[-2000:]
                break

            after, after_an = self._runs(build.binary, ws.root, "after", rdir / "after")
            v = compare_runs(before, after, self.cfg, target_kinds=targets, min_runs=min(self.runs, 5),
                             alpha=self.alpha)
            res.status, res.verdict, res.rounds = v.verdict, v.to_dict(), rnd
            (rdir / "verdict.json").write_text(json.dumps(v.to_dict(), indent=2), encoding="utf-8")
            (self.out / "verdict.json").write_text(json.dumps(v.to_dict(), indent=2), encoding="utf-8")
            if v.verdict != "NOT FIXED":
                break  # VERIFIED, or INCONCLUSIVE (more runs needed, not another patch)
            after_clean = [a for a in after_an if not a.model.lossy]
            findings = _representative_findings(after_clean, None) if after_clean else []
            findings = [f for f in findings if f.severity in ("critical", "high", "medium")]
        return self._finish(res, all_remedies)

    # ----------------------------------------------------------------- helpers
    def _before(self, name: str, traces: list[str | Path] | None):
        if traces:
            analyses = [analyze_file(p, self.cfg) for p in traces]
            return [summarize(a, self.cfg, str(p)) for a, p in zip(analyses, traces)], analyses
        bdir = self.out / "before"
        ws = Workspace.create(self.workload_dir, bdir / "src", self.include_dirs)
        build = self.builder.build(sorted(ws.root.glob("*.c")), [ws.root, *self.include_dirs], bdir / name)
        (bdir / "build.log").write_text(build.log, encoding="utf-8")
        if not build.ok:
            raise RuntimeError(f"the original workload does not build:\n{build.log[-2000:]}")
        return self._runs(build.binary, ws.root, "before", bdir)

    def _runs(self, binary: Path | None, ws_root: Path, label: str, out: Path):
        out.mkdir(parents=True, exist_ok=True)
        summaries: list[RunSummary] = []
        analyses: list[Analysis] = []
        clean, i = 0, 0
        while clean < self.runs and i < 2 * self.runs:  # a lossy capture is replaced, up to N extra
            trace = self.capturer(binary, ws_root, label, i, out)
            i += 1
            a = analyze_file(trace, self.cfg)
            analyses.append(a)
            s = summarize(a, self.cfg, str(trace))
            summaries.append(s)
            clean += not s.lossy
        return summaries, analyses

    def _finish(self, res: FixResult, remedies: list[Remedy]) -> FixResult:
        (self.out / "result.json").write_text(json.dumps(res.to_dict(), indent=2), encoding="utf-8")
        (self.out / "SUMMARY.md").write_text(summary_markdown(res, remedies), encoding="utf-8")
        return res


def _majority_kinds(runs: list[RunSummary], share: float = 0.6) -> list[str]:
    clean = [r for r in runs if not r.lossy]
    kinds = set().union(*(r.kinds for r in clean)) if clean else set()
    return sorted(k for k in kinds if sum(k in r.kinds for r in clean) / len(clean) >= share)


def _representative_findings(clean: list[Analysis], targets: list[str] | None):
    """The findings of the run that shows the most target kinds (ties: the first such run).
    ``targets=None``: every finding of the run with the most distinct kinds."""
    if targets is None:
        return max(clean, key=lambda a: len({f.kind for f in a.findings})).findings
    best = max(clean, key=lambda a: len({f.kind for f in a.findings} & set(targets)))
    return [f for f in best.findings if f.kind in targets] or best.findings


def _diff(before: dict[str, str], after: dict[str, str]) -> str:
    out = []
    for path in sorted(set(before) | set(after)):
        a, b = before.get(path, ""), after.get(path, "")
        if a != b:
            out += difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True),
                                        fromfile=f"a/{path}", tofile=f"b/{path}")
    return "".join(out)


def summary_markdown(res: FixResult, remedies: list[Remedy]) -> str:
    lines = [f"# TraceLens fix: {res.workload}", "", f"- Status: **{res.status}**"
             + (f" after {res.rounds} round{'s' if res.rounds != 1 else ''}" if res.rounds else ""),
             f"- Runs per side: {res.runs}" + (" (quick check, not a verified claim)" if res.quick else ""),
             f"- Findings in most 'before' runs: {', '.join(res.targets) or '-'}"]
    if res.note:
        lines.append(f"- Note: {res.note}")
    for r in remedies:
        head = "Symptom" if r.rule == "symptom" else ("Automatic" if r.automatic else "Guided")
        lines += ["", f"## {head}: {r.title}", "", f"_Rule `{r.rule}`, "
                  f"for finding {r.finding_id} ({r.finding_kind})._", "", r.rationale]
        if r.locations:
            lines += ["", "Source locations:"] + [f"- `{p}:{n}` `{code}`" for p, n, code in r.locations]
        if r.guidance:
            lines += ["", "What to do:"] + [f"- {g}" for g in r.guidance]
        if r.notes:
            lines += ["", "Why not automatic:" if not r.automatic else "Notes:"] + [f"- {n}" for n in r.notes]
    if res.diff:
        lines += ["", "## Patch", "", "```diff", res.diff.rstrip(), "```"]
    if res.verdict:
        v = res.verdict
        lines += ["", f"## Verdict on the target: {v['verdict']}", ""]
        for k, t in v.get("targets", {}).items():
            lines.append(f"- {k}: in {t['before_rate']:.0%} of runs before, {t['after_rate']:.0%} after")
        for d in v.get("deadlines", []):
            lines.append(f"- deadline '{d['name']}': p99 {d['before_p99'] / 1e6:.2f} -> {d['after_p99'] / 1e6:.2f} ms "
                         f"(budget {d['budget_ns'] / 1e6:.2f} ms), misses {d['before_misses']} -> "
                         f"{d['after_misses']}: {d['reason']}")
        lines += [f"- {r}" for r in v.get("reasons", [])]
    return "\n".join(lines) + "\n"
