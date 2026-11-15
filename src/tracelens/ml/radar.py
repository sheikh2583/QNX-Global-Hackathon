"""The radar: findings for thread behaviour unlike anything in healthy QNX traces.

A radar finding is not a proven bug: it is MEDIUM ("worth a look"), carries `source: radar` and the
features that stand out, and never gets an automatic patch. Adjacent unusual windows of one thread
are merged into one finding; at most a few threads are reported, the most unusual first.
"""

from __future__ import annotations

from pathlib import Path

from ..analyze import Analysis
from ..findings import Finding
from .features import windows
from .model import DEFAULT_RADAR, load, radar_score, thread_flagged
from .retrieve import nearest

PLAIN = {
    "share_running": "time running", "share_ready": "time waiting for a CPU", "share_sem": "time blocked on a semaphore",
    "share_mutex": "time blocked on a mutex", "share_condvar": "time waiting on a condition variable",
    "share_send": "time waiting for a server to receive", "share_reply": "time waiting for a reply",
    "share_intr": "time waiting for interrupts", "share_sleep": "time asleep",
    "max_block_frac": "longest single block", "max_ready_frac": "longest wait for a CPU",
    "max_run_frac": "longest unbroken time holding a CPU",
    "intr_masked_frac": "time spent with an interrupt still masked",
    "blocks_per_ms": "how often it blocks", "preempts_per_ms": "how often it is preempted",
    "inversion_frac": "time blocked while a lower-priority thread held its CPU", "prio_rank": "relative priority",
    "migrations_per_ms": "CPU migrations", "cpus_used": "CPUs used",
}
NOTE = ("Learned from healthy QNX 8.0 traces: this thread behaved unlike any healthy run in the features listed. "
        "It is not a proven bug and gets no automatic fix: look at the timeline around it. Any resemblance to a "
        "known pattern is measured against labelled example windows, never a rule that fired.")


def radar_findings(a: Analysis, model: dict, max_threads: int = 3) -> list[Finding]:
    m = a.model
    hot: dict = {}
    seen: dict = {}
    for key, t0, t1, f in windows(m):
        seen[key] = seen.get(key, 0) + 1
        score, top = radar_score(model, f)
        if score <= model["threshold"]:
            continue
        runs = hot.setdefault(key, [])
        if runs and t0 <= runs[-1]["t1"]:  # extend the current run of unusual windows
            r = runs[-1]
            r["t1"], r["n"] = t1, r["n"] + 1
            if score > r["score"]:
                r["score"], r["top"], r["f"] = score, top, f
        else:
            runs.append({"t0": t0, "t1": t1, "score": score, "top": top, "n": 1, "f": f})
    hot = {k: rs for k, rs in hot.items() if thread_flagged(model, sum(r["n"] for r in rs), seen[k])}
    ranked = sorted(((max(rs, key=lambda r: r["score"]), key) for key, rs in hot.items()),
                    key=lambda x: -x[0]["score"])[:max_threads]
    out = []
    for r, key in ranked:
        th = m.threads[key]
        n_windows = sum(x["n"] for x in hot[key])
        stand = ", ".join(f"{PLAIN.get(name, name)} ({'higher' if z > 0 else 'lower'} than healthy)" for name, z in r["top"])
        like = nearest(model.get("exemplars"), model, r["f"])
        extra, metrics = "", {}
        if like is not None:
            metrics = {"like": like["scenario"], "like_label": like["label"], "like_distance": like["distance"],
                       "like_radius": like["radius"], "like_within": like["within"]}
            extra = (f" The closest pattern TraceLens has seen is {like['text']}"
                     + (f" (distance {like['distance']}, inside the {like['radius']} typical for that pattern)."
                        if like["within"] else
                        f", but only loosely (distance {like['distance']} against {like['radius']} typical for it): "
                        "treat this as behaviour of its own."))
        ev = [iv.event_id for iv in th.intervals if iv.start < r["t1"] and iv.end > r["t0"]][:8]
        out.append(Finding(
            kind="unusual_behavior", severity="medium", title=f"Unusual behaviour in {m.label(key)}",
            summary=(f"{m.describe(key)} behaved unlike healthy QNX programs in {n_windows} of its "
                     f"{seen[key]} time windows; the most unusual stretch lasted "
                     f"{(r['t1'] - r['t0']) / 1e6:.0f} ms. It stands out in: {stand}." + extra),
            t_start=r["t0"], t_end=r["t1"], threads=[m.label(key)], evidence=ev,
            metrics={"source": "radar", "score": round(r["score"], 2), "threshold": round(model["threshold"], 2),
                     "unusual_windows": n_windows, **metrics,
                     **{f"z_{name}": round(z, 1) for name, z in r["top"]}},
            qnx_note=NOTE))
    return out


def annotate(a: Analysis, path: str | Path | None = None, append: bool = True) -> list[Finding]:
    """Add radar findings to an analysis, numbered after the rules' own findings.

    ``path``: a radar model, or the bundled one. Returns [] when there is no model, and never raises:
    the rules are the product, the radar is an addition and must not be able to break a report.
    """
    try:
        p = Path(path) if path else DEFAULT_RADAR
        if not p.exists():
            return []
        extra = radar_findings(a, load(p))
    except Exception as exc:  # a corrupt or stale model must not cost the user their report
        a.errors.append(f"radar: {exc!r}")
        return []
    for i, f in enumerate(extra, len(a.findings) + 1):
        f.id = f"TL-{i:03d}"
    if append:
        a.findings.extend(extra)
    return extra
