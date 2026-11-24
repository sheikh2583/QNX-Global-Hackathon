"""The ML data engine and models: plan, collection, features, radar, tree inference, CLI."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tracelens.analyze import analyze_file
from tracelens.cli import main
from tracelens.config import Config, load_config
from tracelens.ml import dataset
from tracelens.ml.features import FEATURES, windows
from tracelens.ml.model import ensemble_proba, fit_radar, radar_score, save
from tracelens.ml.radar import radar_findings
from tracelens.testing import scenarios as S

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "fixtures" / "real"
CFG = load_config(REAL / "tracelens.toml")


# --------------------------------------------------------------------- plan
def test_plan_is_seeded_and_splits_are_fixed_in_advance():
    a, b = dataset.make_plan(20, seed=3), dataset.make_plan(20, seed=3)
    assert a == b and len(a) == 20 * len(dataset.SCENARIOS)
    for item in a:
        sc = dataset.SCENARIOS[item["scenario"]]
        if not sc.known:
            assert item["split"] == "test_unseen"  # families with no rule never train anything
        elif sc.label != dataset.HEALTHY:
            assert item["split"] == ("test" if item["params"]["period_us"] >= dataset.REGION_B_PERIOD else "train")
        assert item["args"][:2] == ["-s", item["scenario"]]
        assert ("-i" in item["args"]) == sc.needs_irq and bool(item["background"]) == sc.needs_irq
        assert item["params"].get("period_us", 10000) % 1000 == 0  # releases stay tick-aligned
    healthy = [i for i in a if i["label"] == dataset.HEALTHY]
    assert 0 < sum(i["split"] == "test" for i in healthy) < len(healthy) / 2


def test_inversion_variants_hold_the_lock_past_a_tick():
    for item in dataset.make_plan(50, seed=1, scenarios=["sem_inversion", "condvar_inversion"]):
        assert item["params"]["cs_us"] > 1000  # otherwise the planted bug would not trigger


# --------------------------------------------------------------------- collection
def test_collect_is_resumable_and_checks_the_planted_problem(tmp_path):
    plan = [dict(i) for i in dataset.make_plan(1, seed=1, scenarios=["sem_inversion", "healthy_periodic"])]
    calls = []

    def capture(item, out):
        calls.append(item["id"])
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"{item['id']}.txt"
        p.write_text(S.z1_prio_inversion() if item["label"] != dataset.HEALTHY else S.z0_clean(), encoding="utf-8")
        return p

    cfg = Config()
    for name, d in __import__("tomllib").loads(S.DEADLINES_TOML)["deadlines"].items():
        from tracelens.config import Deadline
        cfg.deadlines[name] = Deadline(**d)
    rows = dataset.collect(plan, capture, tmp_path, cfg, log=lambda s: None)
    assert [r["status"] for r in rows] == ["ok", "ok"] and all(r["triggered"] for r in rows)
    dataset.collect(plan, capture, tmp_path, cfg, log=lambda s: None)
    assert len(calls) == 2  # second run skipped everything already collected


# --------------------------------------------------------------------- features
def test_generic_inversion_signal_on_real_qnx_traces():
    for name in ("z1_infusion_pump", "z2_brake_by_wire"):  # semaphore and message-channel inversions
        buggy = max(f["inversion_frac"] for _, _, _, f in windows(analyze_file(REAL / f"{name}.txt.gz", CFG).model))
        fixed = max(f["inversion_frac"] for _, _, _, f in windows(analyze_file(REAL / f"{name}_fixed.txt.gz", CFG).model))
        assert buggy > 0.3 and fixed < 0.05, (name, buggy, fixed)


def test_features_are_bounded_and_complete():
    for _, _, _, f in windows(analyze_file(REAL / "z1_infusion_pump.txt.gz", CFG).model):
        assert set(f) == set(FEATURES)
        assert all(0.0 <= f[k] <= 1.0001 for k in FEATURES if k.startswith("share_"))


# --------------------------------------------------------------------- radar
@pytest.fixture(scope="module")
def radar():
    healthy = []
    for name in ("z1_infusion_pump_fixed", "z2_brake_by_wire_fixed", "z3_sensor_fusion_fixed",
                 "z4_camera_pipeline_fixed", "healthy_shell_io"):
        healthy += [f for _, _, _, f in windows(analyze_file(REAL / f"{name}.txt.gz", CFG).model)]
    return fit_radar(healthy)


def test_radar_trained_on_healthy_flags_unseen_bugs_on_the_right_thread(radar):
    """The first experiment (2026-11-15): trained only on healthy real traces, it flags the buggy
    builds it never saw, on the thread the rules blame."""
    expect = {"z1_infusion_pump": "control", "z2_brake_by_wire": "brake_ctrl", "z4_camera_pipeline": "worker"}
    for name, thread in expect.items():
        fs = radar_findings(analyze_file(REAL / f"{name}.txt.gz", CFG), radar)
        assert fs and any(f.threads[0].startswith(thread) for f in fs), (name, [f.threads for f in fs])
        assert all(f.kind == "unusual_behavior" and f.severity == "medium" and f.metrics["source"] == "radar" for f in fs)


def test_radar_stays_quiet_on_held_out_healthy(radar):
    m = analyze_file(REAL / "healthy_idle_system.txt.gz", CFG).model
    assert not [w for w in windows(m) if radar_score(radar, w[3])[0] > radar["threshold"]]


# --------------------------------------------------------------------- trees
def test_tree_ensemble_inference_is_plain_python():
    i = FEATURES.index("inversion_frac")
    tree = {"nodes": [{"f": i, "t": 0.2, "l": 1, "r": 2}, {"v": [9, 1]}, {"v": [1, 3]}]}
    model = {"classes": ["healthy", "priority_inversion"], "trees": [tree, tree]}
    x = [0.0] * len(FEATURES)
    assert ensemble_proba(model, x) == {"healthy": 0.9, "priority_inversion": 0.1}
    x[i] = 0.5
    assert ensemble_proba(model, x)["priority_inversion"] == 0.75


# --------------------------------------------------------------------- CLI
def test_analyze_with_radar_adds_unusual_behaviour(radar, tmp_path, capsys):
    path = tmp_path / "radar.json"
    save(radar, path)
    rc = main(["analyze", str(REAL / "z1_infusion_pump.txt.gz"), "-c", str(REAL / "tracelens.toml"),
               "--radar", str(path), "--json", str(tmp_path / "out.json")])
    out = json.loads((tmp_path / "out.json").read_text())
    kinds = [f["kind"] for f in out["findings"]]
    assert rc == 1 and "unusual_behavior" in kinds and kinds[0] == "priority_inversion"


def test_data_plan_cli(tmp_path):
    out = tmp_path / "plan.jsonl"
    assert main(["data", "plan", "--per-scenario", "3", "--out", str(out)]) == 0
    assert len(dataset.read_jsonl(out)) == 3 * len(dataset.SCENARIOS)


@pytest.mark.skipif(not sys.platform.startswith("linux") or shutil.which("gcc") is None,
                    reason="host stub check needs Linux gcc")
def test_generator_compiles_against_qnx_stubs():
    b = ROOT / "bugzoo"
    cp = subprocess.run(["gcc", "-fsyntax-only", "-Wall", "-Wextra", "-Werror", "-std=gnu11", "-D_GNU_SOURCE",
                         f"-I{b / 'hostcheck'}", f"-I{b / 'common'}", str(b / "gen" / "tlgen.c")],
                        capture_output=True, text=True)
    assert cp.returncode == 0, cp.stderr


# --------------------------------------------------------------------- the longest-CPU-burst feature
def test_longest_cpu_burst_separates_a_masked_handler_from_a_correct_one():
    """The feature that closed the real Z5 miss: a handler holding its line masked runs in long bursts
    (real Z5 buggy: 2.4 ms) where the same handler fixed runs in short ones (7 us)."""
    from tracelens.ml.features import windows as W
    def burst(name, thread):
        m = analyze_file(REAL / f"{name}.txt.gz", CFG).model
        v = sorted(f["max_run_frac"] for k, _, _, f in W(m) if m.label(k) == thread)
        return v[len(v) // 2]
    buggy, fixed = burst("z5_motor_encoder", "encoder_ist"), burst("z5_motor_encoder_fixed", "encoder_ist")
    assert buggy > 10 * fixed, (buggy, fixed)
    z4 = analyze_file(REAL / "z4_camera_pipeline.txt.gz", CFG).model
    assert all(0.0 <= f["max_run_frac"] <= 1.0 for _, _, _, f in W(z4))


# --------------------------------------------------------------------- retrieval of labelled exemplars
def _rows(scenario, label, role, feature, lo, hi, n=40, split="train"):
    import random as _r
    rng = _r.Random(hash(scenario) % 1000)
    out = []
    for i in range(n):
        f = dict.fromkeys(FEATURES, 0.0)
        f[feature] = rng.uniform(lo, hi)
        out.append({"id": f"{scenario}-{i}", "scenario": scenario, "label": label, "role": role,
                    "split": split, "thread": "t", "f": f})
    return out


@pytest.fixture(scope="module")
def retrieval(radar):
    from tracelens.ml.retrieve import build
    rows = (_rows("healthy_periodic", "healthy", "other", "share_running", 0.0, 0.05)
            + _rows("sem_inversion", "priority_inversion", "victim", "share_sem", 0.5, 0.9)
            + _rows("sem_inversion", "priority_inversion", "culprit", "share_ready", 0.9, 1.0)
            + _rows("mutex_abba", "mutex_abba", "victim", "share_mutex", 0.9, 1.0, split="test_unseen"))
    return build(rows, radar, per_scenario=4)


def test_retrieval_names_the_pattern_a_window_resembles(radar, retrieval):
    from tracelens.ml.retrieve import nearest
    f = dict.fromkeys(FEATURES, 0.0)
    f["share_sem"] = 0.7
    hit = nearest(retrieval, radar, f)
    assert hit["scenario"] == "sem_inversion" and hit["within"] and "semaphore" in hit["text"]


def test_retrieval_never_learns_from_held_out_families_or_culprits(radar, retrieval):
    scenarios = {i["scenario"] for i in retrieval["items"]}
    assert "mutex_abba" not in scenarios  # held out entirely: it may not be in any model
    assert scenarios == {"healthy_periodic", "sem_inversion"}
    # the culprit's windows are not exemplars of the bug: a mutex-heavy window must not match it closely
    from tracelens.ml.retrieve import nearest
    f = dict.fromkeys(FEATURES, 0.0)
    f["share_mutex"] = 0.95
    assert not nearest(retrieval, radar, f)["within"]


def test_radar_findings_report_what_the_behaviour_resembles(radar, retrieval):
    from tracelens.ml.radar import radar_findings
    model = dict(radar, exemplars=retrieval)
    fs = radar_findings(analyze_file(REAL / "z1_infusion_pump.txt.gz", CFG), model)
    assert fs and fs[0].metrics["like"] and "closest pattern" in fs[0].summary


# --------------------------------------------------------------------- the radar as a product addition
def test_annotate_adds_numbered_medium_findings_and_survives_a_bad_model(radar, tmp_path):
    from tracelens.ml.radar import annotate
    a = analyze_file(REAL / "z1_infusion_pump.txt.gz", CFG)
    n_rules = len(a.findings)
    save(radar, tmp_path / "r.json")
    added = annotate(a, tmp_path / "r.json")
    assert added and [f.id for f in added] == [f"TL-{i:03d}" for i in range(n_rules + 1, n_rules + 1 + len(added))]
    assert all(f.severity == "medium" for f in added) and len(a.findings) == n_rules + len(added)
    (tmp_path / "junk.json").write_text("{not json", encoding="utf-8")
    b = analyze_file(REAL / "z1_infusion_pump.txt.gz", CFG)
    assert annotate(b, tmp_path / "junk.json") == [] and b.errors  # reported, not raised
    assert annotate(b, tmp_path / "missing.json") == []


def test_rules_versus_radar_counts_what_the_learned_model_adds(radar):
    """The table the README quotes: of the held-out buggy traces, how many the rules report, how many
    only the radar does, and how often it cries wolf on healthy ones."""
    from tracelens.ml.evaluate import rules_vs_radar, rules_vs_radar_markdown
    hot = dict.fromkeys(FEATURES, 9.0)  # far from healthy in every feature
    calm = dict.fromkeys(FEATURES, 0.0)
    rows, manifest = [], {}
    def trace(tid, label, kinds, f):
        manifest[tid] = {"id": tid, "label": label, "rule_kinds": kinds}
        rows.extend({"id": tid, "scenario": "x", "label": label, "split": "test", "thread": "t", "f": f}
                    for _ in range(10))
    trace("a", "priority_inversion", ["priority_inversion"], hot)   # both
    trace("b", "priority_inversion", ["priority_inversion"], calm)  # rules only
    trace("c", "mutex_abba", [], hot)                               # radar only: the point of it
    trace("d", "mutex_abba", [], calm)                              # neither
    trace("e", "healthy", [], calm)                                 # quiet
    c = rules_vs_radar(rows, radar, manifest)
    assert (c["both"], c["rules_only"], c["radar_only"], c["neither"]) == (1, 1, 1, 1)
    assert c["buggy"] == 4 and c["healthy"] == 1 and c["false_alarms"] == 0
    assert "**1**" in rules_vs_radar_markdown(c) and "find 2 of 4" in rules_vs_radar_markdown(c)


def test_lossy_traces_are_featurised_only_on_request(tmp_path):
    """Training must never see a trace the integrity check condemned; a cross-machine comparison must
    be able to, or a machine whose clocks disagree by a few events drops out of the comparison whole."""
    from tracelens.ml.train import features_from_manifest

    (tmp_path / "traces").mkdir()
    rows = []
    for name, lossy in (("clean", False), ("slipped", True)):
        shutil.copy(REAL / "z1_infusion_pump.txt.gz", tmp_path / "traces" / f"{name}.txt.gz")
        rows.append({"id": name, "scenario": "healthy_periodic", "label": dataset.HEALTHY, "split": "train",
                     "status": "ok", "lossy": lossy, "triggered": True, "trace": f"traces/{name}.txt.gz"})
    dataset.write_jsonl(tmp_path / "manifest.jsonl", rows)
    quiet = {"log": lambda s: None, "workers": 1}
    features_from_manifest(tmp_path, tmp_path / "default.jsonl", Config(), **quiet)
    features_from_manifest(tmp_path, tmp_path / "all.jsonl", Config(), include_lossy=True, **quiet)
    default = dataset.read_jsonl(tmp_path / "default.jsonl")
    everything = dataset.read_jsonl(tmp_path / "all.jsonl")
    assert {r["id"] for r in default} == {"clean"} and not any(r["lossy"] for r in default)
    assert {r["id"] for r in everything} == {"clean", "slipped"}
    assert {r["id"]: r["lossy"] for r in everything} == {"clean": False, "slipped": True}


def test_the_interrupt_number_is_a_plan_parameter():
    """x86's COM1 is interrupt 4; the aarch64 virt machine's UART is 33, and attaching to 4 there waits
    forever. Only the scenarios that drive an interrupt carry -i, and the default is unchanged."""
    default = {i["scenario"]: i["args"] for i in dataset.make_plan(1, seed=1)}
    arm = {i["scenario"]: i["args"] for i in dataset.make_plan(1, seed=1, irq=33)}
    for scenario, spec in dataset.SCENARIOS.items():
        if spec.needs_irq:
            assert default[scenario][default[scenario].index("-i") + 1] == "4"
            assert arm[scenario][arm[scenario].index("-i") + 1] == "33"
        else:
            assert "-i" not in arm[scenario] and arm[scenario] == default[scenario]


def test_the_interrupt_load_is_a_plan_parameter_too():
    default = {i["scenario"]: i["background"] for i in dataset.make_plan(1, seed=1)}
    disk = {i["scenario"]: i["background"] for i in dataset.make_plan(1, seed=1, irq=79, irq_load="DISK-LOOP")}
    for scenario, spec in dataset.SCENARIOS.items():
        if spec.needs_irq:
            assert default[scenario] == dataset.IRQ_BACKGROUND and disk[scenario] == "DISK-LOOP"
        else:
            assert default[scenario] is None and disk[scenario] is None
