"""A discrete-event model of the QNX 8.0 scheduler that writes ``traceprinter`` text.

Why: labelled kernel traces are the fuel for TraceLens's learning phase, and a real QNX target gives
about one trace every 10 seconds. The simulator gives unlimited labelled traces on a laptop, in the
exact text format of a real QNX 8.0 capture (header, 64-bit cycle stamps, continuation lines), so
every downstream piece (parser, detectors, features, models) runs on it unchanged. Real captures
stay the ground truth: the sim-to-real gap is measured, not assumed (docs/ml/DESIGN.md).

What is modelled (each item mirrors behaviour measured on the QNX 8.0 VM, PLAN.md section 15):
  * N CPUs, preemptive fixed-priority scheduling (FIFO among equals; a preempted thread goes to the
    head of its priority queue), CPU run masks, one idle thread per CPU (pid 1, prio 0)
  * timers fire on 1 ms tick boundaries through the clock interrupt thread (pid 1, prio 254, CPU 0),
    optionally whole ticks late (a per-run platform knob)
  * semaphores (no owner, no inheritance); mutexes with priority inheritance, kernel calls only
    when contended, ownership handed to the best waiter; condition variables; timed waits
  * message passing: MsgSend / MsgReceive / MsgReply with server priority inheritance unless the
    channel is _NTO_CHF_FIXED_PRIORITY; COMM SND/REC/REPLY events; send timeouts (TimerTimeout)
  * interrupts: Poisson arrivals, masked until InterruptUnmask(), latched while masked
  * background system threads (drivers, loggers) with random short bursts
  * busy loops measure wall-clock time, like tl_spin_us(): a preempted spin may finish at once

What is not: caches, memory, vCPU stalls, the kernel's own preemption points, adaptive
partitioning. Every trace says it is simulated (TRACE_SIMULATED header line).
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass

TICK_NS = 1_000_000
FIFO, RR, IST_POLICY = 1, 2, 8
ETIMEDOUT = 260  # QNX errno
_MSG = '"" (0x00000001 0x00000000 0x00000000)'


@dataclass
class Knobs:
    """Platform behaviour for one run. ``random()`` draws them (domain randomisation): a model trained
    on many platforms is less likely to learn one simulator's quirks."""
    ncpu: int = 4
    cycles_per_sec: int = 2_419_562_295  # measured on the QEMU guest
    kcall_ns: tuple[int, int] = (500, 2500)  # cost of one kernel call
    ctx_ns: tuple[int, int] = (300, 1500)  # from THRUNNING to the thread's first instruction
    late_ticks: int = 0  # whole extra ticks before a timer fires (QEMU: often one)
    clock_ist_ns: tuple[int, int] = (2000, 9000)  # clock interrupt thread work per tick
    noise: float = 1.0  # background system activity scale
    irq_rate_hz: float = 4000.0  # device interrupt rate on a busy line

    @classmethod
    def random(cls, rng: random.Random) -> Knobs:
        return cls(cycles_per_sec=rng.choice([2_419_562_295, 2_419_200_064, 1_999_999_870, 2_904_002_112]),
                   kcall_ns=(rng.randint(300, 800), rng.randint(1500, 4000)),
                   ctx_ns=(rng.randint(150, 500), rng.randint(900, 2500)),
                   late_ticks=rng.choice([0, 1, 1]), clock_ist_ns=(rng.randint(1000, 3000), rng.randint(5000, 15000)),
                   noise=rng.uniform(0.3, 2.5), irq_rate_hz=rng.uniform(1500, 6500))


class Proc:
    def __init__(self, pid: int, name: str):
        self.pid, self.name, self.ntid = pid, name, 0


class Thread:
    def __init__(self, proc: Proc, tid: int, prio: int, policy: int = FIFO, mask=None, gen=None):
        self.proc, self.pid, self.tid = proc, proc.pid, tid
        self.base = self.prio = prio
        self.policy, self.mask, self.gen = policy, mask, gen
        self.state = "READY"
        self.result = None
        self.cpu: int | None = None
        self.last_cpu: int | None = None
        self.version = 0
        self.spin_end: int | None = None
        self.work_left = 0
        self.run_start = 0
        self.pending: list[tuple] = []  # events emitted when the thread next runs (e.g. KER_EXIT)
        self.held: list[Mutex] = []
        self.blocked_on = None
        self.wait_list: list | None = None
        self.wait_token = 0
        self.wait_seq = 0
        self.enq = 0
        self.joiners: list[Thread] = []
        self.dead = False
        self.lock_exit = None
        self.on_exit = None


class Sem:
    def __init__(self, addr: int, count: int):
        self.addr, self.count, self.waiters = addr, count, []


class Mutex:
    def __init__(self, addr: int, pi: bool = True):
        self.addr, self.pi, self.owner, self.waiters = addr, pi, None, []


class CondVar:
    def __init__(self, addr: int):
        self.addr, self.waiters = addr, []


class Channel:
    def __init__(self, chid: int, proc: Proc, fixed: bool):
        self.chid, self.proc, self.fixed = chid, proc, fixed
        self.receivers: list[Thread] = []
        self.sendq: list[Request] = []


class Conn:
    def __init__(self, coid: int, chan: Channel):
        self.coid, self.chan = coid, chan


class Request:
    def __init__(self, rcvid: str, client: Thread, chan: Channel):
        self.rcvid, self.client, self.chan = rcvid, client, chan
        self.token = 0
        self.done = False


class Irq:
    """An interrupt line. Several handler threads may attach to one line (on the QNX VM, IRQ 4 is
    shared by the serial driver and the program under test, measured): each attachment is masked
    from its delivery until its own InterruptUnmask(), and a source that fires meanwhile is latched
    for that attachment only."""

    def __init__(self, vec: int, cpu: int, rate_hz: float = 0.0):
        self.vec, self.cpu, self.rate_hz = vec, cpu, rate_hz
        self.attaches: list[Attach] = []


class Attach:
    def __init__(self, irq: Irq, th: Thread, kernel: bool):
        self.irq, self.th, self.kernel = irq, th, kernel  # kernel: procnto/driver thread, no kernel-call events
        self.masked = self.latched = self.waiting = False
        self.pending = 0


def _dwords(text: str) -> str:
    b = text.encode() + b"\0"
    b += b"\0" * (-len(b) % 4)
    return " ".join(f"d{i}:0x{int.from_bytes(b[i * 4:i * 4 + 4], 'little'):08x}" for i in range(len(b) // 4))


class Kernel:
    def __init__(self, seed: int = 0, knobs: Knobs | None = None):
        self.rng = random.Random(seed)
        self.k = knobs or Knobs()
        self.now = 0
        self._q: list = []
        self._n = 0
        self.lines: list[str] = []
        self.cpus: list[Thread | None] = [None] * self.k.ncpu
        self.ready: list[Thread] = []
        self.timers: list = []
        self._ticks: set[int] = set()
        self.tick_phase = self.rng.randrange(TICK_NS)
        self.base_cycles = self.rng.randrange(0x1000_0000_0000, 0x2400_0000_0000)
        self.procs: dict[int, Proc] = {}
        self.stop_at: int | None = None
        self._dirty = False
        self._rcvid = self.rng.randrange(1, 0x100)
        self._addr = self.rng.randrange(0x20_0000_0000, 0x50_0000_0000) & ~0xF
        self._enq = 0
        self._chid = 0
        self._coid = 0x40000000
        self.clock_irq = Irq(0x80010000, 0)
        self.clock_att: Attach | None = None

    # ------------------------------------------------------------------ output
    def emit(self, cpu: int, cls: str, kind: str, inline: str = "", cont=()) -> None:
        cyc = self.base_cycles + self.now * self.k.cycles_per_sec // 1_000_000_000
        pad = 17 if cls in ("INTERRUPT", "SYSTEM", "PROCESS") else 18
        line = f"t:0x{cyc:x} CPU:{cpu:02d} {cls:<16}:{kind:<{pad}} {inline}".rstrip()
        if cont:
            line += "".join(f"\n{k:>26}:{v}" for k, v in cont)
        self.lines.append(line)

    def th_event(self, th: Thread, cpu: int) -> None:
        self.emit(cpu, "THREAD", "TH" + th.state, f"pid:{th.pid} tid:{th.tid} priority:{th.prio} policy:{th.policy}")

    def mark(self, cpu: int, text: str) -> None:
        self.emit(cpu, "USREVENT", "EVENT:1", f'STR:"{text}", {_dwords(text)}')

    def text(self, extra: str = "") -> str:
        head = ["TRACEPRINTER version 1.02", "TRACEPARSER LIBRARY version 1.02", " -- HEADER FILE INFORMATION -- "]
        for k, v in (("TRACE_DATE", "simulated"), ("TRACE_VER_MAJOR", "2"), ("TRACE_VER_MINOR", "01"),
                     ("TRACE_LITTLE_ENDIAN", "TRUE"), ("TRACE_ENCODING", "16 byte events"),
                     ("TRACE_CYCLES_PER_SEC", str(self.k.cycles_per_sec)), ("TRACE_CPU_NUM", str(self.k.ncpu)),
                     ("TRACE_SYSNAME", "QNX"), ("TRACE_NODENAME", "tracelens-sim"), ("TRACE_SYS_RELEASE", "8.0.0"),
                     ("TRACE_SIMULATED", extra or "tracelens.sim")):
            head.append(f"{k:>22}:: {v}")
        head.append(" -- KERNEL EVENTS -- ")
        return "\n".join(head + self.lines) + "\n"

    # ------------------------------------------------------------------ helpers
    def rnd(self, span: tuple[int, int]) -> int:
        return self.rng.randint(*span)

    def kcost(self) -> int:
        return self.rnd(self.k.kcall_ns)

    def new_addr(self) -> int:
        self._addr += self.rng.randrange(0x10, 0x400) & ~0x7
        return self._addr

    def new_sem(self, count: int = 0) -> Sem:
        return Sem(self.new_addr(), count)

    def new_mutex(self, pi: bool = True) -> Mutex:
        return Mutex(self.new_addr(), pi)

    def new_cond(self) -> CondVar:
        return CondVar(self.new_addr())

    def new_proc(self, name: str, pid: int | None = None) -> Proc:
        while pid is None or pid in self.procs:
            pid = self.rng.randrange(0x40000, 0x7000000)
        p = self.procs[pid] = Proc(pid, name)
        return p

    def new_thread(self, proc: Proc, prio: int, policy: int = FIFO, mask=None, gen=None) -> Thread:
        proc.ntid += 1
        return Thread(proc, proc.ntid, prio, policy, mask, gen)

    def at(self, t: int, fn, *args) -> None:
        heapq.heappush(self._q, (t, self._n, fn, args))
        self._n += 1

    def tick_ceil(self, t: int) -> int:
        return self.tick_phase + -(-(t - self.tick_phase) // TICK_NS) * TICK_NS

    def add_timer(self, due: int, fn, *args) -> None:
        """Run ``fn(cpu, *args)`` from the clock interrupt thread at the first tick at or after ``due``."""
        tick = self.tick_ceil(max(due, self.now + 1)) + self.k.late_ticks * TICK_NS
        heapq.heappush(self.timers, (tick, self._n, fn, args))
        self._n += 1
        if tick not in self._ticks:
            self._ticks.add(tick)
            self.at(tick, self._tick, tick)

    def _tick(self, tick: int) -> None:
        self._ticks.discard(tick)
        self.interrupt(self.clock_irq)

    # ------------------------------------------------------------------ scheduler
    def make_ready(self, th: Thread, cpu: int, head: bool = False) -> None:
        th.state = "READY"
        self._enq += 1
        th.enq = -self._enq if head else self._enq
        self.ready.append(th)
        self.th_event(th, cpu)
        self._dirty = True

    def block(self, th: Thread, state: str) -> None:
        cpu = th.cpu
        th.state = state
        th.wait_token += 1
        th.version += 1
        self._n += 1
        th.wait_seq = self._n
        self.th_event(th, cpu)
        self.cpus[cpu] = None
        th.last_cpu, th.cpu = cpu, None
        self._dirty = True

    def wake(self, th: Thread, cpu: int, exit=None, result=None) -> None:
        if th.wait_list is not None and th in th.wait_list:
            th.wait_list.remove(th)
        th.wait_list = None
        th.blocked_on = None
        th.wait_token += 1
        th.result = result
        if exit:
            th.pending.append(exit)
        self.make_ready(th, cpu)

    def _preempt(self, th: Thread) -> None:
        cpu = th.cpu
        if th.work_left:
            th.work_left = max(0, th.work_left - max(0, self.now - th.run_start))
        th.version += 1
        self.cpus[cpu] = None
        th.last_cpu, th.cpu = cpu, None
        self.make_ready(th, cpu, head=True)

    def _run_on(self, th: Thread, cpu: int) -> None:
        self.ready.remove(th)
        th.state, th.cpu = "RUNNING", cpu
        self.cpus[cpu] = th
        self.th_event(th, cpu)
        if th.gen is None:
            return
        th.run_start = self.now + self.rnd(self.k.ctx_ns)
        t = th.run_start + th.work_left
        if th.spin_end is not None:
            t = max(t, th.spin_end)
        th.version += 1
        self.at(t, self._step, th, th.version)

    def _pick_cpu(self, th: Thread) -> int | None:
        best, best_key = None, None
        for c in (th.mask if th.mask is not None else range(self.k.ncpu)):
            cur = self.cpus[c]
            p = -1 if cur is None else cur.prio
            if p >= th.prio:
                continue
            key = (p, c != th.last_cpu, c)
            if best_key is None or key < best_key:
                best, best_key = c, key
        return best

    def _reschedule(self) -> None:
        while True:
            for th in sorted(self.ready, key=lambda t: (-t.prio, t.enq)):
                cpu = self._pick_cpu(th)
                if cpu is not None:
                    if self.cpus[cpu] is not None:
                        self._preempt(self.cpus[cpu])
                    self._run_on(th, cpu)
                    break
            else:
                return

    def cont(self, th: Thread, ns: int, wall: bool = False) -> None:
        """Keep running for ``ns``: CPU time, or wall-clock time like tl_spin_us() (``wall``)."""
        if wall:
            th.spin_end, th.work_left = self.now + ns, 0
            t = th.spin_end
        else:
            th.spin_end, th.work_left, th.run_start = None, ns, self.now
            t = self.now + ns
        th.version += 1
        self.at(t, self._step, th, th.version)

    def _step(self, th: Thread, version: int) -> None:
        if th.version != version or th.state != "RUNNING":
            return
        th.work_left, th.spin_end = 0, None
        for cls, kind, inline, cont in th.pending:
            self.emit(th.cpu, cls, kind, inline, cont)
        th.pending.clear()
        try:
            op = th.gen.send(th.result)
        except StopIteration:
            self._exit(th)
            return
        th.result = None
        getattr(self, "op_" + op[0])(th, *op[1:])

    def run(self, limit_ns: int) -> None:
        if self._dirty:  # threads made ready from outside the loop (launch, injected interrupt)
            self._reschedule()
            self._dirty = False
        while self._q:
            t = self._q[0][0]
            if t > limit_ns or (self.stop_at is not None and t > self.stop_at):
                break
            t, _, fn, args = heapq.heappop(self._q)
            self.now = max(self.now, t)
            fn(*args)
            if self._dirty:
                self._reschedule()
                self._dirty = False

    def _effective(self, th: Thread) -> int:
        p = th.base
        for m in th.held:
            if m.pi and m.waiters:
                p = max(p, max(w.prio for w in m.waiters))
        return p

    def _reprio(self, th: Thread, cpu: int | None = None) -> None:
        new = self._effective(th)
        if new == th.prio or th.dead:
            return
        th.prio = new
        self.th_event(th, th.cpu if th.cpu is not None else (cpu if cpu is not None else (th.last_cpu or 0)))
        self._dirty = True
        m = th.blocked_on
        if isinstance(m, Mutex) and m.pi and m.owner is not None:
            self._reprio(m.owner, cpu)

    @staticmethod
    def _best(waiters: list) -> object:
        def key(w):
            t = w.client if isinstance(w, Request) else w
            return (-t.prio, t.wait_seq)
        return min(waiters, key=key)

    # ------------------------------------------------------------------ system
    def boot(self) -> None:
        """procnto with one idle thread per CPU and the clock interrupt thread, as at capture start."""
        nto = self.new_proc("/proc/boot/procnto-smp-instr", pid=1)
        for c in range(self.k.ncpu):
            self.emit(c, "CONTROL", "TIME", f"msb:0x{(self.base_cycles >> 32):08x} "
                                            f"lsb(offset):0x{self.base_cycles & 0xffffffff:08x}")
        self.emit(0, "PROCESS", "PROCCREATE_NAME", "", (("ppid", "0"), ("pid", "1"), ("name", nto.name)))
        for c in range(self.k.ncpu):
            idle = self.new_thread(nto, 0, FIFO, mask=(c,))
            self.emit(0, "THREAD", "THCREATE", f"pid:1 tid:{idle.tid}")
            self.emit(0, "PROCESS", "PROCTHREAD_NAME", "", (("pid", "1"), ("tid", str(idle.tid)), ("name", f"idle_cpu_{c}")))
            idle.state, idle.cpu, self.cpus[c] = "RUNNING", c, idle
            self.th_event(idle, c)
        for _ in range(4):
            nto.ntid += 1  # kernel worker threads we do not model
        vec = self.clock_irq.vec
        for c in range(self.k.ncpu):  # one clock interrupt thread per CPU (QNX 8.0, measured)
            clock = self.new_thread(nto, 254, IST_POLICY, mask=(c,))
            self.emit(0, "SYSTEM", "IST_ATTACH", f"pid:1 tid:{clock.tid} intr_id:0x{vec:x}({vec}) intr_cpu:{c:02d} "
                                                  "flags:0x000000a8 ist_prio:254")
            if c == 0:  # timers expire through CPU 0's clock thread here; the others stay idle
                self.clock_att = Attach(self.clock_irq, clock, kernel=True)
                self.clock_irq.attaches.append(self.clock_att)
                clock.gen = self._clock_prog(self.clock_att)
                self.start_blocked(clock)

    def _clock_prog(self, att):
        while True:
            yield ("kwait", att)
            yield ("work", self.rnd(self.k.clock_ist_ns))
            yield ("expire",)
            yield ("kunmask", att)

    def driver_ist(self, proc: Proc, irq: Irq, work_ns: tuple[int, int] = (8_000, 40_000),
                   own_share: float = 0.1) -> Thread:
        """A device driver's interrupt thread (e.g. devc-ser8250 at priority 254 on the serial line).

        On a shared line a driver wakes for every delivery but only works when its *own* device raised
        the interrupt; otherwise it reads a status register and returns. Without this the simulated
        driver preempted the application's handler on every interrupt (measured against the real Z5
        capture: 4.75 preemptions per ms simulated, 0 real)."""
        th = self.new_thread(proc, 254, IST_POLICY, mask=(irq.cpu,))
        att = Attach(irq, th, kernel=True)
        irq.attaches.append(att)
        self.emit(0, "SYSTEM", "IST_ATTACH", f"pid:{proc.pid} tid:{th.tid} intr_id:0x{irq.vec:x}({irq.vec}) "
                                              "flags:0x10000008 EVENT ist_prio:254")

        def prog():
            while True:
                yield ("kwait", att)
                mine = self.rng.random() < own_share
                yield ("work", self.rnd(work_ns) if mine else self.rng.randint(1_000, 3_000))
                yield ("kunmask", att)

        th.gen = prog()
        self.start_blocked(th)
        return th

    def start_blocked(self, th: Thread) -> None:
        """Start a pre-existing thread inside its first blocking call (sleep or interrupt wait)."""
        op = next(th.gen)
        if op[0] == "kwait":
            th.state, op[1].waiting = "INTR", True
        elif op[0] == "sleep":
            th.state = "NANOSLEEP"
            th.wait_token += 1
            self.add_timer(self.now + op[1], self._timer_wake, th, th.wait_token)
        else:
            raise ValueError(op)
        th.last_cpu = (th.mask or (self.rng.randrange(self.k.ncpu),))[0]

    def system_noise(self, procs) -> None:
        """Background processes: (name, pid, [(prio, mean_sleep_ms, mean_work_us), ...])."""
        for name, pid, threads in procs:
            p = self.new_proc(name, pid)
            self.emit(0, "PROCESS", "PROCCREATE_NAME", "", (("ppid", "1"), ("pid", str(pid)), ("name", name)))
            if name.endswith("devc-ser8250"):
                self.serial_proc = p
            for prio, sleep_ms, work_us in threads:
                th = self.new_thread(p, prio, RR)
                th.gen = self._noise_prog(sleep_ms * 1e6 / max(self.k.noise, 0.05), work_us * 1e3)
                self.emit(0, "THREAD", "THCREATE", f"pid:{pid} tid:{th.tid}")
                self.start_blocked(th)

    def _noise_prog(self, mean_sleep: float, mean_work: float):
        while True:
            yield ("sleep", int(self.rng.expovariate(1 / mean_sleep)) + 50_000)
            yield ("work", int(self.rng.expovariate(1 / mean_work)) + 1_000)

    def launch(self, name: str, gen_fn, *args, prio: int = 10, ppid: int = 1):
        """A program started from the shell: new process, main thread READY."""
        p = self.new_proc(name)
        cpu = self.rng.randrange(self.k.ncpu)
        self.emit(cpu, "PROCESS", "PROCCREATE_NAME", "", (("ppid", str(ppid)), ("pid", str(p.pid)), ("name", name)))
        th = self.new_thread(p, prio, RR)
        th.gen = gen_fn(*args)
        self.emit(cpu, "THREAD", "THCREATE", f"pid:{p.pid} tid:{th.tid}")
        th.last_cpu = cpu
        self.make_ready(th, cpu)
        return th

    def device_irq(self, vec: int, cpu: int, rate_hz: float) -> Irq:
        irq = Irq(vec, cpu, rate_hz)
        if rate_hz > 0:
            self.at(self.now + int(self.rng.expovariate(rate_hz) * 1e9), self._arrive, irq)
        return irq

    def _arrive(self, irq: Irq) -> None:
        self.interrupt(irq)
        self.at(self.now + 2000 + int(self.rng.expovariate(irq.rate_hz) * 1e9), self._arrive, irq)

    def interrupt(self, irq: Irq, only: Attach | None = None) -> None:
        targets = [only] if only is not None else irq.attaches
        open_ = [a for a in targets if not a.masked]
        for a in targets:
            if a.masked:
                a.latched = True
        if not open_:
            return
        self.emit(irq.cpu, "INTERRUPT", "INT_DELIVER", f"intr_id:0x{irq.vec:x}({irq.vec})")
        for a in open_:
            a.masked = True
            if a.waiting:
                a.waiting = False
                a.th.last_cpu = irq.cpu
                self.wake(a.th, irq.cpu, exit=None if a.kernel else ("KER_EXIT", "INTERRUPT_WAIT/58", "ret_val:0", ()))
            else:
                a.pending += 1

    def _timer_wake(self, cpu: int, th: Thread, token: int) -> None:
        if th.wait_token == token and th.state == "NANOSLEEP":
            self.wake(th, cpu)

    def _exit(self, th: Thread, cpu: int | None = None) -> None:
        cpu = th.cpu if th.cpu is not None else cpu
        if th.state == "READY":
            self.ready.remove(th)
        if th.wait_list is not None and th in th.wait_list:
            th.wait_list.remove(th)
        self.emit(cpu, "THREAD", "THDESTROY", f"pid:{th.pid} tid:{th.tid}")
        th.state, th.dead = "DEAD", True
        self.th_event(th, cpu)
        th.version += 1
        if th.cpu is not None:
            self.cpus[th.cpu] = None
            th.cpu = None
        self._dirty = True
        for j in th.joiners:
            self.wake(j, cpu, exit=("KER_EXIT", "THREAD_JOIN/50", "ret_val:0x00000000 status_p:0x00000000", ()))
        th.joiners.clear()
        if th.on_exit:
            th.on_exit()

    # ------------------------------------------------------------------ ops: time and identity
    def op_now(self, th):
        th.result = self.now
        self.cont(th, 100)

    def op_mark(self, th, text):
        self.mark(th.cpu, text)
        self.cont(th, self.kcost())

    def op_spin(self, th, ns):
        self.cont(th, int(ns), wall=True)

    def op_work(self, th, ns):
        self.cont(th, int(ns))

    def op_sleep_until(self, th, t):
        if t <= self.now:
            self.cont(th, self.kcost())
            return
        self.block(th, "NANOSLEEP")
        self.add_timer(t, self._timer_wake, th, th.wait_token)

    def op_sleep(self, th, ns):
        self.op_sleep_until(th, self.now + int(ns))

    def op_runmask(self, th, mask):
        th.mask = mask
        if mask is not None and th.cpu not in mask:
            self._preempt(th)  # migrates at the next reschedule
        else:
            self.cont(th, self.kcost())

    def op_sched(self, th, prio):
        self.emit(th.cpu, "KER_CALL", "SCHED_SET/89", "", (("pid", "0"), ("tid", "0"), ("policy", str(FIFO)),
                                                          ("sched_priority", str(prio)), ("sched_curpriority", "-32768")))
        th.base, th.policy = prio, FIFO
        th.pending.append(("KER_EXIT", "SCHED_SET/89", "ret_val:0", ()))
        self._reprio(th)
        self.cont(th, self.kcost())

    def op_setname(self, th, name):
        self.emit(th.cpu, "PROCESS", "PROCTHREAD_NAME", "", (("pid", str(th.pid)), ("tid", str(th.tid)), ("name", name)))
        self.cont(th, self.kcost())

    # ------------------------------------------------------------------ ops: threads and processes
    def op_spawn(self, th, gen_fn, *args):
        child = self.new_thread(th.proc, 10, FIFO, th.mask, gen_fn(*args))
        self.emit(th.cpu, "THREAD", "THCREATE", f"pid:{child.pid} tid:{child.tid}")
        child.last_cpu = th.cpu
        self.make_ready(child, th.cpu)
        th.result = child
        self.cont(th, 3 * self.kcost())

    def op_fork(self, th, gen_fn, *args):
        p = self.new_proc(th.proc.name)
        self.emit(th.cpu, "PROCESS", "PROCCREATE_NAME", "", (("ppid", str(th.pid)), ("pid", str(p.pid)), ("name", p.name)))
        child = self.new_thread(p, th.base, th.policy, th.mask, gen_fn(*args))
        self.emit(th.cpu, "THREAD", "THCREATE", f"pid:{p.pid} tid:{child.tid}")
        child.last_cpu = th.cpu
        self.make_ready(child, th.cpu)
        th.result = child
        self.cont(th, 20 * self.kcost())

    def op_join(self, th, other):
        self.emit(th.cpu, "KER_CALL", "THREAD_JOIN/50", "", (("tid", str(other.tid)), ("status_p", "0x0000000000000000")))
        if other.dead:
            th.pending.append(("KER_EXIT", "THREAD_JOIN/50", "ret_val:0x00000000 status_p:0x00000000", ()))
            self.cont(th, self.kcost())
            return
        other.joiners.append(th)
        self.block(th, "JOIN")

    def op_cancel(self, th, other):
        if not other.dead:
            self._exit(other, th.cpu)
        self.cont(th, self.kcost())

    # ------------------------------------------------------------------ ops: semaphores
    def op_sem_wait(self, th, s):
        self.emit(th.cpu, "KER_CALL", "SYNC_SEM_WAIT/85", "", (("sync_p", f"0x{s.addr:016x}"), ("try", "0"),
                                                              ("count", str(s.count)), ("owner", "-4")))
        if s.count > 0:
            s.count -= 1
            th.pending.append(("KER_EXIT", "SYNC_SEM_WAIT/85", "ret_val:0", ()))
            self.cont(th, self.kcost())
            return
        s.waiters.append(th)
        th.wait_list, th.blocked_on = s.waiters, s
        self.block(th, "SEM")

    def op_sem_post(self, th, s):
        self.emit(th.cpu, "KER_CALL", "SYNC_SEM_POST/84", "", (("sync_p", f"0x{s.addr:016x}"), ("count", str(s.count)),
                                                              ("owner", "-4")))
        if s.waiters:
            self.wake(self._best(s.waiters), th.cpu, exit=("KER_EXIT", "SYNC_SEM_WAIT/85", "ret_val:0", ()))
        else:
            s.count += 1
        th.pending.append(("KER_EXIT", "SYNC_SEM_POST/84", "ret_val:0", ()))
        self.cont(th, self.kcost())

    # ------------------------------------------------------------------ ops: mutexes and condvars
    def _owner_id(self, m: Mutex) -> str:
        o = m.owner
        return str(((o.pid & 0x7FFF) << 16) | o.tid) if o is not None else "0"

    def op_mutex_lock(self, th, m, timeout_ns=None, exit_kind="SYNC_MUTEX_LOCK/80"):
        if m.owner is None:  # uncontended: user space only, no kernel event (as on QNX)
            m.owner = th
            th.held.append(m)
            self.cont(th, 150)
            return
        self.emit(th.cpu, "KER_CALL", "SYNC_MUTEX_LOCK/80", "", (("sync_p", f"0x{m.addr:016x}"),
                                                                ("count", "-2147483648"), ("owner", self._owner_id(m))))
        self._enqueue_mutex(th, m, th.cpu, exit_kind)
        if timeout_ns:
            self.add_timer(self.now + timeout_ns, self._mutex_timeout, th, m, th.wait_token)

    def _enqueue_mutex(self, th, m, cpu, exit_kind):
        m.waiters.append(th)
        th.wait_list, th.blocked_on, th.lock_exit = m.waiters, m, exit_kind
        if th.state == "RUNNING":
            self.block(th, "MUTEX")
        else:  # woken from a condvar, must reacquire
            th.state = "MUTEX"
            self._n += 1
            th.wait_seq = self._n
            self.th_event(th, cpu)
        if m.pi:
            self._reprio(m.owner, cpu)

    def _mutex_timeout(self, cpu, th, m, token):
        if th.wait_token != token or th not in m.waiters:
            return
        self.wake(th, cpu, exit=("KER_EXIT", th.lock_exit, f"ret_val:{ETIMEDOUT}", ()), result="timeout")
        if m.owner is not None:
            self._reprio(m.owner, cpu)

    def _release(self, th, m, cpu):
        th.held.remove(m)
        if m.waiters:
            w = self._best(m.waiters)
            m.owner = w
            w.held.append(m)
            self.wake(w, cpu, exit=("KER_EXIT", w.lock_exit, "ret_val:0", ()))
            self._reprio(w, cpu)
        else:
            m.owner = None
        self._reprio(th, cpu)

    def op_mutex_unlock(self, th, m):
        if not m.waiters:
            th.held.remove(m)
            m.owner = None
            self.cont(th, 120)
            return
        self.emit(th.cpu, "KER_CALL", "SYNC_MUTEX_UNLOCK/81", "", (("sync_p", f"0x{m.addr:016x}"),
                                                                  ("count", "-2147483648"), ("owner", self._owner_id(m))))
        self._release(th, m, th.cpu)
        th.pending.append(("KER_EXIT", "SYNC_MUTEX_UNLOCK/81", "ret_val:0 empty:0x00000000", ()))
        self.cont(th, self.kcost())

    def op_cond_wait(self, th, cv, m, timeout_ns=None):
        self.emit(th.cpu, "KER_CALL", "SYNC_CONDVAR_WAIT/82", "", (("sync_p", f"0x{cv.addr:016x}"),
                                                                  ("mutex_p", f"0x{m.addr:016x}")))
        cpu = th.cpu
        cv.waiters.append(th)
        th.wait_list, th.blocked_on, th.relock = cv.waiters, cv, m
        self.block(th, "CONDVAR")
        if timeout_ns:
            self.add_timer(self.now + timeout_ns, self._cond_timeout, th, cv, th.wait_token)
        self._release(th, m, cpu)

    def _cond_wakeup(self, w, cpu, ret):
        """A condvar waiter leaves the condvar and must hold the mutex again before it returns."""
        w.wait_list = None
        m = w.relock
        if m.owner is None:
            m.owner = w
            w.held.append(m)
            self.wake(w, cpu, exit=("KER_EXIT", "SYNC_CONDVAR_WAIT/82", f"ret_val:{ret}", ()),
                      result="timeout" if ret else None)
        else:
            self._enqueue_mutex(w, m, cpu, "SYNC_CONDVAR_WAIT/82")

    def _cond_timeout(self, cpu, th, cv, token):
        if th.wait_token == token and th in cv.waiters:
            cv.waiters.remove(th)
            self._cond_wakeup(th, cpu, ETIMEDOUT)

    def op_cond_broadcast(self, th, cv, all_=True):
        self.emit(th.cpu, "KER_CALL", "SYNC_CONDVAR_SIGNAL/83", "", (("sync_p", f"0x{cv.addr:016x}"),
                                                                    ("all", "1" if all_ else "0"),
                                                                    ("sync->count", "0"), ("sync->owner", "-5")))
        for w in sorted(cv.waiters, key=lambda t: (-t.prio, t.wait_seq))[:None if all_ else 1]:
            cv.waiters.remove(w)
            self._cond_wakeup(w, th.cpu, 0)
        th.pending.append(("KER_EXIT", "SYNC_CONDVAR_SIG/83", "ret_val:0 empty:0x00000000", ()))
        self.cont(th, self.kcost())

    def op_cond_signal(self, th, cv):
        self.op_cond_broadcast(th, cv, all_=False)

    # ------------------------------------------------------------------ ops: message passing
    def op_channel_create(self, th, fixed=False):
        self._chid += 1
        ch = Channel(self._chid, th.proc, fixed)
        self.emit(th.cpu, "KER_CALL", "CHANNEL_CREATE/35", f"flags:0x{0x1 if fixed else 0:08x} empty:0x00000000")
        th.pending.append(("KER_EXIT", "CHANNEL_CREATE/35", f"chid:0x{ch.chid:08x} empty:0x00000000", ()))
        th.result = ch
        self.cont(th, self.kcost())

    def op_connect(self, th, ch):
        self._coid += 1
        conn = Conn(self._coid, ch)
        self.emit(th.cpu, "KER_CALL", "CONNECT_ATTACH/39", "", (("nd", "0x00000000"), ("pid", str(ch.proc.pid)),
                                                               ("chid", f"0x{ch.chid:08x}"), ("index", "1073741824"),
                                                               ("flags", "0x00000000")))
        th.pending.append(("KER_EXIT", "CONNECT_ATTACH/39", f"coid:0x{conn.coid:08x} empty:0x00000000", ()))
        th.result = conn
        self.cont(th, self.kcost())

    def _deliver(self, srv: Thread, req: Request, cpu: int, running: bool) -> None:
        c = req.client
        if not req.chan.fixed:  # the server runs at its client's priority (QNX default)
            srv.base = c.prio
        exit = ("KER_EXIT", "MSG_RECEIVEV/14", "", (("rcvid", req.rcvid), ("rmsg[0]", _MSG), ("info->nd", "0"),
                                                   ("info->srcnd", "0"), ("info->pid", str(c.pid)),
                                                   ("info->tid", str(c.tid))))
        rec = ("COMM", "REC_MESSAGE", f"rcvid:{req.rcvid} pid:{c.pid}", ())
        if running:
            self.emit(cpu, *rec)
            srv.pending.append(exit)
            srv.result = req
            self._reprio(srv)
        else:
            srv.prio = self._effective(srv)
            self.wake(srv, cpu, result=req)
            srv.pending[:0] = [rec, exit]

    def op_msg_send(self, th, conn, timeout_ns=None):
        cpu, ch = th.cpu, conn.chan
        if timeout_ns:
            self.emit(cpu, "KER_CALL", "TIMER_TIMEOUT/75", "", (("id", "2"), ("timeout_flags", "0x00000050"),
                                                               ("ntime(sec)", str(timeout_ns // 1_000_000_000)),
                                                               ("ntime(nsec)", str(timeout_ns % 1_000_000_000))))
            self.emit(cpu, "KER_EXIT", "TIMER_TIMEOUT/75", "", (("prev_timeout_flags", "0x00000000"),
                                                               ("otime(sec)", "0"), ("otime(nsec)", "0")))
        self.emit(cpu, "KER_CALL", "MSG_SENDV/11", "", (("coid", f"0x{conn.coid:08x}"), ("sparts", "1"),
                                                       ("rparts", "1"), ("msg[0]", _MSG)))
        self._rcvid += 1
        req = Request(f"0x{self._rcvid:08x}", th, ch)
        self.emit(cpu, "COMM", "SND_MESSAGE", f"rcvid:{req.rcvid} pid:{ch.proc.pid}")
        if ch.receivers:
            srv = ch.receivers[0]
            self.block(th, "REPLY")
            self._deliver(srv, req, cpu, running=False)
        else:
            ch.sendq.append(req)
            self.block(th, "SEND")
        req.token = th.wait_token
        th.blocked_on = req
        if timeout_ns:
            self.add_timer(self.now + timeout_ns, self._send_timeout, req)

    def _send_timeout(self, cpu, req):
        c = req.client
        if req.done or c.wait_token != req.token or c.state not in ("SEND", "REPLY"):
            return
        if req in req.chan.sendq:
            req.chan.sendq.remove(req)
        req.done = True
        self.wake(c, cpu, exit=("KER_EXIT", "MSG_SENDV/11", f"ret_val:-1 errno:{ETIMEDOUT}", ()), result="timeout")

    def op_msg_receive(self, th, ch, timeout_ns=None):
        if timeout_ns:  # TimerTimeout(_NTO_TIMEOUT_RECEIVE) before the call, as QNX programs do
            self.emit(th.cpu, "KER_CALL", "TIMER_TIMEOUT/75", "", (("id", "2"), ("timeout_flags", "0x00000010"),
                                                                  ("ntime(sec)", str(timeout_ns // 1_000_000_000)),
                                                                  ("ntime(nsec)", str(timeout_ns % 1_000_000_000))))
            self.emit(th.cpu, "KER_EXIT", "TIMER_TIMEOUT/75", "", (("prev_timeout_flags", "0x00000000"),
                                                                  ("otime(sec)", "0"), ("otime(nsec)", "0")))
        self.emit(th.cpu, "KER_CALL", "MSG_RECEIVEV/14", "", (("chid", f"0x{ch.chid:08x}"), ("rparts", "1")))
        if ch.sendq:
            req = self._best(ch.sendq)
            ch.sendq.remove(req)
            req.client.state = "REPLY"
            self.th_event(req.client, th.cpu)
            self._deliver(th, req, th.cpu, running=True)
            self.cont(th, self.kcost())
            return
        ch.receivers.append(th)
        th.wait_list = ch.receivers
        self.block(th, "RECEIVE")
        if timeout_ns:
            self.add_timer(self.now + timeout_ns, self._receive_timeout, th, ch, th.wait_token)

    def _receive_timeout(self, cpu, th, ch, token):
        if th.wait_token == token and th in ch.receivers:
            self.wake(th, cpu, exit=("KER_EXIT", "MSG_RECEIVEV/14", f"ret_val:-1 errno:{ETIMEDOUT}", ()),
                      result="timeout")

    def op_msg_reply(self, th, req):
        self.emit(th.cpu, "KER_CALL", "MSG_REPLYV/15", "", (("rcvid", req.rcvid), ("sparts", "1"),
                                                           ("status", "0x0000000000000000"), ("smsg[0]", _MSG)))
        c = req.client
        if not req.done and c.state == "REPLY" and c.wait_token == req.token:
            self.emit(th.cpu, "COMM", "REPLY_MESSAGE", f"tid:{c.tid} pid:{c.pid}")
            self.wake(c, th.cpu, exit=("KER_EXIT", "MSG_SENDV/11", "", (("status", "0"), ("rmsg[0]", _MSG))))
        req.done = True
        th.pending.append(("KER_EXIT", "MSG_REPLYV/15", "ret_val:0", ()))
        self.cont(th, self.kcost())

    # ------------------------------------------------------------------ ops: interrupts
    def op_interrupt_attach(self, th, irq):
        att = Attach(irq, th, kernel=False)
        irq.attaches.append(att)
        self.emit(th.cpu, "SYSTEM", "IST_ATTACH", f"pid:{th.pid} tid:{th.tid} intr_id:0x{irq.vec:x}({irq.vec}) "
                                                  f"flags:0x00000008 ist_prio:{th.prio}")
        th.result = att
        self.cont(th, 5 * self.kcost())

    def op_interrupt_detach(self, th, att):
        if att in att.irq.attaches:
            att.irq.attaches.remove(att)
        self.cont(th, self.kcost())

    def op_interrupt_wait(self, th, att):
        self.emit(th.cpu, "KER_CALL", "INTERRUPT_WAIT/58", "", (("flags", "0x00000000"), ("timeout_tv_sec", "0"),
                                                               ("timeout_tv_nsec", "0")))
        if att.pending:
            att.pending = 0
            th.pending.append(("KER_EXIT", "INTERRUPT_WAIT/58", "ret_val:0", ()))
            self.cont(th, self.kcost())
            return
        att.waiting = True
        self.block(th, "INTR")

    def op_interrupt_unmask(self, th, att):
        self.emit(th.cpu, "KER_CALL", "INTERRUPT_UNMASK/60", f"intr:{att.irq.vec} id:1")
        th.pending.append(("KER_EXIT", "INTERRUPT_UNMASK/60", "ret_val:0", ()))
        self._unmask(att)
        self.cont(th, self.kcost())

    def _unmask(self, att):
        att.masked = False
        if att.latched:  # the source is still asserted: deliver again to this attachment
            att.latched = False
            self.at(self.now + 1000, self.interrupt, att.irq, att)

    def op_kwait(self, th, att):  # kernel or driver interrupt thread: no kernel-call events
        if att.pending:
            att.pending = 0
            self.cont(th, 200)
            return
        att.waiting = True
        self.block(th, "INTR")

    def op_kunmask(self, th, att):
        self._unmask(att)
        self.cont(th, 200)

    def op_expire(self, th):
        n = 0
        while self.timers and self.timers[0][0] <= self.now:
            _, _, fn, args = heapq.heappop(self.timers)
            fn(th.cpu, *args)
            n += 1
        self.cont(th, 300 + 700 * n)
