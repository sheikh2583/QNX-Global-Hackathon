"""R2.2: build and capture the mutants. Resumable; logs host load. Run it where the QNX SDP and the VM are reachable
(WSL2 Ubuntu in our setup, with ~/qnx800/qnxsdp-env.sh sourced and the venv active).

    python research/mutants/run.py list
    python research/mutants/run.py build                      # patch + qcc for every zoo mutant and the 5 unpatched builds
    python research/mutants/run.py capture --host 127.0.0.1:2222 --irq 4 --n 20 [--only Z1-mask,Z1-ref] [--workload z1_infusion_pump]
    python research/mutants/run.py status

Only the five bug-zoo workloads are automated. TP-ttk-ref and MC-ref are third-party controls whose before/after captures
already exist (docs/results/third_party_fix, docs/results/memcached_logger); MC-wrong needs the memcached daemon harness
(third_party/memcached_logger/build_daemon.sh) and is run by hand.

Layout. Traces and binaries stay out of git: data/research/mutants/<id>/{build,traces}. Committed (small): per-capture
summaries at docs/results/oracle_study/<id>/<attempt>.json (kinds, response times per deadline, lossy flag, trace SHA-256,
host load at start) and docs/results/oracle_study/hostload.jsonl. A capture is "clean" when its summary says lossy=false;
lossy captures are kept (counted) and replaced until N clean exist or 2N attempts were made.
Unpatched builds use the id <workload>-before and are shared by every mutant of that workload.

Preconditions the script checks, not assumes: the E2 freeze record in docs/research/PROTOCOL.md must exist before `capture`
runs (pass --allow-unfrozen to rehearse), and the host must be idle (loadavg1 below --max-load, default 0.5).
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research" / "mutants"))
import make_mutants  # noqa: E402

DATA = ROOT / "data" / "research" / "mutants"
RES = ROOT / "docs" / "results" / "oracle_study"
ZOO = ROOT / "bugzoo"
PROTOCOL = ROOT / "docs" / "research" / "PROTOCOL.md"
ZOO_WORKLOADS = ("z1_infusion_pump", "z2_brake_by_wire", "z3_sensor_fusion", "z4_camera_pipeline", "z5_motor_encoder")


def mutants():
    return [m for m in make_mutants.build() if m.workload in ZOO_WORKLOADS]


def targets():
    """(id, workload, patch path or None) for every zoo mutant plus one unpatched build per workload."""
    out = [(f"{w}-before", w, None) for w in ZOO_WORKLOADS]
    out += [(m.id, m.workload, make_mutants.OUT / m.workload / m.id / "patch.diff") for m in mutants()]
    return out


def frozen() -> bool:
    """True when the E2 section of PROTOCOL.md carries a `- frozen: <git sha> ...` line."""
    inside = False
    for line in PROTOCOL.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.startswith("## E2")
        elif inside and re.match(r"-\s*frozen:\s*[0-9a-f]{7,40}", line.strip()):
            return True
    return False


def loadavg() -> float:
    try:
        return float(Path("/proc/loadavg").read_text().split()[0])
    except OSError:
        return os.getloadavg()[0] if hasattr(os, "getloadavg") else -1.0


def build_one(tid: str, workload: str, patch: Path | None, arch: str) -> bool:
    from tracelens.fix import QccBuilder
    d = DATA / tid / "build"
    d.mkdir(parents=True, exist_ok=True)
    src = d / "main.c"
    src.write_text((ZOO / workload / "main.c").read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    if patch is not None:
        cp = subprocess.run(["patch", "-p1", "-s", "-i", str(patch)], cwd=d, capture_output=True, text=True)
        if cp.returncode:
            print(f"  {tid}: patch failed: {cp.stdout}{cp.stderr}")
            return False
    res = QccBuilder(arch=arch).build([src], [ZOO / "common"], d / tid)
    (d / "build.log").write_text(res.log, encoding="utf-8")
    print(f"  {tid}: {'ok' if res.ok else 'BUILD FAILED, see ' + str(d / 'build.log')}")
    return res.ok


def cmd_build(a) -> int:
    only = set(a.only.split(",")) if a.only else None
    bad = 0
    for tid, w, patch in targets():
        if only and tid not in only:
            continue
        if a.workload and w != a.workload:
            continue
        bad += not build_one(tid, w, patch, a.arch)
    return 1 if bad else 0


def attempts(tid: str) -> list[dict]:
    d = RES / tid
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("[0-9]*.json"), key=lambda p: int(p.stem))] if d.exists() else []


def cmd_capture(a) -> int:
    from tracelens.analyze import analyze_file
    from tracelens.config import load_config
    from tracelens.evaluation import load_for, load_zoo
    from tracelens.target import Target, capture
    from tracelens.verdict import summarize

    if not frozen() and not a.allow_unfrozen:
        print("E2 is not frozen in docs/research/PROTOCOL.md: freeze it first (or --allow-unfrozen to rehearse)", file=sys.stderr)
        return 2
    cfg = load_config(ZOO / "tracelens.toml")
    zoo = {z.name: z for z in load_zoo(ZOO / "zoo.toml")[0]}
    host, _, port = a.host.partition(":")
    target = Target(host=host, user="root", port=int(port or 22), key=a.key)
    only = set(a.only.split(",")) if a.only else None
    RES.mkdir(parents=True, exist_ok=True)
    log = RES / "hostload.jsonl"
    for tid, w, _patch in targets():
        if (only and tid not in only) or (a.workload and w != a.workload):
            continue
        binary = DATA / tid / "build" / tid
        if not binary.exists():
            print(f"{tid}: not built (run `build` first)")
            continue
        entry = zoo[w]
        if entry.needs_irq and a.irq is None:
            print(f"{tid}: needs --irq")
            continue
        wargs = [x.replace("{irq}", str(a.irq)) for x in entry.args]
        done = attempts(tid)
        clean = sum(1 for r in done if not r["lossy"])
        idx = len(done)
        while clean < a.n and idx < 2 * a.n:
            load = loadavg()
            if load > a.max_load:
                print(f"host load {load:.2f} > {a.max_load}: stopping; rerun when idle")
                return 3
            out = DATA / tid / "traces"
            res = capture(target, binary, wargs, out, seconds=a.seconds, name=f"{tid}-{idx}",
                          background=load_for(entry, a.irq_load))
            text = Path(res.text) if res.text else None
            if text is None or not text.exists():
                print(f"{tid}-{idx}: no trace text")
                return 1
            s = summarize(analyze_file(text, cfg), cfg, str(text))
            rec = {"id": tid, "attempt": idx, "lossy": s.lossy, "kinds": sorted(s.kinds), "responses": s.responses,
                   "trace_sha256": hashlib.sha256(text.read_bytes()).hexdigest(), "workload_rc": res.workload_rc,
                   "loadavg_start": load, "loadavg_end": loadavg(), "time": time.strftime("%Y-%m-%dT%H:%M:%S")}
            (RES / tid).mkdir(parents=True, exist_ok=True)
            (RES / tid / f"{idx}.json").write_text(json.dumps(rec), encoding="utf-8")
            with log.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({k: rec[k] for k in ("id", "attempt", "loadavg_start", "loadavg_end", "time")}) + "\n")
            clean += not s.lossy
            idx += 1
            print(f"{tid}: attempt {idx} lossy={s.lossy} kinds={sorted(s.kinds)} clean {clean}/{a.n}")
        if clean < a.n:
            print(f"{tid}: only {clean} clean captures after {idx} attempts: reported as short, not hidden")
    return 0


def cmd_status(_a) -> int:
    for tid, _w, _p in targets():
        r = attempts(tid)
        print(f"{tid:28s} attempts {len(r):2d}  clean {sum(1 for x in r if not x['lossy']):2d}")
    return 0


def cmd_list(_a) -> int:
    for m in mutants():
        print(f"{m.id:14s} {m.truth:4s} {m.workload}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("list", cmd_list), ("build", cmd_build), ("capture", cmd_capture), ("status", cmd_status)):
        p = sub.add_parser(name)
        p.set_defaults(func=fn)
        if name in ("build", "capture"):
            p.add_argument("--only")
            p.add_argument("--workload")
        if name == "build":
            p.add_argument("--arch", default="x86_64")
        if name == "capture":
            p.add_argument("--host", required=True)
            p.add_argument("--key")
            p.add_argument("--irq", type=int)
            p.add_argument("--irq-load")
            p.add_argument("--n", type=int, default=20)
            p.add_argument("--seconds", type=int, default=4)
            p.add_argument("--max-load", type=float, default=0.5)
            p.add_argument("--allow-unfrozen", action="store_true")
    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
