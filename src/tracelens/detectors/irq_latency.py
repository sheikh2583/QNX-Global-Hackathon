"""Interrupt latency and handler overrun (event-driven IST model).

For each vector attached with InterruptAttachEvent()/InterruptAttach(), pair
each INT_ENTR with the handler thread's next InterruptWait() return
(latency), then measure how long the handler works before InterruptUnmask()
or its next InterruptWait() (handler time, during which the IRQ stays masked).
"""

from __future__ import annotations

from ..config import Config
from ..findings import Finding
from ..model.trace import TraceModel, irq_vector
from ._util import fmt_ms, ms, percentile, us

QNX_NOTE = ("The interrupt stays masked until the handler thread calls InterruptUnmask(). "
            "Keep the IST minimal: read/ack the device, unmask, and hand the heavy work to a "
            "lower-priority worker with MsgSendPulse().")


def detect(model: TraceModel, cfg: Config) -> list[Finding]:
    t = cfg.thresholds
    handlers: dict[int, list] = {k: list(v) for k, v in model.irq_handlers.items()}  # QNX 8.0 IST_ATTACH
    for th in model.threads.values():
        for e in th.calls:
            if e.kind.startswith("INTERRUPT_ATTACH"):
                vec = e.arg_int("intr")
                if vec is not None and th.key not in handlers.setdefault(vec, []):
                    handlers[vec].append(th.key)

    samples: dict[tuple, list] = {}
    for irq in model.irq_entries:
        vec = irq_vector(irq)
        if vec is None:
            continue
        for key in handlers.get(vec, ()):
            th = model.threads.get(key)
            if th is None:  # attached but never ran in the capture (e.g. another CPU's clock thread)
                continue
            # Only interrupts this handler could have served: on a shared, busy line (the QNX VM's serial
            # IRQ 4) deliveries before the program attached are not its latency (found by the simulator).
            if irq.t_ns < model.irq_attached_at.get((vec, key), model.t_start):
                continue
            wake = model.next_exit_after(th, irq.t_ns, ("INTERRUPT_WAIT",))
            if wake is None:
                continue
            done = model.next_call_after(th, wake.t_ns, ("INTERRUPT_UNMASK", "INTERRUPT_WAIT"))
            work = (done.t_ns - wake.t_ns) if done else None
            samples.setdefault((vec, key), []).append((irq, wake, done, wake.t_ns - irq.t_ns, work))

    # Every interrupt service thread on the target (all drivers, not just this program): deferred
    # application work must run below all of them, or it can delay some driver's interrupts.
    ist_prios = [(model.threads[k].prio, model.label(k)) for ks in handlers.values() for k in ks
                 if k in model.threads and model.threads[k].prio is not None]
    lowest_ist = min(ist_prios) if ist_prios else None

    findings = []
    for (vec, key), items in samples.items():
        lat = [s[3] for s in items]
        work = [s[4] for s in items if s[4] is not None]
        p99_lat = percentile(lat, 99)
        max_work = max(work) if work else 0
        metrics = {
            "interrupts": len(items),
            "p50_latency_us": round(us(percentile(lat, 50)), 1),
            "p99_latency_us": round(us(p99_lat), 1),
            "max_latency_us": round(us(max(lat)), 1),
            "p50_handler_us": round(us(percentile(work, 50)), 1) if work else 0,
            "p99_handler_us": round(us(percentile(work, 99)), 1) if work else 0,
            "max_handler_us": round(us(max_work), 1),
            "handler_prio": model.threads[key].prio,
            "lowest_interrupt_thread_prio": lowest_ist[0] if lowest_ist else None,
            "lowest_interrupt_thread": lowest_ist[1] if lowest_ist else None,
        }
        if us(p99_lat) > t.irq_max_latency_us:
            worst = max(items, key=lambda s: s[3])
            findings.append(Finding(
                kind="irq_latency",
                severity="high",
                title=f"Slow interrupt response on IRQ {vec}",
                summary=(f"Handler {model.describe(key)} took p99 {us(p99_lat):.0f} us to start "
                         f"after IRQ {vec} (budget {t.irq_max_latency_us:.0f} us)."),
                t_start=worst[0].t_ns, t_end=worst[1].t_ns,
                threads=[model.label(key)],
                evidence=[worst[0].id, worst[1].id],
                metrics=metrics, qnx_note=QNX_NOTE,
            ))
        median_over = bool(work) and t.irq_median_handler_us > 0 and us(percentile(work, 50)) > t.irq_median_handler_us
        if work and (us(max_work) > t.irq_max_handler_us or median_over):
            worst = max((s for s in items if s[4] is not None), key=lambda s: s[4])
            over = sum(1 for w in work if us(w) > t.irq_max_handler_us)
            p99_work = percentile(work, 99)
            # Systematic (p99 over budget) or gross (> 2x budget) overruns fail the gate. A rare,
            # small one is reported at MEDIUM: on the QEMU VM the reference handler (p99 81 us)
            # once ran 564 us in 9,686 interrupts, which is vCPU noise, not a code defect (measured).
            systematic = (median_over or us(p99_work) > t.irq_max_handler_us
                          or us(max_work) > 2 * t.irq_max_handler_us)
            findings.append(Finding(
                kind="irq_handler_overrun",
                severity="high" if systematic else "medium",
                title=f"Interrupt handler overrun on IRQ {vec}",
                summary=(f"Handler {model.describe(key)} kept IRQ {vec} masked for up to "
                         f"{fmt_ms(max_work)} ({over}/{len(work)} interrupts over the "
                         f"{t.irq_max_handler_us:.0f} us budget)."
                         + (f" The median handler time is {us(percentile(work, 50)):.0f} us "
                            f"(budget {t.irq_median_handler_us:.0f} us)." if median_over else "")
                         + ("" if systematic else
                            f" Isolated: p99 handler time is {us(p99_work):.0f} us, within budget.")),
                t_start=worst[1].t_ns, t_end=worst[2].t_ns,
                threads=[model.label(key)],
                evidence=[worst[0].id, worst[1].id, worst[2].id],
                metrics={**metrics, "overruns": over, "max_handler_ms": round(ms(max_work), 3)},
                qnx_note=QNX_NOTE,
            ))
    return findings
