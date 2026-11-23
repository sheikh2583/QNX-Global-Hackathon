"""Train the radar and the classifier on any mix of datasets, and evaluate on held-out data.

    python scripts/train_eval.py --real data/real                      # real only (train + test on real)
    python scripts/train_eval.py --sim data/sim                        # simulated only
    python scripts/train_eval.py --sim data/sim --real data/real       # both for training
    python scripts/train_eval.py --sim data/sim --test-on data/real    # train simulated, test on real
    python scripts/train_eval.py --real data/real --no-classifier      # radar only (no scikit-learn needed)

What it does, in order:

1. loads feature rows (``features.jsonl``) from every ``--sim``/``--real`` dataset given;
2. trains the radar on the **healthy training** rows only, and calibrates its persistence rule;
3. trains the classifier on the **training** rows (needs ``pip install -e ".[ml]"``; skip with --no-classifier);
4. evaluates on the held-out rows of ``--test-on`` (default: the same datasets), per the protocol in
   docs/ml/DESIGN.md section 5: unseen families never train anything, and known families are tested on
   the parameter region held out in advance;
5. writes the models and a markdown report.

The split of every row was decided when the plan was made, so training can never see its own test set.
Nothing here samples or shuffles: the same inputs give the same models and the same numbers.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tracelens.ml import evaluate, model as M, train  # noqa: E402
from tracelens.ml.dataset import HEALTHY, read_jsonl  # noqa: E402


def load(paths: list[str], source: str) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        d = Path(p)
        f = d / "features.jsonl" if d.is_dir() else d
        got = read_jsonl(f)
        if not got:
            print(f"  !! no feature rows in {f} (run `tracelens data features --data {d}` first)", file=sys.stderr)
        for r in got:
            r.setdefault("source", source)
        rows += got
        print(f"  {len(got):>7,} rows from {f}")
    return rows


def describe(rows: list[dict], label: str) -> None:
    traces = {r["id"] for r in rows}
    healthy = {r["id"] for r in rows if r["label"] == HEALTHY}
    splits = {s: len({r["id"] for r in rows if r["split"] == s}) for s in sorted({r["split"] for r in rows})}
    print(f"{label}: {len(rows):,} windows from {len(traces):,} traces ({len(healthy):,} healthy); "
          f"traces per split {splits}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--sim", action="append", default=[], metavar="DIR", help="simulated dataset (repeatable)")
    ap.add_argument("--real", action="append", default=[], metavar="DIR", help="real dataset (repeatable)")
    ap.add_argument("--test-on", action="append", default=[], metavar="DIR",
                    help="evaluate on this dataset's held-out rows instead of the training ones")
    ap.add_argument("--out", default=str(ROOT / "models"), help="where to write radar.json / classifier.json")
    ap.add_argument("--report", default=str(ROOT / "docs" / "ml" / "results_train.md"))
    ap.add_argument("--no-classifier", action="store_true", help="radar only (no scikit-learn needed)")
    ap.add_argument("--trees", type=int, default=60)
    ap.add_argument("--depth", type=int, default=8)
    ap.add_argument("--quantile", type=float, default=0.995, help="healthy window quantile for the radar threshold")
    args = ap.parse_args()

    if not args.sim and not args.real:
        ap.error("give at least one --sim or --real dataset")

    print("loading")
    rows = load(args.sim, "sim") + load(args.real, "qnx")
    if not rows:
        return 2
    test_rows = load(args.test_on, "qnx") if args.test_on else rows
    describe(rows, "training pool")
    if args.test_on:
        describe(test_rows, "evaluation pool")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print("\ntraining the radar on the healthy training rows")
    radar = train.train_radar(rows, quantile=args.quantile)
    M.save(radar, out / "radar.json")
    print(f"  {radar['note']}")
    print(f"  window threshold {radar['threshold']:.2f}; a thread is reported above "
          f"{radar['min_frac']:.0%} of its windows (and at least {radar['min_windows']})")

    clf = None
    if not args.no_classifier:
        try:
            clf = train.train_classifier(rows, n_trees=args.trees, max_depth=args.depth)
            M.save(clf, out / "classifier.json")
            print(f"  {clf['note']}")
        except RuntimeError as exc:  # scikit-learn missing: the radar still stands on its own
            print(f"  skipping the classifier: {exc}")

    print("\nevaluating on held-out rows")
    md = ["# TraceLens models: training run", "",
          f"Trained on {len(rows):,} windows from {len({r['id'] for r in rows}):,} traces "
          f"({', '.join(sorted({r.get('source', 'qnx') for r in rows}))}); evaluated on "
          f"{len({r['id'] for r in test_rows}):,} traces"
          + (f" from {', '.join(args.test_on)}" if args.test_on else " (the held-out rows of the same datasets)")
          + ". Reproduce: `python scripts/train_eval.py "
          + " ".join(f"--sim {p}" for p in args.sim) + " " + " ".join(f"--real {p}" for p in args.real)
          + ("".join(f" --test-on {p}" for p in args.test_on)) + "`.", "",
          evaluate.markdown(evaluate.evaluate_radar(test_rows, radar),
                            evaluate.evaluate_classifier(test_rows, clf) if clf else None).strip(), ""]
    manifest = {}
    for d in (args.test_on or args.sim + args.real):
        for row in read_jsonl(Path(d) / "manifest.jsonl"):
            manifest[row["id"]] = row
    if manifest:
        md += [evaluate.rules_vs_radar_markdown(evaluate.rules_vs_radar(test_rows, radar, manifest)).strip(), ""]
    Path(args.report).write_text("\n".join(md), encoding="utf-8", newline="\n")
    print("\n".join(md))
    print(f"\nmodels in {out}/ ; report in {args.report}", file=sys.stderr)
    print("to ship the radar with the tool: copy it over src/tracelens/ml/radar.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
