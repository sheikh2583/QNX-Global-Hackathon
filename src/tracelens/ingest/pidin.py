"""Parse a ``pidin`` thread listing taken at capture start.

Default ``pidin`` output looks like (verify column layout on QNX 8.0)::

         pid tid name               prio STATE       Blocked
           1   1 procnto-smp-instr    0f READY
           1   2 procnto-smp-instr  255r RECEIVE     1
      585743   1 ./z1_infusion_pump   10r NANOSLEEP
      585743   2 ./z1_infusion_pump   50f SEM         0x0804c040

The priority column is a number followed by the scheduling policy letter
(f = FIFO, r = round robin, o = other, s = sporadic). Parsing is tolerant: any
line starting with pid and tid integers and containing a ``<n><letter>`` token
is used; everything else is skipped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_PRIO = re.compile(r"^(\d{1,3})([a-z])$")

Key = tuple[int, int]


@dataclass
class ThreadSnapshot:
    prio: dict[Key, int] = field(default_factory=dict)
    policy: dict[Key, str] = field(default_factory=dict)
    proc_names: dict[int, str] = field(default_factory=dict)


def parse_pidin(text: str) -> ThreadSnapshot:
    snap = ThreadSnapshot()
    last_pid: int | None = None
    for line in text.splitlines():
        tokens = line.split()
        if len(tokens) < 3:
            continue
        if tokens[0].isdigit() and tokens[1].isdigit():
            pid, tid, rest = int(tokens[0]), int(tokens[1]), tokens[2:]
        elif tokens[0].isdigit() and last_pid is not None:
            pid, tid, rest = last_pid, int(tokens[0]), tokens[1:]  # continuation line without pid (verify)
        else:
            continue
        prio_i = next((i for i, t in enumerate(rest) if _PRIO.match(t)), None)
        if prio_i is None:
            continue
        m = _PRIO.match(rest[prio_i])
        snap.prio[(pid, tid)] = int(m.group(1))
        snap.policy[(pid, tid)] = m.group(2)
        if prio_i > 0:
            snap.proc_names.setdefault(pid, " ".join(rest[:prio_i]).rsplit("/", 1)[-1])
        last_pid = pid
    return snap


def load_pidin(path: str | Path) -> ThreadSnapshot:
    return parse_pidin(Path(path).read_text(encoding="utf-8", errors="replace"))


def sibling_snapshot(trace_path: str | Path) -> Path | None:
    """``run.txt`` -> ``run.pidin.txt`` if it exists (``tracelens capture`` writes both)."""
    p = Path(trace_path)
    stem = p.name[:-len(".txt.gz")] if p.name.endswith(".txt.gz") else p.stem
    cand = p.with_name(stem + ".pidin.txt")
    return cand if cand.exists() else None
