"""Timing baselines and the regression gate: "did my change make this slower?"

``tracelens compare`` answers "is the fix real?" from two sets of captures taken together.
A release gate has a harder job: the reference runs were taken weeks ago, by someone else, and
all it has is a file in the repository. So:

``tracelens baseline save``  records, per declared deadline and per job stream (the thread that
                             runs it), the response-time distribution of several captures, plus
                             the provenance needed to know whether a later comparison is fair:
                             tool version, config fingerprint, trace names and hashes, date.
``tracelens gate``           compares new captures against that file and exits non-zero when
                             something is significantly worse.

What counts as a regression
---------------------------

1. **A new finding kind.** A priority inversion that was not there before is a regression even if
   every deadline still fits. Rules cite the events that prove them, so this needs no statistics:
   any kind at or above ``fail_on`` present now and in no baseline run fails the gate. A kind the
   baseline *already* had is the baseline's problem (``tracelens analyze`` fails on it); its rate
   change is reported, not gated.
2. **A slower deadline.** Per metric, the p99 response time, compared two ways:

   * **Run-level (the trustworthy one).** With ``--min-runs`` (default 5) clean captures on each
     side, one p99 per capture is one sample, and a one-sided Mann-Whitney U test asks whether the
     new p99s are drawn from a slower distribution. Captures are the independent unit; the jobs
     inside one capture are not (they share a boot, a host load, a cache state), and treating 200
     jobs as 200 samples is how a timing gate ends up crying wolf.
   * **Threshold (fewer captures).** With fewer runs there is no rank test to run -- 1 against 1
     has no p-value at all -- so the gate says so and falls back to a stated rule: fail if the new
     p99 exceeds the *worst* p99 the baseline recorded, by more than the effect floors. Under no
     change, a fresh draw beats the worst of ``n`` baseline draws with probability ``1/(n+1)``,
     and the gate prints that number so nobody mistakes the answer for proof. ``--strict`` turns
     this mode into INCONCLUSIVE instead.
3. **Newly over budget.** A declared deadline the baseline met and this build misses fails the
   gate whatever the p-value says. If the baseline was already over budget, that is reported but
   does not fail: a regression gate reports what *changed*.

Honesty rules
-------------

*Effect floors.* A statistically real 2% shift is not a release blocker. A regression must also
exceed ``--min-regression-pct`` (default 10%) **and** ``--min-regression-us`` (default 50 us).
Both are tunable to 0 for hard real-time work.

*Multiple comparisons.* Test ten deadlines at alpha and one crosses by chance about ten times in
a hundred. All regression tests in one gate run form one family, Holm-Bonferroni adjusted
(:func:`tracelens.verdict.holm`), so ``--alpha`` bounds the chance of failing a build that did not
regress *overall*, not per metric. Raw and adjusted p-values are both reported. Family-wise
control, not FDR: for a gate, the expensive mistake is the false alarm.

*Lossy captures never pass quietly.* A lossy capture means the scheduler state machine broke, so
its timings are fiction. They are excluded, counted, printed, and listed in the JSON; if too few
clean captures remain the verdict is INCONCLUSIVE, and under ``--strict`` a single lossy capture
is enough for INCONCLUSIVE.

*A metric that vanished is not a pass.* If the baseline recorded a deadline and the new captures
contain no jobs for it, the gate returns INCONCLUSIVE: the markers may be gone, or the workload
may no longer run that job, and either way the question was not answered.

*A moved goalpost is not a comparison.* The baseline stores the deadline budgets, periods and
thresholds it was built with. If a compared deadline's budget or period has changed since, that
metric is INCONCLUSIVE; changed thresholds or ``fail_on`` are warnings, since they change which
findings count.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .analyze import Analysis, analyze_file
from .config import Config
from .detectors import deadline
from .detectors._util import percentile
from .findings import at_least
from .verdict import INCONCLUSIVE, holm, mann_whitney_greater, mann_whitney_less

SCHEMA = "tracelens/baseline/1"
PASS, REGRESSION = "PASS", "REGRESSION"

WORSE, BETTER, SAME, UNKNOWN = "worse", "better", "same", "inconclusive"


# --------------------------------------------------------------------------- samples from a capture


def metric_samples(a: Analysis, cfg: Config) -> dict[str, list[int]]:
    """Response times in ns per metric key: ``"<deadline>"`` pooled, ``"<deadline>@<thread>"`` per
    stream when more than one thread serves that deadline."""
    out: dict[str, list[int]] = {}
    for name, per in deadline.response_streams(a.model, cfg).items():
        pooled = [x for v in per.values() for x in v]
        if not pooled:
            continue
        out[name] = pooled
        if len(per) > 1:
            for label, v in per.items():
                out[f"{name}@{label}"] = v
    return out


@dataclass
class CaptureStats:
    """One capture, reduced to what a baseline file and a gate need."""

    path: str
    sha256: str
    lossy: bool
    kinds: list[str]  # findings at or above cfg.fail_on
    samples: dict[str, list[int]] = field(default_factory=dict)  # metric key -> response times (ns)

    @property
    def name(self) -> str:
        return Path(self.path).name


def _sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def stats_of(path: str | Path, cfg: Config, **kw) -> CaptureStats:
    a = analyze_file(path, cfg, **kw)
    return CaptureStats(
        path=str(path),
        sha256=_sha256(path),
        lossy=a.model.lossy,
        kinds=sorted({f.kind for f in a.findings if at_least(f.severity, cfg.fail_on)}),
        samples=metric_samples(a, cfg),
    )


def _ms(ns: float) -> float:
    return round(ns / 1e6, 4)


# --------------------------------------------------------------------------- baseline file


def build_baseline(captures: list[CaptureStats], cfg: Config, name: str,
                   config_path: str | Path | None = None) -> dict:
    """The baseline document. Lossy captures are excluded from every number and listed as lossy.

    One short array per metric per statistic, in capture order, so a reviewer can read the file and
    ``git diff`` tells them which capture moved.
    """
    clean = [c for c in captures if not c.lossy]
    streams_everywhere = set.intersection(*(set(c.samples) for c in clean)) if clean else set()
    metrics: dict[str, dict] = {}
    for key in sorted(streams_everywhere):
        dl_name, _, stream = key.partition("@")
        dl = cfg.deadlines.get(dl_name)
        per_run = [c.samples[key] for c in clean]
        metrics[key] = {
            "deadline": dl_name,
            "stream": stream or None,
            "budget_ms": _ms(dl.budget_us * 1000) if dl else None,
            "jobs_per_run": [len(v) for v in per_run],
            "p50_ms": [_ms(percentile(v, 50)) for v in per_run],
            "p99_ms": [_ms(percentile(v, 99)) for v in per_run],
            "max_ms": [_ms(max(v)) for v in per_run],
        }
    dropped = sorted({k for c in clean for k in c.samples} - streams_everywhere)
    rates = {}
    for kind in sorted({k for c in clean for k in c.kinds}):
        rates[kind] = round(sum(1 for c in clean if kind in c.kinds) / len(clean), 3)
    return {
        "schema": SCHEMA,
        "name": name,
        "tool_version": __version__,
        "created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runs": len(clean),
        "lossy_excluded": len(captures) - len(clean),
        "config": {
            "path": str(config_path) if config_path else None,
            "sha256": _sha256(config_path) if config_path else None,
            "fail_on": cfg.fail_on,
            "deadlines": {n: {"budget_us": d.budget_us, "period_us": d.period_us}
                          for n, d in sorted(cfg.deadlines.items())},
            "thresholds": dict(sorted(asdict(cfg.thresholds).items())),
        },
        "traces": [{"name": c.name, "sha256": c.sha256, "lossy": c.lossy,
                    "jobs": sum(len(v) for k, v in c.samples.items() if "@" not in k)}
                   for c in captures],
        "finding_rates": rates,
        "metrics": metrics,
        "metrics_not_in_every_run": dropped,
    }


def save_baseline(path: str | Path, doc: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def load_baseline(path: str | Path) -> dict:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != SCHEMA:
        raise ValueError(f"{path}: not a TraceLens baseline (schema {doc.get('schema')!r}, expected {SCHEMA!r})")
    if not doc.get("runs"):
        raise ValueError(f"{path}: the baseline has no clean captures in it")
    return doc


# --------------------------------------------------------------------------- the gate


@dataclass
class MetricGate:
    key: str
    deadline: str
    stream: str | None
    budget_ms: float | None
    base_p99_ms: float
    base_floor_ms: float  # the best p99 the baseline recorded
    base_ceiling_ms: float  # the worst p99 the baseline recorded: the threshold-mode bar
    new_p99_ms: float
    delta_ms: float
    delta_pct: float
    runs_base: int
    runs_new: int
    jobs_base: int
    jobs_new: int
    p_value: float | None = None  # raw, one-sided, "this build is slower"
    p_adjusted: float | None = None  # Holm-Bonferroni over every metric tested in this run
    p_improved: float | None = None  # the other direction, reported only (not part of the family)
    over_budget: bool = False
    status: str = SAME
    reason: str = ""

    @property
    def label(self) -> str:
        return self.key


@dataclass
class GateResult:
    verdict: str
    name: str = ""
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: list[MetricGate] = field(default_factory=list)
    new_kinds: list[str] = field(default_factory=list)
    gone_kinds: list[str] = field(default_factory=list)
    kind_rates: dict[str, tuple[float, float]] = field(default_factory=dict)
    runs_base: int = 0
    runs_new: int = 0
    lossy_excluded: int = 0
    lossy_traces: list[str] = field(default_factory=list)
    alpha: float = 0.05
    statistical: bool = False
    false_alarm_bound: float | None = None  # threshold mode: P(a fresh draw beats the baseline's worst)
    baseline: dict = field(default_factory=dict)

    @property
    def regressions(self) -> list[MetricGate]:
        return [m for m in self.metrics if m.status == WORSE]

    @property
    def improvements(self) -> list[MetricGate]:
        return [m for m in self.metrics if m.status == BETTER]

    def to_dict(self) -> dict:
        b = self.baseline
        return {
            "verdict": self.verdict,
            "name": self.name,
            "evidence": "run-level Mann-Whitney U" if self.statistical else "threshold (too few runs for a p-value)",
            "alpha": self.alpha,
            "false_alarm_bound": self.false_alarm_bound,
            "runs": {"baseline": self.runs_base, "candidate": self.runs_new,
                     "lossy_excluded": self.lossy_excluded, "lossy_traces": self.lossy_traces},
            "baseline": {"name": b.get("name"), "created": b.get("created"),
                         "tool_version": b.get("tool_version"), "traces": [t["name"] for t in b.get("traces", [])]},
            "findings": {"new_kinds": self.new_kinds, "no_longer_present": self.gone_kinds,
                         "rates": {k: {"baseline": a, "candidate": c} for k, (a, c) in self.kind_rates.items()}},
            "metrics": [asdict(m) for m in self.metrics],
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


def fmt_delta(m: MetricGate) -> str:
    """"+147%", or "15.4x slower" once a percentage stops being readable."""
    if m.base_p99_ms > 0 and abs(m.delta_pct) >= 1000:
        ratio = m.new_p99_ms / m.base_p99_ms
        return f"{ratio:.1f}x slower" if ratio >= 1 else f"{1 / ratio:.1f}x faster"
    return f"{m.delta_pct:+.0f}%"


def _headline(m: MetricGate) -> str:
    """"brake p99 0.77 -> 1.90 ms (+147%), Mann-Whitney U p=0.004 over 5+5 runs"."""
    out = f"{m.key} p99 {m.base_p99_ms:.2f} -> {m.new_p99_ms:.2f} ms ({fmt_delta(m)})"
    if m.p_adjusted is not None:
        out += (f", Mann-Whitney U p={m.p_value:.3g} (adjusted {m.p_adjusted:.3g}) "
                f"over {m.runs_base}+{m.runs_new} runs")
    else:
        out += f", {m.runs_base}+{m.runs_new} runs: no p-value"
    return out


def _config_drift(doc: dict, cfg: Config) -> tuple[dict[str, str], list[str]]:
    """Per-deadline "the goalposts moved" notes, and config warnings."""
    saved = doc.get("config", {})
    moved: dict[str, str] = {}
    for name, d in saved.get("deadlines", {}).items():
        now = cfg.deadlines.get(name)
        if now is None:
            moved[name] = f"deadline '{name}' is no longer declared in the config"
        elif now.budget_us != d.get("budget_us") or now.period_us != d.get("period_us"):
            moved[name] = (f"deadline '{name}' changed since the baseline: budget "
                           f"{d.get('budget_us')} -> {now.budget_us} us, period "
                           f"{d.get('period_us')} -> {now.period_us} us")
    warnings = []
    if saved.get("fail_on") and saved["fail_on"] != cfg.fail_on:
        warnings.append(f"fail_on changed since the baseline ({saved['fail_on']} -> {cfg.fail_on}): "
                        "the finding kinds on each side were selected by different rules")
    changed = [k for k, v in saved.get("thresholds", {}).items()
               if getattr(cfg.thresholds, k, v) != v]
    if changed:
        warnings.append("detector thresholds changed since the baseline (" + ", ".join(sorted(changed))
                        + "): which findings count is not the same on both sides")
    if saved.get("sha256") is None:
        warnings.append("the baseline was built with no config file, so no deadline could be declared "
                        "unless the defaults supplied one")
    return moved, warnings


def gate(captures: list[CaptureStats], doc: dict, cfg: Config, min_runs: int = 5, alpha: float = 0.05,
         min_regression_pct: float = 10.0, min_regression_us: float = 50.0,
         strict: bool = False) -> GateResult:
    """Compare ``captures`` against the baseline document ``doc``. See the module docstring."""
    r = GateResult(verdict=PASS, name=doc.get("name", ""), alpha=alpha, baseline=doc)
    clean = [c for c in captures if not c.lossy]
    r.lossy_traces = [c.name for c in captures if c.lossy]
    r.lossy_excluded = len(r.lossy_traces)
    r.runs_base, r.runs_new = int(doc["runs"]), len(clean)
    if r.lossy_excluded:
        r.warnings.append(f"{r.lossy_excluded} lossy capture(s) excluded ({', '.join(r.lossy_traces)}): a broken "
                          "scheduler state machine makes their timings fiction")
    if doc.get("lossy_excluded"):
        r.warnings.append(f"the baseline itself excluded {doc['lossy_excluded']} lossy capture(s)")

    if not clean:
        r.verdict = INCONCLUSIVE
        r.reasons.append(f"no clean capture to gate: all {len(captures)} were lossy")
        return r
    if strict and r.lossy_excluded:
        r.verdict = INCONCLUSIVE
        r.reasons.append("--strict: a lossy capture in the set is enough to withhold a verdict")
        return r

    r.statistical = r.runs_base >= min_runs and r.runs_new >= min_runs
    if not r.statistical:
        r.false_alarm_bound = 1.0 / (r.runs_base + 1)
        note = (f"{r.runs_base} baseline and {r.runs_new} candidate capture(s): fewer than the {min_runs} per side "
                f"a rank test needs, so no p-value is computed. Timing uses the stated threshold rule instead; "
                f"a build that did not change would beat the baseline's worst p99 about "
                f"{r.false_alarm_bound:.0%} of the time by chance. Record {min_runs}+ captures per side for a "
                f"verdict you can lean on.")
        if strict:
            r.verdict = INCONCLUSIVE
            r.reasons.append("--strict: " + note)
            return r
        r.warnings.append(note)

    moved, cfg_warnings = _config_drift(doc, cfg)
    r.warnings.extend(cfg_warnings)

    # 1. finding kinds. A rule finding cites the events that prove it, so no statistics here.
    base_rates: dict[str, float] = dict(doc.get("finding_rates", {}))
    new_rates = {k: round(sum(1 for c in clean if k in c.kinds) / len(clean), 3)
                 for k in sorted({k for c in clean for k in c.kinds})}
    r.kind_rates = {k: (base_rates.get(k, 0.0), new_rates.get(k, 0.0))
                    for k in sorted(set(base_rates) | set(new_rates))}
    r.new_kinds = [k for k in sorted(new_rates) if not base_rates.get(k)]
    r.gone_kinds = [k for k in sorted(base_rates) if base_rates[k] and not new_rates.get(k)]
    failed = bool(r.new_kinds)
    for k in r.new_kinds:
        r.reasons.append(f"new finding kind '{k}' in {new_rates[k]:.0%} of the new captures, in none of the "
                         f"{r.runs_base} baseline captures (at or above '{cfg.fail_on}')")
    for k, (rb, ra) in r.kind_rates.items():
        if rb and ra > rb:
            r.warnings.append(f"'{k}' was already in the baseline and got more frequent "
                              f"({rb:.0%} -> {ra:.0%} of runs); the gate reports what changed, and "
                              f"`tracelens analyze` is what fails a build for a finding it already had")

    # 2. timing, metric by metric.
    pending: list[tuple[MetricGate, list[float], list[float]]] = []
    for key, saved in sorted(doc.get("metrics", {}).items()):
        base_p99 = list(saved["p99_ms"])
        new_vals = [c.samples[key] for c in clean if key in c.samples]
        m = MetricGate(
            key=key, deadline=saved.get("deadline", key), stream=saved.get("stream"),
            budget_ms=saved.get("budget_ms"),
            base_p99_ms=percentile(base_p99, 50), base_floor_ms=min(base_p99), base_ceiling_ms=max(base_p99),
            new_p99_ms=0.0, delta_ms=0.0, delta_pct=0.0,
            runs_base=len(base_p99), runs_new=len(new_vals),
            jobs_base=sum(saved.get("jobs_per_run", [])), jobs_new=sum(len(v) for v in new_vals),
        )
        r.metrics.append(m)
        if not new_vals:
            m.status, m.reason = UNKNOWN, ("no jobs for this deadline in the new captures: the markers or the "
                                           "workload changed, so the question was not answered")
            continue
        if m.deadline in moved:
            m.status, m.reason = UNKNOWN, moved[m.deadline]
            continue
        new_p99 = [percentile(v, 99) / 1e6 for v in new_vals]
        m.new_p99_ms = round(percentile(new_p99, 50), 4)
        m.delta_ms = round(m.new_p99_ms - m.base_p99_ms, 4)
        m.delta_pct = round(100.0 * m.delta_ms / m.base_p99_ms, 1) if m.base_p99_ms else 0.0
        m.over_budget = bool(m.budget_ms and m.new_p99_ms > m.budget_ms)
        pending.append((m, base_p99, new_p99))

    if r.statistical:
        for m, b, n in pending:
            m.p_value = mann_whitney_greater(n, b)[1]
            m.p_improved = mann_whitney_less(n, b)[1]
        for m, adj in zip([m for m, _, _ in pending], holm([m.p_value for m, _, _ in pending]), strict=True):
            m.p_adjusted = adj

    def worse_enough(delta_ms: float, reference_ms: float) -> bool:
        """Is this slowdown worth a release engineer's attention, never mind its p-value?"""
        return (delta_ms > 0 and reference_ms > 0
                and 100.0 * delta_ms / reference_ms >= min_regression_pct
                and delta_ms * 1000 >= min_regression_us)

    for m, _b, _n in pending:
        base_over = bool(m.budget_ms and m.base_p99_ms > m.budget_ms)
        if m.over_budget and not base_over:
            m.status = WORSE
            m.reason = f"{_headline(m)}, over the {m.budget_ms:.2f} ms budget the baseline met"
            continue
        budget_note = f"; still over the {m.budget_ms:.2f} ms budget, as the baseline was" if m.over_budget else ""
        if r.statistical:
            significant = m.p_adjusted is not None and m.p_adjusted < alpha
            if significant and worse_enough(m.delta_ms, m.base_p99_ms):
                m.status, m.reason = WORSE, f"slower: {_headline(m)}{budget_note}"
            elif significant:
                m.reason = (f"slower but by less than the floors ({m.delta_pct:+.1f}%, {m.delta_ms * 1000:+.0f} us; "
                            f"floors {min_regression_pct:.0f}% and {min_regression_us:.0f} us){budget_note}")
            elif m.p_improved < alpha and worse_enough(-m.delta_ms, m.base_p99_ms):
                m.status, m.reason = BETTER, f"faster: {_headline(m)}{budget_note}"
            else:
                m.reason = f"no significant change (p={m.p_value:.3g}, {m.delta_pct:+.1f}%){budget_note}"
        else:  # threshold mode: beat the worst p99 the baseline recorded, by more than the floors
            over_ceiling = m.new_p99_ms - m.base_ceiling_ms
            if worse_enough(over_ceiling, m.base_ceiling_ms):
                m.status = WORSE
                m.reason = (f"slower: {_headline(m)}; above the baseline's worst capture "
                            f"({m.base_ceiling_ms:.2f} ms) by {over_ceiling * 1000:.0f} us{budget_note}")
            elif worse_enough(m.base_floor_ms - m.new_p99_ms, m.base_floor_ms):
                m.status, m.reason = BETTER, f"faster: {_headline(m)}{budget_note}"
            else:
                m.reason = (f"within the baseline's range ({m.base_floor_ms:.2f}-{m.base_ceiling_ms:.2f} ms), "
                            f"{m.delta_pct:+.1f}%{budget_note}")

    # One reason per deadline: when the pooled distribution already fails, the streams that fail
    # with it are a count, not five more lines saying the same thing (Z4 has four tile workers).
    failed = failed or any(m.status == WORSE for m in r.metrics)
    worse_streams: dict[str, int] = {}
    for m in r.metrics:
        if m.status == WORSE and m.stream:
            worse_streams[m.deadline] = worse_streams.get(m.deadline, 0) + 1
    for m in r.metrics:
        if m.status not in (WORSE, UNKNOWN):
            continue
        if m.stream and any(o.key == m.deadline and o.status == WORSE for o in r.metrics):
            continue
        extra = ""
        if not m.stream and worse_streams.get(m.deadline):
            extra = f" ({worse_streams[m.deadline]} of its job streams regressed too)"
        r.reasons.append(f"deadline '{m.key}': {m.reason}{extra}")

    if failed:
        r.verdict = REGRESSION
    elif any(m.status == UNKNOWN for m in r.metrics):
        r.verdict = INCONCLUSIVE
    else:
        r.verdict = PASS
        if not r.metrics:
            r.warnings.append("the baseline recorded no deadline response times, so this gate compared finding "
                              "kinds only: declare a [deadlines.<job>] budget to gate timing too")
    return r


def gate_files(traces: list[str | Path], baseline: str | Path, cfg: Config, **kw) -> GateResult:
    doc = load_baseline(baseline)
    return gate([stats_of(p, cfg) for p in traces], doc, cfg, **kw)
