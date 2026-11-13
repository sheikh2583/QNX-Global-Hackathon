"""Citation validator: an explanation may only cite events it was shown.

Rules (all must hold for an explanation to be marked *verified*):
  1. Every step of the causal chain cites at least one event.
  2. Every cited id, in the ``evidence`` lists or written inline as ``E123``
     anywhere in the text, exists in the evidence pack.
  3. At least one citation is one of the detector's own evidence events, so the
     story is anchored to what was actually detected.
"""

from __future__ import annotations

import re

_INLINE = re.compile(r"\bE(\d+)\b")

TEXT_FIELDS = ("headline", "qnx_mechanism", "impact")


def cited_ids(expl: dict) -> set[int]:
    ids: set[int] = set()
    for step in expl.get("causal_chain", []):
        ids.update(int(i) for i in step.get("evidence", []))
        ids.update(int(m) for m in _INLINE.findall(step.get("text", "")))
    for key in TEXT_FIELDS:
        ids.update(int(m) for m in _INLINE.findall(str(expl.get(key, ""))))
    fix = expl.get("fix", {})
    for text in [fix.get("summary", ""), *fix.get("steps", [])]:
        ids.update(int(m) for m in _INLINE.findall(str(text)))
    return ids


def validate(expl: dict, allowed: set[int], core: set[int]) -> list[str]:
    problems: list[str] = []
    chain = expl.get("causal_chain", [])
    if not chain:
        problems.append("causal_chain is empty")
    for n, step in enumerate(chain, start=1):
        if not step.get("evidence"):
            problems.append(f"causal_chain step {n} cites no events")
    ids = cited_ids(expl)
    unknown = sorted(ids - allowed)
    if unknown:
        problems.append("cites events that are not in the evidence: "
                        + ", ".join(f"E{i}" for i in unknown))
    if core and not (ids & core):
        problems.append("cites none of the detector's own evidence events (marked * in the evidence)")
    return problems
