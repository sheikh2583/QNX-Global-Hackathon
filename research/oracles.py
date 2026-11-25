"""R2.3: five acceptance oracles for "is this patch a fix?", as pure functions over before/after RunSummary lists.

Each oracle answers ACCEPT, REJECT or INCONCLUSIVE:

  O1 single-run     the first clean after-capture has no target finding            (the "I ran it once" tester)
  O2 deadline-only  pooled after p99 is within every declared budget               (the stopwatch tester)
  O3 findings-only  no target finding in any clean after-capture, no statistics
  O4 full           `compare_runs` as shipped: VERIFIED = accept, NOT FIXED = reject, INCONCLUSIVE = inconclusive.
                    Its deadline test pools every job of every capture into one Mann-Whitney U test ("job" unit).
  O4c full/capture  the same verdict with the deadline significance test run on one p99 per capture (the gate's unit,
                    exact test). Findings, new kinds, the budget check and the minimum-runs rule are identical.
  O5 full + bound   O4 accepts AND the 95% residual-rate bound is at most `max_residual` (default 0.2)

"Target findings" are the kinds present in at least `target_share` of the clean before-captures (the same rule compare_runs
uses). With no target kind nothing can be verified: O1/O3 report INCONCLUSIVE. O2 with no declared deadline accepts vacuously;
that is a property of the oracle, reported as such. Lossy captures are ignored by every oracle.

Nothing here is imported by src/tracelens/.
"""

# ruff: noqa: E501

from __future__ import annotations

import random
from collections.abc import Callable

from tracelens.config import Config
from tracelens.detectors._util import percentile
from tracelens.verdict import (INCONCLUSIVE, NOT_FIXED, VERIFIED, RunSummary, compare_runs, mann_whitney_less,
                               residual_rate_upper)

ACCEPT, REJECT, UNSURE = "accept", "reject", "inconclusive"
NAMES = ("O1", "O2", "O3", "O4", "O4c", "O5")
TARGET_SHARE = 0.6


def _clean(runs: list[RunSummary]) -> list[RunSummary]:
    return [r for r in runs if not r.lossy]


def target_kinds(before: list[RunSummary], share: float = TARGET_SHARE) -> list[str]:
    b = _clean(before)
    if not b:
        return []
    kinds = set().union(*(r.kinds for r in b))
    return sorted(k for k in kinds if sum(1 for r in b if k in r.kinds) / len(b) >= share)


def o1_single_run(before: list[RunSummary], after: list[RunSummary], cfg: Config) -> str:
    a, targets = _clean(after), target_kinds(before)
    if not a or not targets:
        return UNSURE
    return ACCEPT if not (set(targets) & a[0].kinds) else REJECT


def o2_deadline_only(before: list[RunSummary], after: list[RunSummary], cfg: Config) -> str:
    a = _clean(after)
    if not a:
        return UNSURE
    for name, dl in cfg.deadlines.items():
        pooled = [x for r in a for x in r.responses.get(name, [])]
        if pooled and percentile(pooled, 99) > dl.budget_us * 1000:
            return REJECT
    return ACCEPT


def o3_findings_only(before: list[RunSummary], after: list[RunSummary], cfg: Config) -> str:
    a, targets = _clean(after), target_kinds(before)
    if not a or not targets:
        return UNSURE
    return ACCEPT if not any(set(targets) & r.kinds for r in a) else REJECT


def o4_full(before: list[RunSummary], after: list[RunSummary], cfg: Config) -> str:
    v = compare_runs(before, after, cfg)
    return {VERIFIED: ACCEPT, NOT_FIXED: REJECT, INCONCLUSIVE: UNSURE}[v.verdict]


def o4c_full_capture_unit(before: list[RunSummary], after: list[RunSummary], cfg: Config, min_runs: int = 5,
                          alpha: float = 0.01) -> str:
    """O4 with the deadline significance test over per-capture p99s instead of pooled jobs (see the module docstring).

    Implemented without touching src/tracelens: the shipped comparison runs with the deadlines removed (findings and
    new kinds), and the deadline part is redone here with the same rules as `compare_runs` except for the unit.
    """
    import copy
    b, a = _clean(before), _clean(after)
    if len(b) < min_runs or len(a) < min_runs:
        return UNSURE
    bare = copy.copy(cfg)
    bare.deadlines = {}
    v = compare_runs(before, after, bare, min_runs=min_runs, alpha=alpha)
    if v.verdict == NOT_FIXED:
        return REJECT
    had_problem = v.verdict == VERIFIED
    for name, dl in cfg.deadlines.items():
        bj = [x for r in b for x in r.responses.get(name, [])]
        aj = [x for r in a for x in r.responses.get(name, [])]
        if not bj or not aj:
            continue
        budget = int(dl.budget_us * 1000)
        b99 = [percentile(r.responses[name], 99) for r in b if r.responses.get(name)]
        a99 = [percentile(r.responses[name], 99) for r in a if r.responses.get(name)]
        misses_before = sum(1 for x in bj if x > budget)
        had_problem = had_problem or bool(misses_before)
        if percentile(aj, 99) > budget:
            return REJECT
        if misses_before and mann_whitney_less(a99, b99)[1] >= alpha:
            return REJECT
    return ACCEPT if had_problem else UNSURE


def o5_full_with_bound(before: list[RunSummary], after: list[RunSummary], cfg: Config, max_residual: float = 0.2) -> str:
    verdict = o4_full(before, after, cfg)
    if verdict != ACCEPT:
        return verdict
    a, targets = _clean(after), target_kinds(before)
    worst = max((residual_rate_upper(len(a), sum(1 for r in a if k in r.kinds)) for k in targets), default=1.0)
    return ACCEPT if worst <= max_residual else UNSURE


ORACLES: dict[str, Callable[..., str]] = {
    "O1": o1_single_run, "O2": o2_deadline_only, "O3": o3_findings_only, "O4": o4_full, "O4c": o4c_full_capture_unit, "O5": o5_full_with_bound,
}


def judge(before: list[RunSummary], after: list[RunSummary], cfg: Config) -> dict[str, str]:
    return {n: fn(before, after, cfg) for n, fn in ORACLES.items()}


def sweep(before: list[RunSummary], after: list[RunSummary], cfg: Config, ns=(1, 3, 5, 10, 20), draws: int = 1000,
          seed: str = "oracle-sweep") -> dict[int, dict[str, dict[str, int]]]:
    """R2.4: for each N, ``draws`` seeded random subsets of N before- and N after-captures; count each oracle's answers.

    Subsets overlap (they come from one pool of captures), so the full-pool result is the main number and this is a curve.
    At N equal to the pool size every draw is the same set, so the counts are all-or-nothing.
    """
    out: dict[int, dict[str, dict[str, int]]] = {}
    for n in ns:
        rng = random.Random(f"{seed}:{n}")
        counts = {o: {ACCEPT: 0, REJECT: 0, UNSURE: 0} for o in NAMES}
        for _ in range(draws):
            b = rng.sample(before, min(n, len(before)))
            a = rng.sample(after, min(n, len(after)))
            for o, ans in judge(b, a, cfg).items():
                counts[o][ans] += 1
        out[n] = counts
    return out
