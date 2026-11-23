"""The evaluation protocol of docs/ml/DESIGN.md section 5, as code (decided before the data exists).

Radar, per trace: a trace is flagged if any of its windows scores above the threshold fixed on the
healthy training windows. Reported per scenario family, on held-out data only:
  - unseen families (no rule): detection rate (the radar's real job)
  - held-out healthy: false-alarm rate
  - known families: detection rate, next to the rules' own rate on the same traces
Classifier, per window, on parameter region B: precision and recall per class.
"""

from __future__ import annotations

from collections import defaultdict

from .dataset import HEALTHY, window_label
from .features import vector
from .model import ensemble_proba, persistence, thread_flagged


def evaluate_radar(rows: list[dict], radar: dict) -> dict:
    """A trace is flagged when one of its threads passes the radar's persistence rule
    (``thread_flagged``), the same rule ``analyze --radar`` reports with."""
    per_trace: dict[str, dict] = {}
    for r in rows:
        if r["split"] == "train":
            continue
        t = per_trace.setdefault(r["id"], {"scenario": r["scenario"], "label": r["label"], "split": r["split"],
                                           "triggered": r.get("triggered"), "rows": []})
        t["rows"].append((r["thread"], r["f"]))
    fam = defaultdict(lambda: {"traces": 0, "flagged": 0, "triggered": 0})
    for t in per_trace.values():
        f = fam[t["scenario"]]
        f["label"], f["split"] = t["label"], t["split"]
        f["traces"] += 1
        f["flagged"] += any(thread_flagged(radar, u, n) for u, n in persistence(radar, t["rows"]).values())
        f["triggered"] += bool(t["triggered"])
    return {"threshold": radar["threshold"], "min_frac": radar.get("min_frac", 0.0), "families": dict(fam)}


def evaluate_classifier(rows: list[dict], model: dict) -> dict:
    test = [r for r in rows if r["split"] == "test" and window_label(r) in model["classes"]]
    conf = defaultdict(lambda: defaultdict(int))
    for r in test:
        p = ensemble_proba(model, vector(r["f"]))
        conf[window_label(r)][max(p, key=p.get)] += 1
    per = {}
    for c in model["classes"]:
        tp = conf[c][c]
        fp = sum(conf[o][c] for o in conf if o != c)
        fn = sum(v for k, v in conf[c].items() if k != c)
        per[c] = {"precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None,
                  "support": tp + fn}
    return {"windows": len(test), "per_class": per, "confusion": {k: dict(v) for k, v in conf.items()}}


def markdown(radar_eval: dict, clf_eval: dict | None = None) -> str:
    lines = ["## Radar on held-out QNX traces", "",
             f"Window threshold {radar_eval['threshold']:.2f} (99.5th percentile of healthy training windows); a "
             f"thread is flagged when more than {radar_eval['min_frac']:.0%} of its windows (and at least 3) pass it, "
             "a cut-off calibrated on healthy training traces only.", "",
             "| Family | Label | Split | Traces | Flagged | Planted problem showed up |", "|---|---|---|---|---|---|"]
    for name, f in sorted(radar_eval["families"].items(), key=lambda x: (x[1]["split"], x[0])):
        rate = f["flagged"] / f["traces"] if f["traces"] else 0
        lines.append(f"| `{name}` | {f['label']} | {f['split']} | {f['traces']} | {f['flagged']} ({rate:.0%}) "
                     f"| {f['triggered']}/{f['traces']} |")
    healthy = [f for f in radar_eval["families"].values() if f["label"] == HEALTHY]
    if healthy:
        n, k = sum(f["traces"] for f in healthy), sum(f["flagged"] for f in healthy)
        lines += ["", f"False alarms on held-out healthy traces: **{k} of {n}**."]
    if clf_eval:
        lines += ["", "## Classifier on parameter region B", "", "| Class | Precision | Recall | Windows |",
                  "|---|---|---|---|"]
        for c, m in clf_eval["per_class"].items():
            fmt = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
            lines.append(f"| {c} | {fmt(m['precision'])} | {fmt(m['recall'])} | {m['support']} |")
    return "\n".join(lines) + "\n"


def rules_vs_radar(rows: list[dict], radar: dict, manifest: dict[str, dict]) -> dict:
    """What the learned radar adds to the rules, per held-out trace.

    The only question that decides whether the learning phase was worth building: on traces the rules
    report as clean, how often is the radar right, and how often does it cry wolf? ``manifest`` maps a
    trace id to its collection row, whose ``rule_kinds`` are the kinds that fired at or above the gate.
    """
    per: dict[str, list] = defaultdict(list)
    for r in rows:
        if r["split"] != "train":
            per[r["id"]].append((r["thread"], r["f"]))
    out = {"buggy": 0, "rules_only": 0, "both": 0, "radar_only": 0, "neither": 0,
           "healthy": 0, "false_alarms": 0}
    for tid, pairs in per.items():
        item = manifest.get(tid)
        if item is None:
            continue
        ruled = bool(item.get("rule_kinds"))
        flagged = any(thread_flagged(radar, u, n) for u, n in persistence(radar, pairs).values())
        if item["label"] == HEALTHY:
            out["healthy"] += 1
            out["false_alarms"] += flagged
            continue
        out["buggy"] += 1
        out["both" if ruled and flagged else "rules_only" if ruled
            else "radar_only" if flagged else "neither"] += 1
    return out


def rules_vs_radar_markdown(c: dict) -> str:
    union = c["rules_only"] + c["both"] + c["radar_only"]
    return "\n".join([
        "## What the radar adds to the rules", "",
        f"On {c['buggy']} held-out buggy captures and {c['healthy']} healthy ones:", "",
        "| | Traces |", "|---|---|",
        f"| Caught by the rules, missed by the radar | {c['rules_only']} |",
        f"| Caught by both | {c['both']} |",
        f"| **Caught by the radar with no rule firing** | **{c['radar_only']}** |",
        f"| Caught by neither | {c['neither']} |",
        f"| False alarms on the healthy captures | **{c['false_alarms']}** |", "",
        f"The rules alone find {c['rules_only'] + c['both']} of {c['buggy']}; with the radar, {union}. "
        "A rule finding cites the kernel events that prove it, so on the families it knows the rule is "
        "the better answer; the radar's contribution is the families no rule exists for.", ""])
