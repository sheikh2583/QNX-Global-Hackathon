"""Capture a kernel event trace of one workload run on the QNX target.

Steps (one ``tracelens capture`` call):
  1. copy the workload binary to the target
  2. thread snapshot with ``pidin`` (base priorities and names at capture start)
  3. start ``tracelogger`` in wide mode for a fixed time, run the workload inside that window
  4. copy the ``.kev`` back
  5. decode it with ``traceprinter`` on the host if available (needs the SDP environment),
     otherwise on the target, and copy the text back

Flags marked (verify) still need checking against QNX 8.0's ``use tracelogger`` output.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .ssh import Target, TargetError, q

REMOTE_DIR = "/tmp/tracelens"


@dataclass
class CaptureResult:
    name: str
    kev: Path
    text: Path | None
    snapshot: Path | None
    log: list[str] = field(default_factory=list)
    workload_rc: int | None = None


def trace_command(binary: str | None, args: list[str], kev: str, seconds: int, settle: float = 1.0,
                  raw: str | None = None) -> str:
    """Shell command that runs ``binary`` (or the shell command ``raw``) inside a time-limited
    tracelogger capture."""
    run = f"( {raw} )" if raw is not None else " ".join(q(a) for a in [binary, *args])
    return (
        # QNX 8.0 (verified): -w wide events, -n 0 lifts the default 32-iteration cap, -s timed mode,
        # -k kernel buffers per CPU (default 8): more headroom against dropped events in wide mode.
        f"tracelogger -w -n 0 -k 32 -s {int(seconds)} -f {q(kev)} >/dev/null 2>&1 & "
        f"TL=$!; sleep {settle}; {run}; RC=$?; wait $TL; echo TRACELENS_RC=$RC"
    )


def capture(target: Target, binary: str | Path | None, args: list[str], out_dir: str | Path,
            seconds: int = 4, name: str | None = None, snapshot: bool = True,
            traceprinter: str = "auto", host_runner=None, command: str | None = None) -> CaptureResult:
    """Run ``binary`` on the target under a trace; return local paths of the results.

    ``command``: instead of deploying a binary, trace a shell command already runnable on the
    target (system programs, the negative corpus). ``traceprinter``: "host", "target", or
    "auto" (host if ``traceprinter`` is on PATH).
    """
    if binary is None and command is None:
        raise ValueError("capture needs a binary or a command")
    name = name or (Path(binary).name if binary is not None else "command")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    remote_kev = f"{REMOTE_DIR}/{name}.kev"
    res = CaptureResult(name=name, kev=out / f"{name}.kev", text=None, snapshot=None)

    target.run(f"mkdir -p {REMOTE_DIR}")
    remote_bin = None
    if binary is not None:
        binary = Path(binary)
        remote_bin = f"{REMOTE_DIR}/{binary.name}"
        target.put(binary, remote_bin)
        target.run(f"chmod +x {q(remote_bin)}")
        res.log.append(f"deployed {binary} -> {remote_bin}")
    else:
        res.log.append(f"tracing target command: {command}")

    if snapshot:
        snap = target.run("pidin", timeout=30, check=False)
        if snap.returncode == 0 and snap.stdout.strip():
            res.snapshot = out / f"{name}.pidin.txt"
            res.snapshot.write_text(snap.stdout, encoding="utf-8")
            res.log.append(f"thread snapshot -> {res.snapshot}")
        else:
            res.log.append("thread snapshot failed; priorities will come from trace events only")

    cp = target.run(trace_command(remote_bin, args, remote_kev, seconds, raw=command),
                    timeout=seconds + 60, check=False)
    for line in cp.stdout.splitlines():
        if line.startswith("TRACELENS_RC="):
            try:
                res.workload_rc = int(line.split("=", 1)[1])
            except ValueError:
                pass
    if cp.returncode != 0:
        raise TargetError(f"trace run failed ({cp.returncode}):\n{cp.stderr.strip()}")
    res.log.append(f"traced {seconds}s, workload exit {res.workload_rc}")

    target.get(remote_kev, res.kev)
    res.log.append(f"trace -> {res.kev}")

    text = out / f"{name}.txt"
    where = traceprinter
    if where == "auto":
        where = "host" if shutil.which("traceprinter") else "target"
    if where == "host":
        run = host_runner or (lambda argv: subprocess.run(argv, capture_output=True, text=True, timeout=300))
        cp = run(["traceprinter", "-f", str(res.kev)])
        if cp.returncode != 0:
            raise TargetError(f"host traceprinter failed: {cp.stderr.strip()} "
                              "(license? try --traceprinter target)")
        text.write_text(cp.stdout, encoding="utf-8")
    else:
        remote_txt = f"{REMOTE_DIR}/{name}.txt"
        target.run(f"traceprinter -f {q(remote_kev)} > {q(remote_txt)}", timeout=300)
        target.get(remote_txt, text)
    res.text = text
    res.log.append(f"decoded with traceprinter on the {where} -> {text}")
    return res
