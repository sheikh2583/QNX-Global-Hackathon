"""Offline training (development only). The output is a JSON file the stdlib scores at runtime.

  features_from_manifest   analyze every collected trace and write one row per (thread, window)
  train_radar              healthy training windows -> radar.json (pure Python)
  train_classifier         labelled windows -> classifier.json (scikit-learn, `pip install -e ".[ml]"`)
"""

from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Callable

from ..analyze import analyze_file
from ..config import Config
from .dataset import HEALTHY, read_jsonl, role_of, window_label
from .features import FEATURES, vector, windows
from .model import fit_radar


def _feature_rows(job: tuple[dict, str, str | None]) -> tuple[str, list[dict]]:
    """One trace's feature rows. Takes paths, not objects, so it can run in another process."""
    item, data_dir, config = job
    from ..config import load_config
    cfg = load_config(config) if config else Config()
    trace = Path(item["trace"])
    a = analyze_file(trace if trace.is_absolute() else Path(data_dir) / trace, cfg)
    return item["id"], [
        {"id": item["id"], "scenario": item["scenario"], "label": item["label"], "split": item["split"],
         "triggered": item.get("triggered"), "thread": a.model.label(key),
         "role": role_of(item["scenario"], a.model.label(key)), "t0": t0, "t1": t1, "f": f}
        for key, t0, t1, f in windows(a.model)]


def features_from_manifest(data_dir: str | Path, out: str | Path, cfg: Config,
                           log: Callable[[str], None] = print, workers: int = 0,
                           config_path: str | None = None, resume: bool = False) -> int:
    """One feature row per (thread, 20 ms window) of every usable trace in ``data_dir``.

    ``workers``: processes to parse traces in (0 = one per CPU, 1 = in this one). Parsing dominates,
    and an interrupt-driven capture is ten times the size of a periodic one (35 MB against 3 MB,
    measured), so a serial pass over a night's collection takes hours where a parallel one takes
    minutes. ``resume``: keep the rows already in ``out`` and only add the traces missing from it.
    """
    data = Path(data_dir)
    items = [i for i in read_jsonl(data / "manifest.jsonl") if i.get("status") == "ok" and not i.get("lossy")]
    done: set[str] = set()
    if resume and Path(out).exists():
        with open(out, encoding="utf-8") as fh:
            done = {json.loads(line)["id"] for line in fh if line.strip()}
        items = [i for i in items if i["id"] not in done]
        log(f"{len(done)} traces already featurised, {len(items)} to go")
    jobs = [(item, str(data), config_path) for item in items]
    rows = 0

    with open(out, "a" if done else "w", encoding="utf-8", newline="\n") as fh:
        def write(trace_id: str, got: list[dict], n: int) -> None:
            nonlocal rows
            fh.writelines(json.dumps(r) + "\n" for r in got)
            fh.flush()
            rows += len(got)
            if n % 25 == 0 or n == len(jobs):
                log(f"[{n}/{len(jobs)}] {trace_id}: {rows:,} rows so far")

        if workers == 1 or len(jobs) < 4:
            for n, job in enumerate(jobs, 1):
                write(*_feature_rows(job), n)
        else:
            from concurrent.futures import ProcessPoolExecutor
            with ProcessPoolExecutor(max_workers=workers or None) as pool:
                for n, (trace_id, got) in enumerate(pool.map(_feature_rows, jobs, chunksize=2), 1):
                    write(trace_id, got, n)
    return rows


def train_radar(feature_rows: list[dict], quantile: float = 0.995) -> dict:
    # Only runs the rules also call clean: a "healthy" variant that drew so much load that it misses
    # deadlines is a real problem, and teaching the radar that it is normal would blind it.
    train = [r for r in feature_rows if r["label"] == HEALTHY and r["split"] == "train" and r.get("triggered", True)]
    by_trace: dict[str, list] = {}
    for r in train:
        by_trace.setdefault(r["id"], []).append((r["thread"], r["f"]))
    sources = sorted({r.get("source", "qnx") for r in train})
    model = fit_radar([r["f"] for r in train], quantile,
                      note=f"trained on {len(train)} windows of {len(by_trace)} healthy traces ({', '.join(sources)})")
    from .model import calibrate_persistence, persistence
    from .retrieve import build as build_exemplars
    calibrate_persistence(model, [persistence(model, rows) for rows in by_trace.values()])
    model["sources"] = sources
    model["exemplars"] = build_exemplars(feature_rows, model)  # training-split windows only
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
