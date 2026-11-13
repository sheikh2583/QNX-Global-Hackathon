"""Builds traces in ``traceprinter`` text format.

Used to unit-test detectors before (and alongside) real QNX captures. The
emitted format mirrors the documented traceprinter layout; like real
traceprinter output, kernel calls and user events carry no pid/tid and are
attributed to the thread running on that CPU.
"""

from __future__ import annotations

Key = tuple[int, int]


class TraceBuilder:
    def __init__(self, cycles_per_sec: int = 1_000_000_000, name: str = "synthetic.kev"):
        self.cps = cycles_per_sec
        self.name = name
        self._events: list[tuple[float, int, str]] = []
        self._seq = 0
        self.cur: dict[int, Key] = {}

    # ---------------------------------------------------------------- low level
    def _emit(self, t_us: float, cpu: int, cls: str, body: str) -> None:
        cyc = int(round(t_us * self.cps / 1_000_000)) & 0xFFFFFFFF
        self._events.append((t_us, self._seq, f"t:0x{cyc:08x} CPU:{cpu:02d} {cls:<8}:{body}"))
        self._seq += 1

    @staticmethod
    def idle(cpu: int) -> Key:
        return (1, cpu + 1)

    def state(self, t_us: float, key: Key, state: str, cpu: int = 0) -> None:
        self._emit(t_us, cpu, "THREAD", f"TH{state:<12} pid:{key[0]} tid:{key[1]}")

    def call(self, t_us: float, cpu: int, name: str, num: int = 0, **args) -> None:
        body = " ".join(f"{k}:{v}" for k, v in args.items())
        self._emit(t_us, cpu, "KER_CALL", f"{name}/{num:02d} {body}".rstrip())

    def ret(self, t_us: float, cpu: int, name: str, num: int = 0, **args) -> None:
        body = " ".join(f"{k}:{v}" for k, v in args.items())
        self._emit(t_us, cpu, "KER_EXIT", f"{name}/{num:02d} {body}".rstrip())

    def irq(self, t_us: float, cpu: int, vector: int, exit_after_us: float = 2) -> None:
        self._emit(t_us, cpu, "INT_ENTR", f"0x{vector:08x} ({vector})       IP:0x00401000")
        self._emit(t_us + exit_after_us, cpu, "INT_EXIT", f"0x{vector:08x} ({vector}) inkernel:0x00000000")

    def user(self, t_us: float, cpu: int, text: str, code: int = 100) -> None:
        self._emit(t_us, cpu, "USREVENT", f"EVENT:{code} STR:{text}")

    def proc(self, t_us: float, pid: int, name: str, ppid: int = 1, cpu: int = 0) -> None:
        pad = " " * 22
        self._emit(t_us, cpu, "PROCESS",
                   f"PROCCREATE_NAME\n{pad}ppid:{ppid}\n{pad} pid:{pid}\n{pad}name:{name}")

    # --------------------------------------------------------------- scheduling
    def run(self, t_us: float, cpu: int, key: Key, prev_state: str = "READY") -> None:
        """Context switch on ``cpu`` to ``key``; the previous thread becomes ``prev_state``."""
        cur = self.cur.get(cpu)
        if cur is not None and cur != key:
            self.state(t_us, cur, prev_state, cpu)
        self.state(t_us, key, "RUNNING", cpu)
        self.cur[cpu] = key

    def block(self, t_us: float, cpu: int, state: str, next_key: Key | None = None) -> None:
        """Current thread on ``cpu`` blocks in ``state``; ``next_key`` (default: idle) runs."""
        cur = self.cur[cpu]
        self.state(t_us, cur, state, cpu)
        nxt = next_key or self.idle(cpu)
        self.state(t_us, nxt, "RUNNING", cpu)
        self.cur[cpu] = nxt

    def meta(self, t_us: float, cpu: int, key: Key, name: str, prio: int) -> None:
        self.run(t_us, cpu, key)
        self.user(t_us, cpu, f"TL_META name={name} prio={prio}")

    # ------------------------------------------------------------------- output
    def text(self) -> str:
        header = [
            "TRACEPRINTER version 1.02",
            "TRACEPARSER LIBRARY version 1.02",
            " -- HEADER FILE INFORMATION --",
            f"       TRACE_FILE_NAME:: {self.name}",
            f"        CYCLES_PER_SEC:: {self.cps}",
            "         TRACE_VER_MAJOR:: 1",
            " -- KERNEL EVENTS --",
        ]
        body = [line for _, _, line in sorted(self._events, key=lambda e: (e[0], e[1]))]
        return "\n".join(header + body) + "\n"
