"""The fix-and-verify loop (PLAN.md §7): Claude patches, the real target judges.

  before runs  -> findings F0 (deterministic detectors, N captures)
  Claude       -> complete replacement files for the workload (JSON schema)
  guardrails   -> only existing .c/.h files of this workload may change
  build        -> qcc (or a host compile check in tests)
  after runs   -> N captures of the patched build
  verdict      -> tracelens compare: VERIFIED / NOT FIXED / INCONCLUSIVE
  feedback     -> compile errors, guardrail rejections or verdict reasons go back to Claude

Everything lands in an evidence bundle: before/after traces, each attempt's diff,
build log and verdict, the transcript, and a summary.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..analyze import Analysis, analyze_file
from ..config import Config
from ..explain.evidence import build_pack, format_pack
from ..verdict import INCONCLUSIVE, VERIFIED, RunSummary, compare_runs, summarize
from .prompts import SCHEMA, SYSTEM, build_failed, first_prompt, scope_failed, verdict_failed
from .scope import ScopeError, Workspace

DEFAULT_MODEL = "claude-opus-5-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# (binary or None, workspace dir, label, run index, output dir) -> path of the decoded trace text
Capturer = Callable[[Path | None, Path, str, int, Path], Path]


@dataclass
class Attempt:
    n: int
    diagnosis: str = ""
    expected_effect: str = ""
    files: list[str] = field(default_factory=list)
    diff: str = ""
    stage: str = ""  # model | scope | build | verdict
    ok: bool = False
    detail: str = ""
    verdict: dict | None = None


@dataclass
class FixResult:
    status: str  # VERIFIED | NOT FIXED | NOTHING TO FIX | INCONCLUSIVE | ERROR
    workload: str
    context: str
    runs: int
    targets: list[str] = field(default_factory=list)
    attempts: list[Attempt] = field(default_factory=list)
    bundle: str = ""
    quick: bool = False  # fewer than 5 runs per side: a smoke test, not a verified claim

    def to_dict(self) -> dict:
        return {**{k: v for k, v in self.__dict__.items() if k != "attempts"},
                "attempts": [a.__dict__ for a in self.attempts]}


class FixAgent:
    def __init__(self, workload_dir: str | Path, include_dirs: list[str | Path], cfg: Config,
                 builder: Any, capturer: Capturer, out_dir: str | Path, client: Any | None = None,
                 model: str = DEFAULT_MODEL, effort: str = "high", runs: int = 5, max_attempts: int = 4,
                 context: str = "full", target_kinds: list[str] | None = None, alpha: float = 0.01):
        if context not in ("full", "source-only"):
            raise ValueError("context must be 'full' or 'source-only'")
        if client is None:
            import anthropic  # optional dependency
            client = anthropic.Anthropic()
        self.workload_dir = Path(workload_dir)
        self.include_dirs = [Path(d) for d in include_dirs]
        self.cfg, self.builder, self.capturer, self.client = cfg, builder, capturer, client
        self.out = Path(out_dir)
        self.model, self.effort, self.runs = model, effort, runs
        self.max_attempts, self.context, self.alpha = max_attempts, context, alpha
        self.target_kinds = target_kinds
        self.transcript: list[dict] = []

    # ------------------------------------------------------------------ public
    def run(self, before_traces: list[str | Path] | None = None) -> FixResult:
        name = self.workload_dir.name
        self.out.mkdir(parents=True, exist_ok=True)
        res = FixResult(status=INCONCLUSIVE, workload=name, context=self.context, runs=self.runs,
                        bundle=str(self.out), quick=self.runs < 5)
        original = Workspace.create(self.workload_dir, self.out / "original", self.include_dirs).files()

        before, analyses = self._before(name, before_traces)
        clean = [a for s, a in zip(before, analyses) if not s.lossy]
        if not clean:
            res.status = INCONCLUSIVE
            return self._finish(res, "every 'before' trace is lossy; recapture")
        targets = self.target_kinds or self._majority_kinds(before)
        res.targets = targets
        if not targets:
            res.status = "NOTHING TO FIX"
            return self._finish(res, "the detectors find no consistent problem in the 'before' runs")

        readonly = {f"{d.name}/{p.name}": p.read_text(encoding="utf-8", errors="replace")
                    for d in self.include_dirs for p in sorted(d.glob("*.h"))}
        findings, evidence = None, None
        if self.context == "full":
            a0 = clean[0]
            shown = [f for f in a0.findings if f.kind in targets] or a0.findings
            findings = [f.to_dict() for f in shown]
            evidence = {f.id: format_pack(a0.model, build_pack(a0.model, f)) for f in shown}
        messages: list[dict] = [{"role": "user", "content": first_prompt(original, readonly, findings, evidence)}]

        for n in range(1, self.max_attempts + 1):
            att = Attempt(n=n)
            res.attempts.append(att)
            adir = self.out / f"attempt-{n}"
            adir.mkdir(exist_ok=True)

            data, resp_content, err = self._ask(messages)
            if err:
                att.stage, att.detail = "model", err
                res.status = "ERROR"
                break
            messages.append({"role": "assistant", "content": resp_content})
            att.diagnosis, att.expected_effect = data.get("diagnosis", ""), data.get("expected_effect", "")

            ws = Workspace.create(self.workload_dir, adir / "src", self.include_dirs)
            try:
                att.files = ws.apply(data.get("changes", []))
            except ScopeError as exc:
                att.stage, att.detail = "scope", str(exc)
                messages.append({"role": "user", "content": scope_failed(str(exc))})
                continue
            att.diff = _diff(original, ws.files())
            (adir / "patch.diff").write_text(att.diff, encoding="utf-8")

            sources = sorted(ws.root.glob("*.c"))
            build = self.builder.build(sources, [ws.root, *self.include_dirs], adir / name)
            (adir / "build.log").write_text(build.log, encoding="utf-8")
            if not build.ok:
                att.stage, att.detail = "build", build.log[-2000:]
                messages.append({"role": "user", "content": build_failed(build.log)})
                continue

            after, after_an = self._runs(build.binary, ws.root, "after", adir)
            v = compare_runs(before, after, self.cfg, target_kinds=targets,
                             min_runs=self.runs, alpha=self.alpha)
            att.stage, att.verdict = "verdict", v.to_dict()
            (adir / "verdict.json").write_text(json.dumps(v.to_dict(), indent=2), encoding="utf-8")
            if v.verdict == VERIFIED:
                att.ok, res.status = True, VERIFIED
                break
            res.status = v.verdict
            if v.verdict == INCONCLUSIVE:
                att.detail = "; ".join(v.reasons)
                break  # more runs are needed, not a different patch
            after_findings = [f.to_dict() for a in after_an for f in a.findings]
            messages.append({"role": "user", "content": verdict_failed(v.reasons, after_findings[:8])})
        return self._finish(res, "")

    # ----------------------------------------------------------------- helpers
    def _before(self, name: str, traces: list[str | Path] | None):
        bdir = self.out / "before"
        bdir.mkdir(exist_ok=True)
        if traces:
            analyses = [analyze_file(p, self.cfg) for p in traces]
            return [summarize(a, self.cfg, str(p)) for a, p in zip(analyses, traces)], analyses
        ws = Workspace.create(self.workload_dir, bdir / "src", self.include_dirs)
        build = self.builder.build(sorted(ws.root.glob("*.c")), [ws.root, *self.include_dirs], bdir / name)
        (bdir / "build.log").write_text(build.log, encoding="utf-8")
        if not build.ok:
            raise RuntimeError(f"the original workload does not build:\n{build.log[-2000:]}")
        return self._runs(build.binary, ws.root, "before", bdir)

    def _runs(self, binary: Path | None, ws_root: Path, label: str, out: Path):
        summaries: list[RunSummary] = []
        analyses: list[Analysis] = []
        for i in range(self.runs):
            trace = self.capturer(binary, ws_root, label, i, out)
            a = analyze_file(trace, self.cfg)
            analyses.append(a)
            summaries.append(summarize(a, self.cfg, str(trace)))
        return summaries, analyses

    @staticmethod
    def _majority_kinds(runs: list[RunSummary], share: float = 0.6) -> list[str]:
        clean = [r for r in runs if not r.lossy]
        kinds = set().union(*(r.kinds for r in clean)) if clean else set()
        return sorted(k for k in kinds if sum(k in r.kinds for r in clean) / len(clean) >= share)

    def _ask(self, messages: list[dict]) -> tuple[dict, Any, str]:
        try:
            resp = self.client.beta.messages.create(
                model=self.model, max_tokens=16000, betas=[FALLBACK_BETA], fallbacks="default",
                system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=list(messages),  # snapshot: the loop keeps appending to its own list
            )
        except Exception as exc:  # network/API errors end the run visibly
            return {}, None, f"{type(exc).__name__}: {exc}"
        if resp.stop_reason in ("refusal", "max_tokens"):
            return {}, None, f"model stopped: {resp.stop_reason}"
        text = next((b.text for b in resp.content if b.type == "text"), "")
        self.transcript.append({"role": "assistant", "text": text})
        try:
            return json.loads(text), resp.content, ""
        except json.JSONDecodeError as exc:
            return {}, None, f"invalid JSON from model: {exc}"

    def _finish(self, res: FixResult, note: str) -> FixResult:
        (self.out / "result.json").write_text(json.dumps(res.to_dict(), indent=2), encoding="utf-8")
        (self.out / "transcript.json").write_text(json.dumps(self.transcript, indent=2), encoding="utf-8")
        lines = [f"# TraceLens fix: {res.workload}", "", f"- Status: **{res.status}**",
                 f"- Context given to the model: {res.context}", f"- Runs per side: {res.runs}"
                 + (" (quick check, not a verified claim)" if res.quick else ""),
                 f"- Target findings: {', '.join(res.targets) or '-'}"]
        if note:
            lines.append(f"- Note: {note}")
        for a in res.attempts:
            lines += ["", f"## Attempt {a.n}: {a.stage} {'OK' if a.ok else 'failed'}", "", a.diagnosis or a.detail]
            if a.diff:
                lines += ["", "```diff", a.diff.rstrip(), "```"]
            if a.verdict:
                lines += ["", f"Verdict: {a.verdict['verdict']}"] + [f"- {r}" for r in a.verdict["reasons"]]
        (self.out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return res


def _diff(before: dict[str, str], after: dict[str, str]) -> str:
    out = []
    for path in sorted(set(before) | set(after)):
        a, b = before.get(path, ""), after.get(path, "")
        if a != b:
            out += difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True),
                                        fromfile=f"a/{path}", tofile=f"b/{path}")
    return "".join(out)
