"""Multi-run before/after verdict (tracelens compare)."""

import tomllib

import pytest

from tracelens.analyze import analyze_text
from tracelens.cli import main
from tracelens.config import Config, Deadline
from tracelens.testing import scenarios as S
from tracelens.verdict import (INCONCLUSIVE, NOT_FIXED, VERIFIED, RunSummary, compare_runs,
                               mann_whitney_less, summarize)


@pytest.fixture
def cfg() -> Config:
    c = Config()
    for name, d in tomllib.loads(S.DEADLINES_TOML)["deadlines"].items():
        c.deadlines[name] = Deadline(**d)
    return c


def runs(text: str, cfg: Config, n: int) -> list[RunSummary]:
    return [summarize(analyze_text(text, cfg), cfg, f"run{i}") for i in range(n)]


def test_mann_whitney_direction_and_ties():
    _, p_small = mann_whitney_less([1, 2, 3, 4, 5], [10, 11, 12, 13, 14])
    _, p_big = mann_whitney_less([10, 11, 12, 13, 14], [1, 2, 3, 4, 5])
    _, p_same = mann_whitney_less([5] * 6, [5] * 6)
    assert p_small < 0.01 < 0.99 < p_big
    assert p_same == 1.0 or p_same > 0.4


def test_real_fix_is_verified(cfg):
    v = compare_runs(runs(S.z1_prio_inversion(), cfg, 5), runs(S.z0_clean(), cfg, 5), cfg)
    assert v.verdict == VERIFIED, v.reasons
    assert v.targets["priority_inversion"] == (1.0, 0.0)
    d = next(d for d in v.deadlines if d.name == "control")
    assert d.ok and d.before_misses > 0 and d.after_misses == 0 and d.p_value < 0.01


def test_unchanged_bug_is_not_fixed(cfg):
    v = compare_runs(runs(S.z1_prio_inversion(), cfg, 5), runs(S.z1_prio_inversion(), cfg, 5), cfg)
    assert v.verdict == NOT_FIXED
    assert any("still present" in r for r in v.reasons)


def test_new_finding_after_fix_is_a_regression(cfg):
    after = runs(S.z0_clean(), cfg, 5)
    after[2].kinds.add("mutex_contention")
    v = compare_runs(runs(S.z1_prio_inversion(), cfg, 5), after, cfg)
    assert v.verdict == NOT_FIXED and v.new_kinds == ["mutex_contention"]


def test_too_few_clean_runs_is_inconclusive(cfg):
    before = runs(S.z1_prio_inversion(), cfg, 5)
    after = runs(S.z0_clean(), cfg, 5)
    for r in after[:2]:
        r.lossy = True  # dropped events: excluded
    v = compare_runs(before, after, cfg)
    assert v.verdict == INCONCLUSIVE and v.lossy_skipped == 2 and v.runs_after == 3


def test_noise_floor_run_has_nothing_to_verify(cfg):
    v = compare_runs(runs(S.z0_clean(), cfg, 5), runs(S.z0_clean(), cfg, 5), cfg)
    assert v.verdict == INCONCLUSIVE and any("nothing to verify" in r for r in v.reasons)


def test_compare_cli_exit_codes(tmp_path, cfg):
    (tmp_path / "t.toml").write_text(S.DEADLINES_TOML)
    b = tmp_path / "b.txt"
    a = tmp_path / "a.txt"
    b.write_text(S.z1_prio_inversion())
    a.write_text(S.z0_clean())
    conf = str(tmp_path / "t.toml")
    assert main(["compare", "-c", conf, "--before", *[str(b)] * 5, "--after", *[str(a)] * 5]) == 0
    assert main(["compare", "-c", conf, "--before", *[str(b)] * 5, "--after", *[str(b)] * 5]) == 1
    assert main(["compare", "-c", conf, "--before", str(b), "--after", str(a)]) == 3
