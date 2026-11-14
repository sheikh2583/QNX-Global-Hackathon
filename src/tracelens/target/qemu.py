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
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

DEFAULT_IMAGE_DIR = "~/qnx-vm"
LEASES = "/var/lib/libvirt/dnsmasq/virbr0.status"
_IP = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_MAC = re.compile(r"mac=([0-9a-fA-F:]{17})")

Run = Callable[[list[str], str, float], subprocess.CompletedProcess]


def _run(argv: list[str], cwd: str, timeout: float = 60) -> subprocess.CompletedProcess:
    with open(os.devnull, "rb") as devnull:
        return subprocess.run(argv, cwd=cwd, stdin=devnull, capture_output=True, text=True, timeout=timeout)


def _ssh_open(ip: str, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((ip, 22), timeout=timeout):
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

    def up(self, timeout: float = 180, poll: float = 3) -> str:
        if not (Path(self.dir) / "output").is_dir():
            raise RuntimeError(f"no VM image in {self.dir}: build one with mkqnximage (see `tracelens target --help`)")
        if not Path(self.leases_path).exists():
            raise RuntimeError("libvirt's network is not running (no DHCP): "
                               "sudo virsh net-start default   (if virbr0 is stale: sudo ip link delete virbr0 first)")
        running = self.lease_ip()
        if running and self.reachable(running):  # never start a second QEMU on the same disk image
            self.log.append(f"target already running at {running}")
            return running
        try:
            cp = self.run(["mkqnximage", "--run=-h", "--noprompt"], self.dir, timeout)
        except FileNotFoundError:
            raise RuntimeError("mkqnximage not found: run `source ~/qnx800/qnxsdp-env.sh` first") from None
        out = (cp.stdout or "") + (cp.stderr or "")
        (Path(self.dir) / "tracelens-qemu.log").write_text(out)
        if "not setuid" in out:
            raise RuntimeError("QEMU's bridge helper is not setuid: sudo chmod u+s /usr/lib/qemu/qemu-bridge-helper")
        self.log.append(f"started the VM headless (mkqnximage --run=-h); console: {self.dir}/output/qemu.out")
        waited = 0.0
        while waited < timeout:
            ip = self.lease_ip()
            if ip:
                self.log.append(f"target is up at {ip} after {waited:.0f}s")
                return ip
            self.sleep(poll)
            waited += poll
        raise RuntimeError(f"no DHCP lease after {timeout:.0f}s; see {self.dir}/output/qemu.out")

    def down(self) -> None:
        cp = self.run(["mkqnximage", "--stop"], self.dir, 60)
        if cp.returncode != 0:
            raise RuntimeError(f"mkqnximage --stop failed: {(cp.stderr or cp.stdout).strip()}")
        self.log.append("stopped")
