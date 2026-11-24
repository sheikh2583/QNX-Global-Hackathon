"""The real QNX pilot against the simulator, and the frozen models against the real pilot.

    python scripts/real_vs_sim.py [--real data/pilot] [--sim data/sim] [--out docs/ml/results_real.md]

Two questions, one report:

1. **How close is the simulator?** For every thread the two have in common (the planted victim of each
   scenario, and the threads of the healthy ones), the median of each feature, real against simulated.
   A gap table is the only honest way to say "the simulator is good enough": it names where it is not.
2. **Do models trained only on simulated traces work on real ones?** The radar and the classifier here
   were trained before these captures existed and have never seen a real trace, so this is a clean
   held-out test, unlike the committed bug-zoo traces (a development set since 2026-11-15).

Collect the pilot first (QNX target running, host idle):

    tracelens data plan --per-scenario 1 --out data/pilot/plan.jsonl
    tracelens data collect --plan data/pilot/plan.jsonl --out data/pilot --binary bugzoo/out/tlgen \\
        -c bugzoo/gen/tlgen.toml
    tracelens data features --data data/pilot --out data/pilot/features.jsonl -c bugzoo/gen/tlgen.toml
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

from tracelens.ml.dataset import HEALTHY, SCENARIOS, read_jsonl, role_of
from tracelens.ml.features import FEATURES, vector
from tracelens.ml.model import ensemble_proba, load, persistence, thread_flagged

ROOT = Path(__file__).resolve().parents[1]
AGREE = 0.10  # a feature/thread pair counts as agreeing when the medians are this close


def by_thread(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Feature windows per (scenario, thread), for the threads a comparison is about."""
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["label"] == HEALTHY or role_of(r["scenario"], r.get("thread", "")) == "victim":
            out[(r["scenario"], r["thread"])].append(r["f"])
    return out


def gap_rows(real: list[dict], sim: list[dict]) -> tuple[list[tuple], int]:
    R, S = by_thread(real), by_thread(sim)
    rows = []
    for key in sorted(set(R) & set(S)):
        for f in FEATURES:
            a, b = median(x[f] for x in R[key]), median(x[f] for x in S[key])
            if max(abs(a), abs(b)) > 0.02:  # a feature both sides leave at zero says nothing
                rows.append((abs(a - b), key[0], key[1], f, a, b))
    rows.sort(reverse=True)
    return rows, sum(1 for r in rows if r[0] <= AGREE)


def score(real: list[dict], radar: dict, clf: dict | None):
    per_trace: dict[str, list[dict]] = defaultdict(list)
    for r in real:
        per_trace[r["id"]].append(r)
    out = []
    for rows in sorted(per_trace.values(), key=lambda rs: list(SCENARIOS).index(rs[0]["scenario"])):
        per = persistence(radar, [(r["thread"], r["f"]) for r in rows])
        flagged = sorted(((u / n, t, u, n) for t, (u, n) in per.items() if thread_flagged(radar, u, n)), reverse=True)
        causes = []
        if clf is not None:
            votes: dict[str, Counter] = defaultdict(Counter)
            for r in rows:
                p = ensemble_proba(clf, vector(r["f"]))
                votes[r["thread"]][max(p, key=p.get)] += 1
            causes = sorted(((c.most_common(1)[0][1] / sum(c.values()), t, c.most_common(1)[0][0])
                             for t, c in votes.items() if c.most_common(1)[0][0] != HEALTHY
                             and sum(c.values()) >= 3 and c.most_common(1)[0][1] > 0.5 * sum(c.values())), reverse=True)
        out.append((rows[0]["scenario"], rows[0]["label"], flagged, causes))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--real", default=str(ROOT / "data" / "pilot"))
    ap.add_argument("--sim", default=str(ROOT / "data" / "sim"))
    ap.add_argument("--radar", default=str(ROOT / "src" / "tracelens" / "ml" / "radar.json"))
    ap.add_argument("--classifier", default=str(ROOT / "data" / "sim" / "classifier.json"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "ml" / "results_real.md"))
    args = ap.parse_args()

    real = read_jsonl(Path(args.real) / "features.jsonl")
    sim = read_jsonl(Path(args.sim) / "features.jsonl")
    if not real:
        print(f"no features in {args.real}: collect the pilot first (see this file's docstring)", file=sys.stderr)
        return 2
    manifest = read_jsonl(Path(args.real) / "manifest.jsonl")
    radar = load(args.radar)
    clf = load(args.classifier) if Path(args.classifier).exists() else None

    rows, agreed = gap_rows(real, sim)
    ok = [r for r in manifest if r.get("status") == "ok"]
    md = ["# TraceLens on real QNX 8.0: the pilot against the simulator", "",
          f"One real capture per scenario ({len(ok)} of {len(manifest)} succeeded, "
          f"{sum(1 for r in ok if r.get('triggered'))} with the planted problem showing, "
          f"{sum(1 for r in ok if r.get('lossy'))} lossy), on the QEMU x86_64 guest with 4 CPUs and "
          "`procnto-smp-instr`, host idle. Reproduce with `python scripts/real_vs_sim.py --radar data/sim/radar.json` "
          "(the radar trained on simulated traces only, which is what this report scored; the radar shipped in "
          "`src/tracelens/ml/radar.json` was retrained on real data on 2026-11-16, so the default now gives different "
          "window counts).", "",
          "## Did each planted problem show up on the real target?", "",
          "| Scenario | Label | Planted problem showed up | Rules that fired (HIGH+) |", "|---|---|---|---|"]
    for r in manifest:
        kinds = ", ".join(r.get("rule_kinds") or []) or "none"
        md.append(f"| `{r['scenario']}` | {r['label']} | {'yes' if r.get('triggered') else '**no**'} | {kinds} |")

    md += ["", "## How close is the simulator? (median per feature, real against simulated)", "",
           f"{agreed} of {len(rows)} compared feature/thread pairs agree within {AGREE:.2f}. The widest gaps:", "",
           "| Scenario | Thread | Feature | Real | Simulated | Gap |", "|---|---|---|---|---|---|"]
    for d, sc, th, f, a, b in rows[:12]:
        md.append(f"| `{sc}` | {th} | `{f}` | {a:.3f} | {b:.3f} | {d:.3f} |")

    md += ["", "## The frozen models on the real pilot", "",
           "Neither model has ever seen a real trace, and these captures did not exist when they were trained.", "",
           "| Scenario | Label | Radar (persistent unusual threads) | Classifier (thread: cause) |", "|---|---|---|---|"]
    hit = miss = fa = quiet = 0
    for sc, label, flagged, causes in score(real, radar, clf):
        if label == HEALTHY:
            fa += bool(flagged)
            quiet += not flagged
        else:
            hit += bool(flagged)
            miss += not flagged
        r_txt = ", ".join(f"{t} ({u}/{n})" for _, t, u, n in flagged[:3]) or "quiet"
        c_txt = ", ".join(f"{t}: {k}" for _, t, k in causes[:2]) or "healthy"
        md.append(f"| `{sc}` | {label} | {r_txt} | {c_txt} |")
    md += ["", f"**Radar: {hit} of {hit + miss} planted-bug traces flagged on the thread that suffers, "
               f"{fa} false alarms on {quiet + fa} healthy traces.**", ""]
    Path(args.out).write_text("\n".join(md), encoding="utf-8", newline="\n")
    print("\n".join(md))
    print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
