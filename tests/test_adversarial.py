"""Regression tests for the judge-roast probes (2026-11-13): each one broke the v0 analyzer.

Synthetic traces remain unit tests only; headline accuracy numbers must come from real
QNX captures (PLAN.md §14).
"""

import pytest

from tracelens.analyze import analyze_text
from tracelens.cli import main
from tracelens.config import Config, Deadline
from tracelens.ingest.traceprinter import TraceFormatError, parse_text
from tracelens.model.trace import TraceModel
from tracelens.testing import scenarios as S
from tracelens.testing.synth import TraceBuilder

HDR = "TRACEPRINTER version 1.02\n -- HEADER FILE INFORMATION --\n        CYCLES_PER_SEC:: {cps}\n -- KERNEL EVENTS --\n"


def kinds(a):
    return sorted(f.kind for f in a.findings)


# ----------------------------------------------------------------- priority inversion (SMP)

def test_p1_signal_semaphore_with_medium_on_other_cpu_is_not_inversion():
    """L runs undisturbed on CPU1, M runs on CPU2, H waits on L's signal: correct code."""
    b = TraceBuilder()
    H, L, M = (100, 3), (100, 1), (100, 2)
    b.meta(0, 0, H, "consumer", 50)
    b.meta(0, 1, L, "producer", 10)
    b.meta(0, 2, M, "telemetry", 20)
    b.call(100, 0, "SYNC_SEM_WAIT", sync="0x9000", count=0)
    b.block(100, 0, "SEM")
    b.call(3100, 1, "SYNC_SEM_POST", sync="0x9000")
    b.run(3101, 0, H)
    b.user(3200, 0, "TL_JOB_END name=x")
    a = analyze_text(b.text())
    assert "priority_inversion" not in kinds(a)


def _p2_trace(lock: bool) -> str:
    """L is preempted on its own CPU by M1 while H waits; M2 runs on another CPU meanwhile."""
    b = TraceBuilder()
    H, L, M1, M2 = (100, 3), (100, 1), (100, 2), (100, 4)
    b.meta(0, 0, H, "control", 50)
    b.meta(0, 1, L, "logger", 10)
    b.meta(0, 2, M2, "telemetry2", 20)
    b.set_prio(M1, 20)
    if lock:
        b.call(50, 1, "SYNC_SEM_WAIT", sync="0x9000", count=1)  # L takes the semaphore as a lock
    b.call(100, 0, "SYNC_SEM_WAIT", sync="0x9000", count=0)
    b.block(100, 0, "SEM")
    b.run(100, 1, M1)  # M1 preempts L on CPU1: L READY
    b.user(100, 1, "TL_META name=telemetry1")
    b.block(3000, 1, "NANOSLEEP", next_key=L)
    b.call(3100, 1, "SYNC_SEM_POST", sync="0x9000")
    b.run(3101, 0, H)
    b.user(3200, 0, "TL_JOB_END name=x")
    return b.text()


def test_p2_interference_is_union_on_low_cpus_and_bounded():
    a = analyze_text(_p2_trace(lock=True))
    inv = [f for f in a.findings if f.kind == "priority_inversion"]
    assert len(inv) == 1
    f = inv[0]
    assert 0 < f.metrics["interference_ratio"] <= 1.0
    assert "telemetry1" in f.threads and "telemetry2" not in f.threads  # M2 never held L's CPU
    assert "used as a signal" not in f.title


def test_semaphore_used_as_signal_is_a_different_lower_severity_finding():
    a = analyze_text(_p2_trace(lock=False))
    inv = [f for f in a.findings if f.kind == "priority_inversion"]
    assert len(inv) == 1 and "used as a signal" in inv[0].title
    assert inv[0].severity in ("high", "medium")


def test_priority_comes_from_kernel_events_not_tl_meta():
    """Z1 with every TL_META line removed must still be detected (real programs have no markers)."""
    text = "\n".join(line for line in S.z1_prio_inversion().splitlines() if "TL_META" not in line)
    a = analyze_text(text)
    assert "priority_inversion" in kinds(a)


def test_tl_meta_priority_is_ignored():
    b = TraceBuilder()
    T = (100, 1)
    b.run(0, 0, T)
    b.user(0, 0, "TL_META name=liar prio=99")
    m = TraceModel(parse_text(b.text()))
    assert m.threads[T].name == "liar" and m.threads[T].prio is None


def test_inheritance_boost_in_trace_suppresses_inversion():
    """L is boosted to H's priority for the whole block: inheritance worked, no inversion."""
    b = TraceBuilder()
    H, L, M = (100, 3), (100, 1), (100, 2)
    b.meta(0, 0, L, "logger", 10)
    b.meta(1, 0, M, "telemetry", 20)
    b.meta(2, 0, H, "control", 50)
    b.call(10, 0, "SYNC_MUTEX_LOCK", sync="0x8040", count=0)
    b.set_prio(L, 50)
    b.block(10, 0, "MUTEX", next_key=L)
    b.call(2000, 0, "SYNC_MUTEX_UNLOCK", sync="0x8040")
    b.set_prio(L, 10)
    b.run(2001, 0, H)
    m = TraceModel(parse_text(b.text()))
    assert m.threads[L].prio_range(10_000, 2_000_000) == (50, 50)
    assert "priority_inversion" not in kinds(analyze_text(b.text()))


# ------------------------------------------------------------------- mutex contention

def _clean_mutex_pattern(periods: int) -> str:
    b = TraceBuilder()
    L, M, H = (100, 1), (100, 2), (100, 3)
    b.meta(0, 0, L, "logger", 10)
    b.meta(1, 0, M, "telemetry", 20)
    b.meta(2, 0, H, "control", 50)
    b.state(3, M, "NANOSLEEP")
    b.block(3, 0, "NANOSLEEP", next_key=L)
    for k in range(periods):
        base = 1000 + k * 10_000
        b.run(base + 500, 0, H)
        b.call(base + 505, 0, "SYNC_MUTEX_LOCK", sync="0x8040", count=0)
        b.set_prio(L, 50)
        b.block(base + 505, 0, "MUTEX", next_key=L)
        b.call(base + 700, 0, "SYNC_MUTEX_UNLOCK", sync="0x8040")
        b.set_prio(L, 10)
        b.run(base + 701, 0, H)
        b.block(base + 850, 0, "NANOSLEEP", next_key=M)
        b.block(base + 8850, 0, "NANOSLEEP", next_key=L)
    return b.text()


def test_p4_long_capture_of_clean_pattern_has_no_contention():
    a = analyze_text(_clean_mutex_pattern(200))  # 2 s, not 30 ms
    assert a.findings == [], [f.summary for f in a.findings]


def test_contention_share_is_a_union_not_a_sum():
    a = analyze_text(S.z4_mutex_contention())
    f = next(f for f in a.findings if f.kind == "mutex_contention")
    assert 0 < f.metrics["share_of_trace"] <= 1.0


# ------------------------------------------------------------------------ deadlines

def test_release_jitter_and_skipped_period_are_caught():
    b = TraceBuilder()
    T = (100, 1)
    b.meta(0, 0, T, "control", 50)
    b.block(1, 0, "NANOSLEEP")
    for k in range(10):
        if k == 7:
            continue  # skipped period
        start = 100 + k * 10_000 + (3000 if k == 5 else 0)  # job 5 starts 3 ms late
        b.run(start, 0, T)
        b.user(start, 0, "TL_JOB_START name=control")
        b.user(start + 200, 0, "TL_JOB_END name=control")
        b.block(start + 201, 0, "NANOSLEEP")
    cfg = Config()
    cfg.deadlines["control"] = Deadline(budget_us=1000, period_us=10_000)
    f = next(f for f in analyze_text(b.text(), cfg).findings if f.kind == "deadline_miss")
    assert f.metrics["misses"] == 1 and f.metrics["skipped_periods"] == 1
    assert f.metrics["worst_response_ms"] == pytest.approx(3.2, abs=0.01)


# ---------------------------------------------------------------------------- IRQs

def test_shared_irq_vector_measures_every_handler():
    b = TraceBuilder()
    A, B = (500, 1), (600, 1)
    b.meta(0, 0, A, "ist_a", 60)
    b.call(10, 0, "INTERRUPT_ATTACH_EVENT", intr=9)
    b.call(20, 0, "INTERRUPT_WAIT")
    b.block(20, 0, "INTR")
    b.meta(30, 1, B, "ist_b", 60)
    b.call(40, 1, "INTERRUPT_ATTACH_EVENT", intr=9)
    b.call(50, 1, "INTERRUPT_WAIT")
    b.block(50, 1, "INTR")
    for k in range(5):
        t = 1000 + k * 5000
        b.irq(t, 0, 9)
        for cpu, key in ((0, A), (1, B)):
            b.run(t + 30, cpu, key)
            b.ret(t + 31, cpu, "INTERRUPT_WAIT")
            b.call(t + 2031, cpu, "INTERRUPT_UNMASK", intr=9)
            b.call(t + 2040, cpu, "INTERRUPT_WAIT")
            b.block(t + 2040, cpu, "INTR")
    overruns = [f for f in analyze_text(b.text()).findings if f.kind == "irq_handler_overrun"]
    assert sorted(f.threads[0] for f in overruns) == ["ist_a", "ist_b"]


# --------------------------------------------------------------------------- parser

def test_counter_wrap_with_long_gap():
    """1.5 s gap across a 32-bit wrap at 2 GHz (between 2^31 and 2^32 cycles)."""
    t0 = 0xF0000000
    t1 = (t0 + 3_000_000_000) & 0xFFFFFFFF
    text = HDR.format(cps=2_000_000_000) + (
        f"t:0x{t0:08x} CPU:00 THREAD  :THRUNNING pid:1 tid:1\n"
        f"t:0x{t1:08x} CPU:00 THREAD  :THREADY   pid:1 tid:1\n")
    tr = parse_text(text)
    assert [e.t_ns for e in tr.events] == [0, 1_500_000_000]
    assert tr.wraps == 1


def test_out_of_order_cpus_are_sorted_and_never_negative():
    text = HDR.format(cps=1_000_000_000) + (
        "t:0x000003e8 CPU:00 THREAD  :THRUNNING pid:1 tid:1\n"
        "t:0x00001000 CPU:01 THREAD  :THRUNNING pid:2 tid:1\n"
        "t:0x00000800 CPU:00 THREAD  :THREADY   pid:1 tid:1\n"  # earlier than the CPU1 line above
        "t:0x00002000 CPU:01 THREAD  :THREADY   pid:2 tid:1\n")
    tr = parse_text(text)
    assert [e.t_ns for e in tr.events] == sorted(e.t_ns for e in tr.events)
    assert tr.reordered == 1 and tr.issues
    m = TraceModel(tr)
    assert all(iv.duration >= 0 for th in m.threads.values() for iv in th.intervals)
    assert not m.lossy


def test_missing_clock_rate_fails_loudly(tmp_path):
    text = " -- KERNEL EVENTS --\nt:0x00000010 CPU:00 THREAD  :THRUNNING pid:1 tid:1\n"
    with pytest.raises(TraceFormatError):
        parse_text(text)
    assert parse_text(text, cycles_per_sec=2_000_000_000).cycles_per_sec == 2_000_000_000
    p = tmp_path / "nocps.txt"
    p.write_text(text)
    assert main(["analyze", str(p), "-q"]) == 2
    assert main(["analyze", str(p), "-q", "--cycles-per-sec", "1000000000"]) == 0


def test_dropped_event_makes_trace_lossy_and_verdict_inconclusive(tmp_path):
    """Thread 1 shows up RUNNING on CPU1 while still RUNNING on CPU0: an event was dropped."""
    text = HDR.format(cps=1_000_000_000) + (
        "t:0x00000010 CPU:00 THREAD  :THRUNNING pid:1 tid:1\n"
        "t:0x00000020 CPU:01 THREAD  :THRUNNING pid:1 tid:1\n"
        "t:0x00000030 CPU:01 THREAD  :THREADY   pid:1 tid:1\n")
    m = TraceModel(parse_text(text))
    assert m.lossy and "two CPUs" in m.integrity[0]
    p = tmp_path / "lossy.txt"
    p.write_text(text)
    assert main(["analyze", str(p), "-q"]) == 3
    assert main(["analyze", str(p), "-q", "--allow-lossy"]) == 0


def test_bug_zoo_synthetic_traces_are_not_lossy():
    for name, make in S.SCENARIOS.items():
        assert not TraceModel(parse_text(make())).lossy, name
