"""Models as small JSON files, scored by the standard library (no numpy, no network, no key).

  radar        robust z-scores against healthy windows (median, MAD); trains in pure Python
  trees        a tree ensemble (random forest / gradient boosting exported from scikit-learn offline);
               inference here, training in tracelens.ml.train (optional `ml` extra, dev only)

The same file and the same input always give the same score.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from .features import FEATURES

CLIP = 50.0
FLOOR = {"cpus_used": 0.5, "prio_rank": 0.15}  # smallest meaningful change per feature
DEFAULT_FLOOR = 0.02  # 2% of a window, or 0.02 events per ms


# ----------------------------------------------------------------------------- radar
def _q(sorted_vals: list[float], q: float) -> float:
    return sorted_vals[min(len(sorted_vals) - 1, max(0, int(q * len(sorted_vals))))]


def fit_radar(vectors: list[dict], quantile: float = 0.995, top_k: int = 3, note: str = "") -> dict:
    """Fit on healthy windows only. Each feature gets a scale per side of its median, from the
    healthy data's own tail: a value at the healthy 99th (or 1st) percentile scores z = 3. (A plain
    MAD scale fails on sparse features, e.g. semaphore time that is zero in almost every healthy
    window: one healthy wait would look infinitely unusual. Found on real QNX traces.)
    Threshold = the ``quantile`` of the healthy scores themselves."""
    if len(vectors) < 20:
        raise ValueError(f"need at least 20 healthy windows to fit the radar, got {len(vectors)}")
    med, hi, lo = {}, {}, {}
    for f in FEATURES:
        vals = sorted(v[f] for v in vectors)
        m = statistics.median(vals)
        mad = statistics.median(abs(x - m) for x in vals) * 1.4826
        floor = FLOOR.get(f, DEFAULT_FLOOR)
        med[f] = m
        hi[f] = max(mad, (_q(vals, 0.99) - m) / 3, floor)
        lo[f] = max(mad, (m - _q(vals, 0.01)) / 3, floor)
    model = {"type": "radar", "version": 2, "features": FEATURES, "median": med, "scale_hi": hi, "scale_lo": lo,
             "top_k": top_k, "clip": CLIP, "threshold": 0.0, "quantile": quantile,
             "trained_windows": len(vectors), "note": note}
    scores = sorted(radar_score(model, v)[0] for v in vectors)
    model["threshold"] = scores[min(len(scores) - 1, int(quantile * len(scores)))]
    return model


# A real-time bug repeats (every period, every interrupt); noise does not. A thread is reported only
# when enough of its windows are unusual. Without this, "any window above the 99.5th percentile" flags
# a long healthy trace by chance (simulated data: 5 of 37 held-out healthy traces).
MIN_UNUSUAL_WINDOWS = 3


def thread_flagged(model: dict, unusual: int, total: int) -> bool:
    return unusual >= model.get("min_windows", 1) and unusual / max(1, total) > model.get("min_frac", 0.0)


def calibrate_persistence(model: dict, healthy_traces: list[dict], q: float = 0.99) -> dict:
    """``healthy_traces``: per healthy *training* trace, {thread: (unusual windows, windows)}. The cut-off
    is the ``q`` quantile of the most persistent thread per healthy trace, so at most ~1% of healthy
    training traces would be flagged."""
    worst = sorted(max((u / max(1, t) for u, t in th.values() if u >= MIN_UNUSUAL_WINDOWS), default=0.0)
                   for th in healthy_traces)
    model["min_windows"] = MIN_UNUSUAL_WINDOWS
    model["min_frac"] = _q(worst, q) if worst else 0.0
    model["persistence_traces"] = len(worst)
    return model


def persistence(model: dict, rows) -> dict:
    """{thread: (unusual windows, windows)} for one trace's feature rows (``(thread, features)`` pairs)."""
    out: dict = {}
    for thread, f in rows:
        u, t = out.get(thread, (0, 0))
        out[thread] = (u + (radar_score(model, f)[0] > model["threshold"]), t + 1)
    return out


def radar_score(model: dict, f: dict) -> tuple[float, list[tuple[str, float]]]:
    """(score, the features that stand out most, with their z)."""
    zs = []
    for name in model["features"]:
        d = f[name] - model["median"][name]
        z = d / (model["scale_hi"][name] if d > 0 else model["scale_lo"][name])
        zs.append((name, max(-model["clip"], min(model["clip"], z))))
    top = sorted(zs, key=lambda x: -abs(x[1]))[:model["top_k"]]
    return sum(abs(z) for _, z in top) / len(top), top


# ----------------------------------------------------------------------------- tree ensembles
def tree_predict(tree: dict, x: list[float]) -> list[float]:
    """One tree: nodes are {"f": feature index, "t": threshold, "l": left, "r": right} or {"v": [values]}."""
    nodes, i = tree["nodes"], 0
    while "v" not in nodes[i]:
        n = nodes[i]
        i = n["l"] if x[n["f"]] <= n["t"] else n["r"]
    return nodes[i]["v"]


def ensemble_proba(model: dict, x: list[float]) -> dict[str, float]:
    """Average the trees' class distributions (a random forest; boosted trees are exported the same way)."""
    total = [0.0] * len(model["classes"])
    for tree in model["trees"]:
        v = tree_predict(tree, x)
        s = sum(v) or 1.0
        for k, val in enumerate(v):
            total[k] += val / s
    n = len(model["trees"]) or 1
    return {c: total[k] / n for k, c in enumerate(model["classes"])}


# ----------------------------------------------------------------------------- files
def save(model: dict, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(model, indent=1, sort_keys=True), encoding="utf-8", newline="\n")


def load(path: str | Path) -> dict:
    model = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [f for f in model.get("features", []) if f not in FEATURES]
    if missing:
        raise ValueError(f"model expects features this TraceLens does not compute: {missing}")
    return model


DEFAULT_RADAR = Path(__file__).with_name("radar.json")
