"""Evidence packs: the exact slice of the trace an explanation is allowed to cite.

Each pack holds the finding's own evidence events plus a little surrounding
context (the events just before and after each one, from the whole trace).
Every line is tagged ``[E<id>]``; the citation validator later rejects any
explanation that cites an id that is not in the pack.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..events import Event
from ..findings import Finding
from ..model.trace import TraceModel


@dataclass
class EvidencePack:
    finding: Finding
    events: list[Event] = field(default_factory=list)

    @property
    def allowed_ids(self) -> set[int]:
        return {e.id for e in self.events}

    @property
    def core_ids(self) -> set[int]:
        """The detector's own evidence: an explanation must cite at least one of these."""
        return set(self.finding.evidence) & self.allowed_ids


def build_pack(model: TraceModel, finding: Finding, context: int = 3, max_events: int = 120) -> EvidencePack:
    index = {e.id: i for i, e in enumerate(model.events)}
    chosen: dict[int, Event] = {}
    core = [i for i in finding.evidence if i in index]
    for eid in core:
        chosen[eid] = model.by_id[eid]
    # Context around each evidence event, nearest first, until the budget is used.
    for radius in range(1, context + 1):
        for eid in core:
            for j in (index[eid] - radius, index[eid] + radius):
                if 0 <= j < len(model.events) and len(chosen) < max_events:
                    e = model.events[j]
                    chosen.setdefault(e.id, e)
    events = sorted(chosen.values(), key=lambda e: (e.t_ns, e.id))
    return EvidencePack(finding=finding, events=events)


def format_event(model: TraceModel, e: Event, t0: int) -> str:
    who = model.describe(e.key) if e.key is not None else "-"
    body = e.raw.strip() or f"{e.cls} {e.kind} {e.text}".strip()
    return f"[E{e.id}] +{(e.t_ns - t0) / 1e6:.3f} ms cpu{e.cpu} {who} | {body}"


def format_pack(model: TraceModel, pack: EvidencePack) -> str:
    t0 = model.t_start
    core = set(pack.finding.evidence)
    lines = []
    for e in pack.events:
        mark = "*" if e.id in core else " "
        lines.append(mark + format_event(model, e, t0))
    return "\n".join(lines)
