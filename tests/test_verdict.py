"""Multi-run before/after verdict (tracelens compare)."""

import tomllib

import pytest

from tracelens.analyze import analyze_text
from tracelens.cli import main
from tracelens.config import Config, Deadline
from tracelens.testing import scenarios as S
from tracelens.verdict import (INCONCLUSIVE, NOT_FIXED, VERIFIED, RunSummary, clopper_pearson, compare_runs, holm,
                               mann_whitney_greater, mann_whitney_less, residual_rate_upper, runs_needed,
                               summarize)


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


def test_small_samples_get_the_exact_p_value():
    """5 against 5 has only 252 arrangements, so the smallest one-sided p-value is 1/252 = 0.004.

    The normal approximation puts it near 0.002, which would make a 5-run gate look twice as sure
    of itself as the data allows.
    """
    _, p = mann_whitney_greater([10, 11, 12, 13, 14], [1, 2, 3, 4, 5])
    assert p == pytest.approx(1 / 252)
    _, p4 = mann_whitney_greater([5, 6, 7, 8], [1, 2, 3, 4])
    assert p4 == pytest.approx(1 / 70)
    _, p3 = mann_whitney_greater([4, 5, 6], [1, 2, 3])
    assert p3 == pytest.approx(1 / 20)  # 3 runs a side can never reach alpha = 0.05 after correction
    # Ties are handled exactly too: identical samples cannot be told apart in either direction.
    assert mann_whitney_greater([1, 1, 1, 1], [1, 1, 1, 1])[1] == 1.0
    # ...and the two directions agree with each other.
    a, b = [1, 4, 2, 9, 3], [2, 5, 3, 1, 8]
    assert mann_whitney_greater(a, b)[1] == pytest.approx(mann_whitney_less(b, a)[1])


def test_large_samples_fall_back_to_the_normal_approximation():
    """The fix engine pools every job of every run; the approximation is right there and is fast."""
    big_a, big_b = list(range(200)), list(range(100, 300))
    _, p = mann_whitney_less(big_a, big_b)
    assert 0 < p < 1e-10
    assert mann_whitney_less(list(range(40)), list(range(40)))[1] == pytest.approx(0.5, abs=0.05)


def test_holm_keeps_the_family_wise_error_rate():
    assert holm([0.004]) == [0.004]
    assert holm([0.01, 0.02, 0.03]) == pytest.approx([0.03, 0.04, 0.04])  # x3, x2, x1, kept monotone
    assert holm([0.5, 0.6]) == pytest.approx([1.0, 1.0])  # clamped at 1
    # Order in, order out: the adjusted values line up with the metrics they came from.
    assert holm([0.9, 0.001, 0.5]) == pytest.approx([1.0, 0.003, 1.0])


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


def test_a_bug_that_never_reproduced_cannot_be_verified_fixed(cfg):
    """Found live on QNX: Z3 deadlocked in 0 of 5 'before' runs and its fix was reported VERIFIED."""
    clean = runs(S.z0_clean(), cfg, 5)
    v = compare_runs(clean, runs(S.z0_clean(), cfg, 5), cfg, target_kinds=["ipc_deadlock"])
    assert v.verdict == INCONCLUSIVE and any("reproduced in only 0%" in r for r in v.reasons)
    # 1 of 5 is not enough either; 3 of 5 (the default 60% share) is
    before = runs(S.z3_ipc_deadlock(), cfg, 1) + runs(S.z0_clean(), cfg, 4)
    assert compare_runs(before, clean, cfg, target_kinds=["ipc_deadlock"]).verdict == INCONCLUSIVE
    before = runs(S.z3_ipc_deadlock(), cfg, 3) + runs(S.z0_clean(), cfg, 2)
    assert compare_runs(before, clean, cfg, target_kinds=["ipc_deadlock"]).verdict == VERIFIED


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


# ---- the residual-rate bound (research track R1) ------------------------------------------------

def test_zero_of_n_bound_matches_the_closed_form():
    assert [round(residual_rate_upper(n), 3) for n in (5, 10, 20)] == [0.451, 0.259, 0.139]


def test_bound_with_one_failure_matches_the_tabulated_value():
    # Clopper-Pearson one-sided 95% upper limit for 1 of 10 (standard tables): 0.3942
    assert residual_rate_upper(10, 1) == pytest.approx(0.3942, abs=5e-4)
    # and the two-sided interval for 3 of 10: 0.0667 to 0.6525
    lo, hi = clopper_pearson(3, 10)
    assert (lo, hi) == (pytest.approx(0.0667, abs=5e-4), pytest.approx(0.6525, abs=5e-4))


def test_bound_gets_tighter_with_more_captures_and_looser_with_more_failures():
    bounds = [residual_rate_upper(n) for n in (5, 10, 20, 40)]
    assert bounds == sorted(bounds, reverse=True)
    assert residual_rate_upper(10, 0) < residual_rate_upper(10, 1) < residual_rate_upper(10, 2)
    assert residual_rate_upper(0) == 1.0 and residual_rate_upper(5, 5) == 1.0


def test_runs_needed_for_a_target_rate():
    assert runs_needed(0.1) == 29 and runs_needed(0.2) == 14
    assert residual_rate_upper(runs_needed(0.1)) <= 0.1 < residual_rate_upper(runs_needed(0.1) - 1)


def test_the_verdict_carries_the_bound_without_changing_the_category(cfg):
    before, after = runs(S.z1_prio_inversion(), cfg, 6), runs(S.z0_clean(), cfg, 6)
    v = compare_runs(before, after, cfg, target_kinds=["priority_inversion"])
    assert v.verdict == VERIFIED
    d = v.to_dict()["targets"]["priority_inversion"]
    assert (d["after_k"], d["after_n"], d["before_k"], d["before_n"]) == (0, 6, 6, 6)
    assert d["residual_rate_upper_95"] == pytest.approx(residual_rate_upper(6), abs=1e-4)
    assert any("not seen in 6 of 6 clean after-captures" in n and "at most 39%" in n for n in v.notes)
    assert compare_runs(before, after, cfg, target_kinds=["priority_inversion"], confidence=0.99).verdict == VERIFIED
