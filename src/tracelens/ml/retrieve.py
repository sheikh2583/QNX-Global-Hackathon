"""Explaining a radar finding by the labelled pattern it most resembles.

The radar says "this thread is unlike anything healthy". That is true but thin. Retrieval adds the
other half: of the labelled patterns we *have* seen, which does this window look like? A handful of
exemplar windows per scenario are stored with the radar model, and a finding reports the nearest one
with its distance and how close that pattern's own windows usually are.

Distance is measured in the radar's own z-space (how far from healthy, per feature), so it compares
*deviations from healthy*, not raw numbers: a thread blocked on a semaphore while a lower-priority
thread runs lands near the semaphore-inversion exemplars whatever the clock rate or the priorities.

Honesty rules, so this cannot leak the evaluation:
  * exemplars come from training-split windows only, so the held-out families have none; a finding on
    one of those reports its nearest *known* pattern (useful: a lock-order deadlock looks like mutex
    contention) and the distance says how loose the match is
  * only the planted victim thread's windows are exemplars for a bug (the culprit looks healthy)
  * a match beyond that pattern's own radius is reported as "no known pattern matches"
"""

from __future__ import annotations

import math
import random

from .dataset import HEALTHY, SCENARIOS

PER_SCENARIO = 8  # exemplars kept per scenario (k-center picks the spread, not the average)
SAMPLE = 4000  # windows looked at per scenario when picking
RADIUS_Q = 0.9  # a pattern's radius: this quantile of its own windows' distance to its exemplars

# One plain line per scenario, for the report. A table, not a model: it never decides anything.
DESCRIPTIONS = {
    "healthy_periodic": "healthy periodic work (independent tasks, no shared state)",
    "healthy_pi_mutex": "healthy work behind a priority-inheriting mutex",
    "healthy_ipc": "healthy client/server message passing",
    "healthy_mixed": "healthy mixed workload (periodic work, a mutex and message passing)",
    "healthy_irq": "healthy interrupt handling (acknowledge, unmask, then defer the work)",
    "sem_inversion": "priority inversion through a semaphore used as a lock",
    "chan_inversion": "priority inversion through a fixed-priority message channel",
    "condvar_inversion": "priority inversion while waiting on a condition variable",
    "ipc_deadlock": "two processes blocked sending to each other",
    "lock_contention": "many threads serialised on one mutex",
    "irq_overrun": "an interrupt handler working with its line still masked",
    "cpu_starvation": "a periodic task starved by a busy higher-priority thread",
    "mutex_abba": "a lock-order (ABBA) deadlock between two mutexes",
    "lost_wakeup": "a lost wake-up: the signal arrived before the wait, so the consumer waits out its timeout",
    "period_overrun": "a job whose work no longer fits in its period, starving everything below it",
}


def zvec(model: dict, f: dict) -> list[float]:
    """The window as deviations from healthy, one clipped z per feature (the radar's own space)."""
    out = []
    for name in model["features"]:
        d = f[name] - model["median"][name]
        z = d / (model["scale_hi"][name] if d > 0 else model["scale_lo"][name])
        out.append(max(-model["clip"], min(model["clip"], z)))
    return out


def distance(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b, strict=False)) / len(a))


def _k_center(vectors: list[list[float]], k: int) -> list[int]:
    """Greedy k-center: start from the most extreme window, then repeatedly take the one farthest
    from everything chosen so far. Deterministic, stdlib, and it keeps the rare shapes a mean would
    average away."""
    if len(vectors) <= k:
        return list(range(len(vectors)))
    first = max(range(len(vectors)), key=lambda i: sum(x * x for x in vectors[i]))
    chosen = [first]
    best = [distance(v, vectors[first]) for v in vectors]
    while len(chosen) < k:
        i = max(range(len(vectors)), key=lambda j: best[j])
        if best[i] <= 0:
            break
        chosen.append(i)
        for j, v in enumerate(vectors):
            best[j] = min(best[j], distance(v, vectors[i]))
    return chosen


def build(rows: list[dict], radar: dict, per_scenario: int = PER_SCENARIO, seed: int = 7) -> dict:
    """Exemplars from the training split: the bug's victim windows, and healthy windows."""
    rng = random.Random(seed)
    by: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("split") != "train":
            continue
        if r["label"] != HEALTHY and r.get("role") != "victim":
            continue
        by.setdefault(r["scenario"], []).append(r["f"])
    items, radius = [], {}
    for scenario, feats in sorted(by.items()):
        if len(feats) > SAMPLE:
            feats = rng.sample(feats, SAMPLE)
        vectors = [zvec(radar, f) for f in feats]
        picked = _k_center(vectors, per_scenario)
        chosen = [vectors[i] for i in picked]
        label = SCENARIOS[scenario].label if scenario in SCENARIOS else scenario
        items += [{"scenario": scenario, "label": label, "v": [round(x, 3) for x in v]} for v in chosen]
        dists = sorted(min(distance(v, c) for c in chosen) for v in vectors)
        radius[scenario] = round(dists[min(len(dists) - 1, int(RADIUS_Q * len(dists)))], 3)
    return {"type": "exemplars", "features": list(radar["features"]), "items": items, "radius": radius,
            "per_scenario": per_scenario,
            "note": f"{len(items)} exemplar windows from {len(by)} scenarios (training split only)"}


def nearest(exemplars: dict, radar: dict, f: dict) -> dict | None:
    """The closest labelled pattern to one window, or None without exemplars.

    ``within``: the window is inside that pattern's usual radius, so the match means something."""
    if not exemplars or not exemplars.get("items"):
        return None
    z = zvec(radar, f)
    best = min(exemplars["items"], key=lambda it: distance(z, it["v"]))
    d = distance(z, best["v"])
    r = exemplars["radius"].get(best["scenario"], 0.0)
    return {"scenario": best["scenario"], "label": best["label"], "distance": round(d, 2), "radius": r,
            "within": d <= r, "text": DESCRIPTIONS.get(best["scenario"], best["scenario"])}
