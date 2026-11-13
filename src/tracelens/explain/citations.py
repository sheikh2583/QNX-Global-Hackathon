"""Citation validator: an explanation may only cite events it was shown, and must say
correctly what each cited event is.

Each causal step cites typed claims ``{"event": 97, "thread": "logger", "observed": "SYNC_SEM_POST"}``.
Rules (all must hold for an explanation to be marked *verified*):
  1. Every step of the causal chain cites at least one event.
  2. Every cited id (typed claim, or inline ``E123`` in any text) exists in the evidence pack.
  3. At least one citation is one of the detector's own evidence events.
  4. Typed claims match the trace: the event is on the claimed thread, and ``observed`` names
     what the event is (a thread state such as SEM/READY, a kernel call such as SYNC_SEM_POST,
     a TL marker, or IRQ). "Logger held the semaphore [E97]" fails if E97 is an interrupt.

This proves each citation is the event the model says it is. It does not prove the
sentence's reasoning; the deterministic finding remains the source of truth.
"""

from __future__ import annotations

import re

from ..events import Event
from ..model.trace import TraceModel

_INLINE = re.compile(r"\bE(\d+)\b")

TEXT_FIELDS = ("headline", "qnx_mechanism", "impact")


def _claims(step: dict) -> list[dict]:
    """Normalise a step's evidence: typed claims, or bare ints from older explanations."""
    out = []
    for c in step.get("evidence", []):
        if isinstance(c, dict):
            out.append(c)
        else:
            out.append({"event": c})
    return out


def cited_ids(expl: dict) -> set[int]:
    ids: set[int] = set()
    for step in expl.get("causal_chain", []):
        ids.update(int(c["event"]) for c in _claims(step) if "event" in c)
        ids.update(int(m) for m in _INLINE.findall(step.get("text", "")))
    for key in TEXT_FIELDS:
        ids.update(int(m) for m in _INLINE.findall(str(expl.get(key, ""))))
    fix = expl.get("fix", {})
    for text in [fix.get("summary", ""), *fix.get("steps", [])]:
        ids.update(int(m) for m in _INLINE.findall(str(text)))
    return ids


def observed_tokens(e: Event) -> set[str]:
    """What an event *is*, in the vocabulary the model may use for ``observed``."""
    toks = {e.cls.upper(), e.kind.upper()}
    if e.cls == "INT_ENTR":
        toks |= {"IRQ", "INTERRUPT", f"IRQ {e.kind}"}
    if e.cls == "USREVENT" and e.text:
        toks.add(e.text.split()[0].upper())
    return {t for t in toks if t}


def _thread_ok(model: TraceModel, e: Event, claimed: str) -> bool:
    c = claimed.strip().lower()
    if e.key is None:  # interrupts, process events: no owning thread
        return c in ("", "-", "none", "kernel", "irq") or c.startswith("cpu")
    names = {model.label(e.key).lower(), model.describe(e.key).lower(), f"{e.key[0]}/{e.key[1]}"}
    return any(c == n or (len(c) >= 3 and (c in n or n.split(" (")[0] in c)) for n in names)


def _observed_ok(e: Event, claimed: str) -> bool:
    c = claimed.strip().upper()
    if not c:
        return False
    return any(c == t or t.startswith(c) or c.startswith(t) for t in observed_tokens(e) if len(t) >= 3)


def validate(expl: dict, allowed: set[int], core: set[int], model: TraceModel | None = None) -> list[str]:
    problems: list[str] = []
    chain = expl.get("causal_chain", [])
    if not chain:
        problems.append("causal_chain is empty")
    for n, step in enumerate(chain, start=1):
        claims = _claims(step)
        if not claims:
            problems.append(f"causal_chain step {n} cites no events")
        if model is None:
            continue
        for c in claims:
            eid = int(c.get("event", -1))
            e = model.by_id.get(eid)
            if e is None or eid not in allowed:
                continue  # reported below as an unknown id
            if "thread" in c and not _thread_ok(model, e, str(c["thread"])):
                who = model.label(e.key) if e.key else "no thread (kernel/interrupt)"
                problems.append(f"step {n}: E{eid} is on {who}, not {c['thread']!r}")
            if "observed" in c and not _observed_ok(e, str(c["observed"])):
                what = f"{e.cls} {e.kind}".strip() + (f" '{e.text}'" if e.text else "")
                problems.append(f"step {n}: E{eid} is {what}, not {c['observed']!r}")
    ids = cited_ids(expl)
    unknown = sorted(ids - allowed)
    if unknown:
        problems.append("cites events that are not in the evidence: " + ", ".join(f"E{i}" for i in unknown))
    if core and not (ids & core):
        problems.append("cites none of the detector's own evidence events (marked * in the evidence)")
    return problems
