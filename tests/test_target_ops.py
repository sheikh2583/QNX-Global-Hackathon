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
            # Real QNX 8.0 QEMU output (captured 2026-11-14 from a mkqnximage VM).
            "uname -a": cp(out="QNX tracelens 8.0.0 2026/10/30-09:10:05EDT x86pc x86_64\n"),
            "pidin info": cp(out="CPU:X86_64 Release:8.0.0  FreeMem:1861MB/2047MB BootTime:Nov 14 06:05:10 UTC 2026\n"
                                 "Processes: 22, Threads: 143\n"
                                 + "".join(f"Processor{i}: 721582 Intel 686 F6M183S1 2419MHz FPU \n"
                                           for i in range(1, 5))),
            "ls /proc/boot": cp(out="procnto-smp-instr\nlibc.so.6\n"),
            "command -v tracelogger": cp(out="/system/bin/tracelogger\n"),
            "command -v pidin": cp(out="/proc/boot/pidin\n"),
            "command -v traceprinter": cp(1, ""),
            "rm -f /tmp/tl_check.kev": cp(out="120611\n"),
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
    assert checks["os"].status == PASS and checks["cpus"].detail == "4 CPUs"
    assert checks["instrumented kernel"].status == PASS
    assert checks["tracelogger"].status == PASS and checks["traceprinter"].status == WARN
    assert checks["trace capture"].status == PASS and "120611" in checks["trace capture"].detail
    assert summary_status(list(checks.values())) == WARN  # traceprinter decodes on the host instead


def test_preflight_fails_fast_without_ssh_and_on_empty_trace():
    down = preflight(Target("10.0.2.15", runner=FakeQnx(**{"uname -a": cp(255, "", "Connection refused")})))
    assert [c.name for c in down] == ["ssh"] and down[0].status == FAIL and "tracelens target up" in down[0].hint
    empty = {c.name: c for c in preflight(Target("h", runner=FakeQnx(**{"rm -f /tmp/tl_check.kev": cp(out="")})))}
    assert empty["trace capture"].status == FAIL


def test_qemu_up_waits_for_a_dhcp_lease(tmp_path):
    """Mirrors the verified flow: mkqnximage --run=-h, then the IP from libvirt's lease file by MAC."""
    (tmp_path / "output").mkdir()
    leases = tmp_path / "virbr0.status"
    leases.write_text("[]")
    polls = []

    def run(argv, cwd, timeout):
        assert argv == ["mkqnximage", "--run=-h", "--noprompt"]
        return cp(0, "QEMU Command: qemu-system-x86_64 ... -device virtio-net-pci,netdev=net0,mac=52:54:00:94:22:ff")

    def sleep(s):
        polls.append(s)
        if len(polls) == 2:
            leases.write_text('[{"ip-address": "10.9.9.9", "mac-address": "52:54:00:00:00:01", "expiry-time": 9},'
                              ' {"ip-address": "192.168.122.238", "mac-address": "52:54:00:94:22:ff", "expiry-time": 5}]')

    q = QemuImage(str(tmp_path), run=run, sleep=sleep, leases_path=str(leases))
    assert q.up(timeout=30, poll=3) == "192.168.122.238"  # our MAC, not the other VM's newer lease
    assert any("192.168.122.238" in line for line in q.log)


def test_qemu_up_explains_the_known_setup_problems(tmp_path):
    (tmp_path / "output").mkdir()
    q = QemuImage(str(tmp_path), run=lambda a, c, t: cp(0), sleep=lambda s: None,
                  leases_path=str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="virsh net-start default"):
        q.up()
    (tmp_path / "virbr0.status").write_text("[]")
    q = QemuImage(str(tmp_path), run=lambda a, c, t: cp(0, "/usr/lib/qemu/qemu-bridge-helper not setuid"),
                  sleep=lambda s: None, leases_path=str(tmp_path / "virbr0.status"))
    with pytest.raises(RuntimeError, match=r"chmod u\+s"):
        q.up()
    with pytest.raises(RuntimeError, match="no VM image"):
        QemuImage(str(tmp_path / "nothing")).up()
