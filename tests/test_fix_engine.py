"""The find -> fix -> prove loop with a fake target and builder (no QNX, no network)."""

import tomllib
from pathlib import Path

import pytest

from tracelens.config import Config, Deadline
from tracelens.fix import BuildResult, FixEngine
from tracelens.testing import scenarios as S

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg():
    c = Config()
    for name, d in tomllib.loads(S.DEADLINES_TOML)["deadlines"].items():
        c.deadlines[name] = Deadline(**d)
    return c


class FakeBuilder:
    def __init__(self, ok=True):
        self.ok, self.built = ok, []

    def build(self, sources, include_dirs, out):
        self.built.append([Path(s).read_text(encoding="utf-8") for s in sources])
        out.parent.mkdir(parents=True, exist_ok=True)
        return BuildResult(self.ok, out if self.ok else None, "" if self.ok else "main.c:1: error: boom")


def capturer(before_text, after_text):
    calls = []

    def cap(binary, ws_root, label, i, out):
        calls.append((label, binary))
        p = Path(out) / f"{label}-{i}.txt"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(before_text() if label == "before" else after_text(), encoding="utf-8")
        return p
    cap.calls = calls
    return cap


def engine(name, cfg, tmp_path, cap, builder=None):
    return FixEngine(ROOT / "bugzoo" / name, [ROOT / "bugzoo" / "common"], cfg, builder or FakeBuilder(), cap,
                     tmp_path / "bundle", runs=5)


def test_semaphore_inversion_is_fixed_and_proven(cfg, tmp_path):
    cap = capturer(S.z1_prio_inversion, S.z0_clean)
    b = FakeBuilder()
    res = engine("z1_infusion_pump", cfg, tmp_path, cap, b).run()
    assert res.status == "VERIFIED", res.verdict
    assert [r["rule"] for r in res.remedies if r["automatic"]] == ["semaphore-as-lock"]
    assert "+static pthread_mutex_t buf_lock;" in res.diff
    assert "pthread_mutex_lock(&buf_lock)" in b.built[-1][0]  # the patched copy is what was built
    assert sum(1 for side, _ in cap.calls if side == "after") == 5
    bundle = tmp_path / "bundle"
    assert (bundle / "patch.diff").exists() and (bundle / "verdict.json").exists()
    summary = (bundle / "SUMMARY.md").read_text(encoding="utf-8")
    assert "Status: **VERIFIED**" in summary and "main.c:" in summary
    report = (bundle / "report.html").read_text(encoding="utf-8")
    assert "VERIFIED" in report and "pthread_mutex_lock(&amp;buf_lock)" in report  # the patch, escaped
    assert report.count('<svg class="tl"') == 2  # before and after timelines
    assert "priority inversion: runs with the finding" in report
    # the workload itself was never modified
    assert "sem_wait(&buf_lock)" in (ROOT / "bugzoo" / "z1_infusion_pump" / "main.c").read_text(encoding="utf-8")


def test_a_fix_that_does_not_work_is_reported_not_fixed(cfg, tmp_path):
    res = engine("z1_infusion_pump", cfg, tmp_path, capturer(S.z1_prio_inversion, S.z1_prio_inversion)).run()
    assert res.status == "NOT FIXED"


def test_deadlock_gets_guidance_and_no_rebuild(cfg, tmp_path):
    b = FakeBuilder()
    cap = capturer(S.z3_ipc_deadlock, S.z0_clean)
    res = engine("z3_sensor_fusion", cfg, tmp_path, cap, b).run()
    assert res.status == "GUIDED" and not res.diff and res.verdict is None
    assert len(b.built) == 1  # only the original 'before' build
    assert "MsgSendPulse" in (tmp_path / "bundle" / "SUMMARY.md").read_text(encoding="utf-8")


def test_build_failure_is_reported(cfg, tmp_path):
    class FailSecond(FakeBuilder):
        def build(self, sources, include_dirs, out):
            res = super().build(sources, include_dirs, out)
            return res if len(self.built) == 1 else BuildResult(False, None, "error: boom")

    res = engine("z1_infusion_pump", cfg, tmp_path, capturer(S.z1_prio_inversion, S.z0_clean), FailSecond()).run()
    assert res.status == "BUILD FAILED" and "boom" in res.note


def test_clean_workload_has_nothing_to_fix(cfg, tmp_path):
    res = engine("z1_infusion_pump", cfg, tmp_path, capturer(S.z0_clean, S.z0_clean)).run()
    assert res.status == "NOTHING TO FIX"


def test_second_round_fixes_what_the_first_fix_uncovered(cfg, tmp_path):
    """Real QNX: the PI mutex removed Z1's inversion, then the re-trace showed contention on the
    long critical section; round 2 moves the private work out of the lock."""
    rounds = iter([S.z4_mutex_contention] * 5 + [S.z0_clean] * 5)
    cap = capturer(S.z1_prio_inversion, lambda: next(rounds)())
    b = FakeBuilder()
    res = engine("z1_infusion_pump", cfg, tmp_path, cap, b).run()
    assert res.status == "VERIFIED" and res.rounds == 2, res.verdict
    rules = [(r["round"], r["rule"]) for r in res.remedies if r["automatic"]]
    assert rules == [(1, "semaphore-as-lock"), (2, "shrink-critical-section")]
    final = b.built[-1][0]
    logger = final[final.index("static void *logger"):]
    assert logger.index("pthread_mutex_unlock(&buf_lock)") < logger.index("tl_spin_us(2500)")
    assert (tmp_path / "bundle" / "round-2" / "verdict.json").exists()


def test_every_step_is_reported_for_the_live_view(cfg, tmp_path):
    """events.jsonl (and on_event) carry the whole fix: runs, diagnosis, remedy, build, verdicts."""
    import json
    rounds = iter([S.z4_mutex_contention] * 5 + [S.z0_clean] * 5)
    seen = []
    eng = FixEngine(ROOT / "bugzoo" / "z1_infusion_pump", [ROOT / "bugzoo" / "common"], cfg, FakeBuilder(),
                    capturer(S.z1_prio_inversion, lambda: next(rounds)()), tmp_path / "bundle", runs=5,
                    on_event=seen.append)
    res = eng.run()
    assert res.status == "VERIFIED"
    on_disk = [json.loads(line) for line in (tmp_path / "bundle" / "events.jsonl").read_text().splitlines()]
    assert [e["type"] for e in on_disk] == [e["type"] for e in seen]
    types = [e["type"] for e in seen]
    assert types[0] == "start" and types[-1] == "done" and seen[-1]["status"] == "VERIFIED"
    assert types.count("run") == 15 and types.count("verdict") == 2 and types.count("remedy") == 2
    first = next(e for e in seen if e["type"] == "diagnosis")
    assert first["findings"][0]["name"] == "A high-priority task was held up by lower-priority work"
    assert isinstance(first["radar"], list)  # the learned second opinion, context only, never a target
    remedy = next(e for e in seen if e["type"] == "remedy")
    assert any(loc[0] == "main.c" for r in remedy["remedies"] for loc in r["locations"])
    assert "pthread_mutex_lock(&buf_lock)" in remedy["files"]["main.c"] and remedy["diff"]
    before = [e for e in seen if e["type"] == "run" and e["side"] == "before"]
    assert all(e["kinds"] for e in before) and before[0]["deadlines"]["control"]["late"] > 0


def test_a_broken_viewer_never_breaks_the_fix(cfg, tmp_path):
    def boom(evt):
        raise RuntimeError("viewer gone")
    eng = FixEngine(ROOT / "bugzoo" / "z1_infusion_pump", [ROOT / "bugzoo" / "common"], cfg, FakeBuilder(),
                    capturer(S.z1_prio_inversion, S.z0_clean), tmp_path / "bundle", runs=5, on_event=boom)
    assert eng.run().status == "VERIFIED"
