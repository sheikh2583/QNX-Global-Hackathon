"""QEMU image control and target preflight, against scripted fakes."""

import subprocess

import pytest

from tracelens.target import Target
from tracelens.target.check import FAIL, PASS, WARN, preflight, summary_status
from tracelens.target.qemu import QemuImage


def cp(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


class FakeQnx:
    """Answers the preflight's ssh commands like a healthy QNX 8.0 QEMU guest."""

    def __init__(self, **override):
        self.answers = {
            "uname -a": cp(out="QNX localhost 8.0.0 2025/01/01-00:00:00EST x86pc x86_64\n"),
            "pidin info": cp(out="CPU:X86_64 Release:8.0.0  FreeMem:3.5Gb/4Gb BootTime:...\n"
                                 "Processes: 60, Threads: 250\nProcessors: 8\n"),
            "ls /proc/boot": cp(out="procnto-smp-instr\nlibc.so.6\n"),
            "command -v tracelogger": cp(out="/usr/bin/tracelogger\n"),
            "command -v pidin": cp(out="/bin/pidin\n"),
            "command -v traceprinter": cp(1, ""),
            "rm -f /tmp/tl_check.kev": cp(out="-rw-r--r--  1 root root  482304 Nov 13 21:00 /tmp/tl_check.kev\n"),
        }
        self.answers.update(override)

    def __call__(self, argv, timeout):
        if argv[0] != "ssh":
            raise AssertionError(argv)
        cmd = argv[-1]
        for prefix, answer in self.answers.items():
            if cmd.startswith(prefix):
                return answer
        return cp(1, "", f"unexpected command {cmd}")


def test_preflight_on_a_healthy_target():
    checks = {c.name: c for c in preflight(Target("10.0.2.15", runner=FakeQnx()))}
    assert checks["os"].status == PASS and checks["cpus"].detail == "8 CPUs"
    assert checks["instrumented kernel"].status == PASS
    assert checks["tracelogger"].status == PASS and checks["traceprinter"].status == WARN
    assert checks["trace capture"].status == PASS and "482304" in checks["trace capture"].detail
    assert summary_status(list(checks.values())) == WARN  # traceprinter decodes on the host instead


def test_preflight_fails_fast_without_ssh_and_on_empty_trace():
    down = preflight(Target("10.0.2.15", runner=FakeQnx(**{"uname -a": cp(255, "", "Connection refused")})))
    assert [c.name for c in down] == ["ssh"] and down[0].status == FAIL and "tracelens target up" in down[0].hint
    empty = {c.name: c for c in preflight(Target("h", runner=FakeQnx(**{"rm -f /tmp/tl_check.kev": cp(out="")})))}
    assert empty["trace capture"].status == FAIL


def test_qemu_up_waits_for_an_ip(tmp_path):
    ips = iter([None, None, "inet 192.168.122.57\n"])
    spawned = []

    def run(argv, cwd):
        out = next(ips) if argv[-1] == "--getip" else ""
        return cp(0 if out else 1, out or "")

    q = QemuImage(str(tmp_path), run=run, spawn=lambda argv, cwd, log: spawned.append(argv) or 4242,
                  sleep=lambda s: None)
    assert q.up(timeout=30, poll=3) == "192.168.122.57"
    assert spawned == [["mkqnximage", "--run"]] and any("192.168.122.57" in l for l in q.log)


def test_qemu_up_needs_the_image_folder(tmp_path):
    q = QemuImage(str(tmp_path / "missing"), run=lambda a, c: cp(1), spawn=lambda *a: 0, sleep=lambda s: None)
    with pytest.raises(RuntimeError, match="Quick Start"):
        q.up()
