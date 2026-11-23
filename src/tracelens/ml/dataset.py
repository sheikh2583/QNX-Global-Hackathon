"""The data engine: plan, collect and check labelled QNX kernel traces from the tlgen generator.

  plan     seeded parameter samples per scenario, with the evaluation split fixed in advance
  collect  run each planned variant on the QNX target under tracelogger (resumable)
  check    after capture: lossy? did the planted problem actually show up?

The label is the scenario we planted. Splits (docs/ml/DESIGN.md section 5):
  train          healthy variants (radar) and known-bug variants in parameter region A (classifier)
  test           held-out healthy variants and known-bug variants in parameter region B
  test_unseen    every variant of a family that has no TraceLens rule (radar's real test)
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from ..analyze import Analysis, analyze_file
from ..config import Config
from ..findings import at_least


@dataclass(frozen=True)
class Scenario:
    label: str  # finding kind, "healthy", or the unseen family's own name
    known: bool  # a TraceLens rule exists for it
    params: dict  # name -> (low, high) for ints, or a tuple of choices
    needs_irq: bool = False  # drives an interrupt: run with -i <irq> and a background load on the line


HEALTHY = "healthy"
SCENARIOS: dict[str, Scenario] = {
    "healthy_periodic": Scenario(HEALTHY, True, {"work_us": ("frac", 0.01, 0.25), "pin": (0, 1),
                                                 "period_us": (10000, 20000)}),
    # Long low-priority critical sections behind a PI mutex are healthy and common (the fixed Z1's logger
    # holds one 2.5 ms): the low thread waits READY a lot, and that must not look alien to the radar.
    # Medium loads up to 70% of a core are healthy too (the fixed Z1's telemetry uses 60%; widened from
    # 50% after the first sim-to-real check, so the real zoo traces are a development set now).
    "healthy_pi_mutex": Scenario(HEALTHY, True, {"work_us": ("frac", 0.01, 0.06), "cs_us": ("frac", 0.02, 0.30),
                                                 "mid_us": ("frac", 0.15, 0.65), "pin": (1,),
                                                 "period_us": (10000, 20000)}),
    # Unpinned too: a client that migrates between CPUs and waits longer for its reply is healthy.
    "healthy_ipc": Scenario(HEALTHY, True, {"work_us": ("frac", 0.01, 0.05), "cs_us": ("frac", 0.005, 0.06),
                                            "mid_us": ("frac", 0.10, 0.60), "pin": (0, 1),
                                            "period_us": (10000, 20000)}),
    "healthy_mixed": Scenario(HEALTHY, True, {"work_us": ("frac", 0.01, 0.08), "cs_us": ("frac", 0.02, 0.25),
                                              "mid_us": ("frac", 0.10, 0.50), "pin": (0, 1),
                                              "period_us": (10000, 20000)}),
    # cs_us > 1 tick so the low thread still holds the lock when the medium one wakes a tick later
    "sem_inversion": Scenario("priority_inversion", True, {"work_us": (100, 500), "cs_us": (1500, 3000),
                                                           "mid_us": (3000, 6000), "pin": (1,),
                                                           "period_us": (10000, 20000)}),
    "chan_inversion": Scenario("priority_inversion", True, {"work_us": (100, 500), "cs_us": (200, 800),
                                                            "mid_us": (3000, 6000), "pin": (1,),
                                                            "period_us": (10000, 20000)}),
    "ipc_deadlock": Scenario("ipc_deadlock", True, {"period_us": (10000, 20000)}),
    "lock_contention": Scenario("mutex_contention", True, {"work_us": (800, 2000), "workers": (2, 6), "pin": (0,),
                                                           "period_us": (10000, 20000)}),
    # The inversion rule also follows condition variables (found by the simulator, 2026-11-15), so this
    # family is a known one, not a held-out test of the radar.
    "condvar_inversion": Scenario("priority_inversion", True, {"work_us": (100, 500), "cs_us": (1500, 3000),
                                                               "mid_us": (3000, 6000), "pin": (1,),
                                                               "period_us": (10000, 20000)}),
    "cpu_starvation": Scenario("cpu_starvation", False, {"work_us": (200, 800), "mid_us": (3000, 8000), "pin": (1,),
                                                         "period_us": (10000, 20000)}),
    "mutex_abba": Scenario("mutex_abba", False, {"period_us": (10000,)}),
    # Job names here are not declared deadlines, so no rule sees the symptom: only behaviour can.
    "lost_wakeup": Scenario("lost_wakeup", False, {"work_us": (100, 500), "cs_us": (50, 300), "mid_us": (2000, 6000),
                                                   "pin": (0, 1), "period_us": (10000, 20000)}),
    "period_overrun": Scenario("period_overrun", False, {"work_us": (16000, 24000), "cs_us": (100, 400), "pin": (1,),
                                                         "period_us": (10000, 15000)}),
    # Interrupt-driven programs. The first radar experiment flagged a healthy interrupt handler as
    # unusual because no healthy one was in its training data: healthy coverage has to be broad.
    # A correct handler acknowledges the device and defers: the real reference handler does ~7 us per
    # interrupt (measured on the Z5 fix). 20-150 us made every healthy handler look busy.
    "healthy_irq": Scenario(HEALTHY, True, {"cs_us": (5, 60), "period_us": (10000,)}, needs_irq=True),
    "irq_overrun": Scenario("irq_handler_overrun", True, {"work_us": (600, 2500), "period_us": (10000, 20000)},
                            needs_irq=True),
    # The textbook QNX fix, and the one TraceLens's own ist-defer-work remedy writes: unmask at once and
    # hand the heavy work to a lower-priority worker. The radar must know this shape as healthy, or
    # TraceLens would flag the fix it just recommended (it flagged the real Z5 fix's worker, 2026-11-15).
    "healthy_irq_deferred": Scenario(HEALTHY, True, {"work_us": (1500, 3000), "cs_us": (5, 60),
                                                     "period_us": (10000,)}, needs_irq=True),
}
# Where each planted problem is, by thread name (tlgen.c and the simulator use the same names). The
# victim is the thread whose behaviour shows the problem; only its windows carry the bug's label when
# learning, every other thread's windows are normal behaviour (a preempted lock holder in an inversion
# looks exactly like a healthy one; labelling it "inversion" taught the classifier to blame the fixed
# Z1's logger, 2026-11-15).
TRUTH = {
    "sem_inversion": {"victims": ["hi"], "culprits": ["lo", "mid"]},
    "chan_inversion": {"victims": ["client"], "culprits": ["server", "mid"]},
    "condvar_inversion": {"victims": ["hi"], "culprits": ["lo", "mid"]},
    "ipc_deadlock": {"victims": ["fusion_a", "fusion_b"], "culprits": ["fusion_a", "fusion_b"]},
    "lock_contention": {"victims": ["w*"], "culprits": ["w*"]},
    "irq_overrun": {"victims": ["ist"], "culprits": ["ist"]},
    "cpu_starvation": {"victims": ["job"], "culprits": ["hog"]},
    "mutex_abba": {"victims": ["ab", "ba"], "culprits": ["ab", "ba"]},
    "lost_wakeup": {"victims": ["consumer"], "culprits": ["producer"]},
    "period_overrun": {"victims": ["logger"], "culprits": ["ctl"]},
}


def role_of(scenario: str, thread: str) -> str:
    """"victim", "culprit" or "other" for a thread of a planted scenario ("other" for healthy ones)."""
    t = TRUTH.get(scenario)
    if not t:
        return "other"

    def match(names):
        return any(thread == n or (n.endswith("*") and thread.startswith(n[:-1])) for n in names)
    return "victim" if match(t["victims"]) else "culprit" if match(t["culprits"]) else "other"


def window_label(row: dict) -> str:
    """Learning label of one feature row: the bug for the victim's windows, healthy for everything else."""
    if row["label"] == HEALTHY:
        return HEALTHY
    return row["label"] if row.get("role", role_of(row["scenario"], row.get("thread", ""))) == "victim" else HEALTHY


IRQ_BACKGROUND = "while :; do echo 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef; done > /dev/ser1"
FLAG = {"work_us": "-w", "cs_us": "-c", "mid_us": "-m", "workers": "-n", "pin": "-p", "period_us": "-P"}
REGION_B_PERIOD = 15000  # known-bug variants with a period at or above this are the classifier's test set
HEALTHY_LOAD = 0.75  # most CPU a healthy variant may demand of one core, so it keeps its deadlines
JOB_BUDGET_US = 2500  # the 'job' deadline declared in bugzoo/gen/tlgen.toml
JOB_MARGIN_US = 600  # slack a healthy variant keeps for wake-up and scheduling noise


def sample(scenario: str, rng: random.Random) -> dict:
    """One variant's parameters. A spec is a range, a tuple of choices, or ``("frac", lo, hi)``: a
    fraction of this run's period. Durations drawn as fractions keep the *utilisation* spread even, so
    heavily loaded but healthy programs are common in training. Absolute ranges alone made them rare:
    only the corner where a short period met a long critical section produced one, and the radar then
    flagged the busy low-priority thread of a real, correct program (the Z1 reference fix's logger)."""
    spec_all = SCENARIOS[scenario].params
    out = {}
    period = spec_all.get("period_us", (10000,))
    out["period_us"] = (rng.randrange(period[0] // 1000, period[1] // 1000 + 1) * 1000 if len(period) == 2
                        else rng.choice(period))
    for name, spec in spec_all.items():
        if name == "period_us":
            continue
        if spec and spec[0] == "frac":
            out[name] = max(50, round(rng.uniform(spec[1], spec[2]) * out["period_us"] / 10) * 10)
        elif len(spec) == 2 and isinstance(spec[0], int) and spec[1] > spec[0] + 1:
            out[name] = rng.randint(*spec)
        else:
            out[name] = rng.choice(spec)
    if SCENARIOS[scenario].label == HEALTHY:
        # A healthy variant must still be schedulable, or the rules are right to flag it and it is no
        # longer healthy data. Two limits: a critical section shorter than the job budget it shares a
        # CPU with, and a total CPU demand that leaves headroom when everything is pinned to one core.
        if "work_us" in out:
            out["work_us"] = min(out["work_us"], JOB_BUDGET_US // 2)
        if "cs_us" in out:  # the job waits for this lock, so its holder must fit inside the budget
            out["cs_us"] = max(50, min(out["cs_us"], JOB_BUDGET_US - out.get("work_us", 0) - JOB_MARGIN_US))
        parts = [k for k in ("work_us", "cs_us", "mid_us") if k in out]
        total = sum(out[k] for k in parts)
        budget = HEALTHY_LOAD * out["period_us"]
        if out.get("pin", 1) and total > budget and total:
            for k in parts:
                out[k] = max(50, round(out[k] * budget / total / 10) * 10)
    return out


def split_of(scenario: str, params: dict, item_hash: int) -> str:
    sc = SCENARIOS[scenario]
    if not sc.known:
        return "test_unseen"
    if sc.label == HEALTHY:
        return "test" if item_hash % 5 == 0 else "train"  # 20% of healthy variants held out
    return "test" if params.get("period_us", 0) >= REGION_B_PERIOD else "train"


def tlgen_args(scenario: str, params: dict, seconds: int = 2, irq: int = 4) -> list[str]:
    args = ["-s", scenario, "-d", str(seconds)]
    for name, value in sorted(params.items()):
        args += [FLAG[name], str(value)]
    if SCENARIOS[scenario].needs_irq:
        args += ["-i", str(irq)]
    return args


def make_plan(per_scenario: int, seed: int = 7, scenarios: list[str] | None = None, irq: int = 4) -> list[dict]:
    """``irq``: the interrupt the interrupt scenarios attach to. 4 is COM1 on the x86 QEMU guest; the
    aarch64 ``virt`` machine's PL011 UART is interrupt 33, and attaching to 4 there waits forever."""
    rng = random.Random(seed)
    plan = []
    for scenario in scenarios or list(SCENARIOS):
        for n in range(per_scenario):
            params = sample(scenario, rng)
            ident = f"{scenario}-{n:04d}"
            h = int(hashlib.sha256(f"{seed}:{ident}".encode()).hexdigest(), 16)
            plan.append({"id": ident, "scenario": scenario, "label": SCENARIOS[scenario].label,
                         "known": SCENARIOS[scenario].known, "split": split_of(scenario, params, h),
                         "params": params, "args": tlgen_args(scenario, params, irq=irq),
                         "background": IRQ_BACKGROUND if SCENARIOS[scenario].needs_irq else None})
    return plan


def write_jsonl(path: str | Path, rows) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def read_jsonl(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


# ----------------------------------------------------------------------------- after capture
def check(item: dict, a: Analysis, cfg: Config) -> dict:
    """Did the planted problem show up? (Known families: the matching rule fired. Unseen families: the
    symptom the scenario is built to cause. Healthy: no finding at or above the gate.)"""
    kinds = {f.kind for f in a.findings if at_least(f.severity, cfg.fail_on)}
    label = item["label"]
    if label == HEALTHY:
        triggered = not kinds
    elif item["known"]:
        triggered = label in kinds
    elif label == "cpu_starvation":  # the job waits READY behind the hog; a deadline rule cannot see a
        # constant late start without release markers, so check the symptom itself
        triggered = any(iv.state == "READY" and iv.duration > 1_000_000
                        for k, th in a.model.threads.items() if k[0] != 1 and th.name == "job" for iv in th.intervals)
    elif label == "period_overrun":  # the logger never gets the CPU for several periods
        triggered = any(iv.state == "READY" and iv.duration > 20_000_000
                        for k, th in a.model.threads.items() if k[0] != 1 and th.name == "logger" for iv in th.intervals)
    else:  # mutex_abba, lost_wakeup: a long MUTEX / CONDVAR wait in the workload
        state = {"mutex_abba": "MUTEX", "lost_wakeup": "CONDVAR"}[label]
        triggered = any(iv.state == state and iv.duration > 1_000_000
                        for k, th in a.model.threads.items() if k[0] != 1 for iv in th.intervals)
    out = {"lossy": a.model.lossy, "triggered": bool(triggered), "rule_kinds": sorted(kinds)}
    if a.errors:  # a crashed detector must not pass as "no finding" (found by the simulator)
        out["errors"] = a.errors
    return out


# ----------------------------------------------------------------------------- collection
# (item, run dir) -> path of the decoded trace text
Capturer = Callable[[dict, Path], Path]


def collect(plan: list[dict], capture: Capturer, out_dir: str | Path, cfg: Config,
            limit: int | None = None, log: Callable[[str], None] = print) -> list[dict]:
    """Capture every planned item not yet in the manifest; append each result as it lands, so an
    interrupted run resumes where it stopped."""
    out = Path(out_dir)
    manifest = out / "manifest.jsonl"
    done = {r["id"] for r in read_jsonl(manifest) if r.get("status") == "ok"}
    todo = [p for p in plan if p["id"] not in done][:limit]
    log(f"{len(done)} already collected, {len(todo)} to go")
    for n, item in enumerate(todo, 1):
        started = time.time()
        row = dict(item)
        try:
            trace = capture(item, out / "traces")
            a = analyze_file(trace, cfg)
            row |= check(item, a, cfg) | {"trace": str(Path(trace).relative_to(out)) if Path(trace).is_relative_to(out)
                                          else str(trace), "status": "ok"}
        except Exception as exc:  # one bad run must not stop an overnight collection
            row |= {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
        row["seconds"] = round(time.time() - started, 1)
        with open(manifest, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row) + "\n")
        log(f"[{n}/{len(todo)}] {item['id']}: {row['status']}"
            + (f", triggered={row['triggered']}, lossy={row['lossy']}" if row["status"] == "ok" else f" ({row['error']})"))
    return read_jsonl(manifest)
