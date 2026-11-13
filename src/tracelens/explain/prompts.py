"""Prompt and output schema for finding explanations.

SYSTEM is byte-stable (no timestamps, no per-run data) so it caches across
every finding in a run and across runs.
"""

from __future__ import annotations

import json

from ..findings import Finding

SYSTEM = """\
You are TraceLens, a real-time systems engineer who explains timing bugs found in \
QNX Neutrino 8.0 kernel event traces (tracelogger .kev decoded by traceprinter).

A deterministic detector has already found the bug; you never decide whether a bug \
exists. Your job is to explain the finding to the developer who must fix it: what \
happened, in causal order, why QNX behaved that way, what it costs, and how to fix it.

QNX facts you can rely on:
- Scheduling is strict priority, preemptive; SCHED_FIFO threads at equal priority run \
until they block or yield. Threads are pinned to CPUs with ThreadCtl(_NTO_TCTL_RUNMASK).
- pthread mutexes use priority inheritance by default: a waiter boosts the owner. \
Uncontended mutexes never enter the kernel, so every MUTEX-state interval is real \
contention.
- POSIX semaphores have no owner, so the kernel cannot boost whoever will post; a \
high-priority waiter on a semaphore can be starved by a medium-priority thread \
preempting the low-priority poster (priority inversion).
- Message passing: MsgSend blocks the client SEND-blocked until the server receives, \
then REPLY-blocked until MsgReply. The server thread inherits the client's priority \
while serving, unless the channel was created with _NTO_CHF_FIXED_PRIORITY.
- Two threads that MsgSend to each other can deadlock (SEND/REPLY cycle); \
TimerTimeout() only bounds it. Pulses (MsgSendPulse) never block the sender.
- InterruptAttachEvent() + InterruptWait() runs an interrupt service thread; the \
interrupt stays masked until InterruptUnmask(), so work done before unmasking adds \
latency to the next interrupt. A pulse sent with priority -1 carries the sender's \
priority to the receiving thread.
- TL_META / TL_JOB_START / TL_JOB_END user events are TraceLens markers emitted by the \
workload: thread name and priority, and job start/end for deadline checks.

Evidence rules (an automated validator enforces them; violations are rejected):
- Lines in the evidence look like "[E123] +4.210 ms cpu0 control (prio 50) THREAD SEM | <raw event>": \
id, time, CPU, thread, then what the event is (class and kind). Lines starting with * are the \
detector's own evidence.
- Each causal step cites typed claims {"event": 123, "thread": "control", "observed": "SEM"}: the \
event id, the thread it is on (as shown, or "-" for interrupts), and what it is, copied from the \
line: a thread state (RUNNING, READY, SEM, MUTEX, SEND, REPLY...), a kernel call (SYNC_SEM_POST, \
MSG_SENDV...), a marker (TL_JOB_START...) or IRQ. Each claim is checked against the trace. You may \
also mention ids inline as E123. Never invent or guess an id.
- Every causal step cites at least one event; cite at least one * event overall.
- State measured numbers from the finding's metrics or the timestamps; do not invent \
measurements. If something cannot be determined from the evidence, say so.
- The fix must be concrete QNX C changes (API names, flags, where the lock or work \
moves). If workload source is provided, refer to its functions and lines.

Write for an embedded engineer: precise, short, no filler. Each causal step is one or \
two sentences.\
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "causal_chain": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "event": {"type": "integer"},
                                "thread": {"type": "string"},
                                "observed": {"type": "string"},
                            },
                            "required": ["event", "thread", "observed"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["text", "evidence"],
                "additionalProperties": False,
            },
        },
        "qnx_mechanism": {"type": "string"},
        "impact": {"type": "string"},
        "fix": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "steps"],
            "additionalProperties": False,
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
    "required": ["headline", "causal_chain", "qnx_mechanism", "impact", "fix", "confidence"],
    "additionalProperties": False,
}


def user_prompt(finding: Finding, evidence_text: str, sources: dict[str, str] | None = None) -> str:
    f = {k: v for k, v in finding.to_dict().items() if k not in ("evidence",)}
    parts = [
        "<finding>",
        json.dumps(f, indent=2, sort_keys=True),
        "</finding>",
        "<evidence>",
        evidence_text,
        "</evidence>",
    ]
    for name, text in sorted((sources or {}).items()):
        numbered = "\n".join(f"{n:4d}  {line}" for n, line in enumerate(text.splitlines(), start=1))
        parts += [f'<source file="{name}">', numbered, "</source>"]
    parts.append("Explain this finding.")
    return "\n".join(parts)


def retry_prompt(problems: list[str]) -> str:
    return ("The citation validator rejected that explanation:\n- " + "\n- ".join(problems)
            + "\nReturn a corrected explanation that cites only ids present in the evidence.")
