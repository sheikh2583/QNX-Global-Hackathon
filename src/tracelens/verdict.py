"""Before/after verdict over several captures (PLAN.md §14, judge-roast backlog).

One run under Windows -> Hyper-V -> WSL2 -> KVM -> QEMU -> QNX is too noisy to
prove a fix, so a fix is VERIFIED only when, across >= ``min_runs`` clean
(non-lossy) captures on each side:

  1. every target finding kind (present in most "before" runs) is absent from
     every "after" run;
  2. no finding kind appears after that never appeared before (regression);
  3. for every declared deadline, the "after" p99 response is within budget, and
     where "before" missed it, "after" response times are significantly lower
     (one-sided Mann-Whitney U, p < alpha).

Too few clean runs gives INCONCLUSIVE rather than a guess. Running two batches
of the same build through ``compare`` measures the noise floor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .analyze import Analysis, analyze_file
from .config import Config
from .detectors import deadline
from .detectors._util import percentile
from .findings import at_least

VERIFIED, NOT_FIXED, INCONCLUSIVE = "VERIFIED", "NOT FIXED", "INCONCLUSIVE"


def mann_whitney_less(after: list[float], before: list[float]) -> tuple[float, float]:
    """One-sided Mann-Whitney U test that ``after`` tends to be smaller than ``before``.

    Returns (U for ``after``, p-value) using the normal approximation with tie
    correction and continuity correction (fine for the >= 5 runs x several jobs
    sample sizes used here).
    """
    n1, n2 = len(after), len(before)
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0
    pooled = sorted([(v, 0) for v in after] + [(v, 1) for v in before])
    ranks = [0.0] * len(pooled)
    ties = 0.0
    i = 0
    while i < len(pooled):
        j = i
        while j + 1 < len(pooled) and pooled[j + 1][0] == pooled[i][0]:
            j += 1
        rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = rank
        t = j - i + 1
        ties += t ** 3 - t
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, pooled) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    n = n1 + n2
    var = n1 * n2 / 12 * ((n + 1) - ties / (n * (n - 1)))
    if var <= 0:
        return u1, 1.0
    z = (u1 - mu + 0.5) / math.sqrt(var)  # small U = after smaller; +0.5 continuity
    p = 0.5 * math.erfc(-z / math.sqrt(2))  # P(Z <= z)
    return u1, p


@dataclass
class RunSummary:
    path: str
    lossy: bool
    kinds: set[str]
    responses: dict[str, list[int]]


@dataclass
class DeadlineCompare:
    name: str
    budget_ns: int
    before_p99: float
    after_p99: float
    before_misses: int
    after_misses: int
    p_value: float
    ok: bool
    reason: str


@dataclass
class Verdict:
    verdict: str
    reasons: list[str] = field(default_factory=list)
    targets: dict[str, tuple[float, float]] = field(default_factory=dict)  # kind -> (before rate, after rate)
    new_kinds: list[str] = field(default_factory=list)
    deadlines: list[DeadlineCompare] = field(default_factory=list)
    runs_before: int = 0
    runs_after: int = 0
    lossy_skipped: int = 0

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict, "reasons": self.reasons,
            "runs": {"before": self.runs_before, "after": self.runs_after, "lossy_skipped": self.lossy_skipped},
            "targets": {k: {"before_rate": b, "after_rate": a} for k, (b, a) in self.targets.items()},
            "new_kinds": self.new_kinds,
            "deadlines": [d.__dict__ for d in self.deadlines],
        }


def summarize(a: Analysis, cfg: Config, path: str = "") -> RunSummary:
    kinds = {f.kind for f in a.findings if at_least(f.severity, cfg.fail_on)}
    return RunSummary(path=path, lossy=a.model.lossy, kinds=kinds, responses=deadline.responses(a.model, cfg))


def compare_runs(before: list[RunSummary], after: list[RunSummary], cfg: Config,
                 target_kinds: list[str] | None = None, min_runs: int = 5,
                 alpha: float = 0.01, target_share: float = 0.6) -> Verdict:
    v = Verdict(verdict=INCONCLUSIVE)
    clean_b = [r for r in before if not r.lossy]
    clean_a = [r for r in after if not r.lossy]
    v.lossy_skipped = (len(before) - len(clean_b)) + (len(after) - len(clean_a))
    v.runs_before, v.runs_after = len(clean_b), len(clean_a)
    if len(clean_b) < min_runs or len(clean_a) < min_runs:
        v.reasons.append(f"need >= {min_runs} clean runs on each side, have {len(clean_b)} before and "
                         f"{len(clean_a)} after ({v.lossy_skipped} lossy skipped)")
        return v

    def rate(kind, runs):
        return sum(1 for r in runs if kind in r.kinds) / len(runs)

    seen_before = set().union(*(r.kinds for r in clean_b))
    seen_after = set().union(*(r.kinds for r in clean_a))
    targets = target_kinds or sorted(k for k in seen_before if rate(k, clean_b) >= target_share)
    failed = False
    if not targets and not target_kinds:
        v.reasons.append("no finding kind is present in most 'before' runs: nothing to verify")
    reproduced = []
    for k in targets:
        rb, ra = rate(k, clean_b), rate(k, clean_a)
        v.targets[k] = (rb, ra)
        if rb >= target_share:
            reproduced.append(k)
        else:
            # A fix can only be verified against a bug that showed up before it. Found live: a
            # workload that deadlocked in 0 of 5 runs made its reference fix look VERIFIED.
            v.reasons.append(f"{k} reproduced in only {rb:.0%} of 'before' runs (need {target_share:.0%})")
        if ra > 0:
            failed = True
            v.reasons.append(f"{k} still present in {ra:.0%} of 'after' runs")
    v.new_kinds = sorted(seen_after - seen_before)
    if v.new_kinds:
        failed = True
        v.reasons.append("new findings after the fix: " + ", ".join(v.new_kinds))

    for name, dl in cfg.deadlines.items():
        b = [x for r in clean_b for x in r.responses.get(name, [])]
        a = [x for r in clean_a for x in r.responses.get(name, [])]
        if not b or not a:
            continue
        budget = int(dl.budget_us * 1000)
        _, p = mann_whitney_less(a, b)
        bm, am = sum(1 for x in b if x > budget), sum(1 for x in a if x > budget)
        ap99 = percentile(a, 99)
        ok, reason = True, "within budget"
        if ap99 > budget:
            ok, reason = False, "after p99 over budget"
        elif bm and p >= alpha:
            ok, reason = False, f"improvement not significant (p={p:.3g} >= {alpha})"
        elif bm:
            reason = f"significantly faster (p={p:.2g})"
        v.deadlines.append(DeadlineCompare(name, budget, percentile(b, 99), ap99, bm, am, p, ok, reason))
        if not ok:
            failed = True
            v.reasons.append(f"deadline '{name}': {reason}")

    had_problem = bool(reproduced) or any(d.before_misses for d in v.deadlines)
    if failed:
        v.verdict = NOT_FIXED
    elif had_problem:
        v.verdict = VERIFIED
    else:
        v.reasons.append("the 'before' runs show no problem, so there is nothing to verify "
                         "(this is what a noise-floor run of one build against itself should say)")
    return v


def compare_files(before: list[str | Path], after: list[str | Path], cfg: Config, **kw) -> Verdict:
    sb = [summarize(analyze_file(p, cfg), cfg, str(p)) for p in before]
    sa = [summarize(analyze_file(p, cfg), cfg, str(p)) for p in after]
    return compare_runs(sb, sa, cfg, **kw)
