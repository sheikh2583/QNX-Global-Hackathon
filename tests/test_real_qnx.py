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
    assert 7.5 < f.metrics["worst_block_ms"] < 9.0 and f.metrics["interference_ratio"] > 0.9
    assert "telemetry (prio 20)" in f.summary
    dl = next(f for f in buggy.findings if f.kind == "deadline_miss")
    assert dl.metrics["misses"] <= 5 and dl.metrics["worst_blocked_ms"] > 7.5  # misses are the inversion


def test_real_reference_fix_is_clean_for_ci(fixed):
    assert not any(f.kind == "priority_inversion" for f in fixed.findings)
    assert not any(at_least(f.severity, "high") for f in fixed.findings)
    for f in fixed.findings:  # what remains is the measured platform noise floor
        assert f.kind == "deadline_miss" and f.severity == "medium"
        assert f.metrics["misses_from_platform_latency"] == f.metrics["misses"]
        assert "platform timer latency" in f.summary
