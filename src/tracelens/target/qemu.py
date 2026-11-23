"""Control a QNX QEMU VM built with ``mkqnximage`` (runs on the Linux/WSL host).

    up    ``mkqnximage --run=-h --noprompt``: QEMU daemonizes itself (headless); wait for an IP
    ip    the VM's DHCP lease from libvirt (falls back to ``mkqnximage --getip``)
    down  ``mkqnximage --stop``

Verified on QNX SDP 8.0 + WSL2 Ubuntu 24.04 (2026-11-14):
  * build the VM once:  mkdir ~/qnx-vm && cd ~/qnx-vm && mkqnximage --type=qemu --cpu=4 --ram=2G
        --ssh-ident=$HOME/.ssh/id_ed25519.pub --sshd-pregen=yes --noprompt
    (the default image runs procnto-smp-instr and includes tracelogger, pidin and sshd);
  * networking bridges to libvirt's virbr0, so /usr/lib/qemu/qemu-bridge-helper must be setuid
    root and libvirt's "default" network must be active (it provides DHCP via dnsmasq);
  * ``mkqnximage --getip`` can hang, so the IP is read from libvirt's lease file by MAC instead.
``mkqnximage`` must be on PATH (``source ~/qnx800/qnxsdp-env.sh``).

Another architecture, or a second VM beside a running one, is its own image directory and its own
forwarded port - nothing here is x86-specific:

    mkdir ~/qnx-vm-aarch64 && cd ~/qnx-vm-aarch64
    mkqnximage --type=qemu --arch=aarch64le --cpu=4 --ram=2G --noprompt
               --ssh-ident=$HOME/.ssh/id_ed25519.pub --sshd-pregen=yes
    tracelens target up --user-net --image-dir ~/qnx-vm-aarch64 --ssh-port 2223

An aarch64le image additionally needs the SDP package "QNX SDP 8.0 QEMU Virtualization Drivers
(Startup)" (``com.qnx.qnx800.target.qemuvirt``), which provides ``startup-qemu-virt``; without it
mkqnximage stops at "Host file 'startup-qemu-virt' not available" (see docs/results/aarch64.md).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable

DEFAULT_IMAGE_DIR = "~/qnx-vm"
LEASES = "/var/lib/libvirt/dnsmasq/virbr0.status"
_IP = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_MAC = re.compile(r"mac=([0-9a-fA-F:]{17})")

Run = Callable[[list[str], str, float], subprocess.CompletedProcess]


def _run(argv: list[str], cwd: str, timeout: float = 60) -> subprocess.CompletedProcess:
    with open(os.devnull, "rb") as devnull:
        return subprocess.run(argv, cwd=cwd, stdin=devnull, capture_output=True, text=True, timeout=timeout)


def _spawn(argv: list[str], cwd: str, log_path: Path):
    """Start a long-running command detached (mkqnximage --run keeps QEMU in the foreground)."""
    log = open(log_path, "wb")  # noqa: SIM115  (the child writes to it; closing here breaks the pipe)
    return subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)


def _bridge_has_address(name: str = "virbr0") -> bool:
    """Does the libvirt bridge carry an IPv4 address? libvirt gives the bridge its gateway address
    and starts dnsmasq together when the network starts, so this answers the same question as finding
    the daemon, and it still works where the daemon's process is invisible."""
    try:
        out = subprocess.run(["ip", "-4", "-br", "addr", "show", name], capture_output=True,
                             text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and bool(re.search(r"\b\d+\.\d+\.\d+\.\d+/\d+", out.stdout))


def _dhcp_running() -> bool:
    """Is libvirt's DHCP serving the default network? (After a reboot the lease file survives while
    the DHCP server does not, and a VM then boots without an address.)

    Two ways, because neither works everywhere: the daemon's own command line in /proc, and failing
    that the bridge's address. Under WSL with systemd, a shell started by `wsl.exe` can land outside
    systemd's PID namespace and see none of its processes, so the /proc scan alone reported a healthy
    network as broken (measured 2026-11-16); a stale bridge left by a crashed session has no address,
    which is exactly the state that needs reporting."""
    proc = Path("/proc")
    if not proc.is_dir():
        return True  # not Linux: cannot tell, do not block
    for cmd in proc.glob("[0-9]*/cmdline"):
        try:
            text = cmd.read_bytes().replace(bytes(1), b" ")
        except OSError:
            continue
        if b"dnsmasq" in text and (b"default.conf" in text or b"virbr0" in text):
            return True
    return _bridge_has_address()


_QEMU_CMD = re.compile(r"QEMU Command:\s*(qemu-system-\S+.*)")
_NETDEV = re.compile(r"-netdev\s+\S+\s+-device\s+(\S*virtio-net\S*)")
USER_NET_PORT = 2222


def user_net_argv(logged_command: str, ssh_port: int = USER_NET_PORT) -> list[str]:
    """The same QEMU command, with its bridge swapped for QEMU's own NAT and an ssh forward.

    `-netdev user` needs no bridge, no DHCP server on the host and no root: QEMU answers the guest's
    DHCP itself and forwards one host port to the guest's ssh. On WSL that matters - libvirt's DHCP
    orphaned itself three times in one evening (2026-11-16), each time needing a password to repair,
    which no unattended collection can survive.
    """
    argv, out = shlex.split(logged_command), []
    skip = False
    for token in argv:
        if skip:
            skip = False
            continue
        if token == "-netdev":
            skip = True  # drop its value too
            out += ["-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{ssh_port}-:22"]
            continue
        out.append(token)
    if "-netdev" not in out:  # the logged command had none: add a NIC as well
        # The device name differs by architecture: QEMU's aarch64 `virt` machine has no PCI NIC in
        # mkqnximage's command (it uses virtio-mmio devices), so copy what runimage uses there.
        nic = "virtio-net-device" if "aarch64" in Path(argv[0]).name else "virtio-net-pci"
        out += ["-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{ssh_port}-:22",
                "-device", f"{nic},netdev=net0"]
    return out


def _pid_alive(pid: int) -> bool:
    """Is that process still there? (``os.kill(pid, 0)`` raises only when it is gone or not ours.)"""
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _ssh_open(ip: str, timeout: float = 2.0) -> bool:
    """Is ssh answering? ``ip`` may carry a port, as ``127.0.0.1:2222``."""
    host, _, port = ip.partition(":")
    try:
        with socket.create_connection((host, int(port or 22)), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class QemuImage:
    image_dir: str = DEFAULT_IMAGE_DIR
    run: Run = _run
    sleep: Callable[[float], None] = time.sleep
    leases_path: str = LEASES
    log: list[str] = field(default_factory=list)
    reachable: Callable[[str], bool] = _ssh_open
    spawn: Callable[[list[str], str, Path], object] = _spawn
    dhcp_running: Callable[[], bool] = _dhcp_running
    ssh_port: int = 22  # set to the forwarded port when the VM runs on QEMU's own NAT
    user_net_port: int = USER_NET_PORT  # host port forwarded to the guest's ssh on QEMU's own NAT
    alive: Callable[[int], bool] = staticmethod(_pid_alive)

    @property
    def dir(self) -> str:
        return os.path.expanduser(self.image_dir)

    def mac(self) -> str | None:
        """The VM's MAC, from mkqnximage's run log or its build output."""
        for p in [Path(self.dir) / "tracelens-qemu.log", *sorted((Path(self.dir) / "output").glob("*"))]:
            try:
                if p.is_file() and p.stat().st_size < 5_000_000 and (m := _MAC.search(p.read_text(errors="ignore"))):
                    return m.group(1).lower()
            except OSError:
                continue
        return None

    def lease_ip(self) -> str | None:
        try:
            leases = json.loads(Path(self.leases_path).read_text() or "[]")
        except (OSError, ValueError):
            return None
        mac = self.mac()
        mine = [lease for lease in leases if mac is None or lease.get("mac-address", "").lower() == mac]
        mine.sort(key=lambda lease: lease.get("expiry-time", 0))
        return mine[-1]["ip-address"] if mine else None

    def ip(self) -> str | None:
        ip = self.lease_ip()
        if ip:
            return ip
        try:
            cp = self.run(["mkqnximage", "--getip"], self.dir, 15)
        except FileNotFoundError:
            raise RuntimeError("mkqnximage not found: run `source ~/qnx800/qnxsdp-env.sh` first") from None
        except subprocess.TimeoutExpired:
            return None
        m = _IP.search(cp.stdout or "") if cp.returncode == 0 else None
        return m.group(1) if m else None

    def up(self, timeout: float = 180, poll: float = 3, user_net: bool | None = None) -> str:
        """Start the VM and return the host to reach it on (``ssh_port`` carries the port).

        ``user_net``: None picks it - libvirt's bridge when its DHCP is actually serving, else QEMU's
        own NAT, which needs nothing from the host and no root.
        """
        if not (Path(self.dir) / "output").is_dir():
            raise RuntimeError(f"no VM image in {self.dir}: build one with mkqnximage (see `tracelens target --help`)")
        if user_net is None:
            user_net = not (Path(self.leases_path).exists() and self.dhcp_running())
        if user_net:
            return self._up_user_net(timeout, poll)
        if not Path(self.leases_path).exists():
            raise RuntimeError("libvirt's network is not running (no DHCP): "
                               "sudo virsh net-start default   (if virbr0 is stale: sudo ip link delete virbr0 "
                               "first), or drop the bridge entirely with `tracelens target up --user-net`")
        if not self.dhcp_running():
            raise RuntimeError("libvirt's DHCP server is not running, so the VM would boot without an address. "
                               "Run once: sudo systemctl enable --now libvirtd && sudo virsh net-start default "
                               "&& sudo virsh net-autostart default, or use `tracelens target up --user-net`")
        running = self.lease_ip()
        if running and self.reachable(running):  # never start a second QEMU on the same disk image
            self.log.append(f"target already running at {running}")
            return running
        # mkqnximage --run keeps QEMU in the foreground for as long as the VM runs (verified on SDP 8.0):
        # start it detached, then wait for the VM's lease AND its ssh port (after a reboot the lease
        # file still holds the previous boot's lease, so a lease alone proves nothing).
        log_path = Path(self.dir) / "tracelens-qemu.log"
        try:
            proc = self.spawn(["mkqnximage", "--run=-h", "--noprompt"], self.dir, log_path)
        except FileNotFoundError:
            raise RuntimeError("mkqnximage not found: run `source ~/qnx800/qnxsdp-env.sh` first") from None
        self.log.append(f"started the VM headless (mkqnximage --run=-h); console: {self.dir}/output/qemu.out")
        waited = 0.0
        while waited < timeout:
            out = log_path.read_text(errors="ignore") if log_path.exists() else ""
            if "not setuid" in out:
                raise RuntimeError("QEMU's bridge helper is not setuid: sudo chmod u+s /usr/lib/qemu/qemu-bridge-helper")
            code = proc.poll() if hasattr(proc, "poll") else None
            if code not in (None, 0):
                raise RuntimeError(f"the VM did not start (exit {code}); see {log_path}: {out.strip()[-300:]}")
            ip = self.lease_ip()
            if ip and self.reachable(ip):
                self.log.append(f"target is up at {ip} after {waited:.0f}s")
                return ip
            self.sleep(poll)
            waited += poll
        raise RuntimeError(f"the VM did not answer on ssh after {timeout:.0f}s; see {self.dir}/output/qemu.out")

    def my_pid(self) -> int | None:
        """The pid of the QEMU serving *this* image dir, if it is still alive.

        QEMU writes ``output/qemu.pid`` relative to the directory it was started in (mkqnximage puts
        ``-pidfile output/qemu.pid`` in every command it builds), so the file answers "is the VM on
        this port mine?" - which is what keeps a second image dir from adopting, or killing, the
        first one's VM when both are reached through 127.0.0.1.
        """
        try:
            pid = int((Path(self.dir) / "output" / "qemu.pid").read_text().strip())
        except (OSError, ValueError):
            return None
        return pid if self.alive(pid) else None

    def _up_user_net(self, timeout: float, poll: float) -> str:
        """Run QEMU ourselves on its own NAT, with ssh forwarded to 127.0.0.1."""
        host, log_path = "127.0.0.1", Path(self.dir) / "tracelens-qemu.log"
        self.ssh_port = self.user_net_port
        where = f"{host}:{self.ssh_port}"
        if self.reachable(where):
            # Something answers there. Only reuse it when it is this image dir's own VM: several VMs
            # (another architecture, another session) can be up at once, and taking the wrong one
            # would analyse the wrong target.
            if self.my_pid() is not None:
                self.log.append(f"target already running at {where}")
                return host
            raise RuntimeError(
                f"{where} is already in use by something that is not the VM in {self.dir} "
                f"(no live {self.dir}/output/qemu.pid): give this VM its own port with "
                "`tracelens target up --user-net --ssh-port <port>`")
        logged = _QEMU_CMD.search(log_path.read_text(errors="ignore")) if log_path.exists() else None
        if logged is None:
            raise RuntimeError(
                f"no QEMU command recorded in {log_path}: run `mkqnximage --run=-h --noprompt` once in "
                f"{self.dir} so the command is logged (it prints it before starting QEMU, and it is "
                "logged even if the bridge then refuses), after which this works without any bridge")
        argv = user_net_argv(logged.group(1), self.ssh_port)
        self.log.append(f"starting the VM on QEMU's own network, ssh on {host}:{self.ssh_port} (no bridge, no sudo)")
        proc = self.spawn(argv, self.dir, Path(self.dir) / "tracelens-qemu-usernet.log")
        waited = 0.0
        while waited < timeout:
            code = proc.poll() if hasattr(proc, "poll") else None
            if code not in (None, 0):
                raise RuntimeError(f"the VM did not start (exit {code}); see {self.dir}/tracelens-qemu-usernet.log")
            if self.reachable(where):
                self.log.append(f"VM answering ssh on {where}")
                return host
            time.sleep(poll)
            waited += poll
        raise RuntimeError(f"the VM did not answer on ssh after {timeout:.0f}s; see {self.dir}/output/qemu.out")

    def down(self) -> None:
        cp = self.run(["mkqnximage", "--stop"], self.dir, 60)
        if cp.returncode != 0:
            raise RuntimeError(f"mkqnximage --stop failed: {(cp.stderr or cp.stdout).strip()}")
        self.log.append("stopped")
