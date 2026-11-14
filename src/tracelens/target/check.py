"""Preflight check of a QNX target: is it ready for TraceLens captures?

Each check runs over SSH and reports PASS / WARN / FAIL with a hint. The last one
records a one-second wide-mode trace to prove the instrumented kernel works.
Commands and outputs follow the QNX docs and are marked (verify) until seen on 8.0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .ssh import Target

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


@dataclass
class Check:
    name: str
    status: str
    detail: str
    hint: str = ""


def _sh(target: Target, cmd: str, timeout: float = 30):
    try:
        return target.run(cmd, timeout=timeout, check=False)
    except Exception as exc:  # connection-level failure or timeout
        return type("CP", (), {"returncode": 255, "stdout": "", "stderr": str(exc)})()


def preflight(target: Target) -> list[Check]:
    out: list[Check] = []
    cp = _sh(target, "uname -a")
    if cp.returncode != 0:
        out.append(Check("ssh", FAIL, (cp.stderr or "no response").strip()[:200],
                         "Is the VM up (`tracelens target up`)? Is sshd running on it? Right IP?"))
        return out
    uname = cp.stdout.strip()
    out.append(Check("ssh", PASS, f"{target.dest}"))
    out.append(Check("os", PASS if uname.upper().startswith("QNX") else FAIL, uname[:120],
                     "" if uname.upper().startswith("QNX") else "This is not a QNX target."))

    cp = _sh(target, "pidin info")
    cpus = None
    if cp.returncode == 0:
        # QNX 8.0 (verified): one "ProcessorN: <id> <model> <MHz> FPU" line per CPU.
        cpus = len(re.findall(r"^\s*Processor\d+\s*:", cp.stdout, re.M)) or None
    if cpus is None:
        out.append(Check("cpus", WARN, "could not read the CPU count from `pidin info` (verify format)"))
    else:
        out.append(Check("cpus", PASS if cpus >= 2 else WARN, f"{cpus} CPUs",
                         "" if cpus >= 2 else "The bug zoo pins threads to CPUs 0-1; build the VM with --cpu=4."))

    cp = _sh(target, "ls /proc/boot 2>/dev/null; pidin -p 1 arg 2>/dev/null")
    instr = "instr" in cp.stdout
    out.append(Check("instrumented kernel", PASS if instr else WARN,
                     "procnto-*-instr found" if instr else "no 'instr' kernel seen in /proc/boot or pidin",
                     "" if instr else "Tracing needs procnto-smp-instr; rebuild the image with it if the "
                                      "trace check below fails (verify)."))

    for tool in ("tracelogger", "pidin", "traceprinter"):
        cp = _sh(target, f"command -v {tool} || which {tool}")
        found = cp.returncode == 0 and cp.stdout.strip() != ""
        status = PASS if found else (WARN if tool == "traceprinter" else FAIL)
        hint = ""
        if not found:
            hint = ("TraceLens will decode on the host instead (needs traceprinter on the host PATH)."
                    if tool == "traceprinter" else f"{tool} is required on the target.")
        out.append(Check(tool, status, cp.stdout.strip() or "not found", hint))

    cp = _sh(target, "rm -f /tmp/tl_check.kev; tracelogger -w -n 0 -s 1 -f /tmp/tl_check.kev >/dev/null 2>&1; "
                     "wc -c < /tmp/tl_check.kev", timeout=60)
    m = re.search(r"^\s*(\d+)\s*$", cp.stdout, re.M)
    size = int(m.group(1)) if m else 0
    out.append(Check("trace capture", PASS if size > 0 else FAIL,
                     f"1 s wide-mode trace: {size} bytes" if size else (cp.stdout or cp.stderr).strip()[:200],
                     "" if size else "tracelogger produced no data: check the instrumented kernel and flags."))
    return out


def summary_status(checks: list[Check]) -> str:
    if any(c.status == FAIL for c in checks):
        return FAIL
    return WARN if any(c.status == WARN for c in checks) else PASS
