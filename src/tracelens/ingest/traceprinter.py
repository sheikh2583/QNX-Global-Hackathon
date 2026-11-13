"""Parser for ``traceprinter`` text output (QNX SDP 8.0 System Analysis Toolkit).

Expected shape (per the QNX docs; exact spacing/field names marked *verify*
until checked against a real QNX 8.0 trace)::

     -- HEADER FILE INFORMATION --
           CYCLES_PER_SEC:: 2000000000
     -- KERNEL EVENTS --
    t:0x4f81e320 CPU:00 THREAD  :THRUNNING     pid:1 tid:1
    t:0x4f81e5be CPU:00 KER_CALL:SYNC_SEM_WAIT/105 sync:0x8040 try:0
    t:0x4f8216d7 CPU:00 INT_ENTR:0x00000009 (9)       IP:0xf008433e
    t:0x4f82dc3c CPU:00 PROCESS :PROCCREATE_NAME
                          ppid:1
                           pid:12291
                          name:./server

Design choices:

* Field parsing is generic (``key:value`` pairs), so unknown event classes
  and extra fields survive instead of breaking the parser.
* Events that do not name a thread (kernel calls, user events, interrupts)
  are attributed to whichever thread was last seen RUNNING on that CPU.
* 32-bit cycle counters are unwrapped into a monotonic 64-bit timeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..events import Event

LINE_RE = re.compile(
    r"^t:0x(?P<t>[0-9a-fA-F]+)\s+CPU:\s*(?P<cpu>\d+)\s+(?P<cls>[A-Z_]+)\s*:\s*(?P<rest>.*)$"
)
HEADER_RE = re.compile(r"^\s*(?P<k>[A-Z_]+)::\s*(?P<v>.*?)\s*$")
CONT_RE = re.compile(r"^\s+(?P<k>[A-Za-z_]\w*):\s*(?P<v>.*?)\s*$")
ARG_RE = re.compile(r"([A-Za-z_]\w*):\s*(\S+)")
STR_RE = re.compile(r"\b(?:STR|str|string):\s?(?P<s>.*)$")

DEFAULT_CYCLES_PER_SEC = 1_000_000_000
_WRAP = 1 << 32

# Event classes whose pid/tid fields identify the thread the event is about.
_SELF_IDENTIFYING = {"THREAD"}


@dataclass
class ParsedTrace:
    source: str
    header: dict[str, str] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    cycles_per_sec: int = DEFAULT_CYCLES_PER_SEC
    unparsed_lines: int = 0

    @property
    def duration_ns(self) -> int:
        if not self.events:
            return 0
        return self.events[-1].t_ns - self.events[0].t_ns


def parse_file(path: str | Path) -> ParsedTrace:
    path = Path(path)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return parse_text(fh, source=str(path))


def parse_text(lines: str | Iterable[str], source: str = "<memory>") -> ParsedTrace:
    if isinstance(lines, str):
        lines = lines.splitlines()

    trace = ParsedTrace(source=source)
    raw_events: list[tuple[int, Event]] = []  # (cycles, event)
    last: Event | None = None
    wrap_hi = 0
    prev_low: int | None = None
    running: dict[int, tuple[int, int]] = {}

    for lineno, line in enumerate(lines, start=1):
        line = line.rstrip("\r\n")
        if not line.strip():
            continue

        m = LINE_RE.match(line)
        if m is None:
            if last is not None and (c := CONT_RE.match(line)):
                last.args[c["k"]] = c["v"]
                last.raw += "\n" + line
                continue
            if h := HEADER_RE.match(line):
                trace.header[h["k"]] = h["v"]
                continue
            if not line.lstrip().startswith(("--", "TRACEPRINTER", "TRACEPARSER")):
                trace.unparsed_lines += 1
            continue

        cycles = int(m["t"], 16)
        if cycles < _WRAP:  # 32-bit counter: unwrap
            if prev_low is not None and cycles < prev_low and prev_low - cycles > _WRAP // 2:
                wrap_hi += _WRAP
            prev_low = cycles
            cycles += wrap_hi

        cpu = int(m["cpu"])
        cls = m["cls"]
        rest = m["rest"].strip()
        kind, payload = _split_kind(cls, rest)

        text = ""
        if s := STR_RE.search(payload):
            text = s["s"].strip()
            payload = payload[: s.start()]
        args = dict(ARG_RE.findall(payload))

        ev = Event(
            id=len(raw_events),
            t_ns=0,
            cpu=cpu,
            cls=cls,
            kind=kind,
            args=args,
            text=text,
            line=lineno,
            raw=line,
        )

        if cls in _SELF_IDENTIFYING:
            ev.pid = ev.arg_int("pid")
            ev.tid = ev.arg_int("tid")
            if kind == "RUNNING" and ev.key is not None:
                running[cpu] = ev.key
        elif cpu in running:
            ev.pid, ev.tid = running[cpu]

        raw_events.append((cycles, ev))
        last = ev

    cps_text = trace.header.get("CYCLES_PER_SEC", "")
    try:
        trace.cycles_per_sec = int(cps_text.split()[0]) if cps_text else DEFAULT_CYCLES_PER_SEC
    except ValueError:
        trace.cycles_per_sec = DEFAULT_CYCLES_PER_SEC

    if raw_events:
        base = raw_events[0][0]
        cps = trace.cycles_per_sec
        for cycles, ev in raw_events:
            ev.t_ns = (cycles - base) * 1_000_000_000 // cps
            trace.events.append(ev)
    return trace


def _split_kind(cls: str, rest: str) -> tuple[str, str]:
    """Split ``rest`` into the event kind and the remaining payload."""
    if not rest:
        return "", ""
    token, _, payload = rest.partition(" ")
    if cls in ("INT_ENTR", "INT_EXIT", "INT_HANDLER_ENTR", "INT_HANDLER_EXIT"):
        try:
            return str(int(token, 16)), payload
        except ValueError:
            return token, payload
    kind = token.split("/", 1)[0]
    if cls == "THREAD" and kind.startswith("TH"):
        kind = kind[2:]
        if kind == "DESTROY":
            kind = "DEAD"
    return kind, payload
