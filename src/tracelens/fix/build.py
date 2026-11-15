"""Builders: turn a workload workspace into a binary (or at least a compile check).

``QccBuilder`` cross-compiles for the QNX target (needs the SDP environment,
i.e. ``source ~/qnx800/qnxsdp-env.sh``). ``HostCheckBuilder`` only type-checks
with the host gcc against the QNX API stubs in ``bugzoo/hostcheck``; it catches
compile errors early and lets the loop run in tests and CI without QNX.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable

WARN = ["-Wall", "-Wextra", "-std=gnu11"]


@dataclass
class BuildResult:
    ok: bool
    binary: Path | None
    log: str


Run = Callable[[list[str]], subprocess.CompletedProcess]


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=300)


@dataclass
class QccBuilder:
    arch: str = "x86_64"
    cflags: list[str] = field(default_factory=lambda: ["-O2", "-g"])
    run: Run = _run

    def build(self, sources: list[Path], include_dirs: list[Path], out: Path) -> BuildResult:
        argv = ["qcc", f"-Vgcc_nto{self.arch}", *self.cflags, *WARN,
                *[f"-I{d}" for d in include_dirs], "-o", str(out), *map(str, sources)]
        try:
            cp = self.run(argv)
        except FileNotFoundError:
            return BuildResult(False, None, "qcc not found: source ~/qnx800/qnxsdp-env.sh first")
        return BuildResult(cp.returncode == 0, out if cp.returncode == 0 else None, cp.stdout + cp.stderr)


@dataclass
class HostCheckBuilder:
    """Compile check only (no QNX binary): host gcc against the QNX API stubs."""

    stubs: Path
    cc: str = "gcc"
    extra: list[str] = field(default_factory=list)
    run: Run = _run

    def build(self, sources: list[Path], include_dirs: list[Path], out: Path) -> BuildResult:
        argv = [self.cc, "-fsyntax-only", *WARN, "-D_GNU_SOURCE", *self.extra, f"-I{self.stubs}",
                *[f"-I{d}" for d in include_dirs], *map(str, sources)]
        try:
            cp = self.run(argv)
        except FileNotFoundError:
            return BuildResult(False, None, f"{self.cc} not found")
        return BuildResult(cp.returncode == 0, out if cp.returncode == 0 else None, cp.stdout + cp.stderr)
