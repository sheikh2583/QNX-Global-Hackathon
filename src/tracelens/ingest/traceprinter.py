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
* 32-bit cycle counters are unwrapped into a monotonic 64-bit timeline: any
  backwards step larger than cross-CPU reordering is a wrap; CONTROL TIME
  events, when present, supply the high bits directly.
* Events are stably sorted by time (per-CPU buffers interleave).
* A trace without a clock rate is rejected rather than assumed to be 1 GHz.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Iterable

from ..events import Event

LINE_RE = re.compile(
    r"^t:0x(?P<t>[0-9a-fA-F]+)\s+CPU:\s*(?P<cpu>\d+)\s+(?P<cls>[A-Z_]+)\s*:\s*(?P<rest>.*)$"
)
HEADER_RE = re.compile(r"^\s*(?P<k>[A-Z_]+)::\s*(?P<v>.*?)\s*$")
# Continuation lines carry one key:value each; real QNX 8.0 keys include "sig_blocked->bits[0]".
# traceprinter right-aligns keys, so long ones ("event->sigev_notify_function_p") start at column 0.
CONT_RE = re.compile(r"^\s*(?P<k>[^\s:][^:]*?):\s*(?P<v>.*?)\s*$")
ARG_RE = re.compile(r"([A-Za-z_]\w*):\s*(\S+)")
EQ_ARG_RE = re.compile(r"([A-Za-z_]\w*)\s=\s([^,]+)")  # "target_cpu = 2, ipicmd = 0x000001 RESCHED"
# QNX 8.0 (verified): STR:"TL_META name=x", d0:0x... ; older docs show an unquoted string.
STR_RE = re.compile(r'\b(?:STR|str|string):\s?(?:"(?P<q>[^"]*)"|(?P<s>.*))')
ARG_ALIASES = {"sync_p": "sync"}  # QNX 8.0 names the sync object address sync_p

_WRAP = 1 << 32

# Event classes whose pid/tid fields identify the thread the event is about.
_SELF_IDENTIFYING = {"THREAD"}


class TraceFormatError(ValueError):
    """The trace cannot be interpreted safely (e.g. no clock rate)."""


@dataclass
class ParsedTrace:
    source: str
    header: dict[str, str] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    cycles_per_sec: int = 0
    unparsed_lines: int = 0
    wraps: int = 0  # 32-bit counter wraps unwrapped
    reordered: int = 0  # events that arrived out of time order (cross-CPU) and were sorted
    max_reorder_ns: int = 0
    issues: list[str] = field(default_factory=list)  # human-readable parse warnings

    @property
    def duration_ns(self) -> int:
        if not self.events:
            return 0
        return self.events[-1].t_ns - self.events[0].t_ns


def parse_file(path: str | Path, cycles_per_sec: int | None = None) -> ParsedTrace:
    """Parse a traceprinter text file; ``.gz`` files (committed real captures) are read directly."""
    path = Path(path)
    if path.suffix == ".gz":
        import gzip
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
            return parse_text(fh, source=str(path), cycles_per_sec=cycles_per_sec)
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        return parse_text(fh, source=str(path), cycles_per_sec=cycles_per_sec)


def _header_cps(header: dict[str, str]) -> int | None:
    # QNX 8.0 traceprinter (verified) writes TRACE_CYCLES_PER_SEC.
    text = (header.get("TRACE_CYCLES_PER_SEC") or header.get("CYCLES_PER_SEC", "")).split()
    try:
        value = int(text[0]) if text else 0
    except ValueError:
        return None
    return value if value > 0 else None


def parse_text(lines: str | Iterable[str], source: str = "<memory>",
               cycles_per_sec: int | None = None) -> ParsedTrace:
    """Parse traceprinter text.

    ``cycles_per_sec`` overrides the header value; without either the parse
    fails loudly, because every timing in the trace would be wrong.
    """
    if isinstance(lines, str):
        lines = lines.splitlines()

    trace = ParsedTrace(source=source)
    raw_events: list[tuple[int, Event]] = []  # (cycles, event)
    last: Event | None = None
    wrap_hi = 0
    high_low: int | None = None  # highest low-32-bit value seen in the current wrap epoch
    running: dict[int, tuple[int, int]] = {}

    for lineno, line in enumerate(lines, start=1):
        line = line.rstrip("\r\n")
        if not line.strip():
            continue

        m = LINE_RE.match(line)
        if m is None:
            if last is not None and line.lstrip().startswith('"'):
                last.raw += "\n" + line  # wrapped tail of a quoted string argument (seen on QNX 8.0)
                continue
            if last is not None and (c := CONT_RE.match(line)):
                k = c["k"].strip()
                last.args[k] = c["v"]
                if k in ARG_ALIASES:
                    last.args.setdefault(ARG_ALIASES[k], c["v"])
                last.raw += "\n" + line
                continue
            if h := HEADER_RE.match(line):
                trace.header[h["k"]] = h["v"]
                continue
            if not line.lstrip().startswith(("--", "TRACEPRINTER", "TRACEPARSER")):
                trace.unparsed_lines += 1
            continue

        cpu = int(m["cpu"])
        cls = m["cls"]
        rest = m["rest"].strip()
        kind, payload = _split_kind(cls, rest)
        text = ""
        if s := STR_RE.search(payload):
            text = (s["q"] if s["q"] is not None else s["s"]).strip()
            payload = payload[: s.start()] + (payload[s.end():] if s["q"] is not None else "")
        args = dict(ARG_RE.findall(payload))
        for k, v in EQ_ARG_RE.findall(payload):
            args.setdefault(k, v.strip())
        for k, alias in ARG_ALIASES.items():
            if k in args:
                args.setdefault(alias, args[k])

        cycles = int(m["t"], 16)
        if cls == "CONTROL" and kind == "TIME":
            # CONTROL TIME events carry the counter's high bits (verify field names on QNX 8.0).
            msb = _hex(args.get("msb") or args.get("hi") or args.get("high"))
            if msb is not None:
                wrap_hi = msb << 32
                high_low = cycles if cycles < _WRAP else None
        if cycles < _WRAP:  # 32-bit counter: unwrap
            cps_now = cycles_per_sec or _header_cps(trace.header) or 1_000_000_000
            tolerance = max(cps_now // 1000, 1 << 16)  # cross-CPU reordering is far below 1 ms
            if high_low is not None and cycles < high_low and high_low - cycles > tolerance:
                wrap_hi += _WRAP  # any real step backwards is a wrap, however long the gap
                trace.wraps += 1
                high_low = cycles
            else:
                high_low = cycles if high_low is None else max(high_low, cycles)
            cycles += wrap_hi

        ev = Event(id=len(raw_events), t_ns=0, cpu=cpu, cls=cls, kind=kind, args=args,
                   text=text, line=lineno, raw=line)

        if cls in _SELF_IDENTIFYING:
            ev.pid = ev.arg_int("pid")
            ev.tid = ev.arg_int("tid")
            if kind == "RUNNING" and ev.key is not None:
                running[cpu] = ev.key
        elif cpu in running:
            ev.pid, ev.tid = running[cpu]

        raw_events.append((cycles, ev))
        last = ev

    cps = cycles_per_sec or _header_cps(trace.header)
    if cps is None:
        if raw_events:
            raise TraceFormatError(
                f"{source}: no valid CYCLES_PER_SEC in the trace header; refusing to guess the clock "
                "rate (pass --cycles-per-sec)")
        cps = 1_000_000_000
    trace.cycles_per_sec = cps

    if raw_events:
        # Per-CPU buffers interleave: sort by time, keeping file order for ties.
        latest = raw_events[0][0]
        for cycles, _ in raw_events:
            if cycles < latest:
                trace.reordered += 1
                trace.max_reorder_ns = max(trace.max_reorder_ns, (latest - cycles) * 1_000_000_000 // cps)
            latest = max(latest, cycles)
        raw_events.sort(key=lambda ce: (ce[0], ce[1].id))
        base = raw_events[0][0]
        for cycles, ev in raw_events:
            ev.t_ns = (cycles - base) * 1_000_000_000 // cps
            trace.events.append(ev)
    if trace.reordered:
        trace.issues.append(f"{trace.reordered} events arrived out of time order "
                            f"(max {trace.max_reorder_ns / 1000:.1f} us) and were sorted")
    if trace.wraps:
        trace.issues.append(f"32-bit cycle counter wrapped {trace.wraps}x; gaps of 2^32 cycles or more "
                            "cannot be recovered without CONTROL TIME events")
    return trace


def _hex(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.rstrip(","), 0)
    except ValueError:
        return None


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
