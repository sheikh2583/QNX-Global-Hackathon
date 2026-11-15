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
