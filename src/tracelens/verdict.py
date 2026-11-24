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


EXACT_MAX_N = 60  # above this the normal approximation is used (the DP below gets slow, and n is ample)


# --- How sure can we be that a fix worked? (research track R1) -----------------------------------
# "The bug did not show in 0 of 5 after-captures" bounds the remaining per-capture rate only to about
# 45% (0 of 10: about 26%, at 95% confidence). A reader would compute this anyway, so we report it.
# The unit is the capture: periods inside one capture are not independent samples.


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p), summed in log space so n in the thousands is fine."""
    if k < 0 or p >= 1.0:
        return 0.0
    if k >= n or p <= 0.0:
        return 1.0
    lp, lq = math.log(p), math.log1p(-p)
    terms = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq
             for i in range(k + 1)]
    m = max(terms)
    return min(1.0, math.exp(m) * sum(math.exp(t - m) for t in terms))


def _root_decreasing(f) -> float:
    """The p in (0, 1) where the decreasing function f crosses zero, by bisection."""
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def residual_rate_upper(n_clean_after: int, k_after: int = 0, confidence: float = 0.95) -> float:
    """One-sided Clopper-Pearson upper bound on the per-capture rate at which a bug still shows, given it
    showed in ``k_after`` of ``n_clean_after`` clean after-captures. For k = 0 it is 1 - (1 - c)^(1/n)."""
    if n_clean_after <= 0 or k_after >= n_clean_after:
        return 1.0
    alpha = 1.0 - confidence
    if k_after == 0:
        return 1.0 - alpha ** (1.0 / n_clean_after)
    return _root_decreasing(lambda p: _binom_cdf(k_after, n_clean_after, p) - alpha)


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Two-sided Clopper-Pearson interval for a rate seen in ``k`` of ``n`` captures."""
    if n <= 0:
        return (0.0, 1.0)
    a = (1.0 - confidence) / 2.0
    lo = 0.0 if k <= 0 else _root_decreasing(lambda p: _binom_cdf(k - 1, n, p) - (1.0 - a))
    hi = 1.0 if k >= n else _root_decreasing(lambda p: _binom_cdf(k, n, p) - a)
    return (lo, hi)


def runs_needed(target_rate: float, confidence: float = 0.95) -> int:
    """Fewest clean after-captures, the bug in none of them, that bound the residual rate by ``target_rate``."""
    return math.ceil(math.log(1.0 - confidence) / math.log(1.0 - target_rate))


def _midranks(pooled: list[tuple[float, int]]) -> tuple[list[float], float]:
    """Mid-ranks of a sorted pooled sample, plus the tie correction sum(t^3 - t)."""
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
    return ranks, ties


def _exact_p_le(ranks: list[float], n1: int, r1: float) -> float:
    """P(rank sum of a random size-``n1`` subset <= ``r1``) under the null, ties and all.

    The exact conditional permutation distribution: every one of the C(n, n1) splits of these
    rank values is equally likely when the two samples come from the same distribution. Mid-ranks
    are multiples of 0.5, so the sums are counted in doubled units with an integer DP over
    (subset size, doubled sum) -- no enumeration of the splits themselves.
    """
    doubled = [int(round(2 * r)) for r in ranks]
    total = sum(doubled)
    counts = [[0] * (total + 1) for _ in range(n1 + 1)]
    counts[0][0] = 1
    for d in doubled:
        for k in range(min(n1, len(doubled)) - 1, -1, -1):
            row, nxt = counts[k], counts[k + 1]
            for sm in range(total - d, -1, -1):
                if row[sm]:
                    nxt[sm + d] += row[sm]
    row = counts[n1]
    whole = sum(row)
    target = int(round(2 * r1))
    return sum(row[: target + 1]) / whole if whole else 1.0


def mann_whitney_less(after: list[float], before: list[float], exact: bool | None = None) -> tuple[float, float]:
    """One-sided Mann-Whitney U test that ``after`` tends to be smaller than ``before``.

    Returns (U for ``after``, p-value). Small samples (``n <= EXACT_MAX_N``, or ``exact=True``)
    get the exact conditional permutation p-value, which matters for the run-level comparisons the
    regression gate makes: with 5 runs against 5 the normal approximation is off by a factor of
    two, and the smallest p-value obtainable is 1/252 = 0.004. Larger samples (the fix engine pools
    every job of every run) use the normal approximation with tie and continuity corrections.
    """
    n1, n2 = len(after), len(before)
    if n1 == 0 or n2 == 0:
        return 0.0, 1.0
    pooled = sorted([(v, 0) for v in after] + [(v, 1) for v in before])
    ranks, ties = _midranks(pooled)
    r1 = sum(r for r, (_, g) in zip(ranks, pooled, strict=True) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    if exact or (exact is None and n1 + n2 <= EXACT_MAX_N):
        return u1, _exact_p_le(ranks, n1, r1)
    mu = n1 * n2 / 2
    n = n1 + n2
    var = n1 * n2 / 12 * ((n + 1) - ties / (n * (n - 1)))
    if var <= 0:
        return u1, 1.0
    z = (u1 - mu + 0.5) / math.sqrt(var)  # small U = after smaller; +0.5 continuity
    p = 0.5 * math.erfc(-z / math.sqrt(2))  # P(Z <= z)
    return u1, p


def mann_whitney_greater(x: list[float], y: list[float], exact: bool | None = None) -> tuple[float, float]:
    """One-sided test that ``x`` tends to be *larger* than ``y`` -- the regression direction."""
    u, p = mann_whitney_less(y, x, exact=exact)
    return u, p


def holm(p_values: list[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the order given.

    Test k metrics at alpha and one of them crosses by chance roughly k*alpha of the time. Holm
    multiplies the smallest raw p-value by k, the next by k-1, and so on (keeping the sequence
    monotone), which holds the chance of failing a build that did not regress at alpha *overall*,
    not per metric. Chosen over Benjamini-Hochberg because a release gate's expensive mistake is
    the false alarm: controlling the family-wise error rate is the behaviour a team can trust.
    Uniformly more powerful than plain Bonferroni, and stdlib arithmetic.
    """
    k = len(p_values)
    order = sorted(range(k), key=lambda i: p_values[i])
    out = [0.0] * k
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (k - rank) * p_values[i]))
        out[i] = running
    return out


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
    confidence: float = 0.95
    counts: dict[str, tuple[int, int, int, int]] = field(default_factory=dict)  # (k, n) before, (k, n) after
    notes: list[str] = field(default_factory=list)  # plain sentences for the reader, not failure reasons

    def to_dict(self) -> dict:
        pct = f"{round(self.confidence * 100):d}"
        targets = {}
        for k, (b, a) in self.targets.items():
            t = {"before_rate": b, "after_rate": a}
            if k in self.counts:
                kb, nb, ka, na = self.counts[k]
                lo, hi = clopper_pearson(kb, nb, self.confidence)
                t.update({"before_k": kb, "before_n": nb, "before_rate_ci": [round(lo, 4), round(hi, 4)],
                          "after_k": ka, "after_n": na,
                          f"residual_rate_upper_{pct}": round(residual_rate_upper(na, ka, self.confidence), 4)})
            targets[k] = t
        return {
            "verdict": self.verdict, "reasons": self.reasons, "notes": self.notes, "confidence": self.confidence,
            "runs": {"before": self.runs_before, "after": self.runs_after, "lossy_skipped": self.lossy_skipped},
            "targets": targets,
            "new_kinds": self.new_kinds,
            "deadlines": [d.__dict__ for d in self.deadlines],
        }


def summarize(a: Analysis, cfg: Config, path: str = "") -> RunSummary:
    kinds = {f.kind for f in a.findings if at_least(f.severity, cfg.fail_on)}
    return RunSummary(path=path, lossy=a.model.lossy, kinds=kinds, responses=deadline.responses(a.model, cfg))


def compare_runs(before: list[RunSummary], after: list[RunSummary], cfg: Config,
                 target_kinds: list[str] | None = None, min_runs: int = 5,
                 alpha: float = 0.01, target_share: float = 0.6, confidence: float = 0.95) -> Verdict:
    v = Verdict(verdict=INCONCLUSIVE, confidence=confidence)
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
        kb, ka = sum(1 for r in clean_b if k in r.kinds), sum(1 for r in clean_a if k in r.kinds)
        v.counts[k] = (kb, len(clean_b), ka, len(clean_a))
        upper = residual_rate_upper(len(clean_a), ka, confidence)
        if ka == 0:
            v.notes.append(f"{k}: not seen in {len(clean_a)} of {len(clean_a)} clean after-captures; if the bug is "
                           f"still there, it shows in at most {upper:.0%} of captures ({confidence:.0%} confidence).")
        else:
            v.notes.append(f"{k}: seen in {ka} of {len(clean_a)} clean after-captures; the rate it still shows at is "
                           f"at most {upper:.0%} of captures ({confidence:.0%} confidence).")
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
