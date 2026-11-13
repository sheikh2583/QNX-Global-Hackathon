"""Priority inversion.

Rule: a high-priority thread H is blocked (SEM / MUTEX / CONDVAR / SEND / REPLY)
for longer than the threshold; the thread L that eventually unblocks it has a
lower priority; and during the block, threads M with pL < pM < pH ran on the
CPU — i.e. H effectively waited for medium-priority work.

QNX nuance: mutexes inherit priority by default and message-passing servers run
at the client's priority unless the channel uses ``_NTO_CHF_FIXED_PRIORITY``.
So on QNX the realistic inversions come from semaphores (no owner -> nothing to
boost), fixed-priority channels, or mutexes with inheritance disabled.
"""

from __future__ import annotations

from ..config import Config
from ..events import Event
from ..findings import Finding
from ..model.trace import Interval, ThreadInfo, TraceModel
from ._util import fmt_ms, ms

WAIT_CALLS = {
    "SEM": ("SYNC_SEM_WAIT",),
    "MUTEX": ("SYNC_MUTEX_LOCK",),
    "CONDVAR": ("SYNC_CONDVAR_WAIT",),
}
WAKE_CALLS = {
    "SEM": ("SYNC_SEM_POST",),
    "MUTEX": ("SYNC_MUTEX_UNLOCK", "SYNC_MUTEX_REVIVE"),
    "CONDVAR": ("SYNC_CONDVAR_SIGNAL",),
}
OBJECT_NAME = {"SEM": "semaphore", "MUTEX": "mutex", "CONDVAR": "condition variable",
               "SEND": "message channel", "REPLY": "message channel"}

QNX_NOTES = {
    "SEM": ("QNX semaphores have no owner, so the kernel cannot apply priority inheritance. "
            "A pthread mutex (priority inheritance is the QNX default) would have boosted {low} "
            "to priority {hp} and the medium-priority work could not have preempted it."),
    "MUTEX": ("QNX mutexes inherit priority by default; an inversion through a mutex means "
              "inheritance was disabled (PTHREAD_PRIO_NONE) or a priority ceiling is too low."),
    "CONDVAR": ("Condition variables carry no ownership, so no inheritance applies. "
                "Protect the shared state with a mutex and keep the signalling thread's work short."),
    "SEND": ("By default a QNX server thread inherits the priority of the client it is serving. "
             "This server ran below its client: check for _NTO_CHF_FIXED_PRIORITY on ChannelCreate()."),
    "REPLY": ("By default a QNX server thread inherits the priority of the client it is serving. "
              "This server ran below its client: check for _NTO_CHF_FIXED_PRIORITY on ChannelCreate()."),
}


def _waker(model: TraceModel, h: ThreadInfo, iv: Interval) -> tuple[Event | None, Event | None, str | None]:
    """Return (blocking call, waking call, object id) for H's blocked interval."""
    state = iv.state
    if state in WAIT_CALLS:
        block = model.last_call_before(h, iv.start, WAIT_CALLS[state])
        if block is None or (addr := block.args.get("sync")) is None:
            return block, None, None
        wake = None
        for e in model.sync_ops.get(addr, ()):
            if e.t_ns > iv.end:
                break
            if e.t_ns >= iv.start and e.kind.startswith(WAKE_CALLS[state]) and e.key != h.key:
                wake = e
        return block, wake, addr

    # SEND / REPLY: the server process that eventually receives / replies.
    block = model.last_call_before(h, iv.start, ("MSG_SEND",))
    if block is None:
        return None, None, None
    server = model.server_of(block)
    if server is None:
        return block, None, None
    want = ("MSG_REPLY", "MSG_ERROR") if state == "REPLY" else ("MSG_RECEIVE",)
    wake = None
    for th in model.threads.values():
        if th.pid != server:
            continue
        for e in th.calls if state == "REPLY" else th.exits:
            if iv.start <= e.t_ns <= iv.end and e.kind.startswith(want):
                if wake is None or e.t_ns > wake.t_ns:
                    wake = e
    return block, wake, f"pid {server} coid {block.args.get('coid')}"


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    t = cfg.thresholds
    min_block = t.inversion_min_block_us * 1000
    min_interf = t.inversion_min_interference_us * 1000

    groups: dict[tuple, list[dict]] = {}
    for h in model.threads.values():
        if h.prio is None:
            continue
        for iv in h.intervals:
            if iv.state not in OBJECT_NAME or iv.open_at_end or iv.duration < min_block:
                continue
            block, wake, obj = _waker(model, h, iv)
            if wake is None or wake.key is None:
                continue
            low = model.threads.get(wake.key)
            if low is None or low.prio is None or low.prio >= h.prio:
                continue

            interferers = []
            for m in model.threads.values():
                if m.prio is None or not (low.prio < m.prio < h.prio):
                    continue
                ran = model.overlap(m, {"RUNNING"}, iv.start, iv.end)
                if ran > 0:
                    first = model.first_interval(m, {"RUNNING"}, iv.start, iv.end)
                    interferers.append((m, ran, first.event_id if first else None))
            interference = sum(r for _, r, _ in interferers)
            if interference < min_interf:
                continue

            groups.setdefault((h.key, low.key, iv.state, obj), []).append({
                "iv": iv, "block": block, "wake": wake, "interferers": interferers,
                "interference": interference,
                "low_ready": model.overlap(low, {"READY"}, iv.start, iv.end),
            })

    findings = []
    for (hkey, lkey, state, obj), occ in groups.items():
        worst = max(occ, key=lambda o: o["iv"].duration)
        iv = worst["iv"]
        h, low = model.threads[hkey], model.threads[lkey]
        ratio = worst["interference"] / iv.duration if iv.duration else 0
        mids = sorted(worst["interferers"], key=lambda x: -x[1])
        mid_names = ", ".join(model.describe(m.key) for m, _, _ in mids[:3])

        evidence = [e for e in (worst["block"].id if worst["block"] else None, iv.event_id,
                                worst["wake"].id) if e is not None]
        evidence += [eid for _, _, eid in mids[:3] if eid is not None]

        findings.append(Finding(
            kind="priority_inversion",
            severity="critical" if ratio >= 0.5 else "high",
            title=f"Priority inversion: {model.label(hkey)} waited on {model.label(lkey)} "
                  f"via a {OBJECT_NAME[state]}",
            summary=(f"{model.describe(hkey)} was blocked {fmt_ms(iv.duration)} on a "
                     f"{OBJECT_NAME[state]} ({obj}) released by lower-priority "
                     f"{model.describe(lkey)}, while {mid_names} ran for "
                     f"{fmt_ms(worst['interference'])}. Seen {len(occ)}x."),
            t_start=iv.start,
            t_end=iv.end,
            threads=[model.label(hkey), model.label(lkey)] + [model.label(m.key) for m, _, _ in mids[:3]],
            evidence=evidence,
            metrics={
                "occurrences": len(occ),
                "worst_block_ms": round(ms(iv.duration), 3),
                "worst_interference_ms": round(ms(worst["interference"]), 3),
                "interference_ratio": round(ratio, 3),
                "low_prio_ready_ms": round(ms(worst["low_ready"]), 3),
                "object": OBJECT_NAME[state],
                "object_id": obj or "",
                "high_prio": h.prio,
                "low_prio": low.prio,
            },
            qnx_note=QNX_NOTES[state].format(low=model.label(lkey), hp=h.prio),
        ))
    return findings
