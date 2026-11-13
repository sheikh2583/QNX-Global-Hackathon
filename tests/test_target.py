"""Capture pipeline and pidin snapshot tests, with a scripted fake target (no QNX needed)."""

import re
import subprocess

import pytest

from tracelens.analyze import analyze_file
from tracelens.cli import main
from tracelens.ingest.pidin import parse_pidin
from tracelens.target import Target, TargetError, capture
from tracelens.target.capture import trace_command
from tracelens.testing import scenarios as S

PIDIN = """\
     pid tid name               prio STATE       Blocked
       1   1 procnto-smp-instr    0f READY
       1   2 procnto-smp-instr  255r RECEIVE     1
     100   1 ./infusion_pump     10r READY
     100   2 ./infusion_pump     20f NANOSLEEP
     100   3 ./infusion_pump     50f NANOSLEEP
"""


def z1_without_priorities() -> str:
    """Z1 as an unmodified program would trace: no TL_META, no prio on THREAD events."""
    text = "\n".join(l for l in S.z1_prio_inversion().splitlines() if "TL_META" not in l)
    return re.sub(r" prio:\d+", "", text) + "\n"


class FakeTarget:
    """Plays ssh/scp: records argv, serves files for scp downloads."""

    def __init__(self, trace_text: str, pidin: str = PIDIN, fail: str | None = None):
        self.calls: list[list[str]] = []
        self.trace_text = trace_text
        self.pidin = pidin
        self.fail = fail

    def __call__(self, argv, timeout):
        self.calls.append(argv)
        joined = " ".join(argv)
        if self.fail and self.fail in joined:
            return subprocess.CompletedProcess(argv, 1, "", "boom")
        if argv[0] == "ssh":
            cmd = argv[-1]
            if cmd == "pidin":
                return subprocess.CompletedProcess(argv, 0, self.pidin, "")
            if cmd.startswith("tracelogger"):
                return subprocess.CompletedProcess(argv, 0, "TRACELENS_RC=0\n", "")
            return subprocess.CompletedProcess(argv, 0, "", "")
        if argv[0] == "scp":
            src, dst = argv[-2], argv[-1]
            if ":" in src and not src.startswith(("/", ".")) and src.split(":")[0].count("@"):
                content = self.trace_text if src.endswith(".txt") else "KEV-BINARY"
                with open(dst, "w", encoding="utf-8") as fh:
                    fh.write(content)
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(argv)


def test_pidin_parser():
    snap = parse_pidin(PIDIN)
    assert snap.prio[(100, 3)] == 50 and snap.policy[(100, 3)] == "f"
    assert snap.prio[(1, 2)] == 255
    assert snap.proc_names[100] == "infusion_pump"
    assert (0, 0) not in snap.prio  # header line skipped


def test_trace_command_runs_workload_inside_capture_window():
    cmd = trace_command("/tmp/tracelens/z1", ["-d", "2"], "/tmp/tracelens/z1.kev", 4)
    assert cmd.startswith("tracelogger -w -s 4 -f /tmp/tracelens/z1.kev")
    assert "/tmp/tracelens/z1 -d 2" in cmd and "wait $TL" in cmd and "TRACELENS_RC=" in cmd


def test_capture_flow_and_analysis_with_snapshot(tmp_path):
    binary = tmp_path / "infusion_pump"
    binary.write_bytes(b"\x7fELF")
    fake = FakeTarget(z1_without_priorities())
    target = Target(host="10.0.2.15", runner=fake)
    res = capture(target, binary, ["-d", "2"], tmp_path / "out", traceprinter="target")

    kinds = [c[0] for c in fake.calls]
    assert kinds.count("scp") == 3  # binary up, .kev down, .txt down
    assert any("StrictHostKeyChecking=no" in c for c in fake.calls)
    assert res.workload_rc == 0 and res.kev.exists() and res.text.exists() and res.snapshot.exists()

    # Without the snapshot the trace has no priorities at all, so no inversion can be found ...
    bare = analyze_file(res.text, snapshot=None)
    assert "priority_inversion" not in [f.kind for f in bare.findings]
    # ... with it (auto-detected next to the trace), the planted bug is found.
    a = analyze_file(res.text)
    assert a.snapshot_path and a.snapshot_path.endswith("infusion_pump.pidin.txt")
    inv = [f for f in a.findings if f.kind == "priority_inversion"]
    assert inv and inv[0].metrics["priority_source"] == "snapshot"


def test_capture_reports_target_failures(tmp_path):
    binary = tmp_path / "w"
    binary.write_bytes(b"x")
    target = Target(host="h", runner=FakeTarget("", fail="scp"))
    with pytest.raises(TargetError):
        capture(target, binary, [], tmp_path / "out")


def test_capture_cli_needs_a_host(tmp_path, monkeypatch):
    monkeypatch.delenv("TRACELENS_TARGET", raising=False)
    assert main(["capture", str(tmp_path / "w")]) == 2
