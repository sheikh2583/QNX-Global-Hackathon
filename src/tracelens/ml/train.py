"""Offline training (development only). The output is a JSON file the stdlib scores at runtime.

  features_from_manifest   analyze every collected trace and write one row per (thread, window)
  train_radar              healthy training windows -> radar.json (pure Python)
  train_classifier         labelled windows -> classifier.json (scikit-learn, `pip install -e ".[ml]"`)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ..analyze import analyze_file
from ..config import Config
from .dataset import HEALTHY, read_jsonl, role_of, window_label
from .features import FEATURES, vector, windows
from .model import fit_radar


def features_from_manifest(data_dir: str | Path, out: str | Path, cfg: Config,
                           log: Callable[[str], None] = print) -> int:
    data = Path(data_dir)
    rows = 0
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        for item in read_jsonl(data / "manifest.jsonl"):
            if item.get("status") != "ok" or item.get("lossy"):
                continue
            trace = Path(item["trace"])
            trace = trace if trace.is_absolute() else data / trace
            a = analyze_file(trace, cfg)
            for key, t0, t1, f in windows(a.model):
                fh.write(json.dumps({"id": item["id"], "scenario": item["scenario"], "label": item["label"],
                                     "split": item["split"], "triggered": item.get("triggered"),
                                     "thread": a.model.label(key), "role": role_of(item["scenario"], a.model.label(key)),
                                     "t0": t0, "t1": t1, "f": f}) + "\n")
                rows += 1
            log(f"{item['id']}: features")
    return rows


def train_radar(feature_rows: list[dict], quantile: float = 0.995) -> dict:
    train = [r for r in feature_rows if r["label"] == HEALTHY and r["split"] == "train"]
    by_trace: dict[str, list] = {}
    for r in train:
        by_trace.setdefault(r["id"], []).append((r["thread"], r["f"]))
    sources = sorted({r.get("source", "qnx") for r in train})
    model = fit_radar([r["f"] for r in train], quantile,
                      note=f"trained on {len(train)} windows of {len(by_trace)} healthy traces ({', '.join(sources)})")
    from .model import calibrate_persistence, persistence
    calibrate_persistence(model, [persistence(model, rows) for rows in by_trace.values()])
    model["sources"] = sources
    return model


def _export_forest(clf, classes: list[str]) -> dict:
    trees = []
    for est in clf.estimators_:
        t = est.tree_
        nodes = []
        for i in range(t.node_count):
            if t.children_left[i] == -1:
                nodes.append({"v": [float(x) for x in t.value[i][0]]})
            else:
                nodes.append({"f": int(t.feature[i]), "t": float(t.threshold[i]),
                              "l": int(t.children_left[i]), "r": int(t.children_right[i])})
        trees.append({"nodes": nodes})
    return {"type": "trees", "version": 1, "features": FEATURES, "classes": classes, "trees": trees}


def train_classifier(feature_rows: list[dict], n_trees: int = 60, max_depth: int = 8, seed: int = 7) -> dict:
    """Random forest over the known classes (and healthy), training split only."""
    try:
        from sklearn.ensemble import RandomForestClassifier
    except ImportError as exc:  # training is a development step; inference needs nothing
        raise RuntimeError("training the classifier needs scikit-learn: pip install -e \".[ml]\"") from exc
    train = [r for r in feature_rows if r["split"] == "train"]
    labels = [window_label(r) for r in train]  # the bug's label on its victim thread only
    classes = sorted(set(labels))
    X = [vector(r["f"]) for r in train]
    y = [classes.index(lab) for lab in labels]
    clf = RandomForestClassifier(n_estimators=n_trees, max_depth=max_depth, random_state=seed, class_weight="balanced")
    clf.fit(X, y)
    model = _export_forest(clf, classes)
    model["note"] = f"random forest, {n_trees} trees, depth {max_depth}, {len(train)} training windows"
    return model
