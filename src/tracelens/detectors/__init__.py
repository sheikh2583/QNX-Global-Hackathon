"""Deterministic detectors. Each is ``detect(model, cfg) -> list[Finding]``.

Nothing else creates findings: the remedies and the fix loop act only on what these rules prove.
"""

from . import deadline, ipc_chain, irq_latency, lost_wakeup, mutex_contention, prio_inversion, stuck_job

ALL = [
    ("priority_inversion", prio_inversion.detect),
    ("ipc_chain", ipc_chain.detect),
    ("mutex_contention", mutex_contention.detect),
    ("irq_latency", irq_latency.detect),
    ("lost_wakeup", lost_wakeup.detect),
    ("deadline", deadline.detect),
    ("stuck_job", stuck_job.detect),
]
