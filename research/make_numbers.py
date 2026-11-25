"""Regenerate every number a paper may quote, from committed data only.

    python research/make_numbers.py          # writes docs/research/numbers.json and numbers.tex
    python research/make_numbers.py --check  # fails if the committed files differ from a fresh run

Sources (all committed): docs/research/gate_study.json, bench/manifest.toml, docs/results/ml.json,
docs/results/memcached_logger/daemon/verdict.json, docs/results/nng_close/compare.json, and the exact
arithmetic in src/tracelens/verdict.py. No number is typed by hand here except the labels.
Each value has a LaTeX macro \\tl<CamelName>; the paper uses the macro, never the digits.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

from tracelens.verdict import residual_rate_upper, runs_needed

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "docs" / "results"
OUT_JSON = ROOT / "docs" / "research" / "numbers.json"
OUT_TEX = ROOT / "docs" / "research" / "numbers.tex"


def load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def pct(x: float, nd: int = 1) -> str:
    return f"{100 * x:.{nd}f}\\%"


def numbers() -> dict[str, str]:
    n: dict[str, str] = {}

    # R1: what "0 of n clean after-captures" lets us say (95 % one-sided Clopper-Pearson)
    for k in (5, 10, 20):
        n[f"ResidualZeroOf{ {5: 'Five', 10: 'Ten', 20: 'Twenty'}[k] }"] = pct(residual_rate_upper(k, 0, 0.95))
    n["RunsNeededTenPercent"] = str(runs_needed(0.10, 0.95))
    n["ResidualOneOfTen"] = pct(residual_rate_upper(10, 1, 0.95))

    # R8, simulator: gate false alarms and power
    g = load(ROOT / "docs" / "research" / "gate_study.json")
    n["GateSplits"] = str(g["splits"])
    n["GateCapturesPerArm"] = str(min(g["captures_per_arm"].values()))
    for side, word in (("5v5", "Five"), ("10v10", "Ten")):
        for cmp in ("capture", "job"):
            c = g["aa"][side][f"{cmp}_floors_off"]
            n[f"AA{cmp.capitalize()}{word}FloorsOff"] = pct(c["rate"])
    fam = g["family"]["any_false_alarm"]
    for m in ("none", "holm", "bh"):
        n[f"Family{m.capitalize()}"] = pct(fam[m]["rate"])
    p = g["power"]
    n["PowerOnePercentFloorsOff"] = pct(p["+1%_n5"]["capture_floors_off"]["rate"], 0)
    n["PowerTenPercentFloorsOn"] = pct(p["+10%_n15"]["capture_floors_on"]["rate"], 0)
    n["PowerTwentyPercentFloorsOn"] = pct(p["+20%_n5"]["capture_floors_on"]["rate"], 0)
    b = g["baseline_p99_ms"]
    n["SimPNinetyNineSpreadPct"] = f"{100 * (b['max'] - b['min']) / b['median']:.1f}\\%"

    # case studies (labelled case studies, not blind results)
    for tag, path, kind in (("Memcached", RES / "memcached_logger" / "daemon" / "verdict.json", "lost_wakeup"),
                            ("Nng", RES / "nng_close" / "compare.json", "stuck_job")):
        v = load(path)
        n[f"{tag}Verdict"] = v["verdict"]
        n[f"{tag}RunsBefore"] = str(v["runs"]["before"])
        n[f"{tag}RunsAfter"] = str(v["runs"]["after"])
        n[f"{tag}LossySkipped"] = str(v["runs"]["lossy_skipped"])
        n[f"{tag}BeforeRate"] = pct(v["targets"][kind]["before_rate"], 0)
        n[f"{tag}AfterRate"] = pct(v["targets"][kind]["after_rate"], 0)
        after_n = v["runs"]["after"]
        n[f"{tag}ResidualUpper"] = pct(residual_rate_upper(after_n, 0, 0.95), 0)


    # bug-zoo detection and fix tables (docs/results/detect.json, fix.json)
    det = load(RES / "detect.json")
    wl = det["workloads"]
    runs = det["runs_per_build"]
    n["ZooDetectPerBuild"] = f"{min(w['detected_runs'] for w in wl)} of {runs}"
    n["ZooReferenceFlagged"] = f"{sum(w['reference_runs_with_findings'] for w in wl)} of {sum(w['reference_clean_runs'] for w in wl)}"
    neg = det["negatives"]
    n["ZooHealthyRuns"] = f"{sum(x['runs_with_findings'] for x in neg)} of {sum(x['runs'] - x['lossy'] for x in neg)}"
    fx = load(RES / "fix.json")["rows"]
    n["ZooFixVerified"] = str(sum(1 for r in fx if r["status"] == "VERIFIED"))
    n["ZooFixWorkloads"] = str(len(fx))
    names = {"z1_infusion_pump": "ZOne", "z2_brake_by_wire": "ZTwo", "z4_camera_pipeline": "ZFour"}
    for r in fx:
        tag = names.get(r["workload"])
        if tag and r["verdict"]["deadlines"]:
            d = r["verdict"]["deadlines"][0]
            n[f"{tag}PNinetyNineBefore"] = f"{d['before_p99'] / 1e6:.2f}"
            n[f"{tag}PNinetyNineAfter"] = f"{d['after_p99'] / 1e6:.2f}"
    # NOT available in a committed machine-readable file: Z5 masked p99 (2.41 -> 0.24 ms is in PLAN.md prose only)

    # third-party TTK4147 fix (docs/results/third_party_fix/compare/primary_10v10.json)
    tp = load(RES / "third_party_fix" / "compare" / "primary_10v10.json")
    d = tp["deadlines"][0]
    n["TtkVerdict"] = tp["verdict"]
    n["TtkCaught"] = pct(tp["targets"]["priority_inversion"]["before_rate"], 0)
    n["TtkPNinetyNineBefore"] = f"{d['before_p99'] / 1e6:.0f}"
    n["TtkPNinetyNineAfter"] = f"{d['after_p99'] / 1e6:.0f}"
    n["TtkP"] = f"{d['p_value']:.1e}".replace("e-0", "e-")

    # rt-tests and the busy-medium control (docs/results/third_party/{json,control/json})
    tpd = RES / "third_party"
    def has_pi(p: Path) -> bool:
        return any(f["kind"] == "priority_inversion" for f in load(p)["findings"])
    rt = [p for p in sorted((tpd / "json").glob("*.json"))
          if p.name.startswith(("pi_stress_default", "pi_stress_uniproc", "pmqtest", "ptsematest"))]
    n["RtTestsRuns"] = str(len(rt))
    n["RtTestsFindings"] = str(sum(1 for p in rt if any(f["kind"] != "unusual_behavior" for f in load(p)["findings"])))
    n["RtTestsRadarFlags"] = str(sum(1 for p in rt if any(f["kind"] == "unusual_behavior" for f in load(p)["findings"])))
    bm = sorted((tpd / "control" / "json").glob("busy_medium_*.json")) + sorted((tpd / "json").glob("busy_medium_*.json"))
    nopi = [p for p in bm if p.name.startswith(("busy_medium_none", "busy_medium_sem"))]
    pi = [p for p in bm if p.name.startswith("busy_medium_pi")]
    n["BusyMediumNoPi"] = f"{sum(has_pi(p) for p in nopi)} of {len(nopi)}"
    n["BusyMediumPi"] = f"{sum(has_pi(p) for p in pi)} of {len(pi)}"

    # radar contribution on the generator zoo (honest: generator data, not real bugs)
    c = load(RES / "ml.json")["contribution"]
    n["ZooBuggyWindows"] = str(c["buggy"])
    n["ZooRulesOnly"] = str(c["rules_only"])
    n["ZooRadarOnly"] = str(c["radar_only"])
    n["ZooBoth"] = str(c["both"])
    n["ZooNeither"] = str(c["neither"])
    n["RadarHealthy"] = f"{c['false_alarms']} of {c['healthy']}"

    # size of the code base (changes with every edit of src/; excluded from the staleness test)
    n["LinesOfCode"] = str(sum(len(p.read_text(encoding="utf-8").splitlines())
                               for p in (ROOT / "src" / "tracelens").rglob("*.py")))

    # benchmark manifest
    bugs = tomllib.loads((ROOT / "bench" / "manifest.toml").read_text(encoding="utf-8"))["bug"]
    for st in ("candidate", "reproduced", "excluded"):
        n[f"Bench{st.capitalize()}"] = str(sum(1 for x in bugs if x["status"] == st))
    n["BenchTotal"] = str(len(bugs))
    blind = [x for x in bugs if x["tool_frozen_before_driver"]]
    n["BenchBlindAttempted"] = str(len(blind))
    n["BenchBlindReproduced"] = str(sum(1 for x in blind if x["status"] == "reproduced"))
    return n


def render_tex(n: dict[str, str]) -> str:
    lines = ["% Generated by research/make_numbers.py. Do not edit."]
    for k, v in sorted(n.items()):
        assert re.fullmatch(r"[A-Za-z]+", k), k
        lines.append(f"\\newcommand{{\\tl{k}}}{{{v}}}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    n = numbers()
    js = json.dumps(n, indent=1, sort_keys=True) + "\n"
    tex = render_tex(n)
    if args.check:
        same = (OUT_JSON.exists() and OUT_JSON.read_text(encoding="utf-8") == js
                and OUT_TEX.exists() and OUT_TEX.read_text(encoding="utf-8") == tex)
        print("numbers up to date" if same else "numbers.json/numbers.tex are stale: run research/make_numbers.py")
        return 0 if same else 1
    OUT_JSON.write_text(js, encoding="utf-8", newline="\n")
    OUT_TEX.write_text(tex, encoding="utf-8", newline="\n")
    print(f"wrote {len(n)} numbers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
