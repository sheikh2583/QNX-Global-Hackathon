"""Two collections of the same scenarios, feature by feature - built to compare architectures.

    python scripts/arch_compare.py --a data/aarch64 --b data/real \
        --label-a aarch64le --label-b x86_64 --out docs/results/aarch64_features.md

Everything TraceLens publishes was measured on one QEMU x86_64 guest. The learned features were
designed to be platform-independent (time *shares*, block lengths, priority *rank*, CPU migrations)
and the rules encode QNX semantics rather than x86 ones, so a second architecture should look much
the same. This script is how that is checked instead of asserted: the same gap table
`scripts/real_vs_sim.py` uses for real-against-simulated, pointed at two real collections.

A cross-architecture gap only means something next to a same-architecture control, so run the control
first - two x86 collections against each other - and compare the two gap tables:

    python scripts/arch_compare.py --a data/pilot --b data/real \
        --label-a "x86_64 (pilot)" --label-b "x86_64 (overnight)" --out docs/results/arch_control.md

`--a` is also scored by the shipped radar, which was trained on x86 traces only: that is the transfer
question. Collect `--a` with `scripts/collect.sh` (or `tracelens data collect`) exactly as the x86 data
was collected, so the only thing that differs is the machine.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from real_vs_sim import AGREE, gap_rows, score  # noqa: E402  (sibling script, not a package)

from tracelens.ml.dataset import HEALTHY, read_jsonl  # noqa: E402
from tracelens.ml.model import load  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--a", required=True, help="collection under test (also scored by the radar)")
    ap.add_argument("--b", required=True, help="reference collection (the x86 data the models come from)")
    ap.add_argument("--label-a", default="A")
    ap.add_argument("--label-b", default="B")
    ap.add_argument("--radar", default=str(ROOT / "src" / "tracelens" / "ml" / "radar.json"))
    ap.add_argument("--rows", type=int, default=15, help="widest gaps to list")
    ap.add_argument("--out", help="write the markdown report here (default: stdout only)")
    args = ap.parse_args()

    A, B = (read_jsonl(Path(d) / "features.jsonl") for d in (args.a, args.b))
    for name, rows, where in (("--a", A, args.a), ("--b", B, args.b)):
        if not rows:
            print(f"no features in {where} ({name}): collect it first", file=sys.stderr)
            return 2
    manifest = read_jsonl(Path(args.a) / "manifest.jsonl")
    ok = [r for r in manifest if r.get("status") == "ok"]
    rows, agreed = gap_rows(A, B)

    md = [f"# {args.label_a} against {args.label_b}, feature by feature", "",
          f"`{args.a}`: {len(ok)} of {len(manifest)} captures succeeded, "
          f"{sum(1 for r in ok if r.get('triggered'))} with the planted problem showing, "
          f"{sum(1 for r in ok if r.get('lossy'))} lossy. Reproduce with `python scripts/arch_compare.py "
          f"--a {args.a} --b {args.b} --label-a '{args.label_a}' --label-b '{args.label_b}'`.", ""]

    if manifest:
        md += ["## Did each planted problem show up?", "",
               f"| Scenario | Label | Showed up on {args.label_a} | Rules that fired (HIGH+) |", "|---|---|---|---|"]
        for r in manifest:
            kinds = ", ".join(r.get("rule_kinds") or []) or "none"
            md.append(f"| `{r['scenario']}` | {r['label']} | {'yes' if r.get('triggered') else '**no**'} | {kinds} |")
        md.append("")

    md += ["## Median per feature", "",
           f"{agreed} of {len(rows)} compared feature/thread pairs agree within {AGREE:.2f}. The widest gaps:", "",
           f"| Scenario | Thread | Feature | {args.label_a} | {args.label_b} | Gap |", "|---|---|---|---|---|---|"]
    for d, sc, th, f, a, b in rows[: args.rows]:
        md.append(f"| `{sc}` | {th} | `{f}` | {a:.3f} | {b:.3f} | {d:.3f} |")

    radar = load(args.radar)
    md += ["", f"## The shipped radar on {args.label_a}", "",
           "The radar in `src/tracelens/ml/radar.json` was trained on x86 traces only, so this is a "
           "transfer test: it has never seen this machine.", "",
           "| Scenario | Label | Radar (persistent unusual threads) |", "|---|---|---|"]
    hit = miss = fa = quiet = 0
    for sc, label, flagged, _causes in score(A, radar, None):
        if label == HEALTHY:
            fa += bool(flagged)
            quiet += not flagged
        else:
            hit += bool(flagged)
            miss += not flagged
        md.append(f"| `{sc}` | {label} | {', '.join(f'{t} ({u}/{n})' for _, t, u, n in flagged[:3]) or 'quiet'} |")
    md += ["", f"**Radar on {args.label_a}: {hit} of {hit + miss} planted-bug traces flagged on the thread "
               f"that suffers, {fa} false alarms on {quiet + fa} healthy traces.**", ""]

    text = "\n".join(md)
    print(text)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
