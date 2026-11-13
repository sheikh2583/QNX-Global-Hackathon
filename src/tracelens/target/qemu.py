"""Control the QNX Quick Start QEMU image with ``mkqnximage`` (runs on the Linux/WSL host).

    up    start ``mkqnximage --run`` detached (log in <image>/tracelens-qemu.log), wait for an IP
    ip    ``mkqnximage --getip``
    down  ``mkqnximage --stop``

``mkqnximage`` must be on PATH (``source ~/qnx800/qnxsdp-env.sh``). Its flags come
from the QNX Everywhere QEMU guide; running it detached is our own choice **(verify)**.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

DEFAULT_IMAGE_DIR = "~/qnx800/images/qemu/qemu"
_IP = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")

Run = Callable[[list[str], str], subprocess.CompletedProcess]


def _run(argv: list[str], cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60)


def _spawn(argv: list[str], cwd: str, log: Path) -> int:
    with open(log, "ab") as fh:
        proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)
    return proc.pid


@dataclass
class QemuImage:
    image_dir: str = DEFAULT_IMAGE_DIR
    run: Run = _run
    spawn: Callable[[list[str], str, Path], int] = _spawn
    sleep: Callable[[float], None] = time.sleep
    log: list[str] = field(default_factory=list)

    @property
    def dir(self) -> str:
        return os.path.expanduser(self.image_dir)

    def ip(self) -> str | None:
        try:
            cp = self.run(["mkqnximage", "--getip"], self.dir)
        except FileNotFoundError:
            raise RuntimeError("mkqnximage not found: run `source ~/qnx800/qnxsdp-env.sh` first") from None
        if cp.returncode != 0:
            return None
        m = _IP.search(cp.stdout)
        return m.group(1) if m else None

    def up(self, timeout: float = 180, poll: float = 3) -> str:
        if not Path(self.dir).is_dir():
            raise RuntimeError(f"no QEMU image folder at {self.dir}: install 'QNX SDP 8.0 Quick Start "
                               "Target Image for QEMU' in the Software Center and run unpack_qemu_image.sh")
        existing = self.ip()
        if existing:
            self.log.append(f"already running at {existing}")
            return existing
        log = Path(self.dir) / "tracelens-qemu.log"
        pid = self.spawn(["mkqnximage", "--run"], self.dir, log)
        self.log.append(f"started mkqnximage --run (pid {pid}); console log: {log}")
        waited = 0.0
        while waited < timeout:
            self.sleep(poll)
            waited += poll
            ip = self.ip()
            if ip:
                self.log.append(f"target is up at {ip} after {waited:.0f}s")
                return ip
        raise RuntimeError(f"no IP after {timeout:.0f}s; see {log}")

    def down(self) -> None:
        cp = self.run(["mkqnximage", "--stop"], self.dir)
        if cp.returncode != 0:
            raise RuntimeError(f"mkqnximage --stop failed: {cp.stderr.strip() or cp.stdout.strip()}")
        self.log.append("stopped")
