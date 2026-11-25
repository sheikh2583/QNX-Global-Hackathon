"""R8, simulator part: false alarms and power of the capture-as-unit regression gate.

Everything here is seeded and regenerable:  python research/gate_study.py
Captures come from the built-in simulator (`healthy_periodic`, high-priority job `hi` whose
work is `work_us`). Raw per-capture response times are cached in data/research/gate_sim/ (not in
git); the committed output is docs/research/gate_study.json (read by research/make_numbers.py).

Comparators, all given the same captures:
  capture   tracelens gate: one p99 per capture, one-sided Mann-Whitney over captures.
  job       research-only: pool every job of every capture on each side, one-sided Mann-Whitney
            over jobs. This treats jobs that share a boot and a cache as independent: the thing
            the gate refuses to do.
Each is run with the effect floors on (10%, 50 us) and off.
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import tempfile
from pathlib import Path

from tracelens import gate as G
from tracelens.config import load_config
from tracelens.detectors._util import percentile
from tracelens.sim import simulate, write_trace
from tracelens.verdict import clopper_pearson, holm, mann_whitney_greater

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "research" / "gate_sim"
OUT = ROOT / "docs" / "research" / "gate_study.json"

BASE_WORK = 300
EFFECTS = (0, 1, 2, 5, 10, 20, 50)  # percent more work in the high-priority job
SEEDS = range(1, 31)
SPLITS = 1000
ALPHA = 0.05
FLOOR_PCT, FLOOR_US = 10.0, 50.0


def work_for(pct: int) -> int:
    return round(BASE_WORK * (1 + pct / 100))


def cfg_for():
    d = Path(tempfile.mkdtemp())
    (d / "t.toml").write_text('fail_on = "high"\n\n[deadlines.hi]\nbudget_us = 2500\n', encoding="utf-8")
    return load_config(d / "t.toml")


def capture(pct: int, seed: int, cfg) -> dict:
    """Response times (ns) of the `hi` deadline in one simulated capture, cached."""
    f = CACHE / f"w{work_for(pct)}_s{seed}.json"
    if f.exists():
        return json.loads(f.read_text())
    text = simulate("healthy_periodic", {"work_us": work_for(pct)}, seed=seed)
    p = write_trace(Path(tempfile.mkdtemp()) / "c.txt", text)
    s = G.stats_of(p, cfg)
    doc = {"lossy": s.lossy, "kinds": s.kinds, "hi": s.samples.get("hi", [])}
    f.write_text(json.dumps(doc))
    return doc


def p99_ms(c: dict) -> float:
    return percentile(c["hi"], 99) / 1e6


def floors_ok(delta_ms: float, ref_ms: float, on: bool) -> bool:
    if not on:
        return delta_ms > 0
    return delta_ms > 0 and ref_ms > 0 and 100 * delta_ms / ref_ms >= FLOOR_PCT and delta_ms * 1000 >= FLOOR_US


def alarm_capture(base: list[dict], new: list[dict], floors: bool) -> bool:
    b, n = [p99_ms(c) for c in base], [p99_ms(c) for c in new]
    p = mann_whitney_greater(n, b)[1]
    return p < ALPHA and floors_ok(percentile(n, 50) - percentile(b, 50), percentile(b, 50), floors)


def alarm_job(base: list[dict], new: list[dict], floors: bool) -> bool:
    b = [x for c in base for x in c["hi"]]
    n = [x for c in new for x in c["hi"]]
    p = mann_whitney_greater(n, b, exact=False)[1]
    pb, pn = percentile(b, 99) / 1e6, percentile(n, 99) / 1e6
    return p < ALPHA and floors_ok(pn - pb, pb, floors)


def rate(k: int, n: int) -> dict:
    lo, hi = clopper_pearson(k, n, 0.95)
    return {"k": k, "n": n, "rate": round(k / n, 4), "ci95": [round(lo, 4), round(hi, 4)]}


def tally(draw, n_trials: int) -> dict:
    cnt = {(c, f): 0 for c in ("capture", "job") for f in (False, True)}
    for _ in range(n_trials):
        a, b = draw()
        for c, fn in (("capture", alarm_capture), ("job", alarm_job)):
            for f in (False, True):
                cnt[(c, f)] += fn(a, b, f)
    return {f"{c}_floors_{'on' if f else 'off'}": rate(v, n_trials) for (c, f), v in cnt.items()}


def aa(pool: list[dict]) -> dict:
    out = {}
    for n in (5, 10):
        rng = random.Random(f"aa{n}")

        def draw(n=n, rng=rng):
            idx = rng.sample(range(len(pool)), 2 * n)
            return [pool[i] for i in idx[:n]], [pool[i] for i in idx[n:]]

        out[f"{n}v{n}"] = tally(draw, SPLITS)
    return out


def power(base_pool: list[dict], eff_pools: dict[int, list[dict]]) -> dict:
    out = {}
    for pct, pool in eff_pools.items():
        for n in (5, 10, 15):
            rng = random.Random(f"pw{pct}:{n}")

            def draw(n=n, rng=rng, pool=pool):
                return rng.sample(base_pool, n), rng.sample(pool, n)

            out[f"+{pct}%_n{n}"] = tally(draw, SPLITS)
    return out


def bh(ps: list[float]) -> list[float]:
    k = len(ps)
    order = sorted(range(k), key=lambda i: ps[i], reverse=True)
    out, run = [0.0] * k, 1.0
    for pos, i in enumerate(order):
        run = min(run, ps[i] * k / (k - pos))
        out[i] = run
    return out


def family(pool: list[dict], k: int = 10) -> dict:
    """k independent metrics under A/A. Each metric's per-capture p99 is the real `hi` p99 of a
    capture drawn independently (a separate draw per metric): real marginals, no correlation.
    Labelled synthetic in the write-up: real metrics of one capture are correlated, which makes
    every correction look slightly better than it would be in practice."""
    p99s = [p99_ms(c) for c in pool]
    n = 5
    res = {"none": 0, "holm": 0, "bh": 0}
    rng = random.Random("family")
    for _ in range(SPLITS):
        ps = []
        for _m in range(k):
            idx = rng.sample(range(len(p99s)), 2 * n)
            ps.append(mann_whitney_greater([p99s[i] for i in idx[:n]], [p99s[i] for i in idx[n:]])[1])
        res["none"] += min(ps) < ALPHA
        res["holm"] += min(holm(ps)) < ALPHA
        res["bh"] += min(bh(ps)) < ALPHA
    return {"metrics": k, "n_per_side": n, "any_false_alarm": {m: rate(v, SPLITS) for m, v in res.items()}}


def main() -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    cfg = cfg_for()
    pools = {pct: [capture(pct, s, cfg) for s in SEEDS] for pct in EFFECTS}
    lossy = {str(p): sum(c["lossy"] for c in v) for p, v in pools.items()}
    pools = {p: [c for c in v if not c["lossy"] and c["hi"]] for p, v in pools.items()}
    base = pools[0]
    p99s = [p99_ms(c) for c in base]
    doc = {
        "simulator": "tracelens.sim healthy_periodic, seeds 1-30, hi job work_us=300 (+effect)",
        "unit": "capture", "alpha": ALPHA, "floors": {"pct": FLOOR_PCT, "us": FLOOR_US}, "splits": SPLITS,
        "captures_per_arm": {str(p): len(v) for p, v in pools.items()}, "lossy_excluded": lossy,
        "baseline_p99_ms": {"median": round(statistics.median(p99s), 4), "min": round(min(p99s), 4),
                            "max": round(max(p99s), 4)},
        "jobs_per_capture_median": int(statistics.median(len(c["hi"]) for c in base)),
        "aa": aa(base),
        "power": power(base, {p: pools[p] for p in EFFECTS if p}),
        "family": family(base),
    }
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"aa": doc["aa"], "baseline_p99_ms": doc["baseline_p99_ms"], "family": doc["family"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
