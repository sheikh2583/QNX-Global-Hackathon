"""Mutex contention hotspots.

QNX mutexes are acquired in user space when uncontended; a thread only enters
the kernel (SyncMutexLock -> MUTEX state) when it has to wait. So every MUTEX
interval in the trace is real contention, keyed by the sync object address.
"""

from __future__ import annotations

from ..config import Config
from ..findings import Finding
from ..model.trace import TraceModel
from ._util import fmt_ms, ms, percentile, union_ns

QNX_NOTE = ("Every MUTEX-state interval is real contention: uncontended QNX mutexes never enter "
            "the kernel. Shrink the critical section (copy outside the lock), split the lock "
            "per resource, or hand buffers between threads with message passing.")


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    t = cfg.thresholds
    waits: dict[str, list] = {}
    for th in model.threads.values():
        for iv in th.intervals:
            if iv.state != "MUTEX":
                continue
            call = model.last_call_before(th, iv.start, ("SYNC_MUTEX_LOCK",))
            addr = call.args.get("sync") if call else None
            if addr is None:
                continue
            waits.setdefault(addr, []).append((iv, th, call))

    window = max(1, model.t_end - model.t_start)
    findings = []
    for addr, items in waits.items():
        durs = [iv.duration for iv, _, _ in items]
        p99 = percentile(durs, 99)
        union = union_ns((iv.start, iv.end) for iv, _, _ in items)  # concurrent waits count once
        share = union / window
        rate = len(items) / (window / 1e9)
        if len(items) < t.contention_min_waits:
            continue
        if share < t.contention_min_share and p99 < t.contention_p99_wait_us * 1000:
            continue  # short, rare waits: the mutex is doing its job (e.g. inheritance working)
        total = sum(durs)
        holders = {e.key for e in model.sync_ops.get(addr, ())
                   if e.kind.startswith("SYNC_MUTEX_UNLOCK") and e.key is not None}
        waiters = {th.key for _, th, _ in items}
        worst = sorted(items, key=lambda x: -x[0].duration)[:3]
        findings.append(Finding(
            kind="mutex_contention",
            severity="high" if share >= 0.10 or p99 >= 2 * t.contention_p99_wait_us * 1000 else "medium",
            title=f"Mutex contention hotspot at {addr}",
            summary=(f"{len(waiters)} threads waited {len(items)} times ({rate:.0f}/s) for mutex "
                     f"{addr}; someone was waiting {share:.0%} of the time; p99 wait {fmt_ms(p99)}."),
            t_start=min(iv.start for iv, _, _ in items),
            t_end=max(iv.end for iv, _, _ in items),
            threads=sorted(model.label(k) for k in waiters | holders),
            evidence=[x for iv, _, call in worst for x in (call.id, iv.event_id)],
            metrics={
                "waits": len(items),
                "total_wait_ms": round(ms(total), 3),
                "share_of_trace": round(share, 3),
                "waits_per_sec": round(rate, 1),
                "p50_wait_ms": round(ms(percentile(durs, 50)), 3),
                "p99_wait_ms": round(ms(p99), 3),
                "max_wait_ms": round(ms(max(durs)), 3),
                "waiter_threads": len(waiters),
                "holder_threads": len(holders),
            },
            qnx_note=QNX_NOTE,
        ))
    return findings
