"""The regression gate: `tracelens baseline save` and `tracelens gate`.

Real QNX 8.0 captures (``fixtures/real/``) give one capture per build, which is exactly the case
the gate must handle honestly: it states that one capture against one cannot produce a p-value and
falls back to the documented threshold rule. The statistical path -- several captures per build,
a one-sided Mann-Whitney U on per-capture p99 -- is exercised with the simulator, which is the
only way to get many captures of one build without the target.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tracelens import gate as G
from tracelens.cli import main
from tracelens.config import load_config
from tracelens.sim import simulate, write_trace
from tracelens.verdict import INCONCLUSIVE

REAL = Path(__file__).resolve().parents[1] / "fixtures" / "real"
REAL_TOML = REAL / "tracelens.toml"
CFG = load_config(REAL_TOML)

SIM_TOML = """\
fail_on = "high"

[deadlines.hi]
budget_us = 2500
"""

HDR = (" -- HEADER FILE INFORMATION --\n"
       "TRACE_CYCLES_PER_SEC:: {cps}\n"
       "TRACE_CPU_NUM:: 2\n"
       " -- KERNEL EVENTS --\n")


def real(name: str) -> Path:
    return REAL / f"{name}.txt.gz"


def baseline_of(*names: str, cfg=CFG, config_path=REAL_TOML) -> dict:
    caps = [G.stats_of(real(n), cfg) for n in names]
    return G.build_baseline(caps, cfg, names[0], config_path)


def gate_real(baseline: dict, *names: str, cfg=CFG, **kw) -> G.GateResult:
    return G.gate([G.stats_of(real(n), cfg) for n in names], baseline, cfg, **kw)


def lossy_trace(path: Path) -> Path:
    """Thread 1 RUNNING on two CPUs at once: an event was dropped, so the timings are fiction."""
    path.write_text(HDR.format(cps=1_000_000_000)
                    + "t:0x00000010 CPU:00 THREAD  :THRUNNING pid:1 tid:1\n"
                      "t:0x00000020 CPU:01 THREAD  :THRUNNING pid:1 tid:1\n"
                      "t:0x00000030 CPU:01 THREAD  :THREADY   pid:1 tid:1\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------- real captures, one per build


def test_a_build_passes_its_own_baseline():
    """The gate must not cry wolf at a build that did not change."""
    for name in ("z2_brake_by_wire_fixed", "z4_camera_pipeline_fixed", "z1_infusion_pump_fixed"):
        r = gate_real(baseline_of(name), name)
        assert r.verdict == G.PASS, (name, r.reasons)
        assert not r.new_kinds and not r.regressions
        assert all(m.status == G.SAME for m in r.metrics), [(m.key, m.reason) for m in r.metrics]


def test_a_buggy_build_fails_a_fixed_baseline():
    r = gate_real(baseline_of("z2_brake_by_wire_fixed"), "z2_brake_by_wire")
    assert r.verdict == G.REGRESSION
    assert r.new_kinds == ["deadline_miss", "priority_inversion"]
    m = next(m for m in r.metrics if m.key == "brake")
    assert m.status == G.WORSE and m.over_budget
    assert m.base_p99_ms < 0.5 < 5.0 < m.new_p99_ms and m.delta_pct > 1000
    assert "over the 2.00 ms budget" in m.reason


def test_a_fixed_build_passes_a_buggy_baseline():
    """The reference fix is faster than the bug, so the gate lets it through and says so."""
    r = gate_real(baseline_of("z2_brake_by_wire"), "z2_brake_by_wire_fixed")
    assert r.verdict == G.PASS, r.reasons
    assert r.gone_kinds == ["deadline_miss", "priority_inversion"]
    m = next(m for m in r.metrics if m.key == "brake")
    assert m.status == G.BETTER and m.delta_pct < -90
    # The *baseline* was over budget; that is not this build's regression.
    assert not m.over_budget


def test_a_new_finding_kind_fails_the_gate_with_no_deadline_at_all():
    """Z3 and Z5 declare no deadline: the only regression signal is a rule finding appearing."""
    for fixed, buggy, kind in (("z3_sensor_fusion_fixed", "z3_sensor_fusion", "ipc_deadlock"),
                               ("z5_motor_encoder_fixed", "z5_motor_encoder", "irq_latency")):
        base = baseline_of(fixed)
        assert not base["metrics"]  # nothing to time here
        r = gate_real(base, buggy)
        assert r.verdict == G.REGRESSION and kind in r.new_kinds
        assert any(kind in x for x in r.reasons)
        # ...and the same build against itself passes, saying the gate only checked kinds.
        ok = gate_real(base, fixed)
        assert ok.verdict == G.PASS and any("finding kinds only" in w for w in ok.warnings)


def test_every_job_stream_gets_its_own_baseline_and_verdict():
    """Z4 runs four tile workers under one `frame` deadline; one slow worker must be visible."""
    base = baseline_of("z4_camera_pipeline_fixed")
    assert set(base["metrics"]) == {"frame", "frame@worker1", "frame@worker2", "frame@worker3",
                                    "frame@worker4"}
    assert base["metrics"]["frame@worker2"]["stream"] == "worker2"
    assert base["metrics"]["frame"]["stream"] is None
    r = gate_real(base, "z4_camera_pipeline")
    assert r.verdict == G.REGRESSION
    assert {m.key for m in r.regressions} == set(base["metrics"])
    # One line per deadline, not one per stream: the four workers are a count on the pooled reason.
    deadline_reasons = [x for x in r.reasons if x.startswith("deadline ")]
    assert len(deadline_reasons) == 1 and "4 of its job streams regressed too" in deadline_reasons[0]


def test_one_capture_each_side_says_so_instead_of_inventing_a_p_value():
    r = gate_real(baseline_of("z2_brake_by_wire_fixed"), "z2_brake_by_wire")
    assert not r.statistical
    assert r.false_alarm_bound == 0.5  # P(a fresh draw beats the worst of 1) = 1/2
    assert all(m.p_value is None for m in r.metrics)
    assert any("50% of the time by chance" in w for w in r.warnings)
    assert r.to_dict()["evidence"].startswith("threshold")


def test_strict_withholds_a_verdict_rather_than_guessing():
    for name in ("z2_brake_by_wire", "z2_brake_by_wire_fixed"):  # regression and clean alike
        r = gate_real(baseline_of("z2_brake_by_wire_fixed"), name, strict=True)
        assert r.verdict == INCONCLUSIVE
        assert any(x.startswith("--strict") for x in r.reasons)


# --------------------------------------------------------------------- integrity: never pass quietly


def test_a_lossy_capture_is_excluded_counted_and_named(tmp_path):
    base = baseline_of("z2_brake_by_wire_fixed")
    bad = G.stats_of(lossy_trace(tmp_path / "lossy.txt"), CFG)
    good = G.stats_of(real("z2_brake_by_wire_fixed"), CFG)
    r = G.gate([good, bad], base, CFG)
    assert r.verdict == G.PASS and r.runs_new == 1 and r.lossy_excluded == 1
    assert r.lossy_traces == ["lossy.txt"] and any("lossy.txt" in w for w in r.warnings)
    # Nothing but lossy captures is never a pass.
    only_bad = G.gate([bad], base, CFG)
    assert only_bad.verdict == INCONCLUSIVE and "all 1 were lossy" in only_bad.reasons[0]
    # ...and under --strict one lossy capture in the set is enough to withhold the verdict.
    assert G.gate([good, bad], base, CFG, strict=True).verdict == INCONCLUSIVE


def test_baseline_save_refuses_when_every_capture_is_lossy(tmp_path):
    doc = G.build_baseline([G.stats_of(lossy_trace(tmp_path / "l.txt"), CFG)], CFG, "x", None)
    assert doc["runs"] == 0 and doc["lossy_excluded"] == 1 and doc["traces"][0]["lossy"]
    with pytest.raises(ValueError, match="no clean captures"):
        G.load_baseline(G.save_baseline(tmp_path / "b.json", doc))


def test_a_deadline_that_vanished_is_inconclusive_not_a_pass():
    """Z1 emits `control`, not `brake`: the question the baseline asks was not answered."""
    r = gate_real(baseline_of("z2_brake_by_wire_fixed"), "z1_infusion_pump_fixed")
    assert r.verdict == INCONCLUSIVE
    m = next(m for m in r.metrics if m.key == "brake")
    assert m.status == G.UNKNOWN and "no jobs for this deadline" in m.reason


def test_moving_the_goalposts_makes_the_metric_inconclusive():
    base = baseline_of("z2_brake_by_wire_fixed")
    tighter = load_config(REAL_TOML)
    tighter.deadlines["brake"].budget_us = 500  # someone tightened the budget after the baseline
    r = G.gate([G.stats_of(real("z2_brake_by_wire_fixed"), tighter)], base, tighter)
    assert r.verdict == INCONCLUSIVE
    m = next(m for m in r.metrics if m.key == "brake")
    assert m.status == G.UNKNOWN and "budget 2000 -> 500 us" in m.reason


def test_changed_thresholds_and_fail_on_are_warned_about():
    base = baseline_of("z2_brake_by_wire_fixed")
    cfg = load_config(REAL_TOML)
    cfg.fail_on = "medium"
    cfg.thresholds.inversion_min_block_us = 10
    r = G.gate([G.stats_of(real("z2_brake_by_wire_fixed"), cfg)], base, cfg)
    assert any("fail_on changed" in w for w in r.warnings)
    assert any("inversion_min_block_us" in w for w in r.warnings)


def test_a_foreign_json_file_is_rejected(tmp_path):
    p = tmp_path / "not-a-baseline.json"
    p.write_text('{"schema": "something/else", "runs": 3}', encoding="utf-8")
    with pytest.raises(ValueError, match="not a TraceLens baseline"):
        G.load_baseline(p)


def test_the_baseline_file_is_small_readable_and_carries_its_provenance(tmp_path):
    doc = baseline_of("z4_camera_pipeline_fixed")
    path = G.save_baseline(tmp_path / "frame.json", doc)
    text = path.read_text(encoding="utf-8")
    assert len(text) < 8000 and text.endswith("\n")  # a file a reviewer can read in a pull request
    again = G.load_baseline(path)
    assert again == json.loads(text) == doc
    assert doc["tool_version"] and doc["created"].endswith("Z")
    assert doc["traces"][0]["name"] == "z4_camera_pipeline_fixed.txt.gz"
    assert len(doc["traces"][0]["sha256"]) == 64
    assert doc["config"]["deadlines"]["frame"] == {"budget_us": 4000, "period_us": 10000}
    assert doc["config"]["thresholds"]["irq_max_latency_us"] == 1000
    assert doc["config"]["sha256"] == G._sha256(REAL_TOML)
    # one short array per statistic, in capture order, so a diff shows which capture moved
    m = doc["metrics"]["frame"]
    assert len(m["p99_ms"]) == len(m["p50_ms"]) == len(m["max_ms"]) == len(m["jobs_per_run"]) == doc["runs"]


# --------------------------------------------------------------------- simulated: the statistical path


@pytest.fixture(scope="module")
def sim_cfg(tmp_path_factory):
    p = tmp_path_factory.mktemp("simcfg") / "tracelens.toml"
    p.write_text(SIM_TOML, encoding="utf-8")
    return load_config(p)


@pytest.fixture(scope="module")
def sim(tmp_path_factory, sim_cfg):
    """Captures of a `healthy_periodic` build whose high-priority job does ``work_us`` of work."""
    out = tmp_path_factory.mktemp("sim")
    cache: dict[tuple[int, int], G.CaptureStats] = {}

    def runs(work_us: int, seeds) -> list[G.CaptureStats]:
        got = []
        for s in seeds:
            if (work_us, s) not in cache:
                p = write_trace(out / f"w{work_us}_s{s}.txt", simulate("healthy_periodic",
                                                                       {"work_us": work_us}, seed=s))
                cache[(work_us, s)] = G.stats_of(p, sim_cfg)
            got.append(cache[(work_us, s)])
        return got

    return runs


def sim_gate(sim, sim_cfg, base_work: int, new_work: int, **kw) -> G.GateResult:
    doc = G.build_baseline(sim(base_work, range(1, 6)), sim_cfg, "hi")
    return G.gate(sim(new_work, range(11, 16)), doc, sim_cfg, **kw)


def test_five_captures_a_side_gives_a_real_p_value(sim, sim_cfg):
    r = sim_gate(sim, sim_cfg, 300, 300)
    assert r.verdict == G.PASS and r.statistical and r.false_alarm_bound is None
    m = r.metrics[0]
    assert m.runs_base == m.runs_new == 5 and m.jobs_base > 500
    assert m.status == G.SAME and m.p_value > 0.05 and "no significant change" in m.reason


def test_a_slower_build_is_caught_with_the_smallest_p_value_5v5_can_give(sim, sim_cfg):
    r = sim_gate(sim, sim_cfg, 300, 1500)
    assert r.verdict == G.REGRESSION
    m = r.metrics[0]
    assert m.status == G.WORSE
    assert m.p_value == pytest.approx(1 / 252, rel=1e-3)  # complete separation of 5 against 5
    assert m.p_adjusted == pytest.approx(m.p_value)  # one metric tested: nothing to correct for
    assert "Mann-Whitney U p=0.00397" in m.reason and "over 5+5 runs" in m.reason
    assert m.delta_pct > 300 and not m.over_budget  # 1.5 ms is still inside the 2.5 ms budget


def test_a_faster_build_passes_and_is_reported_as_faster(sim, sim_cfg):
    r = sim_gate(sim, sim_cfg, 1500, 300)
    assert r.verdict == G.PASS and r.metrics[0].status == G.BETTER
    assert "faster" in r.metrics[0].reason


def test_a_statistically_real_but_tiny_slowdown_does_not_block_a_release(sim, sim_cfg):
    """+13% but +40 us: significant, and nobody should fail a build over it."""
    r = sim_gate(sim, sim_cfg, 300, 340)
    m = r.metrics[0]
    assert r.verdict == G.PASS and m.status == G.SAME
    assert m.p_adjusted < 0.05 and "less than the floors" in m.reason
    # ...and with the floors turned off, hard real-time gets the strict answer it asked for.
    strict = sim_gate(sim, sim_cfg, 300, 340, min_regression_pct=0, min_regression_us=0)
    assert strict.verdict == G.REGRESSION and strict.metrics[0].status == G.WORSE


def test_a_slowdown_past_both_floors_blocks_the_release(sim, sim_cfg):
    r = sim_gate(sim, sim_cfg, 300, 400)  # +33%, +100 us
    assert r.verdict == G.REGRESSION
    assert r.metrics[0].delta_pct > 10 and r.metrics[0].delta_ms * 1000 > 50


def test_too_few_captures_on_one_side_drops_out_of_the_statistical_mode(sim, sim_cfg):
    doc = G.build_baseline(sim(300, range(1, 6)), sim_cfg, "hi")
    r = G.gate(sim(300, [11, 12]), doc, sim_cfg)
    assert not r.statistical and r.false_alarm_bound == pytest.approx(1 / 6)
    assert r.verdict == G.PASS and any("1/6" not in w and "17% of the time" in w for w in r.warnings)


def test_testing_more_deadlines_costs_certainty(sim, sim_cfg):
    """Ten deadlines tested at alpha and one crosses by chance, so the family is Holm-corrected.

    The same captures, gated against one deadline and against three: the evidence for `hi` has not
    changed, but asking three questions of it makes the answer three times less certain.
    """
    from tracelens.config import Deadline
    cfg = load_config(None)
    for name in ("hi", "mid", "lo"):  # healthy_periodic emits a job stream per thread
        cfg.deadlines[name] = Deadline(budget_us=25_000)
    base = [G.stats_of(c.path, cfg) for c in sim(300, range(1, 6))]
    new = [G.stats_of(c.path, cfg) for c in sim(1500, range(11, 16))]
    r = G.gate(new, G.build_baseline(base, cfg, "all"), cfg)
    assert {m.key for m in r.metrics} == {"hi", "mid", "lo"}
    # A slower high-priority job delays the other two as well, so all three really are worse.
    assert all(m.status == G.WORSE for m in r.metrics)
    raw = sorted(m.p_value for m in r.metrics)
    assert all(m.p_adjusted == pytest.approx(3 * raw[0]) for m in r.metrics)  # the Holm ladder, with ties
    assert all(m.p_adjusted < 0.05 for m in r.metrics)  # still decisive after the correction

    alone = sim_gate(sim, sim_cfg, 300, 1500)  # the same `hi` evidence, one deadline declared
    assert alone.metrics[0].p_value == pytest.approx(raw[0])
    assert alone.metrics[0].p_adjusted == pytest.approx(raw[0])
    assert alone.metrics[0].p_adjusted < r.metrics[0].p_adjusted


def test_the_readme_example_still_says_what_the_readme_says(sim, sim_cfg):
    """The worked example in README.md is a real run; if the numbers move, fix one or the other."""
    r = sim_gate(sim, sim_cfg, 300, 450)
    m = r.metrics[0]
    assert r.verdict == G.REGRESSION and r.statistical
    assert (m.base_p99_ms, m.new_p99_ms) == (pytest.approx(0.30, abs=0.005),
                                             pytest.approx(0.45, abs=0.005))
    assert m.delta_pct == pytest.approx(50, abs=1)
    assert m.p_value == m.p_adjusted == pytest.approx(1 / 252, rel=1e-3)
    assert not m.over_budget and not r.new_kinds  # nothing but "slower than last time"


# --------------------------------------------------------------------- the command line


def test_cli_round_trip_and_exit_codes(tmp_path):
    b = str(tmp_path / "brake.json")
    cfg = ["-c", str(REAL_TOML)]
    assert main(["baseline", "save", str(real("z2_brake_by_wire_fixed")), "--name", "brake",
                 "--out", b, *cfg]) == 0
    assert main(["baseline", "show", b]) == 0
    assert main(["gate", str(real("z2_brake_by_wire_fixed")), "--baseline", b, *cfg, "-q"]) == 0
    assert main(["gate", str(real("z2_brake_by_wire")), "--baseline", b, *cfg, "-q"]) == 1
    assert main(["gate", str(real("z2_brake_by_wire")), "--baseline", b, *cfg, "-q", "--strict"]) == 3
    assert main(["gate", str(real("z1_infusion_pump_fixed")), "--baseline", b, *cfg, "-q"]) == 3


def test_cli_writes_json_and_html(tmp_path, capsys):
    b, j, h = (str(tmp_path / n) for n in ("b.json", "gate.json", "gate.html"))
    cfg = ["-c", str(REAL_TOML)]
    main(["baseline", "save", str(real("z4_camera_pipeline_fixed")), "--out", b, *cfg])
    assert main(["gate", str(real("z4_camera_pipeline")), "--baseline", b, *cfg,
                 "--json", j, "--html", h]) == 1

    out = capsys.readouterr().out
    assert "VERDICT: REGRESSION" in out and "frame@worker1" in out and "NEW" in out

    doc = json.loads(Path(j).read_text(encoding="utf-8"))
    assert doc["verdict"] == "REGRESSION"
    assert doc["findings"]["new_kinds"] == ["deadline_miss", "mutex_contention"]
    assert doc["runs"] == {"baseline": 1, "candidate": 1, "lossy_excluded": 0, "lossy_traces": []}
    assert doc["baseline"]["traces"] == ["z4_camera_pipeline_fixed.txt.gz"]
    assert doc["evidence"].startswith("threshold") and doc["false_alarm_bound"] == 0.5
    frame = next(m for m in doc["metrics"] if m["key"] == "frame")
    assert frame["status"] == "worse" and frame["over_budget"] and frame["jobs_new"] == 800

    html = Path(h).read_text(encoding="utf-8")
    assert "REGRESSION" in html and "frame@worker4" in html
    assert "Why this build is blocked" in html and "deadline_miss" in html
    assert html.count("<html") == 1 and html.rstrip().endswith("</html>")


def test_cli_reports_a_clean_gate_in_html(tmp_path):
    b, h = str(tmp_path / "b.json"), str(tmp_path / "ok.html")
    cfg = ["-c", str(REAL_TOML)]
    main(["baseline", "save", str(real("z2_brake_by_wire")), "--out", b, *cfg])
    assert main(["gate", str(real("z2_brake_by_wire_fixed")), "--baseline", b, *cfg, "--html", h, "-q"]) == 0
    html = Path(h).read_text(encoding="utf-8")
    assert "PASS" in html and "No regression" in html and "faster" in html.lower()
