import tomllib

import pytest

from tracelens.analyze import analyze_text
from tracelens.config import Config, Deadline
from tracelens.testing import scenarios as S


@pytest.fixture
def cfg() -> Config:
    data = tomllib.loads(S.DEADLINES_TOML)
    c = Config()
    for name, d in data["deadlines"].items():
        c.deadlines[name] = Deadline(**d)
    return c


def kinds(a):
    return sorted(f.kind for f in a.findings)


def test_z0_clean_baseline_has_no_findings(cfg):
    a = analyze_text(S.z0_clean(), cfg)
    assert a.errors == []
    assert a.findings == [], [f.summary for f in a.findings]


def test_z1_semaphore_priority_inversion(cfg):
    a = analyze_text(S.z1_prio_inversion(), cfg)
    assert kinds(a) == ["deadline_miss", "priority_inversion"]
    inv = next(f for f in a.findings if f.kind == "priority_inversion")
    assert inv.severity == "critical"
    assert inv.metrics["object"] == "semaphore"
    assert inv.metrics["occurrences"] == 3
    assert inv.metrics["high_prio"] == 50 and inv.metrics["low_prio"] == 10
    assert inv.metrics["worst_interference_ms"] == pytest.approx(8.0, abs=0.01)
    assert "telemetry" in inv.threads
    assert "no owner" in inv.qnx_note
    dl = next(f for f in a.findings if f.kind == "deadline_miss")
    assert dl.metrics["misses"] == 3


def test_z2_fixed_priority_channel_inversion(cfg):
    a = analyze_text(S.z2_fixed_prio_channel(), cfg)
    assert kinds(a) == ["deadline_miss", "priority_inversion"]
    inv = next(f for f in a.findings if f.kind == "priority_inversion")
    assert inv.metrics["object"] == "message channel"
    assert inv.threads[:3] == ["brake_ctrl", "arbiter", "diagnostics"]
    assert "_NTO_CHF_FIXED_PRIORITY" in inv.qnx_note


def test_z3_deadlock_broken_by_timeout(cfg):
    a = analyze_text(S.z3_ipc_deadlock(), cfg)
    assert kinds(a) == ["ipc_deadlock"]
    f = a.findings[0]
    assert f.severity == "critical"
    assert f.metrics["processes"] == 2
    assert f.metrics["resolved_by_timeout"] is True
    assert f.metrics["deadlocked_ms"] == pytest.approx(1000, abs=1)
    assert "fusion_a" in f.metrics["cycle"] and "fusion_b" in f.metrics["cycle"]


def test_z3_deadlock_until_end_of_trace(cfg):
    a = analyze_text(S.z3_ipc_deadlock(resolve_after_us=None), cfg)
    assert kinds(a) == ["ipc_deadlock"]
    assert a.findings[0].metrics["resolved_by_timeout"] is False


def test_z4_mutex_contention(cfg):
    a = analyze_text(S.z4_mutex_contention(), cfg)
    assert kinds(a) == ["mutex_contention"]
    f = a.findings[0]
    assert f.metrics["waits"] == 30
    assert f.metrics["waiter_threads"] == 2
    assert f.severity == "high"


def test_z5_irq_handler_overrun(cfg):
    a = analyze_text(S.z5_irq_overrun(), cfg)
    assert kinds(a) == ["irq_handler_overrun"]
    f = a.findings[0]
    assert f.metrics["overruns"] == 10
    assert f.metrics["p99_latency_us"] == pytest.approx(31, abs=1)


def test_every_finding_cites_existing_events(cfg):
    for make in S.SCENARIOS.values():
        a = analyze_text(make(), cfg)
        for f in a.findings:
            assert f.evidence, f.id
            assert all(i in a.model.by_id for i in f.evidence), f.id


def test_isolated_irq_overrun_is_medium_systematic_or_gross_is_high(cfg):
    # Real QNX: the reference encoder handler (p99 81 us) once ran 564 us in 9,686 interrupts.
    one_small = [50] * 199 + [580]
    f = next(f for f in analyze_text(S.z5_irq_overrun(one_small), cfg).findings if f.kind == "irq_handler_overrun")
    assert f.severity == "medium" and f.metrics["overruns"] == 1 and "Isolated" in f.summary
    one_gross = [50] * 199 + [1100]  # > 2x the 500 us budget: a real defect even once
    f = next(f for f in analyze_text(S.z5_irq_overrun(one_gross), cfg).findings if f.kind == "irq_handler_overrun")
    assert f.severity == "high"
    many = [50] * 190 + [600] * 10  # 5% over budget: p99 over budget
    f = next(f for f in analyze_text(S.z5_irq_overrun(many), cfg).findings if f.kind == "irq_handler_overrun")
    assert f.severity == "high"


def test_one_very_late_job_does_not_shift_the_release_grid():
    """Real QNX (Z2 reference): one job started 5.3 ms late in a 10 ms period; rounding numbered it
    into the next period and the grid moved 4.7 ms early, giving 199/200 false misses."""
    from types import SimpleNamespace as N
    from tracelens.detectors.deadline import _releases
    P = 10_000_000
    starts = [1_000_000 + k * P + 30_000 for k in range(200)]
    starts[61] += 5_300_000
    items = [(N(t_ns=t), None) for t in starts]
    rel = _releases(items, P, [])
    late = [st - r for st, r in zip(starts, rel)]
    assert max(late) == late[61] and 5_200_000 < late[61] < 5_400_000
    assert sorted(late)[-2] < 100_000  # everyone else stays on time



def _late_wakeup_trace(during: str) -> str:
    """control (50) wakes every 10 ms; in period 10 its timer fires 3 ms late while ``during``
    ('low': logger, prio 10; 'high': watchdog, prio 60) holds CPU 0."""
    from tracelens.testing.synth import TraceBuilder
    b = TraceBuilder(name="late.kev")
    L, H, W = (100, 1), (100, 3), (100, 4)
    b.proc(0, 100, "pump")
    b.meta(0, 0, W, "watchdog", 60)
    b.block(0, 0, "NANOSLEEP")
    b.meta(1, 0, L, "logger", 10)
    b.meta(2, 0, H, "control", 50)
    b.block(3, 0, "NANOSLEEP", next_key=L)
    for k in range(20):
        base = 1000 + k * 10_000
        wake = base + 30
        if k == 10:
            if during == "high":
                b.run(base, 0, W)
            wake = base + 3000
        b.run(wake, 0, H)
        b.user(wake + 2, 0, "TL_JOB_START name=control")
        b.user(wake + 100, 0, "TL_JOB_END name=control")
        b.block(wake + 110, 0, "NANOSLEEP", next_key=L)
    return b.text()


def test_late_wakeup_while_only_lower_priority_ran_is_platform_latency(cfg):
    """Real QNX/QEMU (Z2 reference): a prio-60 job woke 5.3 ms late while a prio-30 thread ran;
    a lower-priority thread cannot delay a timer wake-up, so it is the platform, not the program."""
    f = next(f for f in analyze_text(_late_wakeup_trace("low"), cfg).findings if f.kind == "deadline_miss")
    assert f.severity == "medium" and f.metrics["misses_from_platform_latency"] == 1
    assert "platform timer latency" in f.summary
    f = next(f for f in analyze_text(_late_wakeup_trace("high"), cfg).findings if f.kind == "deadline_miss")
    assert f.severity == "high" and f.metrics["misses_from_platform_latency"] == 0


def _jobs_trace(work_us: list[int]) -> str:
    """control (50) runs one job per 10 ms period, taking work_us[k] of CPU."""
    from tracelens.testing.synth import TraceBuilder
    b = TraceBuilder(name="jobs.kev")
    H = (100, 3)
    b.proc(0, 100, "pump")
    b.meta(0, 0, H, "control", 50)
    b.block(1, 0, "NANOSLEEP")
    for k, w in enumerate(work_us):
        base = 1000 + k * 10_000
        b.run(base + 20, 0, H)
        b.user(base + 21, 0, "TL_JOB_START name=control")
        b.user(base + 21 + w, 0, "TL_JOB_END name=control")
        b.block(base + 25 + w, 0, "NANOSLEEP")
    return b.text()


def test_rare_small_deadline_overshoot_is_marginal_unless_hard_real_time(cfg):
    """Real QNX: a reference build missed 4 ms by 94 us in 1 of 800 jobs."""
    def miss(work, c=cfg):
        return next(f for f in analyze_text(_jobs_trace(work), c).findings if f.kind == "deadline_miss")
    f = miss([100] * 199 + [1100])  # 1 of 200, 10% over budget
    assert f.severity == "medium" and "marginal" in f.summary
    assert miss([100] * 199 + [1500]).severity == "high"  # 50% over: not marginal
    assert miss([100] * 196 + [1100] * 4).severity == "high"  # 2% of jobs: a pattern
    cfg.thresholds.deadline_marginal_rate = 0  # hard real-time: every miss counts
    assert miss([100] * 199 + [1100]).severity == "high"


def _mutex_trace(waits_us: list[int]) -> str:
    """holder (10) and waiter (40) share mutex 0x8040; the waiter blocks waits_us[k] in period k."""
    from tracelens.testing.synth import TraceBuilder
    b = TraceBuilder(name="mutex.kev")
    L, H = (100, 1), (100, 3)
    b.proc(0, 100, "app")
    b.meta(0, 0, L, "holder", 10)
    b.meta(1, 0, H, "waiter", 40)
    b.block(2, 0, "NANOSLEEP", next_key=L)
    for k, w in enumerate(waits_us):
        base = 1000 + k * 100_000
        b.run(base, 0, H)
        b.call(base + 1, 0, "SYNC_MUTEX_LOCK", sync="0x00008040", count=0)
        b.block(base + 1, 0, "MUTEX", next_key=L)
        b.call(base + 1 + w, 0, "SYNC_MUTEX_UNLOCK", sync="0x00008040")
        b.run(base + 2 + w, 0, H)
        b.block(base + 10 + w, 0, "NANOSLEEP", next_key=L)
    return b.text()


def test_one_long_mutex_wait_is_not_a_hotspot(cfg):
    """Real QNX: io-sock's allocator lock, 7 waits, one of 2.5 ms, was HIGH in a healthy pidin loop."""
    def cont(waits):
        return next(f for f in analyze_text(_mutex_trace(waits), cfg).findings if f.kind == "mutex_contention")
    assert cont([40] * 6 + [2500]).severity == "medium"
    assert cont([40] * 4 + [2500] * 3).severity == "high"  # three long waits: a pattern
