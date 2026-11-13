"""Priority inversion (SMP-aware).

Rule: a high-priority thread H is blocked (SEM / MUTEX / CONDVAR / SEND / REPLY)
longer than the threshold; the thread L that unblocks it had a lower effective
priority during the block; and medium-priority threads M (pL < pM < pH at that
instant) were RUNNING on a CPU that L runs on while L was READY. Interference is
the union of those intervals, so the ratio never exceeds the block time.

Priorities come from kernel events over time (THREAD ``prio``, SCHED_SET, snapshot),
never from workload markers, so a traced priority-inheritance boost suppresses the
finding. A semaphore counts as a lock only if L waited on it before posting;
otherwise it is reported as a signal dependency, at lower severity.

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
from ._util import fmt_ms, intersect, ms, union_ns

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


QNX_SIGNAL_NOTE = ("{low} never took this semaphore; it only posts it, so this is a producer/consumer "
                   "signal, not a lock. No QNX primitive can lend priority to a future signaller: give "
                   "{low} a priority at least as high as its consumer while it produces, or deliver the "
                   "data with MsgSend/pulses so the server runs at the client's priority.")


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


def _sem_used_as_lock(model: TraceModel, low: ThreadInfo, addr: str | None, wake: Event) -> bool:
    """True if L acquired the semaphore (SYNC_SEM_WAIT on it) before posting: lock usage.
    Otherwise the post is a signal (producer/consumer), not a release of a held lock."""
    if addr is None:
        return False
    last = None
    for e in low.calls:
        if e.t_ns > wake.t_ns or e is wake:
            break
        if e.args.get("sync") == addr and e.kind.startswith(("SYNC_SEM_WAIT", "SYNC_SEM_POST")):
            last = e
    return last is not None and last.kind.startswith("SYNC_SEM_WAIT")


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    """SMP-aware rule: interference is time when a medium-priority thread M was RUNNING on a CPU
    that L may run on (CPUs L was seen on) while L was READY, i.e. L wanted the CPU and M had it.
    Priorities are compared at that moment, so a traced inheritance boost removes the inversion."""
    t = cfg.thresholds
    min_block = t.inversion_min_block_us * 1000
    min_interf = t.inversion_min_interference_us * 1000

    groups: dict[tuple, list[dict]] = {}
    for h in model.threads.values():
        if not h.prio_hist:
            continue
        for iv in h.intervals:
            if iv.state not in OBJECT_NAME or iv.open_at_end or iv.duration < min_block:
                continue
            p_h = h.prio_at(iv.start)
            block, wake, obj = _waker(model, h, iv)
            if wake is None or wake.key is None or p_h is None:
                continue
            low = model.threads.get(wake.key)
            if low is None or low is h or not low.prio_hist:
                continue
            low_range = low.prio_range(iv.start, iv.end)
            if low_range is None or low_range[0] >= p_h:
                continue  # L was never below H during the block (e.g. inheritance boosted it)

            low_ready = model.segments(low, {"READY"}, iv.start, iv.end)
            cpus = low.cpus or None
            per_m: dict = {}
            for m in model.threads.values():
                if m is h or m is low or not m.prio_hist:
                    continue
                running = model.segments(m, {"RUNNING"}, iv.start, iv.end, cpus)
                for s, e in intersect(running, low_ready):
                    p_m, p_l = m.prio_at(s), low.prio_at(s)
                    if p_m is not None and p_l is not None and p_l < p_m < p_h:
                        per_m.setdefault(m.key, []).append((s, e))
            spans = [sp for v in per_m.values() for sp in v]
            interference = union_ns(spans)
            if interference < min_interf:
                continue
            interferers = []
            for mkey, sp in per_m.items():
                first = model.first_interval(model.threads[mkey], {"RUNNING"}, sp[0][0], sp[0][1] + 1)
                interferers.append((model.threads[mkey], union_ns(sp), first.event_id if first else None))

            pattern = ""
            if iv.state == "SEM":
                pattern = "lock" if _sem_used_as_lock(model, low, obj, wake) else "signal"
            groups.setdefault((h.key, low.key, iv.state, obj, pattern), []).append({
                "iv": iv, "block": block, "wake": wake, "interferers": interferers,
                "interference": interference, "p_h": p_h, "p_l": low_range[0],
                "low_ready": union_ns(low_ready),
            })

    findings = []
    for (hkey, lkey, state, obj, pattern), occ in groups.items():
        worst = max(occ, key=lambda o: o["interference"])
        iv = worst["iv"]
        ratio = worst["interference"] / iv.duration if iv.duration else 0
        mids = sorted(worst["interferers"], key=lambda x: -x[1])
        mid_names = ", ".join(model.describe(m.key) for m, _, _ in mids[:3])

        evidence = [e for e in (worst["block"].id if worst["block"] else None, iv.event_id,
                                worst["wake"].id) if e is not None]
        evidence += [eid for _, _, eid in mids[:3] if eid is not None]

        what = OBJECT_NAME[state]
        if pattern == "signal":
            what = "semaphore used as a signal"
            severity = "high" if ratio >= 0.5 else "medium"
            note = QNX_SIGNAL_NOTE
        else:
            severity = "critical" if ratio >= 0.5 else "high"
            note = QNX_NOTES[state]
        findings.append(Finding(
            kind="priority_inversion",
            severity=severity,
            title=f"Priority inversion: {model.label(hkey)} waited on {model.label(lkey)} via a {what}",
            summary=(f"{model.label(hkey)} (prio {worst['p_h']}) was blocked {fmt_ms(iv.duration)} on a "
                     f"{what} ({obj}) released by {model.label(lkey)} (prio {worst['p_l']}); for "
                     f"{fmt_ms(worst['interference'])} of that, {model.label(lkey)} was ready but "
                     f"{mid_names} held its CPU. Seen {len(occ)}x."),
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
                "object": what,
                "object_id": obj or "",
                "high_prio": worst["p_h"],
                "low_prio": worst["p_l"],
                "priority_source": model.threads[hkey].prio_source,
            },
            qnx_note=note.format(low=model.label(lkey), hp=worst["p_h"]),
        ))
    return findings
