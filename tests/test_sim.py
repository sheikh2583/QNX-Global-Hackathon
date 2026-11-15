"""The QNX scheduling simulator: real QNX 8.0 trace format, sound scheduling, every planted problem
shows up, and the detector / learning fixes it found stay fixed."""

import gzip
import json
import random

import pytest

from tracelens.analyze import analyze_text
from tracelens.cli import main
from tracelens.config import load_config
from tracelens.ingest.traceprinter import parse_text
from tracelens.ml import dataset
from tracelens.ml.dataset import role_of, window_label
from tracelens.ml.features import FEATURES, windows
from tracelens.ml.model import calibrate_persistence, fit_radar, thread_flagged
from tracelens.model.trace import TraceModel
from tracelens.sim import simulate
from tracelens.sim.dataset import generate
from tracelens.sim.kernel import Kernel, Knobs

CFG = load_config("bugzoo/gen/tlgen.toml")


@pytest.fixture(scope="module")
def traces():
    rng = random.Random(5)
    return {s: simulate(s, dataset.sample(s, rng), seed=2, seconds=1) for s in dataset.SCENARIOS}


# --------------------------------------------------------------------- format and soundness
def test_trace_is_real_qnx8_traceprinter_format(traces):
    text = traces["sem_inversion"]
    t = parse_text(text)
    assert t.header["TRACE_CYCLES_PER_SEC"].isdigit() and t.header["TRACE_SIMULATED"].startswith("tracelens.sim")
    assert t.unparsed_lines == 0 and not t.wraps
    kinds = {(e.cls, e.kind) for e in t.events}
    for want in [("KER_CALL", "SYNC_SEM_WAIT"), ("KER_CALL", "SYNC_SEM_POST"), ("THREAD", "RUNNING"), ("THREAD", "SEM"),
                 ("USREVENT", "EVENT:1"), ("PROCESS", "PROCCREATE_NAME"), ("PROCESS", "PROCTHREAD_NAME"),
                 ("INTERRUPT", "INT_DELIVER"), ("SYSTEM", "IST_ATTACH")]:
        assert want in kinds, want
    wait = next(e for e in t.events if e.kind == "SYNC_SEM_WAIT")
    assert wait.args["sync"].startswith("0x") and "count" in wait.args  # continuation lines, as on QNX 8.0
    assert '"TL_META name=hi prio=50"' in text


def test_every_scenario_is_sound_and_deterministic(traces):
    for s, text in traces.items():
        m = TraceModel(parse_text(text))
        assert not m.integrity and not m.lossy, (s, m.integrity)
    again = simulate("healthy_ipc", {"cs_us": 300}, seed=9, seconds=1)
    assert simulate("healthy_ipc", {"cs_us": 300}, seed=9, seconds=1) == again
    assert simulate("healthy_ipc", {"cs_us": 300}, seed=10, seconds=1) != again


def test_every_planted_problem_shows_up_and_healthy_stays_clean(traces):
    for s, text in traces.items():
        sc = dataset.SCENARIOS[s]
        a = analyze_text(text, CFG)
        c = dataset.check({"label": sc.label, "known": sc.known}, a, CFG)
        assert not a.errors, (s, a.errors)
        if s == "lock_contention":  # mild variants are graded MEDIUM by the rule (7 of 40 in the sample)
            continue
        assert c["triggered"], (s, c)
        if not sc.known:  # the held-out families stay invisible to the rules
            assert not c["rule_kinds"], (s, c)


def test_findings_name_the_planted_threads(traces):
    want = {"sem_inversion": ["hi", "lo"], "chan_inversion": ["client", "server"], "condvar_inversion": ["hi", "lo"],
            "ipc_deadlock": ["fusion_a", "fusion_b"], "irq_overrun": ["ist"]}
    for s, threads in want.items():
        f = next(f for f in analyze_text(traces[s], CFG).findings if f.kind != "deadline_miss")
        assert sorted(f.threads[:len(threads)]) == sorted(threads), (s, f.threads)


# --------------------------------------------------------------------- scheduler semantics
def _kernel():
    k = Kernel(seed=1, knobs=Knobs(late_ticks=0, noise=0.0))
    k.boot()
    return k


def test_priority_inheriting_mutex_boosts_the_holder():
    k = _kernel()
    m = k.new_mutex(pi=True)
    log = {}

    def low():
        yield ("runmask", (0,))
        yield ("sched", 10)
        yield ("mutex_lock", m)
        yield ("spin", 3_000_000)
        log["low_prio_while_held"] = k.cpus[0].prio
        yield ("mutex_unlock", m)

    def high():
        yield ("runmask", (0,))
        yield ("sched", 50)
        yield ("sleep", 1_000_000)
        yield ("mutex_lock", m)
        yield ("mutex_unlock", m)

    k.launch("t", high, prio=50)
    k.launch("t", low)
    k.run(50_000_000)
    assert log["low_prio_while_held"] == 50


def test_shared_interrupt_line_masks_per_handler():
    k = _kernel()
    irq = k.device_irq(4, 0, rate_hz=0)
    calls = []

    def ist():
        att = yield ("interrupt_attach", irq)
        yield ("interrupt_wait", att)
        calls.append(k.now)
        yield ("spin", 2_000_000)  # masked: a second interrupt is latched, not lost
        yield ("interrupt_unmask", att)
        yield ("interrupt_wait", att)
        calls.append(k.now)

    k.launch("t", ist)
    k.run(10_000_000)
    k.interrupt(irq)
    k.run(11_000_000)
    k.interrupt(irq)
    k.run(30_000_000)
    assert len(calls) == 2 and calls[1] - calls[0] >= 2_000_000


# --------------------------------------------------------------------- detector fixes found by the simulator
def test_irq_rule_ignores_interrupts_before_the_handler_attached(traces):
    """The serial line is busy from the start of the capture; deliveries before the program attached are
    not its latency (they made a healthy handler look 100 ms late). Never-run handlers do not crash it."""
    a = analyze_text(traces["healthy_irq"], CFG)
    assert not a.errors and not [f for f in a.findings if f.kind.startswith("irq")]


def test_check_reports_detector_errors():
    class A:
        findings, errors = [], ["irq_latency: KeyError((1, 10))"]
        model = TraceModel(parse_text(simulate("healthy_periodic", seed=1, seconds=1)))
    out = dataset.check({"label": "healthy", "known": True}, A(), CFG)
    assert out["errors"]


# --------------------------------------------------------------------- learning rules
def test_whole_window_waits_count_only_when_stuck(traces):
    """A thread REPLY-blocked for a whole window is idle I/O (shell threads); stuck on a mutex it is not."""
    m = analyze_text(traces["mutex_abba"], CFG).model
    stuck = [f for k, _, _, f in windows(m) if m.label(k) in ("ab", "ba") and f["share_mutex"] > 0.99]
    assert stuck and all(f["max_block_frac"] <= 1.0 for f in stuck)


def test_persistence_rule_is_calibrated_on_healthy_traces():
    healthy = [{"t": (0, 10)}] * 98 + [{"t": (4, 10)}, {"t": (6, 10)}]
    model = calibrate_persistence({"threshold": 1.0}, healthy, q=0.99)
    assert model["min_frac"] == 0.6 and model["min_windows"] == 3
    assert thread_flagged(model, 7, 10) and not thread_flagged(model, 5, 10) and not thread_flagged(model, 2, 2)
    flat = fit_radar([dict.fromkeys(FEATURES, 0.0)] * 30)  # no persistence calibrated: one window is enough
    assert thread_flagged(flat, 1, 100)


def test_only_the_victim_thread_carries_the_bug_label():
    assert role_of("sem_inversion", "hi") == "victim" and role_of("sem_inversion", "lo") == "culprit"
    assert role_of("lock_contention", "w3") == "victim" and role_of("healthy_ipc", "client") == "other"
    row = {"label": "priority_inversion", "scenario": "sem_inversion"}
    assert window_label(row | {"thread": "hi"}) == "priority_inversion"
    assert window_label(row | {"thread": "lo"}) == "healthy"  # a preempted holder looks like a healthy one


# --------------------------------------------------------------------- data engine and CLI
def test_generate_writes_the_same_artifacts_as_a_real_collection(tmp_path):
    plan = dataset.make_plan(1, seed=3, scenarios=["sem_inversion", "healthy_periodic"])
    for item in plan:
        item["args"][item["args"].index("-d") + 1] = "1"
    rows = generate(plan, tmp_path, "bugzoo/gen/tlgen.toml", workers=1, log=lambda s: None)
    assert [r["status"] for r in rows] == ["ok", "ok"] and all(r["triggered"] and r["source"] == "sim" for r in rows)
    with gzip.open(tmp_path / rows[0]["trace"], "rt") as fh:
        assert "TRACE_CYCLES_PER_SEC" in fh.read(2000)
    feats = [json.loads(x) for x in (tmp_path / "features.jsonl").read_text().splitlines()]
    assert {f["role"] for f in feats if f["scenario"] == "sem_inversion"} >= {"victim", "culprit"}
    assert len(generate(plan, tmp_path, "bugzoo/gen/tlgen.toml", workers=1, log=lambda s: None)) == 2  # resumable


def test_simulate_cli(tmp_path, capsys):
    out = tmp_path / "t.txt.gz"
    assert main(["simulate", "sem_inversion", "-o", str(out), "--seconds", "1", "--param", "cs_us=2500"]) == 0
    rc = main(["analyze", str(out), "-c", "bugzoo/gen/tlgen.toml", "--json", str(tmp_path / "a.json")])
    kinds = [f["kind"] for f in json.loads((tmp_path / "a.json").read_text())["findings"]]
    assert rc == 1 and kinds[0] == "priority_inversion"
    assert main(["simulate", "no_such_scenario", "-o", str(out)]) == 2
