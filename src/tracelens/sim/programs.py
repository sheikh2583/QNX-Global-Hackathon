"""The tlgen scenarios (bugzoo/gen/tlgen.c) as simulator programs, one generator per thread.

Each function mirrors its C counterpart: same threads, priorities, tick offsets, markers and
kernel objects, so a simulated trace and a real capture of ``tlgen -s <scenario>`` are comparable
event for event. Keep the two in step: a change to tlgen.c needs the same change here.
"""

from __future__ import annotations

import gzip
import random
from pathlib import Path

from ..ml.dataset import TRUTH  # noqa: F401  (ground truth, shared with real tlgen captures)
from .kernel import TICK_NS, Kernel, Knobs

US = 1000
DEFAULTS = {"seconds": 2, "period_us": 10000, "work_us": 300, "cs_us": 200, "mid_us": 4000, "workers": 4, "pin": 1,
            "hi": 50, "mid": 20, "lo": 10, "irq": 4}
PLAIN, SEM_HI, SEM_LO, MTX_HI, MTX_LO, CV_HI, CV_LO, BUSY, WORKER, LW_CONS, LW_PROD = range(11)

# Background processes of the QNX 8.0 VM image: (name, pid, [(prio, mean sleep ms, mean burst us)]).
SYSTEM = [
    ("proc/boot/slogger2", 4098, [(10, 40, 25)]),
    ("proc/boot/devc-ser8250", 49157, [(24, 25, 15)]),
    ("proc/boot/pci-server", 12292, [(10, 200, 30)]),
    ("proc/boot/devb-eide", 65544, [(21, 60, 40), (21, 120, 20)]),
    ("usr/sbin/io-sock", 163853, [(21, 15, 20), (21, 50, 60)]),
    ("usr/sbin/sshd", 282643, [(10, 300, 80)]),
    ("proc/boot/ksh", 307219, [(10, 500, 50)]),
]
SHELL_PID = 307219



class Prog:
    """What tlgen keeps in globals: parameters, the epoch t0 and the shared kernel objects."""

    def __init__(self, k: Kernel, A: dict, scenario: str):
        self.k, self.A, self.s = k, A, scenario
        self.t0 = 0
        self.mask = (0,) if A["pin"] else None
        self.periods = A["seconds"] * 1_000_000 // A["period_us"]
        self.sem = k.new_sem(1)
        self.mtx = k.new_mutex(pi=True)  # QNX default protocol: priority inheritance
        self.mtx_b = k.new_mutex(pi=True)
        self.cond = k.new_cond()
        self.ready_gen = 0
        self.chan = None

    def release(self, kk: int, off_ticks: int) -> int:
        return self.t0 + kk * self.A["period_us"] * US + off_ticks * TICK_NS


def mark(text):
    return ("mark", text)


def thread_init(name, prio, mask):
    yield ("runmask", mask)
    yield ("sched", prio)
    yield ("setname", name)
    yield mark(f"TL_META name={name} prio={prio}")


def role(P: Prog, name, prio, off, work_us, kind):
    yield from thread_init(name, prio, P.mask)
    A = P.A
    for kk in range(P.periods):
        yield ("sleep_until", P.release(kk, off))
        if kind in (PLAIN, BUSY):
            yield mark(f"TL_JOB_START name={name}")
            yield ("spin", work_us * US)
            yield mark(f"TL_JOB_END name={name}")
        elif kind == SEM_HI:
            yield mark("TL_JOB_START name=job")
            yield ("sem_wait", P.sem)
            yield ("spin", work_us * US)
            yield ("sem_post", P.sem)
            yield mark("TL_JOB_END name=job")
        elif kind == SEM_LO:
            yield ("sem_wait", P.sem)
            yield ("spin", A["cs_us"] * US)
            yield ("sem_post", P.sem)
        elif kind in (MTX_HI, WORKER):
            job = "job" if kind == MTX_HI else "frame"
            yield mark(f"TL_JOB_START name={job}")
            yield ("mutex_lock", P.mtx)
            yield ("spin", work_us * US)
            yield ("mutex_unlock", P.mtx)
            yield mark(f"TL_JOB_END name={job}")
        elif kind == MTX_LO:
            yield ("mutex_lock", P.mtx)
            yield ("spin", A["cs_us"] * US)
            yield ("mutex_unlock", P.mtx)
        elif kind == CV_HI:  # waits for the low thread's data: no inheritance through a condvar
            yield mark("TL_JOB_START name=job")
            yield ("mutex_lock", P.mtx)
            while P.ready_gen < kk + 1:
                yield ("cond_wait", P.cond, P.mtx)
            yield ("mutex_unlock", P.mtx)
            yield ("spin", work_us * US)
            yield mark("TL_JOB_END name=job")
        elif kind == CV_LO:  # produces outside the lock, then signals
            yield ("spin", A["cs_us"] * US)
            yield ("mutex_lock", P.mtx)
            P.ready_gen = kk + 1
            yield ("cond_broadcast", P.cond)
            yield ("mutex_unlock", P.mtx)
        elif kind == LW_CONS:  # no predicate: a signal sent before this wait is lost
            yield mark(f"TL_JOB_START name={name}")
            yield ("mutex_lock", P.mtx)
            yield ("cond_wait", P.cond, P.mtx, A["mid_us"] * US)
            yield ("mutex_unlock", P.mtx)
            yield ("spin", work_us * US)
            yield mark(f"TL_JOB_END name={name}")
        elif kind == LW_PROD:  # signals one tick before the consumer waits
            yield ("spin", A["cs_us"] * US)
            yield ("mutex_lock", P.mtx)
            yield ("cond_signal", P.cond)
            yield ("mutex_unlock", P.mtx)


def run_roles(P: Prog, roles):
    ths = []
    for r in roles:
        ths.append((yield ("spawn", role, P, *r)))
    for t in ths:
        yield ("join", t)


def server(P: Prog):
    yield from thread_init("server", P.A["lo"], P.mask)
    for _ in range(P.periods):
        req = yield ("msg_receive", P.chan)
        yield ("spin", P.A["cs_us"] * US)
        yield ("msg_reply", req)


def client(P: Prog):
    yield from thread_init("client", P.A["hi"], P.mask)
    conn = yield ("connect", P.chan)
    for kk in range(P.periods):
        yield ("sleep_until", P.release(kk, 0))
        yield mark("TL_JOB_START name=job")
        yield ("msg_send", conn)
        yield ("spin", P.A["work_us"] * US)
        yield mark("TL_JOB_END name=job")


def run_ipc(P: Prog, fixed: bool, with_mid: bool):
    P.chan = yield ("channel_create", fixed)
    s = yield ("spawn", server, P)
    c = yield ("spawn", client, P)
    m = (yield ("spawn", role, P, "mid", P.A["mid"], -1, P.A["mid_us"], BUSY)) if with_mid else None
    yield ("join", c)
    yield ("cancel", s)
    if m is not None:
        yield ("join", m)


def fusion(P: Prog, name: str, peer_chan: list):
    """One side of ipc_deadlock: both stop serving, then MsgSend() to each other (1 s timeout)."""
    yield from thread_init(name, P.A["mid"], None)
    conn = yield ("connect", peer_chan[0])
    yield ("sleep_until", P.t0 + P.A["seconds"] * 1_000_000_000 // 4)
    yield ("msg_send", conn, 1_000_000_000)


def run_ipc_deadlock(P: Prog):
    chan_a = yield ("channel_create", False)
    peer_of_a, peer_of_b = [None], [chan_a]

    def side_b():
        peer_of_a[0] = yield ("channel_create", False)
        yield from fusion(P, "fusion_b", peer_of_b)

    yield ("fork", side_b)
    while peer_of_a[0] is None:  # the pipe read: wait for B's channel id
        yield ("sleep", 200_000)
    yield from fusion(P, "fusion_a", peer_of_a)


def abba(P: Prog, first_a: bool):
    yield from thread_init("ab" if first_a else "ba", P.A["mid"], None)
    yield ("sleep_until", P.t0 + P.A["seconds"] * 1_000_000_000 // 4)
    x, y = (P.mtx, P.mtx_b) if first_a else (P.mtx_b, P.mtx)
    yield ("mutex_lock", x)
    yield ("spin", 2000 * US)  # both now hold their first lock
    got = yield ("mutex_lock", y, 1_000_000_000)
    if got != "timeout":
        yield ("mutex_unlock", y)
    yield ("mutex_unlock", x)


def run_irq(P: Prog, unmask_first: bool):
    A = P.A
    yield from thread_init("ist", A["hi"], (0,))
    att = yield ("interrupt_attach", P.irq)
    end = (yield ("now",)) + A["seconds"] * 1_000_000_000
    while (yield ("now",)) < end:
        yield ("interrupt_wait", att)
        if unmask_first:
            yield ("interrupt_unmask", att)
            yield ("spin", A["cs_us"] * US)  # a little bookkeeping, line already unmasked
        else:
            yield ("spin", A["work_us"] * US)  # the heavy work with the line still masked
            yield ("interrupt_unmask", att)
    yield ("interrupt_detach", att)


def tlgen_main(P: Prog):
    A, s = P.A, P.s
    P.t0 = (yield ("now",)) + 100 * TICK_NS
    yield mark(f"TL_GEN scenario={s} period_us={A['period_us']} work_us={A['work_us']} cs_us={A['cs_us']} "
               f"mid_us={A['mid_us']} workers={A['workers']} pin={A['pin']}")
    hi, mid, lo, w = A["hi"], A["mid"], A["lo"], A["work_us"]
    if s == "healthy_periodic":
        yield from run_roles(P, [("hi", hi, 0, w, PLAIN), ("mid", mid, -1, w, PLAIN), ("lo", lo, -2, w, PLAIN)])
    elif s in ("healthy_pi_mutex", "sem_inversion"):
        sem = s == "sem_inversion"
        yield from run_roles(P, [("hi", hi, 0, w, SEM_HI if sem else MTX_HI), ("mid", mid, -1, A["mid_us"], BUSY),
                                 ("lo", lo, -2, 0, SEM_LO if sem else MTX_LO)])
    elif s in ("healthy_ipc", "chan_inversion"):
        yield from run_ipc(P, s == "chan_inversion", True)
    elif s == "healthy_mixed":
        ths = []
        for r in [("hi", hi, 0, w, MTX_HI), ("mid", mid, -1, w, PLAIN), ("lo", lo, -2, 0, MTX_LO)]:
            ths.append((yield ("spawn", role, P, *r)))
        yield from run_ipc(P, False, False)
        for t in ths:
            yield ("join", t)
    elif s == "ipc_deadlock":
        yield from run_ipc_deadlock(P)
    elif s == "lock_contention":
        yield from run_roles(P, [(f"w{i + 1}", mid, 0, w, WORKER) for i in range(min(A["workers"], 12))])
    elif s == "condvar_inversion":
        yield from run_roles(P, [("hi", hi, 0, w, CV_HI), ("mid", mid, -1, A["mid_us"], BUSY), ("lo", lo, -2, 0, CV_LO)])
    elif s == "cpu_starvation":
        yield from run_roles(P, [("job", mid, 0, w, PLAIN), ("hog", hi, -1, A["mid_us"], BUSY)])
    elif s == "lost_wakeup":
        yield from run_roles(P, [("consumer", hi, 0, w, LW_CONS), ("producer", lo, -1, 0, LW_PROD)])
    elif s == "period_overrun":
        yield from run_roles(P, [("ctl", hi, 0, w, PLAIN), ("logger", lo, -2, A["cs_us"], PLAIN)])
    elif s == "mutex_abba":
        a = yield ("spawn", abba, P, True)
        b = yield ("spawn", abba, P, False)
        yield ("join", a)
        yield ("join", b)
    elif s in ("healthy_irq", "irq_overrun"):
        yield from run_irq(P, s == "healthy_irq")
    else:
        raise ValueError(f"unknown scenario {s}")


def background_writer(k: Kernel):
    """The `while :; do echo ...; done > /dev/ser1` loop that keeps the serial interrupt busy."""
    while True:
        yield ("work", int(k.rng.uniform(80, 400) * US))
        yield ("sleep", int(k.rng.uniform(100, 900) * US))


def simulate(scenario: str, params: dict | None = None, seed: int = 0, seconds: int | None = None,
             knobs: Knobs | None = None, irq_load: bool | None = None) -> str:
    """One simulated capture of ``tlgen -s <scenario>`` as traceprinter text (QNX 8.0 format)."""
    rng = random.Random(f"{scenario}:{seed}")
    A = dict(DEFAULTS, **(params or {}))
    if seconds is not None:
        A["seconds"] = seconds
    knobs = knobs or Knobs.random(rng)
    k = Kernel(seed=rng.randrange(1 << 30), knobs=knobs)
    k.boot()
    k.system_noise(SYSTEM)
    P = Prog(k, A, scenario)
    irq_load = scenario in ("healthy_irq", "irq_overrun") if irq_load is None else irq_load
    P.irq = k.device_irq(A["irq"], 0, knobs.irq_rate_hz if irq_load else 0)
    k.driver_ist(k.serial_proc, P.irq)  # the serial driver shares the line (QNX VM, measured)
    if irq_load:
        k.launch("proc/boot/ksh", background_writer, k, ppid=SHELL_PID)
    start = int(rng.uniform(30, 150) * 1e6)
    k.run(start)
    k.now = max(k.now, start)
    main = k.launch("tmp/tlgen", tlgen_main, P, ppid=SHELL_PID)

    def done():
        k.stop_at = k.now + int(rng.uniform(80, 250) * 1e6)

    main.on_exit = done
    k.run(start + (A["seconds"] + 6) * 1_000_000_000)
    extra = (f"tracelens.sim v1 scenario={scenario} seed={seed} late_ticks={knobs.late_ticks} "
             f"noise={knobs.noise:.2f} " + " ".join(f"{p}={v}" for p, v in sorted((params or {}).items())))
    return k.text(extra.strip())


def write_trace(path: str | Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        path.write_text(text, encoding="utf-8", newline="\n")
    return path
