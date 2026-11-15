"""Turns a flat event stream into per-thread state timelines and lookup indexes."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field

from ..events import Event, parse_kv
from ..ingest.traceprinter import ParsedTrace

Key = tuple[int, int]

LOSSY_MIN_EVENTS = 100_000  # below this, any state-machine violation makes the trace lossy
LOSSY_RATE = 1e-5  # above it: more than 1 violation per 100,000 events

# QNX thread states in which a thread is waiting on another party.
SYNC_STATES = {"SEM", "MUTEX", "CONDVAR"}
IPC_STATES = {"SEND", "REPLY"}
BLOCKED_STATES = SYNC_STATES | IPC_STATES | {"JOIN", "INTR", "WAITPAGE"}


@dataclass(slots=True)
class Interval:
    start: int
    end: int
    state: str
    event_id: int
    open_at_end: bool = False
    cpu: int = -1  # CPU of the event that started the interval

    @property
    def duration(self) -> int:
        return self.end - self.start


@dataclass
class ThreadInfo:
    pid: int
    tid: int
    name: str | None = None
    prio: int | None = None  # first known (base) priority; use prio_at() for comparisons
    prio_source: str = ""  # "kernel" (THREAD/SCHED events) or "snapshot" (pidin at capture start)
    kernel_name: str | None = None  # from PROCTHREAD_NAME events (pthread_setname_np)
    prio_hist: list[tuple[int, int, int]] = field(default_factory=list)  # (t_ns, prio, event id or -1)
    cpus: set[int] = field(default_factory=set)  # CPUs this thread was seen RUNNING on
    intervals: list[Interval] = field(default_factory=list)
    calls: list[Event] = field(default_factory=list)
    exits: list[Event] = field(default_factory=list)
    user: list[Event] = field(default_factory=list)
    _call_times: list[int] = field(default_factory=list, repr=False)
    _exit_times: list[int] = field(default_factory=list, repr=False)

    @property
    def key(self) -> Key:
        return (self.pid, self.tid)

    def set_prio(self, t: int, prio: int, event_id: int, source: str) -> None:
        if self.prio_hist and self.prio_hist[-1][1] == prio:
            return
        self.prio_hist.append((t, prio, event_id))
        if self.prio is None:
            self.prio, self.prio_source = prio, source

    def prio_at(self, t: int) -> int | None:
        """Effective priority at time ``t`` (inheritance boosts included when traced)."""
        if not self.prio_hist:
            return None
        i = bisect.bisect_right(self.prio_hist, (t, float("inf"), 0)) - 1
        return self.prio_hist[max(i, 0)][1]

    def prio_range(self, a: int, b: int) -> tuple[int, int] | None:
        """(min, max) effective priority within [a, b)."""
        if not self.prio_hist:
            return None
        vals = [self.prio_at(a)] + [p for t, p, _ in self.prio_hist if a < t < b]
        vals = [v for v in vals if v is not None]
        return (min(vals), max(vals)) if vals else None


class TraceModel:
    def __init__(self, trace: ParsedTrace, snapshot: dict[Key, int] | None = None,
                 snapshot_names: dict[int, str] | None = None):
        """``snapshot`` seeds base priorities ((pid, tid) -> prio), e.g. from pidin at capture start;
        ``snapshot_names`` seeds process names (pid -> name)."""
        self.trace = trace
        self.snapshot = snapshot or {}
        self.snapshot_names = snapshot_names or {}
        self.integrity: list[str] = []  # scheduler state-machine violations (dropped events?)
        self.events = trace.events
        self.by_id: dict[int, Event] = {e.id: e for e in self.events}
        self.threads: dict[Key, ThreadInfo] = {}
        self.proc_names: dict[int, str] = {}
        self.coid_map: dict[tuple[int, int], int] = {}  # (client pid, coid) -> server pid
        self.coid_chid: dict[tuple[int, int], str] = {}  # (client pid, coid) -> server channel id
        # COMM events (verify kind/field names on QNX 8.0): SND_MESSAGE carries the rcvid and the
        # receiving pid; REC_MESSAGE, attributed to the server thread, carries the same rcvid.
        self.comm_snd: dict[Key, list[Event]] = {}  # client thread -> its SND_MESSAGE events
        self.comm_rec: dict[str, list[Event]] = {}  # rcvid -> REC_MESSAGE events
        self.sync_ops: dict[str, list[Event]] = {}  # sync object address -> kernel calls on it
        self.irq_entries: list[Event] = []
        self.irq_handlers: dict[int, list[Key]] = {}  # interrupt id -> IST threads (SYSTEM :IST_ATTACH)
        self.irq_attached_at: dict[tuple[int, Key], int] = {}  # (interrupt id, IST) -> time of its IST_ATTACH
        self.t_start = self.events[0].t_ns if self.events else 0
        self.t_end = self.events[-1].t_ns if self.events else 0
        self._build()

    # ------------------------------------------------------------------ build
    def _thread(self, key: Key) -> ThreadInfo:
        th = self.threads.get(key)
        if th is None:
            th = self.threads[key] = ThreadInfo(pid=key[0], tid=key[1])
            if key in self.snapshot:  # base priority at capture start; kernel events refine it
                th.set_prio(self.t_start, self.snapshot[key], -1, "snapshot")
        return th

    def _build(self) -> None:
        open_iv: dict[Key, Interval] = {}
        pending_connect: dict[Key, Event] = {}
        on_cpu: dict[int, Key] = {}  # cpu -> thread currently RUNNING there
        running_on: dict[Key, int] = {}  # thread -> cpu it is RUNNING on
        violations: dict[str, int] = {}
        first_seen: dict[str, Event] = {}

        def violation(kind: str, e: Event) -> None:
            violations[kind] = violations.get(kind, 0) + 1
            first_seen.setdefault(kind, e)

        self.proc_names.update(self.snapshot_names)

        for e in self.events:
            if e.cls == "PROCESS":
                pid, name = e.arg_int("pid"), e.args.get("name")
                if e.kind.startswith("PROCTHREAD_NAME"):
                    # Kernel-recorded thread names (pthread_setname_np), verified on QNX 8.0.
                    tid = e.arg_int("tid")
                    if pid is not None and tid is not None and name:
                        self._thread((pid, tid)).kernel_name = name
                elif pid is not None and name:
                    self.proc_names[pid] = name.rsplit("/", 1)[-1]
                continue
            if e.cls == "INT_ENTR" or (e.cls == "INTERRUPT" and e.kind == "INT_DELIVER"):
                # QNX 8.0 (verified) records INTERRUPT :INT_DELIVER intr_id:0x4(4); older docs: INT_ENTR
                self.irq_entries.append(e)
                continue

            if e.cls == "SYSTEM" and e.kind == "IST_ATTACH":
                # QNX 8.0 (verified): SYSTEM :IST_ATTACH pid:.. tid:.. intr_id:0x4(4) ... ist_prio:254
                vec, pid, tid = irq_vector(e), e.arg_int("pid"), e.arg_int("tid")
                if vec is not None and pid is not None and tid is not None:
                    lst = self.irq_handlers.setdefault(vec, [])
                    if (pid, tid) not in lst:
                        lst.append((pid, tid))
                    self.irq_attached_at.setdefault((vec, (pid, tid)), e.t_ns)
                continue
            key = e.key
            if key is None:
                continue
            th = self._thread(key)

            if e.cls == "THREAD":
                prio = e.arg_int("prio", e.arg_int("priority"))
                if prio is not None:
                    th.set_prio(e.t_ns, prio, e.id, "kernel")
                if e.kind == "CREATE":
                    continue
                prev = open_iv.get(key)
                if prev is not None:
                    if e.t_ns < prev.start:
                        violation("negative interval", e)
                    prev.end = e.t_ns
                # Scheduler state machine: one thread per CPU, one CPU per thread.
                if e.kind == "RUNNING":
                    other_cpu = running_on.get(key)
                    if other_cpu is not None and other_cpu != e.cpu and on_cpu.get(other_cpu) == key:
                        violation("thread RUNNING on two CPUs at once", e)
                        on_cpu.pop(other_cpu, None)
                    cur = on_cpu.get(e.cpu)
                    if cur is not None and cur != key and running_on.get(cur) == e.cpu:
                        violation("CPU switched threads without the previous one leaving", e)
                        running_on.pop(cur, None)
                    on_cpu[e.cpu] = key
                    running_on[key] = e.cpu
                    th.cpus.add(e.cpu)
                else:
                    cpu = running_on.pop(key, None)
                    if cpu is not None and on_cpu.get(cpu) == key:
                        on_cpu.pop(cpu)
                iv = Interval(e.t_ns, e.t_ns, e.kind, e.id, cpu=e.cpu)
                th.intervals.append(iv)
                open_iv[key] = iv

            elif e.cls == "KER_CALL":
                th.calls.append(e)
                th._call_times.append(e.t_ns)
                if (addr := e.args.get("sync")) is not None:
                    self.sync_ops.setdefault(addr, []).append(e)
                if e.kind == "CONNECT_ATTACH":
                    pending_connect[key] = e
                if e.kind.startswith("SCHED_SET"):
                    # SchedSet(pid, tid, policy, param): tid 0 means the caller (verify arg names).
                    prio = e.arg_int("prio", e.arg_int("priority"))
                    tid = e.arg_int("tid") or key[1]
                    pid = e.arg_int("pid") or key[0]
                    if prio is not None:
                        self._thread((pid, tid)).set_prio(e.t_ns, prio, e.id, "kernel")

            elif e.cls == "KER_EXIT":
                th.exits.append(e)
                th._exit_times.append(e.t_ns)
                if e.kind == "CONNECT_ATTACH" and key in pending_connect:
                    call = pending_connect.pop(key)
                    coid = e.arg_int("ret_val")
                    server = call.arg_int("pid")
                    if server in (None, 0):
                        server = e.pid
                    if coid is not None and coid >= 0 and server is not None:
                        self.coid_map[(key[0], coid)] = server
                        if (chid := call.args.get("chid")) is not None:
                            self.coid_chid[(key[0], coid)] = _norm(chid)

            elif e.cls == "COMM":
                if e.kind.startswith("SND_MESSAGE"):
                    self.comm_snd.setdefault(key, []).append(e)
                elif e.kind.startswith("REC_MESSAGE") and (rcvid := e.args.get("rcvid")) is not None:
                    self.comm_rec.setdefault(_norm(rcvid), []).append(e)

            elif e.cls == "USREVENT":
                th.user.append(e)
                if e.text.startswith("TL_META"):
                    # Names only: priorities come from the kernel, never from the workload.
                    kv = parse_kv(e.text)
                    if "name" in kv:
                        th.name = kv["name"]

        for iv in open_iv.values():
            iv.end = self.t_end
            iv.open_at_end = True
        # Base priority = the one held longest (threads often start at their creator's priority
        # and raise it right away with pthread_setschedparam; seen on QNX 8.0).
        for th in self.threads.values():
            if len(th.prio_hist) > 1:
                held: dict[int, int] = {}
                for (t, p, _), nxt in zip(th.prio_hist, th.prio_hist[1:] + [(self.t_end, 0, 0)]):
                    held[p] = held.get(p, 0) + max(0, nxt[0] - t)
                th.prio = max(held, key=held.get)
        self.integrity_violations = sum(violations.values())
        for kind, n in violations.items():
            e = first_seen[kind]
            self.integrity.append(f"{kind}: {n}x (first at event E{e.id}, line {e.line})")

    @property
    def lossy(self) -> bool:
        """True when the scheduler state machine is broken often enough to distrust the trace.

        Any violation voids a small trace. In a large one, an isolated violation (seen on QNX 8.0:
        1 in 245,085 events under ~5,000 interrupts/s) only distorts one interval, so the trace is
        lossy above LOSSY_RATE violations per event; isolated ones are still reported."""
        n = getattr(self, "integrity_violations", len(self.integrity))
        if n == 0:
            return False
        if len(self.events) < LOSSY_MIN_EVENTS:
            return True
        return n > len(self.events) * LOSSY_RATE

    # ---------------------------------------------------------------- queries
    def label(self, key: Key) -> str:
        th = self.threads.get(key)
        if th is not None and (th.name or th.kernel_name):
            return th.name or th.kernel_name
        proc = self.proc_names.get(key[0])
        if proc:
            return f"{proc}[{key[1]}]"
        return f"pid {key[0]} tid {key[1]}"

    def describe(self, key: Key) -> str:
        th = self.threads.get(key)
        prio = f" (prio {th.prio})" if th is not None and th.prio is not None else " (prio ?)"
        return f"{self.label(key)}{prio}"

    def overlap(self, th: ThreadInfo, states: set[str], a: int, b: int) -> int:
        """Nanoseconds thread ``th`` spent in any of ``states`` within [a, b)."""
        total = 0
        for iv in th.intervals:
            if iv.start >= b:
                break
            if iv.end <= a or iv.state not in states:
                continue
            total += min(iv.end, b) - max(iv.start, a)
        return total

    def segments(self, th: ThreadInfo, states: set[str], a: int, b: int,
                 cpus: set[int] | None = None) -> list[tuple[int, int, int]]:
        """(start, end, cpu) pieces of ``th``'s intervals in ``states``, clipped to [a, b)."""
        out = []
        for iv in th.intervals:
            if iv.start >= b:
                break
            if iv.end <= a or iv.state not in states or (cpus is not None and iv.cpu not in cpus):
                continue
            out.append((max(iv.start, a), min(iv.end, b), iv.cpu))
        return out

    def first_interval(self, th: ThreadInfo, states: set[str], a: int, b: int) -> Interval | None:
        for iv in th.intervals:
            if iv.start >= b:
                break
            if iv.end > a and iv.state in states:
                return iv
        return None

    def last_call_before(self, th: ThreadInfo, t: int, prefixes: tuple[str, ...]) -> Event | None:
        i = bisect.bisect_right(th._call_times, t)
        for e in reversed(th.calls[:i]):
            if e.kind.startswith(prefixes):
                return e
        return None

    def next_exit_after(self, th: ThreadInfo, t: int, prefixes: tuple[str, ...]) -> Event | None:
        i = bisect.bisect_left(th._exit_times, t)
        for e in th.exits[i:]:
            if e.kind.startswith(prefixes):
                return e
        return None

    def next_call_after(self, th: ThreadInfo, t: int, prefixes: tuple[str, ...]) -> Event | None:
        i = bisect.bisect_left(th._call_times, t)
        for e in th.calls[i:]:
            if e.kind.startswith(prefixes):
                return e
        return None

    def server_of(self, call: Event) -> int | None:
        """Server pid for a MsgSend*-style call (see ``message_target``)."""
        return self.message_target(call)[0]

    def message_target(self, call: Event) -> tuple[int | None, Key | None, str | None]:
        """(server pid, server thread if it received the message, channel id) for a MsgSend* call.

        1. COMM events: the client's SND_MESSAGE right after the call gives the rcvid and the
           receiving pid; a REC_MESSAGE with that rcvid names the server *thread*. This works for
           connections made before the capture started.
        2. Otherwise the ConnectAttach() coid map, when the connection was made inside the trace.
        """
        key = call.key
        coid = call.arg_int("coid")
        chid = self.coid_chid.get((call.pid, coid)) if coid is not None else None
        for snd in self.comm_snd.get(key, ()):
            if snd.t_ns < call.t_ns:
                continue
            nxt = self.threads[key].calls if key in self.threads else []
            later = [c for c in nxt if c.t_ns > call.t_ns and c.kind.startswith("MSG_SEND")]
            if later and snd.t_ns > later[0].t_ns:
                break  # this SND belongs to a later MsgSend
            pid = snd.arg_int("pid")
            server_thread = None
            if (rcvid := snd.args.get("rcvid")) is not None:
                for rec in self.comm_rec.get(_norm(rcvid), ()):
                    if rec.t_ns >= snd.t_ns and rec.key is not None:
                        server_thread = rec.key
                        pid = rec.key[0]
                        break
            if pid is not None:
                return pid, server_thread, chid
            break
        if coid is None or call.pid is None:
            return None, None, chid
        return self.coid_map.get((call.pid, coid)), None, chid

    def receive_channel(self, th: ThreadInfo, t: int) -> str | None:
        """Channel a thread is RECEIVE-blocked on at ``t``: its last MsgReceive* call's chid."""
        call = self.last_call_before(th, t, ("MSG_RECEIVE",))
        if call is None or (chid := call.args.get("chid")) is None:
            return None
        return _norm(chid)


def _norm(value: str) -> str:
    """Normalise ids printed as hex or decimal ("0x0000001d", "29") to one form."""
    v = value.rstrip(",")
    try:
        return str(int(v, 0))
    except ValueError:
        return v


def irq_vector(e: Event) -> int | None:
    """Interrupt number of an INT_ENTR / INT_DELIVER / IST_ATTACH event."""
    raw = e.args.get("intr_id")
    if raw is not None:  # "0x4(4)" on QNX 8.0
        try:
            return int(raw.split("(")[0], 0)
        except ValueError:
            return None
    try:
        return int(e.kind)
    except ValueError:
        return None
