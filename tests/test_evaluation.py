"""Evaluation harness (eval detect / eval fix) with a fake target playing the bug zoo."""

import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from tracelens.config import Config, Deadline
from tracelens.evaluation import eval_detect, eval_fix, load_zoo
from tracelens.testing import scenarios as S

ZOO_TOML = """
[z1_infusion_pump]
expect = ["priority_inversion", "deadline_miss"]
args = ["-d", "2"]

[z3_sensor_fusion]
expect = ["ipc_deadlock"]
args = ["-d", "2"]

[z5_motor_encoder]
expect = ["irq_handler_overrun"]
args = ["-d", "2", "-i", "{irq}"]
needs_irq = true

[negative.idle_system]
command = "sleep 2"
"""

BUGGY = {"z1_infusion_pump": S.z1_prio_inversion, "z3_sensor_fusion": S.z3_ipc_deadlock,
         "z5_motor_encoder": S.z5_irq_overrun}


class FakeTarget:
    def __init__(self, leaky_reference: str | None = None):
        self.calls = []
        self.leaky_reference = leaky_reference

    def __call__(self, label, i, binary, command, args, out, background=None):
        self.calls.append((label, binary, command, tuple(args)))
        name = label.split("-")[0]
        if command is not None or label.endswith("-fixed") and name != self.leaky_reference:
            text = S.z0_clean()
        elif label.endswith("-fixed"):
            text = BUGGY[name]()  # a reference fix that is not actually fixed
        else:
            text = BUGGY[name]()
        p = Path(out) / f"{label}-{i}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p


@pytest.fixture
def zoo(tmp_path):
    z = tmp_path / "bugzoo"
    z.mkdir()
    (z / "zoo.toml").write_text(ZOO_TOML)
    return z


@pytest.fixture
def cfg():
    c = Config()
    for name, d in tomllib.loads(S.DEADLINES_TOML)["deadlines"].items():
        c.deadlines[name] = Deadline(**d)
    return c


def test_real_manifest_parses():
    zoo, neg = load_zoo(Path(__file__).resolve().parents[1] / "bugzoo" / "zoo.toml")
    assert [z.name for z in zoo] == ["z1_infusion_pump", "z2_brake_by_wire", "z3_sensor_fusion",
                                     "z4_camera_pipeline", "z5_motor_encoder"]
    assert next(z for z in zoo if z.name == "z5_motor_encoder").needs_irq and neg


def test_detect_table(zoo, cfg, tmp_path):
    fake = FakeTarget()
    rep = eval_detect(zoo, cfg, fake, tmp_path / "res", runs=5)
    w = {r["name"]: r for r in rep["workloads"]}
    assert w["z1_infusion_pump"]["detected_runs"] == 5 and w["z1_infusion_pump"]["reference_runs_with_findings"] == 0
    assert w["z1_infusion_pump"]["reference_verdict"] == "VERIFIED"
    assert w["z3_sensor_fusion"]["kind_rates"] == {"ipc_deadlock": 1.0}
    assert w["z5_motor_encoder"]["skipped"].startswith("needs --irq")
    assert rep["negatives"][0]["runs_with_findings"] == 0
    md = (tmp_path / "res" / "detect.md").read_text()
    assert "| `z1_infusion_pump` | priority_inversion, deadline_miss | 5/5 | 0/5 | 0 | VERIFIED |" in md
    # buggy binary from out/<name>, reference from out/<name>_fixed, args passed through
    assert ("z1_infusion_pump-buggy", zoo / "out" / "z1_infusion_pump", None, ("-d", "2")) in fake.calls
    assert any(c[1] == zoo / "out" / "z1_infusion_pump_fixed" for c in fake.calls)


def test_detect_reports_a_reference_that_still_has_the_bug(zoo, cfg, tmp_path):
    rep = eval_detect(zoo, cfg, FakeTarget(leaky_reference="z3_sensor_fusion"), tmp_path / "res", runs=5,
                      only=["z3_sensor_fusion"])
    w = rep["workloads"][0]
    assert w["reference_runs_with_findings"] == 5 and w["reference_kinds"] == ["ipc_deadlock"]
    assert w["reference_verdict"] == "NOT FIXED"


def test_irq_is_substituted(zoo, cfg, tmp_path):
    fake = FakeTarget()
    eval_detect(zoo, cfg, fake, tmp_path / "res", runs=5, irq=7, only=["z5_motor_encoder"])
    assert all(c[3] == ("-d", "2", "-i", "7") for c in fake.calls)


def test_fix_table_from_the_engine(zoo, cfg, tmp_path):
    seen_before = []

    def make_engine(workload_dir, out):
        name = Path(workload_dir).name

        def run(before_traces=None):
            seen_before.append((name, tuple(before_traces)))
            if name == "z3_sensor_fusion":
                return SimpleNamespace(status="GUIDED", targets=["ipc_deadlock"], verdict=None, bundle=str(out),
                                       remedies=[{"rule": "ipc-cycle", "automatic": False, "title": "Break the cycle"}])
            return SimpleNamespace(
                status="VERIFIED", targets=["priority_inversion"], bundle=str(out),
                remedies=[{"rule": "semaphore-as-lock", "automatic": True, "title": "sem -> PI mutex"},
                          {"rule": "symptom", "automatic": False, "title": "deadline"}],
                verdict={"targets": {"priority_inversion": {"before_rate": 1.0, "after_rate": 0.0}},
                         "deadlines": [{"name": "control", "before_p99": 5.5e6, "after_p99": 0.6e6,
                                        "budget_ns": 1e6}]})
        return SimpleNamespace(run=run)

    rep = eval_fix(zoo, cfg, make_engine, FakeTarget(), tmp_path / "res", runs=5)
    md = (tmp_path / "res" / "fix.md").read_text()
    assert "| `z1_infusion_pump` | auto: sem -> PI mutex | **VERIFIED** | priority_inversion 100% -> 0% of runs; " \
           "'control' p99 5.50 -> 0.60 ms (budget 1.0) |" in md
    assert "guided: Break the cycle | **GUIDED**" in md
    assert "Automatic remedy for 1 of 2 workloads; **1 of 2 verified on the target**" in md
    assert all(len(b) == 5 for _, b in seen_before) and any(r.get("skipped") for r in rep["rows"])


LOSSY = ("TRACEPRINTER version 1.02\n -- HEADER FILE INFORMATION --\n        CYCLES_PER_SEC:: 1000000000\n"
         " -- KERNEL EVENTS --\nt:0x00000010 CPU:00 THREAD  :THRUNNING pid:1 tid:1\n"
         "t:0x00000020 CPU:01 THREAD  :THRUNNING pid:1 tid:1\nt:0x00000030 CPU:01 THREAD  :THREADY   pid:1 tid:1\n")


def test_a_lossy_run_is_replaced_by_a_fresh_capture(zoo, cfg, tmp_path):
    """Real QNX: 1 of 5 Z3 captures had a dropped event; with 4 clean runs the verdict was INCONCLUSIVE."""
    inner = FakeTarget()

    def flaky(label, i, *a, **kw):
        p = inner(label, i, *a, **kw)
        if label.endswith("-buggy") and i == 2:
            p.write_text(LOSSY, encoding="utf-8")
        return p

    rep = eval_detect(zoo, cfg, flaky, tmp_path / "res", runs=5, only=["z3_sensor_fusion"])
    w = rep["workloads"][0]
    assert w["lossy"] == 1 and w["buggy_clean_runs"] == 5 and w["detected_runs"] == 5
    assert w["reference_verdict"] == "VERIFIED"
    assert sum(1 for c in inner.calls if c[0] == "z3_sensor_fusion-buggy") == 6



def test_bin_dir_selects_another_architectures_build(zoo, cfg, tmp_path):
    """QNX ships mostly on ARM: an aarch64le bug zoo is built beside the x86 one
    (`make -C bugzoo ARCH=aarch64le OUT=out-aarch64le`), and the evaluation must be able to run that
    build without moving binaries around. Default behaviour is unchanged (<zoo>/out)."""
    fake = FakeTarget()
    eval_detect(zoo, cfg, fake, tmp_path / "res", runs=5, bin_dir=zoo / "out-aarch64le")
    assert ("z1_infusion_pump-buggy", zoo / "out-aarch64le" / "z1_infusion_pump", None, ("-d", "2")) in fake.calls
    assert any(c[1] == zoo / "out-aarch64le" / "z1_infusion_pump_fixed" for c in fake.calls)
    # nothing reached for the x86 build; the healthy negatives are shell commands, not binaries
    assert all("out-aarch64le" in str(c[1]) for c in fake.calls if c[1] is not None)
