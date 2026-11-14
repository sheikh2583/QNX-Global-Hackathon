"""Send/Reply blocking chains and deadlocks.

QNX message passing is synchronous: a client is SEND-blocked until a server
receives, then REPLY-blocked until it replies. Every SEND/REPLY-blocked
interval longer than the threshold becomes a time-bounded edge
``client pid -> server pid``. The server comes from COMM events (the client's
SND_MESSAGE rcvid/pid, matched to the server thread's REC_MESSAGE), so
connections made before the capture work too; failing that, from ConnectAttach
coids inside the trace.

* A **deadlock** is a cycle of edges whose time windows all overlap, during
  which no member process has a thread RECEIVE-blocked *on the channel the cycle
  is calling* (a pool thread receiving on some other channel cannot help). When
  the channel is unknown, any RECEIVE-blocked thread counts, as before.
  Deadlocks broken later by a timeout (TimerTimeout) are still reported.
* A **deep chain** is a non-cyclic path of overlapping edges with at least
  ``chain_min_depth`` processes.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..events import Event
from ..findings import Finding
from ..model.trace import IPC_STATES, Interval, ThreadInfo, TraceModel
from ._util import fmt_ms, ms

QNX_NOTE = ("QNX message passing is synchronous: a thread that is SEND- or REPLY-blocked "
            "cannot service its own channel. Servers that MsgSend() to each other deadlock. "
            "Keep a strict send hierarchy (send only 'down'), and notify 'up' with "
            "MsgSendPulse(), which never blocks.")

MAX_DEPTH = 8


@dataclass(frozen=True)
class Edge:
    client: int
    server: int
    start: int
    end: int
    thread: ThreadInfo
    iv: Interval
    call: Event
    chid: str | None = None
    server_thread: tuple | None = None


def _edges(model: TraceModel, min_blocked: int) -> list[Edge]:
    out = []
    for th in model.threads.values():
        for iv in th.intervals:
            if iv.state not in IPC_STATES or iv.duration < min_blocked:
                continue
            call = model.last_call_before(th, iv.start, ("MSG_SEND",))
            if call is None:
                continue
            server, server_thread, chid = model.message_target(call)
            if server is None or server == th.pid:
                continue
            out.append(Edge(th.pid, server, iv.start, iv.end, th, iv, call, chid, server_thread))
    # A thread's SEND then REPLY intervals for one request are one logical edge.
    return out


def _receiving(model: TraceModel, pid: int, a: int, b: int, chid: str | None = None) -> bool:
    """Could process ``pid`` serve a message on ``chid`` during [a, b)?"""
    for th in model.threads.values():
        if th.pid != pid:
            continue
        for iv in th.intervals:
            if iv.start >= b:
                break
            if iv.state != "RECEIVE" or iv.end <= a:
                continue
            rc = model.receive_channel(th, iv.start)
            if chid is None or rc is None or rc == chid:
                return True
    return False


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    min_blocked = cfg.thresholds.deadlock_min_blocked_us * 1000
    edges = _edges(model, min_blocked)
    by_client: dict[int, list[Edge]] = {}
    for e in edges:
        by_client.setdefault(e.client, []).append(e)

    cycles: dict[frozenset, tuple[list[Edge], int, int]] = {}
    chains: dict[tuple, tuple[list[Edge], int, int]] = {}

    def dfs(path: list[Edge], a: int, b: int) -> None:
        last = path[-1]
        start_pid = path[0].client
        extended = False
        for nxt in by_client.get(last.server, ()):
            lo, hi = max(a, nxt.start), min(b, nxt.end)
            if hi - lo < min_blocked:
                continue
            if nxt.server == start_pid:
                cyc = path + [nxt]
                pids = frozenset(e.client for e in cyc)
                wanted = {e.server: e.chid for e in cyc}
                if pids not in cycles and not any(_receiving(model, p, lo, hi, wanted.get(p)) for p in pids):
                    cycles[pids] = (cyc, lo, hi)
                extended = True
                continue
            if any(e.client == nxt.server for e in path) or len(path) >= MAX_DEPTH:
                continue
            extended = True
            dfs(path + [nxt], lo, hi)
        if not extended and len(path) + 1 >= cfg.thresholds.chain_min_depth:
            sig = tuple([e.client for e in path] + [last.server])
            chains.setdefault(sig, (path, a, b))

    for e in edges:
        dfs([e], e.start, e.end)

    findings: list[Finding] = []
    cyc_pids = set().union(*cycles) if cycles else set()
    for pids, (cyc, lo, hi) in cycles.items():
        procs = [model.proc_names.get(e.client, f"pid {e.client}") for e in cyc]
        if len(set(procs)) < len(procs):  # forked servers share a process name: use thread names
            procs = [model.label(e.thread.key) for e in cyc]
        names = " -> ".join(procs + procs[:1])
        resolved = hi < model.t_end
        how = ("then broken by a timeout" if resolved else "until the end of the trace")
        findings.append(Finding(
            kind="ipc_deadlock",
            severity="critical",
            title=f"Send/Reply deadlock: {names}",
            summary=(f"{len(cyc)} processes were each SEND/REPLY-blocked on the next ({names}); "
                     f"none could receive. Deadlocked for {fmt_ms(hi - lo)}, {how}."),
            t_start=lo,
            t_end=hi,
            threads=[model.label(e.thread.key) for e in cyc],
            evidence=[x for e in cyc for x in (e.call.id, e.iv.event_id)],
            metrics={"processes": len(cyc), "deadlocked_ms": round(ms(hi - lo), 3),
                     "resolved_by_timeout": resolved, "cycle": names},
            qnx_note=QNX_NOTE,
        ))

    for sig, (path, lo, hi) in chains.items():
        if set(sig) <= cyc_pids:
            continue
        names = " -> ".join(model.proc_names.get(p, f"pid {p}") for p in sig)
        findings.append(Finding(
            kind="ipc_chain",
            severity="medium",
            title=f"Deep blocking chain: {names}",
            summary=f"A request was blocked through {len(sig)} processes ({names}) for {fmt_ms(hi - lo)}.",
            t_start=lo,
            t_end=hi,
            threads=[model.label(e.thread.key) for e in path],
            evidence=[x for e in path for x in (e.call.id, e.iv.event_id)],
            metrics={"depth": len(sig), "blocked_ms": round(ms(hi - lo), 3), "chain": names},
            qnx_note=QNX_NOTE,
        ))
    return findings
