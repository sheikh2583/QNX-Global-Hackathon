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
    """Detector evidence plus context that is causally related to it: the neighbouring events
    of the same thread, on the same sync object, and on the same CPU (an 8-CPU trace's global
    neighbours are mostly unrelated noise)."""
    core = [i for i in finding.evidence if i in model.by_id]
    chosen: dict[int, Event] = {i: model.by_id[i] for i in core}
    streams: dict[tuple, list[Event]] = {}

    def stream(kind: str, value) -> list[Event]:
        key = (kind, value)
        if key not in streams:
            if kind == "thread":
                streams[key] = [e for e in model.events if e.key == value]
            elif kind == "sync":
                streams[key] = list(model.sync_ops.get(value, ()))
            else:
                streams[key] = [e for e in model.events if e.cpu == value]
        return streams[key]

    for radius in range(1, context + 1):
        for eid in core:
            e = model.by_id[eid]
            related = [("thread", e.key)] if e.key is not None else []
            if (addr := e.args.get("sync")) is not None:
                related.append(("sync", addr))
            related.append(("cpu", e.cpu))
            for kind, value in related:
                evs = stream(kind, value)
                pos = next((i for i, x in enumerate(evs) if x.id == eid), None)
                if pos is None:
                    continue
                for j in (pos - radius, pos + radius):
                    if 0 <= j < len(evs) and len(chosen) < max_events:
                        chosen.setdefault(evs[j].id, evs[j])
    events = sorted(chosen.values(), key=lambda e: (e.t_ns, e.id))
    return EvidencePack(finding=finding, events=events)


def format_event(model: TraceModel, e: Event, t0: int) -> str:
    who = model.describe(e.key) if e.key is not None else "-"
    body = e.raw.strip() or f"{e.cls} {e.kind} {e.text}".strip()
    what = f"{e.cls} {e.kind}".strip()
    if e.cls == "USREVENT" and e.text:
        what = f"USREVENT {e.text.split()[0]}"
    return f"[E{e.id}] +{(e.t_ns - t0) / 1e6:.3f} ms cpu{e.cpu} {who} {what} | {body}"


def format_pack(model: TraceModel, pack: EvidencePack) -> str:
    t0 = model.t_start
    core = set(pack.finding.evidence)
    lines = []
    for e in pack.events:
        mark = "*" if e.id in core else " "
        lines.append(mark + format_event(model, e, t0))
    return "\n".join(lines)
