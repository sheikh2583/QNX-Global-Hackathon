"""research/oracles.py: the five acceptance oracles of the R2 mutation study, on synthetic summaries."""

import importlib.util
import random
import sys
from pathlib import Path

from tracelens.config import Deadline, load_config
from tracelens.verdict import RunSummary

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("oracles", ROOT / "research" / "oracles.py")
oracles = importlib.util.module_from_spec(spec)
sys.modules["oracles"] = oracles
spec.loader.exec_module(oracles)
O = oracles  # noqa: E741

CFG = load_config(None)
CFG.deadlines["hi"] = Deadline(budget_us=2000)
PI = "priority_inversion"


def run(i: int, kinds=(), resp_us=500, lossy=False) -> RunSummary:
    rng = random.Random(i)
    return RunSummary(path=f"r{i}", lossy=lossy, kinds=set(kinds),
                      responses={"hi": [int((resp_us + rng.uniform(-30, 30)) * 1000) for _ in range(100)]})


def batch(n, kinds=(), resp_us=500, rate=None, start=0):
    out = []
    for i in range(n):
        k = kinds if rate is None else (kinds if (i * 7 + start) % 10 < rate * 10 else ())
        out.append(run(start + i, k, resp_us))
    return out


BEFORE = batch(20, {PI}, 5000)


def test_a_good_patch_is_accepted_by_every_oracle_with_enough_captures():
    got = O.judge(BEFORE, batch(20, (), 500, start=100), CFG)
    assert got == dict.fromkeys(O.NAMES, O.ACCEPT)


def test_an_unchanged_build_is_rejected_by_every_oracle():
    got = O.judge(BEFORE, batch(20, {PI}, 5000, start=100), CFG)
    assert got == dict.fromkeys(O.NAMES, O.REJECT)


def test_symptom_masking_fools_only_the_stopwatch():
    """Deadline met, inversion still there: O2 accepts, everything that reads findings rejects."""
    got = O.judge(BEFORE, batch(20, {PI}, 800, start=100), CFG)
    assert got["O2"] == O.ACCEPT
    assert {got[o] for o in ("O1", "O3", "O4", "O4c", "O5")} == {O.REJECT}


def test_five_clean_captures_verify_but_the_bound_asks_for_more():
    got = O.judge(BEFORE, batch(5, (), 500, start=100), CFG)
    assert got["O4"] == O.ACCEPT and got["O5"] == O.UNSURE  # 0 of 5 bounds the rate only to 45%, above the 20% ask
    assert O.judge(BEFORE, batch(14, (), 500, start=100), CFG)["O5"] == O.ACCEPT  # 14 clean captures reach 20%


def test_too_few_captures_make_the_full_oracle_inconclusive_not_wrong():
    got = O.judge(BEFORE, batch(3, (), 500, start=100), CFG)
    assert got["O4"] == O.UNSURE and got["O1"] == O.ACCEPT  # the single-run tester happily accepts


def test_a_rare_bug_is_accepted_by_a_single_run_and_caught_by_the_full_set():
    rare = batch(20, {PI}, 500, rate=0.2, start=100)  # the bug is in 4 of 20 captures
    assert sum(1 for r in rare if r.kinds) == 4
    sw = O.sweep(BEFORE, rare, CFG, ns=(1, 20), draws=300)
    assert sw[1]["O1"][O.ACCEPT] > 0.6 * 300  # most single draws miss it
    assert sw[20]["O3"][O.REJECT] == 300 and sw[20]["O4"][O.ACCEPT] == 0  # the full pool always contains it
    # the false-accept rate of the findings-only tester falls as N grows
    s3 = O.sweep(BEFORE, rare, CFG, ns=(3, 10), draws=400)
    assert s3[3]["O3"][O.ACCEPT] > s3[10]["O3"][O.ACCEPT]


def test_lossy_captures_are_ignored_and_a_declared_deadline_is_required_to_fail_o2():
    after = batch(10, (), 500, start=100) + [run(900, {PI}, 9000, lossy=True)]
    assert O.o1_single_run(BEFORE, after, CFG) == O.ACCEPT and O.o3_findings_only(BEFORE, after, CFG) == O.ACCEPT
    no_deadline = load_config(None)
    assert O.o2_deadline_only(BEFORE, batch(5, {PI}, 9000, start=200), no_deadline) == O.ACCEPT  # vacuous accept


def test_no_target_kind_means_nothing_to_verify_for_the_finding_oracles():
    healthy_before = batch(10, (), 500)
    assert O.o1_single_run(healthy_before, batch(5, (), 500, start=50), CFG) == O.UNSURE
    assert O.o3_findings_only(healthy_before, batch(5, (), 500, start=50), CFG) == O.UNSURE


def test_job_pooled_deadline_test_verifies_a_small_shift_that_capture_level_does_not():
    """The shipped oracle pools every job into one rank test. A 60 us shift on a 200-job-per-capture workload is then
    'significant' (p ~ 0), although 10 captures against 10 cannot tell the two builds apart. Seed 2 is one such pair:
    one before-job misses the budget, so the improvement has to be significant, and only the pooled test says it is."""
    def mk(i, mean):
        r = random.Random(i)
        return RunSummary(f"r{i}", False, set(), {"hi": [int((mean + r.uniform(-60, 60)) * 1000) for _ in range(200)]})
    cfg = load_config(None)
    cfg.deadlines["hi"] = Deadline(budget_us=2600)
    rg = random.Random(2)
    before = [mk(i, 2450 + rg.uniform(-100, 100)) for i in range(10)]
    after = [mk(100 + i, 2390 + rg.uniform(-100, 100)) for i in range(10)]
    assert O.o4_full(before, after, cfg) == O.ACCEPT
    assert O.o4c_full_capture_unit(before, after, cfg) == O.REJECT
    assert O.o4c_full_capture_unit(before, after[:3], cfg) == O.UNSURE  # fewer than 5 clean after-captures


def test_the_committed_mutants_match_the_generator_and_every_bad_mutant_has_a_prediction():
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "research" / "mutants" / "make_mutants.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    import tomllib
    files = sorted((ROOT / "research" / "mutants").glob("*/*/expected.toml"))
    assert len(files) >= 18
    for f in files:
        d = tomllib.loads(f.read_text(encoding="utf-8"))
        assert d["truth"] in ("good", "bad") and set(d["predicted"]) == set(O.NAMES), f
        assert (f.parent / "patch.diff").read_text(encoding="utf-8").startswith("--- a/"), f
    assert {"Z1-ref", "Z4-racy", "Z5-hist"} <= {tomllib.loads(f.read_text(encoding="utf-8"))["id"] for f in files}


def test_run_py_sees_the_e2_freeze_record():
    spec2 = importlib.util.spec_from_file_location("mutrun", ROOT / "research" / "mutants" / "run.py")
    mod = importlib.util.module_from_spec(spec2)
    sys.path.insert(0, str(ROOT / "research" / "mutants"))
    spec2.loader.exec_module(mod)
    assert mod.frozen() is True
