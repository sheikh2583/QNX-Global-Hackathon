"""Simulated labelled datasets: the same plan, splits, checks and features as a real collection.

``generate`` runs a data-engine plan (``tracelens.ml.dataset.make_plan``) through the simulator in
parallel and writes, per run, what ``tracelens data collect`` + ``data features`` would write for a
real QNX capture: ``traces/<id>.txt.gz``, a ``manifest.jsonl`` row (label, split, lossy, triggered)
and the feature rows. Every row is marked ``source: sim`` so simulated and real data never mix by
accident.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from collections.abc import Callable

from ..analyze import analyze_text
from ..config import Config, load_config
from ..ml.dataset import check, read_jsonl, role_of
from ..ml.features import windows
from .programs import simulate


def sim_seed(item: dict, plan_seed: int = 0) -> int:
    return int(hashlib.sha256(f"{plan_seed}:{item['id']}".encode()).hexdigest()[:8], 16)


def seconds_of(item: dict) -> int:
    args = item.get("args", [])
    return int(args[args.index("-d") + 1]) if "-d" in args else 2


def _one(job: tuple[dict, str, str, int, bool]) -> tuple[dict, list[dict]]:
    item, out_dir, config, plan_seed, keep = job
    cfg = load_config(config) if config else Config()
    seed = sim_seed(item, plan_seed)
    text = simulate(item["scenario"], item["params"], seed=seed, seconds=seconds_of(item))
    rel = Path("traces") / f"{item['id']}.txt.gz"
    if keep:
        path = Path(out_dir) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    a = analyze_text(text, cfg)
    row = dict(item) | check(item, a, cfg) | {"trace": str(rel).replace("\\", "/") if keep else None,
                                               "status": "ok", "source": "sim", "sim_seed": seed}
    feats = [] if row["lossy"] else [
        {"id": item["id"], "scenario": item["scenario"], "label": item["label"], "split": item["split"],
         "triggered": row["triggered"], "source": "sim", "thread": a.model.label(key),
         "role": role_of(item["scenario"], a.model.label(key)), "t0": t0, "t1": t1, "f": f}
        for key, t0, t1, f in windows(a.model)]
    return row, feats


def generate(plan: list[dict], out_dir: str | Path, config: str | None, plan_seed: int = 0, workers: int = 0,
             keep_traces: bool = True, log: Callable[[str], None] = print) -> list[dict]:
    """Simulate every planned run not yet in ``out_dir/manifest.jsonl`` (resumable)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifest, features = out / "manifest.jsonl", out / "features.jsonl"
    done = {r["id"] for r in read_jsonl(manifest) if r.get("status") == "ok"}
    todo = [p for p in plan if p["id"] not in done]
    log(f"{len(done)} already simulated, {len(todo)} to go")
    jobs = [(item, str(out), config, plan_seed, keep_traces) for item in todo]

    def write(row, feats, n):
        with open(manifest, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row) + "\n")
        with open(features, "a", encoding="utf-8", newline="\n") as fh:
            fh.writelines(json.dumps(f) + "\n" for f in feats)
        if n % 50 == 0 or n == len(jobs):
            log(f"[{n}/{len(jobs)}] {row['id']}: triggered={row['triggered']} lossy={row['lossy']}")

    if workers == 1:
        for n, job in enumerate(jobs, 1):
            write(*_one(job), n)
    else:
        with ProcessPoolExecutor(max_workers=workers or None) as ex:
            for n, (row, feats) in enumerate(ex.map(_one, jobs, chunksize=4), 1):
                write(row, feats, n)
    return read_jsonl(manifest)
