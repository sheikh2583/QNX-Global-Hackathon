"""QEMU image control and target preflight, against scripted fakes."""

import subprocess
from types import SimpleNamespace

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

    def spawn(argv, cwd, log_path):  # mkqnximage --run stays in the foreground: started detached
        assert argv == ["mkqnximage", "--run=-h", "--noprompt"]
        log_path.write_text("QEMU Command: qemu-system-x86_64 ... -device virtio-net-pci,netdev=net0,mac=52:54:00:94:22:ff")

    def sleep(s):
        polls.append(s)
        if len(polls) == 2:
            leases.write_text('[{"ip-address": "10.9.9.9", "mac-address": "52:54:00:00:00:01", "expiry-time": 9},'
                              ' {"ip-address": "192.168.122.238", "mac-address": "52:54:00:94:22:ff", "expiry-time": 5}]')

    up_after = iter([False, False, True])  # a stale lease does not count until ssh answers
    q = QemuImage(str(tmp_path), dhcp_running=lambda: True, spawn=spawn, sleep=sleep, leases_path=str(leases),
                  reachable=lambda ip: ip == "192.168.122.238" and next(up_after))
    assert q.up(timeout=30, poll=3) == "192.168.122.238"  # our MAC, not the other VM's newer lease
    assert any("192.168.122.238" in line for line in q.log)


def test_qemu_up_explains_the_known_setup_problems(tmp_path):
    (tmp_path / "output").mkdir()
    q = QemuImage(str(tmp_path), dhcp_running=lambda: True, spawn=lambda a, c, p: None, sleep=lambda s: None,
                  leases_path=str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="virsh net-start default"):
        q.up(user_net=False)
    (tmp_path / "virbr0.status").write_text("[]")
    not_setuid = "/usr/lib/qemu/qemu-bridge-helper not setuid"
    q = QemuImage(str(tmp_path), dhcp_running=lambda: True, spawn=lambda a, c, p: p.write_text(not_setuid),
                  sleep=lambda s: None, leases_path=str(tmp_path / "virbr0.status"))
    with pytest.raises(RuntimeError, match=r"chmod u\+s"):
        q.up(user_net=False)
    with pytest.raises(RuntimeError, match="no VM image"):
        QemuImage(str(tmp_path / "nothing")).up()


def test_qemu_up_reuses_a_running_target(tmp_path):
    """Never start a second QEMU on the same disk: a lease that answers on ssh means it is up."""
    (tmp_path / "output").mkdir()
    (tmp_path / "tracelens-qemu.log").write_text("mac=52:54:00:94:22:ff")
    leases = tmp_path / "virbr0.status"
    leases.write_text('[{"ip-address": "192.168.122.238", "mac-address": "52:54:00:94:22:ff", "expiry-time": 5}]')

    def spawn(argv, cwd, log_path):
        raise AssertionError("must not run mkqnximage again")

    q = QemuImage(str(tmp_path), dhcp_running=lambda: True, spawn=spawn, leases_path=str(leases), reachable=lambda ip: True)
    assert q.up() == "192.168.122.238" and "already running" in q.log[0]


def test_qemu_up_names_a_missing_dhcp_server(tmp_path):
    """After a reboot the lease file survives but libvirt's dnsmasq does not (seen on WSL2). With
    `--bridge` the user asked for libvirt, so say how to repair it; left to itself, `up()` uses QEMU's
    own network instead (the next test)."""
    (tmp_path / "output").mkdir()
    (tmp_path / "virbr0.status").write_text("[]")
    q = QemuImage(str(tmp_path), dhcp_running=lambda: False, leases_path=str(tmp_path / "virbr0.status"),
                  spawn=lambda a, c, p: (_ for _ in ()).throw(AssertionError("must not start the VM")))
    with pytest.raises(RuntimeError, match="virsh net-start default"):
        q.up(user_net=False)



# --------------------------------------------------------------------- QEMU's own network
def test_user_net_swaps_the_bridge_for_a_forwarded_ssh_port():
    from tracelens.target.qemu import user_net_argv
    cmd = ("qemu-system-x86_64 -smp 4 --enable-kvm -m 2G -drive file=output/disk-qemu.vmdk,if=ide,id=drv0 "
           "-netdev bridge,br=virbr0,id=net0 -device virtio-net-pci,netdev=net0,mac=52:54:00:94:22:ff "
           "-nographic -kernel output/ifs.bin")
    argv = user_net_argv(cmd, ssh_port=2222)
    line = " ".join(argv)
    assert "bridge" not in line and "virbr0" not in line
    assert "-netdev user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22" in line
    assert "-device virtio-net-pci,netdev=net0,mac=52:54:00:94:22:ff" in line  # the NIC itself is kept
    assert argv[0] == "qemu-system-x86_64" and "output/ifs.bin" in line


def test_up_falls_back_to_qemus_own_network_when_the_dhcp_server_is_down(tmp_path):
    """libvirt's DHCP orphaned itself three times in one evening and each repair needed a password;
    an unattended collection must not depend on it."""
    (tmp_path / "output").mkdir()
    (tmp_path / "tracelens-qemu.log").write_text(
        "QEMU Command: qemu-system-x86_64 -netdev bridge,br=virbr0,id=net0 -kernel output/ifs.bin\n")
    started = {}

    def spawn(argv, cwd, log):
        started["argv"] = argv
        return SimpleNamespace(poll=lambda: None)

    q = QemuImage(str(tmp_path), dhcp_running=lambda: False, spawn=spawn,
                  reachable=lambda where: where == "127.0.0.1:2222" and "argv" in started)
    assert q.up(timeout=5, poll=0) == "127.0.0.1"
    assert q.ssh_port == 2222
    assert "user,id=net0,hostfwd=tcp:127.0.0.1:2222-:22" in " ".join(started["argv"])


# ------------------------------------------- a second VM: another architecture, another port
def test_a_second_vm_gets_its_own_port_and_keeps_the_aarch64_nic():
    """mkqnximage's own runimage gives the aarch64 `virt` machine virtio-mmio devices, not PCI ones,
    so swapping the bridge must keep whatever device the logged command names - and must add the
    right one when the logged command has no NIC at all (networking disabled at build time)."""
    from tracelens.target.qemu import user_net_argv
    cmd = ("qemu-system-aarch64 -machine virt-4.2 -cpu cortex-a57 -smp 4 -m 2G "
           "-drive file=output/disk-qemu.vmdk,if=none,id=drv0 -device virtio-blk-device,drive=drv0 "
           "-netdev bridge,br=virbr0,id=net0 -device virtio-net-device,netdev=net0,mac=52:54:00:94:22:fe "
           "-kernel output/ifs.bin")
    line = " ".join(user_net_argv(cmd, ssh_port=2223))
    assert "bridge" not in line and "virbr0" not in line
    assert "-netdev user,id=net0,hostfwd=tcp:127.0.0.1:2223-:22" in line
    assert "-device virtio-net-device,netdev=net0,mac=52:54:00:94:22:fe" in line
    assert "-machine virt-4.2 -cpu cortex-a57" in line  # the machine is left exactly as mkqnximage built it

    bare = " ".join(user_net_argv("qemu-system-aarch64 -machine virt-4.2 -kernel output/ifs.bin", 2223))
    assert "-device virtio-net-device,netdev=net0" in bare and "virtio-net-pci" not in bare
    bare_x86 = " ".join(user_net_argv("qemu-system-x86_64 -kernel output/ifs.bin", 2223))
    assert "-device virtio-net-pci,netdev=net0" in bare_x86


def test_up_user_net_honours_its_own_port(tmp_path):
    (tmp_path / "output").mkdir()
    (tmp_path / "tracelens-qemu.log").write_text(
        "QEMU Command: qemu-system-aarch64 -netdev bridge,br=virbr0,id=net0 -kernel output/ifs.bin\n")
    started = {}

    def spawn(argv, cwd, log):
        started["argv"] = argv
        return SimpleNamespace(poll=lambda: None)

    q = QemuImage(str(tmp_path), user_net_port=2223, dhcp_running=lambda: False, spawn=spawn,
                  reachable=lambda where: where == "127.0.0.1:2223" and "argv" in started)
    assert q.up(timeout=5, poll=0) == "127.0.0.1" and q.ssh_port == 2223
    assert "hostfwd=tcp:127.0.0.1:2223-:22" in " ".join(started["argv"])


def test_up_user_net_refuses_a_port_that_belongs_to_another_vm(tmp_path):
    """Two VMs can be up at once (x86 on 2222, aarch64 on 2223). If the port answers but this image
    dir has no live QEMU, the VM there is someone else's: say so instead of analysing the wrong
    target - and never start a second QEMU on this disk image either."""
    (tmp_path / "output").mkdir()
    q = QemuImage(str(tmp_path), dhcp_running=lambda: False, reachable=lambda where: True,
                  spawn=lambda a, c, p: (_ for _ in ()).throw(AssertionError("must not start a VM")))
    with pytest.raises(RuntimeError, match="already in use"):
        q.up()
    # its own live QEMU on that port is reused, not restarted
    (tmp_path / "output" / "qemu.pid").write_text("4242\n")
    q = QemuImage(str(tmp_path), dhcp_running=lambda: False, reachable=lambda where: True,
                  alive=lambda pid: pid == 4242,
                  spawn=lambda a, c, p: (_ for _ in ()).throw(AssertionError("must not start a VM")))
    assert q.up() == "127.0.0.1" and "already running at 127.0.0.1:2222" in q.log[0]


def test_up_user_net_says_how_to_log_the_qemu_command_for_a_fresh_image(tmp_path):
    (tmp_path / "output").mkdir()
    q = QemuImage(str(tmp_path), dhcp_running=lambda: False, reachable=lambda where: False)
    with pytest.raises(RuntimeError, match="mkqnximage --run=-h"):
        q.up()


def test_ssh_open_needs_a_banner_not_just_a_connection():
    """QEMU's port forward accepts TCP before the guest has booted; only an sshd greets with SSH-."""
    import socket
    import threading

    from tracelens.target.qemu import _ssh_open

    def serve(payload, hold=0.0):
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)

        def run():
            conn, _ = srv.accept()
            if payload:
                conn.sendall(payload)
            threading.Event().wait(hold)
            conn.close()
            srv.close()

        threading.Thread(target=run, daemon=True).start()
        return srv.getsockname()[1]

    ssh_banner, http = b"SSH-2.0-OpenSSH_9.9\r\n", b"HTTP/1.1 400\r\n"
    assert _ssh_open(f"127.0.0.1:{serve(ssh_banner)}")
    assert not _ssh_open(f"127.0.0.1:{serve(b'', hold=1.0)}", timeout=0.3)  # forward with nothing behind it
    assert not _ssh_open(f"127.0.0.1:{serve(http)}")
    assert not _ssh_open("127.0.0.1:1")  # refused
