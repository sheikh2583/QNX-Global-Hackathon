"""Finding: the output of a detector, with evidence that cites trace event ids."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


@dataclass
class Finding:
    kind: str
    severity: str
    title: str
    summary: str
    t_start: int
    t_end: int
    threads: list[str] = field(default_factory=list)
    evidence: list[int] = field(default_factory=list)  # Event ids
    metrics: dict[str, float | int | str] = field(default_factory=dict)
    qnx_note: str = ""
    id: str = ""

    @property
    def rank(self) -> int:
        return SEVERITY_RANK.get(self.severity, 0)

    def to_dict(self) -> dict:
        return asdict(self)


def at_least(severity: str, threshold: str) -> bool:
    return SEVERITY_RANK.get(severity, 0) >= SEVERITY_RANK.get(threshold, 0)
