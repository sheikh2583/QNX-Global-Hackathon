"""Normalized kernel event: the single currency every TraceLens component speaks."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

_KV_RE = re.compile(r"(\w+)=(\S+)")


@dataclass(slots=True)
class Event:
    """One kernel event.

    ``id`` is stable for a given trace file and is what findings and AI
    explanations cite as evidence.
    """

    id: int
    t_ns: int
    cpu: int
    cls: str  # THREAD, KER_CALL, KER_EXIT, INT_ENTR, INT_EXIT, PROCESS, USREVENT, COMM, CONTROL...
    kind: str  # RUNNING, SEM, SYNC_SEM_WAIT, MSG_SENDV, <irq vector>, EVENT...
    args: dict[str, str] = field(default_factory=dict)
    text: str = ""  # free-text payload (user string events)
    pid: int | None = None  # owning thread: explicit for THREAD events, attributed by CPU otherwise
    tid: int | None = None
    line: int = 0  # 1-based source line in the traceprinter output
    raw: str = ""

    @property
    def key(self) -> tuple[int, int] | None:
        if self.pid is None or self.tid is None:
            return None
        return (self.pid, self.tid)

    def arg_int(self, key: str, default: int | None = None) -> int | None:
        value = self.args.get(key)
        if value is None:
            return default
        value = value.rstrip(",")
        for base in (0, 10):
            try:
                return int(value, base)
            except ValueError:
                continue
        return default

    def to_dict(self) -> dict:
        return asdict(self)


def parse_kv(text: str) -> dict[str, str]:
    """Parse ``key=value`` pairs from a TraceLens marker string."""
    return dict(_KV_RE.findall(text))
