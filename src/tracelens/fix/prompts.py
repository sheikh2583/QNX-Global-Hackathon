"""Prompt and output schema for the fix agent."""

from __future__ import annotations

import json

SYSTEM = """\
You are TraceLens's fix agent: a senior QNX Neutrino 8.0 real-time engineer. You repair \
timing bugs in small C workloads that run on a real QNX target under the instrumented \
kernel. Your patch is compiled with qcc, deployed, run several times under tracelogger, \
and re-analyzed by deterministic detectors. It counts only if the bug's findings vanish \
in every run, no new findings appear, and deadlines are met. You cannot touch the \
detectors, the tests, or any file outside the workload.

QNX facts you can rely on:
- Strict priority preemptive scheduling; SCHED_FIFO threads pinned with ThreadCtl(_NTO_TCTL_RUNMASK).
- pthread mutexes inherit priority by default (PTHREAD_PRIO_INHERIT); uncontended locking stays in \
user space. Semaphores and condition variables have no owner, so nothing is boosted.
- A server thread runs at its client's priority while serving a message, unless the channel was \
created with _NTO_CHF_FIXED_PRIORITY.
- Two servers that MsgSend to each other can deadlock; MsgSendPulse never blocks the sender. \
TimerTimeout only bounds a wait.
- With InterruptAttachEvent + InterruptWait, the interrupt stays masked until InterruptUnmask; \
work done before unmasking delays the next interrupt. A pulse sent with priority -1 carries the \
sender's priority to the receiver.

Rules:
- Fix the cause the evidence points to, with the smallest change that removes it. Keep the \
program's behaviour, timing requirements, thread structure, priorities, CPU pinning and \
TraceEvent markers (TL_META, TL_JOB_START, TL_JOB_END) unless they are the bug.
- Never weaken a requirement to make a check pass (no longer budgets, no removed work, no \
lowered load, no deleted markers).
- Return complete file contents for every file you change, only files listed as editable.
- The code must compile cleanly with qcc (gcc 12, -std=gnu11 -Wall -Wextra).\
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "diagnosis": {"type": "string"},
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                "required": ["path", "content"],
                "additionalProperties": False,
            },
        },
        "expected_effect": {"type": "string"},
    },
    "required": ["diagnosis", "changes", "expected_effect"],
    "additionalProperties": False,
}


def _numbered(text: str) -> str:
    return "\n".join(f"{n:4d}  {line}" for n, line in enumerate(text.splitlines(), start=1))


def first_prompt(editable: dict[str, str], readonly: dict[str, str], findings: list[dict] | None,
                 evidence: dict[str, str] | None) -> str:
    """``findings``/``evidence`` are None in the source-only ablation."""
    parts = []
    for name, text in sorted(editable.items()):
        parts += [f'<file path="{name}" editable="yes">', _numbered(text), "</file>"]
    for name, text in sorted(readonly.items()):
        parts += [f'<file path="{name}" editable="no">', _numbered(text), "</file>"]
    if findings is None:
        parts.append("This workload has a real-time bug on QNX. Find it from the source alone and fix it.")
    else:
        parts.append("<findings>")
        for f in findings:
            parts.append(json.dumps({k: f[k] for k in ("id", "kind", "severity", "title", "summary",
                                                       "metrics", "qnx_note") if k in f}, sort_keys=True))
            if evidence and f.get("id") in evidence:
                parts += [f'<evidence finding="{f["id"]}">', evidence[f["id"]], "</evidence>"]
        parts.append("</findings>")
        parts.append("These findings come from kernel traces of the current build. Fix their cause.")
    return "\n".join(parts)


def build_failed(log: str) -> str:
    return ("The patch did not compile. Compiler output:\n<build_log>\n" + log[-6000:] +
            "\n</build_log>\nReturn a corrected patch (complete file contents).")


def scope_failed(error: str) -> str:
    return f"The patch was rejected by the guardrails: {error}\nReturn a patch that only changes editable files."


def verdict_failed(reasons: list[str], after_findings: list[dict]) -> str:
    lines = ["The patch compiled and ran, but the before/after verdict is NOT FIXED:"]
    lines += [f"- {r}" for r in reasons]
    if after_findings:
        lines.append("Findings in the patched runs:")
        lines += [json.dumps({k: f[k] for k in ("kind", "severity", "summary") if k in f}) for f in after_findings]
    lines.append("Return a new patch against the ORIGINAL files (complete file contents).")
    return "\n".join(lines)
