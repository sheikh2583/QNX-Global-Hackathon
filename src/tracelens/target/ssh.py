"""SSH/SCP access to the QNX target (the QEMU guest).

Runs from the Linux host side (WSL2 Ubuntu), where the QEMU VM is reachable.
Every command goes through a ``Runner`` so tests can script the target.

The QEMU guest is a throwaway local VM whose host key changes on every image
rebuild, so host-key checking is off by default (``strict_host_keys=False``);
turn it on for real hardware.
"""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class Runner(Protocol):
    def __call__(self, argv: list[str], timeout: float) -> subprocess.CompletedProcess: ...


def subprocess_runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


class TargetError(RuntimeError):
    """A command on (or a copy to/from) the target failed."""


@dataclass
class Target:
    host: str
    user: str = "root"
    port: int = 22
    key: str | None = None
    strict_host_keys: bool = False
    connect_timeout: int = 10
    runner: Runner = field(default=subprocess_runner, repr=False)

    def _opts(self) -> list[str]:
        opts = ["-o", f"ConnectTimeout={self.connect_timeout}", "-o", "BatchMode=yes"]
        if not self.strict_host_keys:
            opts += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                     "-o", "LogLevel=ERROR"]
        if self.key:
            opts += ["-i", self.key]
        return opts

    @property
    def dest(self) -> str:
        return f"{self.user}@{self.host}"

    def run(self, command: str, timeout: float = 60, check: bool = True) -> subprocess.CompletedProcess:
        """Run a shell command on the target (QNX ksh/sh)."""
        argv = ["ssh", *self._opts(), "-p", str(self.port), self.dest, command]
        cp = self.runner(argv, timeout)
        if check and cp.returncode != 0:
            raise TargetError(f"target command failed ({cp.returncode}): {command}\n{cp.stderr.strip()}")
        return cp

    def put(self, local: str | Path, remote: str, timeout: float = 120) -> None:
        argv = ["scp", *self._opts(), "-P", str(self.port), str(local), f"{self.dest}:{remote}"]
        cp = self.runner(argv, timeout)
        if cp.returncode != 0:
            raise TargetError(f"copy to target failed: {local} -> {remote}\n{cp.stderr.strip()}")

    def get(self, remote: str, local: str | Path, timeout: float = 120) -> None:
        argv = ["scp", *self._opts(), "-P", str(self.port), f"{self.dest}:{remote}", str(local)]
        cp = self.runner(argv, timeout)
        if cp.returncode != 0:
            raise TargetError(f"copy from target failed: {remote} -> {local}\n{cp.stderr.strip()}")


def q(s: str) -> str:
    """Quote for the target's POSIX shell."""
    return shlex.quote(s)
