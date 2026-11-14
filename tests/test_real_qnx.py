"""Regression tests on REAL QNX 8.0 captures (fixtures/real/), not synthetic traces.

Captured 2026-11-14 with `tracelens capture` on a mkqnximage QEMU x86_64 VM (4 CPUs, KVM,
procnto-smp-instr), decoded by host traceprinter 1.02. Z1 buggy = sem_t used as a lock;
Z1 fixed = the reference fix (PI mutex, short critical section).
"""

from pathlib import Path

import pytest

from tracelens.analyze import analyze_file
from tracelens.config import load_config
from tracelens.findings import at_least
from tracelens.ingest.pidin import load_pidin
from tracelens.ingest.traceprinter import parse_file

REAL = Path(__file__).resolve().parents[1] / "fixtures" / "real"
CFG = load_config(REAL / "tracelens.toml")


@pytest.fixture(scope="module")
def buggy():
    return analyze_file(REAL / "z1_infusion_pump.txt.gz", CFG)


@pytest.fixture(scope="module")
def fixed():
    return analyze_file(REAL / "z1_infusion_pump_fixed.txt.gz", CFG)


def test_real_trace_format_is_fully_understood():
    tr = parse_file(REAL / "z1_infusion_pump.txt.gz")
    assert tr.cycles_per_sec == 2_419_562_295  # TRACE_CYCLES_PER_SEC header
    assert tr.header["TRACE_CPU_NUM"] == "4" and tr.header["TRACE_SYS_RELEASE"] == "8.0.0"
    assert tr.unparsed_lines == 0  # incl. column-0 continuation keys
    assert len(tr.events) > 20_000
    meta = [e.text for e in tr.events if e.cls == "USREVENT" and e.text.startswith("TL_META")]
    assert "TL_META name=control prio=50" in meta  # quoted STR:"..." unwrapped
    sem = next(e for e in tr.events if e.kind == "SYNC_SEM_WAIT")
    assert sem.args["sync"] == sem.args["sync_p"]  # QNX 8.0 sync_p aliased


def test_real_snapshot_and_kernel_names(buggy):
    m = buggy.model
    labels = {m.label(k): th for k, th in m.threads.items()}
    assert {"control", "telemetry", "logger"} <= set(labels)
    assert labels["control"].prio == 50 and labels["telemetry"].prio == 20 and labels["logger"].prio == 10
    snap = load_pidin(REAL / "z1_infusion_pump.pidin.txt")
    assert snap.prio and max(snap.prio.values()) >= 254  # system threads (clock, interrupt) present
    assert not m.lossy


def test_real_buggy_pump_has_semaphore_inversion(buggy):
    inv = [f for f in buggy.findings if f.kind == "priority_inversion"]
    assert len(inv) == 1 and inv[0].severity == "critical"
    f = inv[0]
    assert "via a semaphore" in f.title and "used as a signal" not in f.title
    assert f.threads[:3] == ["control", "logger", "telemetry"]
    # releases one 1 ms tick apart (logger -2 ms, telemetry -1 ms, control 0): every period inverts,
    # control blocked for telemetry's 6 ms minus the 1 ms head start
    assert f.metrics["occurrences"] >= 190 and 4.5 < f.metrics["worst_block_ms"] < 6.5
    assert f.metrics["interference_ratio"] > 0.9 and "telemetry (prio 20)" in f.summary
    dl = next(f for f in buggy.findings if f.kind == "deadline_miss")
    assert dl.metrics["misses"] >= 190 and dl.metrics["worst_blocked_ms"] > 4.5  # misses are the inversion


def test_real_reference_fix_is_clean_for_ci(fixed):
    assert not any(f.kind == "priority_inversion" for f in fixed.findings)
    assert not any(at_least(f.severity, "high") for f in fixed.findings)
    for f in fixed.findings:  # what remains is the measured platform noise floor
        assert f.kind == "deadline_miss" and f.severity == "medium"
        assert f.metrics["misses_from_platform_latency"] == f.metrics["misses"]
        assert "platform timer latency" in f.summary


# ---------------------------------------------------------------- Z2-Z4 (captured the same day)

EXPECTED = {
    # workload: (finding kinds the buggy build must show at >= high, title fragment)
    "z2_brake_by_wire": ({"priority_inversion", "deadline_miss"}, "via a message channel"),
    "z3_sensor_fusion": ({"ipc_deadlock"}, "fusion_a -> fusion_b -> fusion_a"),
    "z4_camera_pipeline": ({"mutex_contention", "deadline_miss"}, "Mutex contention"),
    "z5_motor_encoder": ({"irq_handler_overrun"}, "Interrupt handler overrun on IRQ 4"),
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_buggy_workload_is_caught(name):
    a = analyze_file(REAL / f"{name}.txt.gz", CFG)
    kinds, fragment = EXPECTED[name]
    high = {f.kind for f in a.findings if at_least(f.severity, "high")}
    assert kinds <= high, [f.title for f in a.findings]
    assert any(fragment in f.title for f in a.findings)
    assert a.model.trace.unparsed_lines == 0 and not a.model.lossy


def test_real_kernel_mutex_is_attributed_to_procnto_not_the_program():
    # Z4's reference fix: the only contention left is on a lock inside procnto (proc_pool_thread
    # waiters, kernel address). It is reported for context at LOW and never fails the gate.
    a = analyze_file(REAL / "z4_camera_pipeline_fixed.txt.gz", CFG)
    kernel = [f for f in a.findings if f.kind == "mutex_contention" and f.metrics.get("kernel_space")]
    assert kernel and all(f.severity == "low" and "procnto" in f.title for f in kernel)
    buggy = analyze_file(REAL / "z4_camera_pipeline.txt.gz", CFG)
    user = [f for f in buggy.findings if f.kind == "mutex_contention" and not f.metrics.get("kernel_space")]
    assert user and user[0].severity == "high"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_reference_fix_passes_the_gate(name):
    a = analyze_file(REAL / f"{name}_fixed.txt.gz", CFG)
    assert not any(at_least(f.severity, "high") for f in a.findings), [f.title for f in a.findings]
    assert not a.model.lossy


def test_real_z2_inversion_is_through_the_fixed_priority_channel():
    a = analyze_file(REAL / "z2_brake_by_wire.txt.gz", CFG)
    f = next(f for f in a.findings if f.kind == "priority_inversion")
    assert f.metrics["occurrences"] >= 150 and f.threads[:2] == ["brake_ctrl", "arbiter"]
    assert "_NTO_CHF_FIXED_PRIORITY" in f.qnx_note


def test_real_z3_deadlock_was_broken_by_the_timeout():
    a = analyze_file(REAL / "z3_sensor_fusion.txt.gz", CFG)
    f = next(f for f in a.findings if f.kind == "ipc_deadlock")
    assert f.metrics["resolved_by_timeout"] is True and 900 < f.metrics["deadlocked_ms"] < 1100


def test_real_z5_interrupts_use_qnx8_events():
    """QNX 8.0 reports INTERRUPT :INT_DELIVER intr_id and SYSTEM :IST_ATTACH (not INT_ENTR)."""
    a = analyze_file(REAL / "z5_motor_encoder.txt.gz", CFG)
    m = a.model
    assert len(m.irq_entries) > 1000 and all(e.kind == "INT_DELIVER" for e in m.irq_entries[:50])
    assert len(m.irq_handlers[4]) == 2  # devc-ser8250 shares IRQ 4 with the encoder IST
    f = next(f for f in a.findings if f.kind == "irq_handler_overrun")
    assert 2.0 < f.metrics["max_handler_ms"] < 3.0
    fixed = analyze_file(REAL / "z5_motor_encoder_fixed.txt.gz", CFG)
    assert fixed.findings == []


def test_one_violation_in_a_huge_trace_is_reported_not_fatal():
    """Real Z5 buggy: 1 scheduler violation in ~245k events under heavy interrupt load."""
    m = analyze_file(REAL / "z5_motor_encoder.txt.gz", CFG).model
    assert m.integrity and m.integrity_violations == 1 and len(m.events) > 200_000
    assert not m.lossy


@pytest.mark.parametrize("name", ["pidin_loop", "idle_system", "shell_io"])
def test_real_healthy_system_programs_pass_the_gate(name):
    """Negative corpus: healthy QNX programs traced on the same VM must not fail the gate."""
    a = analyze_file(REAL / f"healthy_{name}.txt.gz", CFG)
    assert not any(at_least(f.severity, "high") for f in a.findings), [f.title for f in a.findings]
    assert a.model.trace.unparsed_lines == 0 and not a.model.lossy
