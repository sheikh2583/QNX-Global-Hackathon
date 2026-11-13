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
