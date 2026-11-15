"""Features for learning: one vector per (thread, time window) of a QNX kernel trace.

Everything is normalised by the window length, so traces of any length and any program mix. Thread
names, process names and absolute priorities are never features: a model must learn behaviour, not
memorise our programs. The inversion signal is generic: time a thread was blocked (on any sync object
or message) while a lower-priority thread held its CPU (same program or not).
"""

from __future__ import annotations

import bisect
from collections import defaultdict

from ..model.trace import IPC_STATES, SYNC_STATES, TraceModel

WINDOW_NS = 20_000_000  # two periods of a 10 ms control loop
SLEEP_STATES = {"NANOSLEEP", "RECEIVE", "SIGWAITINFO", "STOPPED", "JOIN", "WAITPAGE"}
FEATURES = [
    "share_running", "share_ready", "share_sem", "share_mutex", "share_condvar", "share_send", "share_reply",
    "share_intr", "share_sleep",
    "max_block_frac", "max_ready_frac", "max_run_frac", "intr_masked_frac", "blocks_per_ms", "preempts_per_ms",
    "inversion_frac", "prio_rank", "migrations_per_ms", "cpus_used",
]
SYSTEM_PROCS = {"procnto", "procnto-smp-instr", "slogger2", "tracelogger", "pidin", "sshd", "ksh", "sh", "io-sock",
                "devc-ser8250", "devb-eide", "pci-server", "devc-pty", "dumper", "pipe", "mqueue", "random", "io-usb-otg",
                "qconn", "inetd", "devb-ram", "usblauncher_otg", "dhcpcd", "ls", "sleep", "cat"}


def workload_keys(m: TraceModel) -> list[tuple[int, int]]:
    """Threads of the program under test: processes that wrote TraceLens markers, else every
    non-system process."""
    marked = {k[0] for k, th in m.threads.items() if th.user}
    if marked:
        return sorted(k for k in m.threads if k[0] in marked)
    return sorted(k for k in m.threads if k[0] != 1 and (m.proc_names.get(k[0]) or "") not in SYSTEM_PROCS)


class _CpuIndex:
    """RUNNING intervals per CPU, sorted, for 'who held this CPU' queries."""

    def __init__(self, m: TraceModel):
        per = defaultdict(list)
        for k, th in m.threads.items():
            for iv in th.intervals:
                if iv.state == "RUNNING" and iv.cpu >= 0:
                    per[iv.cpu].append((iv.start, iv.end, k))
        self.per = {c: sorted(v) for c, v in per.items()}
        self.starts = {c: [s for s, _, _ in v] for c, v in self.per.items()}

    def running(self, cpu: int, a: int, b: int):
        lst, st = self.per.get(cpu, []), self.starts.get(cpu, [])
        i = max(0, bisect.bisect_left(st, a) - 64)  # intervals that began a little before a
        for s, e, k in lst[i:]:
            if s >= b:
                break
            if e > a:
                yield max(s, a), min(e, b), k


def masked_spans(th) -> list[tuple[int, int]]:
    """When this thread held an interrupt masked: from each InterruptWait() returning (the kernel masks
    the line before waking the handler) to its InterruptUnmask(), or to its next wait if it never
    unmasked. This is the one thing that separates a handler doing its work on the device's time from
    one that unmasked first and deferred: both can hold a CPU for milliseconds (QNX 8.0 semantics,
    and the difference between the Z5 bug and its reference fix)."""
    waits = sorted(e.t_ns for e in th.exits if e.kind.startswith("INTERRUPT_WAIT"))
    if not waits:
        return []
    ends = sorted(e.t_ns for e in th.calls if e.kind.startswith(("INTERRUPT_UNMASK", "INTERRUPT_WAIT")))
    out, j = [], 0
    for i, w in enumerate(waits):
        while j < len(ends) and ends[j] <= w:
            j += 1
        nxt = waits[i + 1] if i + 1 < len(waits) else None
        end = ends[j] if j < len(ends) else nxt
        if end is None:
            continue
        if nxt is not None:
            end = min(end, nxt)
        if end > w:
            out.append((w, end))
    return out


def _prio(m: TraceModel, key, t):
    th = m.threads.get(key)
    if th is None:
        return None
    p = th.prio_at(t)
    return p if p is not None else th.prio


def windows(m: TraceModel, keys=None, window_ns: int = WINDOW_NS, trim_edges: bool = True):
    """Yield (key, t0, t1, features) for every window in which the thread did anything.
    ``trim_edges``: skip each thread's first and last window (creating, joining and exiting threads
    look unusual and say nothing about real-time behaviour; seen on real traces)."""
    keys = keys if keys is not None else workload_keys(m)
    if not keys:
        return
    cpu = _CpuIndex(m)
    prios = sorted({p for k in keys if (p := m.threads[k].prio) is not None})
    span = max(1, m.t_end - m.t_start)
    n_win = max(1, span // window_ns)
    for key in keys:
        th = m.threads[key]
        ivs = sorted(th.intervals, key=lambda iv: iv.start)
        if not ivs:
            continue
        rank = (prios.index(th.prio) / max(1, len(prios) - 1)) if th.prio in prios and len(prios) > 1 else 0.5
        masked = masked_spans(th)
        life0, life1 = ivs[0].start, max(iv.end for iv in ivs)
        j = 0
        for w in range(n_win):
            a = m.t_start + w * window_ns
            b = a + window_ns
            if trim_edges and (a < life0 + window_ns or b > life1 - window_ns):
                continue
            while j < len(ivs) and ivs[j].end <= a:
                j += 1
            acc = defaultdict(int)
            for ms0, ms1 in masked:
                if ms0 >= b:
                    break
                if ms1 > a:
                    acc["masked"] += min(ms1, b) - max(ms0, a)
            max_block = max_ready = max_run = blocks = preempts = inversion = migrations = 0
            cpus, last_cpu, active = set(), None, False
            for iv in ivs[j:]:
                if iv.start >= b:
                    break
                lo, hi = max(iv.start, a), min(iv.end, b)
                if hi <= lo:
                    continue
                d = hi - lo
                st = iv.state
                if st == "RUNNING":
                    acc["running"] += d
                    max_run = max(max_run, iv.duration)
                    active = True
                    if iv.cpu >= 0:
                        cpus.add(iv.cpu)
                        if last_cpu is not None and iv.cpu != last_cpu:
                            migrations += 1
                        last_cpu = iv.cpu
                elif st == "READY":
                    acc["ready"] += d
                    max_ready = max(max_ready, iv.duration)
                    preempts += iv.start >= a
                    active = True
                elif st in SYNC_STATES or st in IPC_STATES or st == "INTR":
                    acc[st.lower()] += d
                    max_block = max(max_block, iv.duration)
                    blocks += iv.start >= a
                    # A thread blocked through the whole window is activity only when it is stuck on another
                    # thread (sync object, unanswered send: a deadlock looks like this). Waiting through a whole
                    # window for a reply or an interrupt is how idle I/O looks (shell threads, real QNX).
                    active = active or iv.start >= a or iv.end < b or st not in ("REPLY", "INTR")
                    if st != "INTR" and iv.cpu >= 0:
                        mine = _prio(m, key, lo)
                        for s, e, k in cpu.running(iv.cpu, lo, hi):
                            if k != key and k[0] != 1:  # any other thread but the kernel's idle/system threads
                                p = _prio(m, k, s)
                                if mine is not None and p is not None and p < mine:
                                    inversion += e - s
                elif st in SLEEP_STATES:
                    acc["sleep"] += d
            if not active:
                continue
            ms = window_ns / 1e6
            f = {
                "share_running": acc["running"] / window_ns, "share_ready": acc["ready"] / window_ns,
                "share_sem": acc["sem"] / window_ns, "share_mutex": acc["mutex"] / window_ns,
                "share_condvar": acc["condvar"] / window_ns, "share_send": acc["send"] / window_ns,
                "share_reply": acc["reply"] / window_ns, "share_intr": acc["intr"] / window_ns,
                "share_sleep": acc["sleep"] / window_ns,
                # a block longer than the window counts as the whole window: beyond that the value says
                # nothing (a shell thread REPLY-blocked for a second scored 50 before this, real QNX)
                "max_block_frac": min(max_block / window_ns, 1.0), "max_ready_frac": min(max_ready / window_ns, 1.0),
                # longest single CPU burst: how long this thread held a CPU without being interrupted.
                # The signature of an interrupt handler that keeps its line masked (real Z5: 2.4 ms vs
                # 7 us for the same handler fixed), a lock holder, and a CPU hog. Nothing else saw it.
                "max_run_frac": min(max_run / window_ns, 1.0),
                "intr_masked_frac": min(acc["masked"] / window_ns, 1.0),
                "blocks_per_ms": blocks / ms, "preempts_per_ms": preempts / ms,
                "inversion_frac": inversion / window_ns, "prio_rank": rank,
                "migrations_per_ms": migrations / ms, "cpus_used": float(len(cpus)),
            }
            yield key, a, b, f


def vector(f: dict) -> list[float]:
    return [float(f[name]) for name in FEATURES]
