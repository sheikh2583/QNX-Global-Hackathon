"""QNX-specific remedies: one per root cause the detectors can prove.

Each rule looks at a finding (from the trace) and the workload's C sources and returns a
``Remedy``. A remedy is *automatic* only when the rewrite is a known-safe transform whose
preconditions the rule has checked in the source; otherwise it is *guided*: the exact source
locations, what to change, and why on QNX. Either way the fix is then judged by re-tracing the
patched build on the target (``tracelens fix``), never by the rule itself.

  semaphore-as-lock      sem_t used as a lock -> priority-inheriting pthread mutex      (auto)
  fixed-priority-channel _NTO_CHF_FIXED_PRIORITY on a server channel -> default flags   (auto)
  ist-defer-work         interrupt thread works before InterruptUnmask() -> unmask
                         first, defer the work to a worker thread via a pulse           (auto)
  shrink-critical-section work that touches no shared data moved out of the lock        (auto)
  ipc-cycle              mutual MsgSend() -> send hierarchy                             (guided)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..findings import Finding
from . import csrc

HELPER_TAG = "/* --- TraceLens remedy"


@dataclass
class Remedy:
    rule: str
    finding_id: str
    finding_kind: str
    title: str
    automatic: bool
    rationale: str
    changes: dict[str, str] = field(default_factory=dict)  # path -> full new text (automatic only)
    locations: list[tuple[str, int, str]] = field(default_factory=list)  # (path, line, code)
    guidance: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # why an automatic rewrite was not attempted

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "changes"} | {"files": sorted(self.changes)}


def _loc(path: str, text: str, pos: int) -> tuple[str, int, str]:
    line = csrc.line_of(text, pos)
    return (path, line, text.splitlines()[line - 1].strip())


def _thread_functions(text: str, m: str, names: list[str]) -> set[str]:
    """Functions that name a thread involved in the finding (tl_thread_init / pthread_setname_np
    / TL_META string literals, or a snprintf pattern like "worker%u")."""
    out = set()
    for f in csrc.functions(m):
        body = text[f.body_open:f.body_close]
        lits = re.findall(r'"([^"\\]*)"', body)
        for n in names:
            base = re.sub(r"\d+$", "", n)
            if any(lit == n or (base and re.fullmatch(re.escape(base) + r"%[ud]", lit)) for lit in lits):
                out.add(f.name)
    return out


def _add_after_includes(text: str, block: str) -> str:
    incs = list(re.finditer(r"^[ \t]*#[ \t]*include[^\n]*\n", text, re.M))
    pos = incs[-1].end() if incs else 0
    return text[:pos] + block + text[pos:]


def _ensure_include(text: str, header: str) -> str:
    if re.search(rf"#\s*include\s*<{re.escape(header)}>", text):
        return text
    incs = list(re.finditer(r"^[ \t]*#[ \t]*include[^\n]*\n", text, re.M))
    pos = incs[0].start() if incs else 0
    return text[:pos] + f"#include <{header}>\n" + text[pos:]


# ============================================================================ semaphore-as-lock
PI_HELPER = f"""
{HELPER_TAG}: priority-inheriting mutex (replaces a semaphore used as a lock) --- */
static int tracelens_pi_mutex_init(pthread_mutex_t *m)
{{
    pthread_mutexattr_t a;
    int rc = pthread_mutexattr_init(&a);
    if (rc == 0)
        rc = pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_INHERIT);
    if (rc == 0)
        rc = pthread_mutex_init(m, &a);
    pthread_mutexattr_destroy(&a);
    if (rc != 0)
        errno = rc;
    return rc;
}}
"""


def semaphore_as_lock(f: Finding, sources: dict[str, str]) -> Remedy | None:
    if f.kind != "priority_inversion" or "semaphore" not in f.title:
        return None
    r = Remedy("semaphore-as-lock", f.id, f.kind,
               "Replace the semaphore used as a lock with a priority-inheriting mutex", False,
               "A POSIX semaphore has no owner, so the QNX kernel cannot raise the priority of the thread "
               "that holds it: a medium-priority thread preempts the holder and the high-priority waiter "
               "waits for both. A pthread mutex has an owner; with PTHREAD_PRIO_INHERIT (the QNX default) "
               "the holder runs at the waiter's priority until it unlocks.")
    cands = []
    for path, text in sources.items():
        m = csrc.mask(text)
        for name, decl, _static in csrc.top_level_decls(text, m):
            if not re.search(r"\bsem_t\b", decl):
                continue
            uses = re.findall(rf"\b(sem_\w+)\s*\(\s*&\s*{re.escape(name)}\b", m)
            inits = re.findall(rf"\bsem_init\s*\(\s*&\s*{re.escape(name)}\s*,[^,]*,\s*([^)]*?)\s*\)", m)
            lockish = (inits == ["1"] and set(uses) <= {"sem_init", "sem_wait", "sem_post", "sem_destroy"}
                       and uses.count("sem_wait") == uses.count("sem_post") > 0)
            balanced = all(
                len(re.findall(rf"\bsem_wait\s*\(\s*&\s*{name}\b", m[fn.body_open:fn.body_close]))
                == len(re.findall(rf"\bsem_post\s*\(\s*&\s*{name}\b", m[fn.body_open:fn.body_close]))
                for fn in csrc.functions(m))
            other = len(re.findall(rf"\b{re.escape(name)}\b", m)) - len(uses) - 1  # minus the declaration
            r.locations += [_loc(path, text, x.start()) for x in
                            re.finditer(rf"\bsem_(wait|post)\s*\(\s*&\s*{re.escape(name)}\b", m)]
            if lockish and balanced and other == 0:
                cands.append((path, name))
            else:
                r.notes.append(f"{path}: {name} is not used strictly as a lock (init value, trywait/timedwait, "
                               f"waits and posts in different functions, or other uses)")
    involved = set()
    for text in sources.values():
        involved |= _thread_functions(text, csrc.mask(text), f.threads)
    if len(cands) > 1 and involved:
        cands = [c for c in cands if any(re.search(rf"\bsem_wait\s*\(\s*&\s*{c[1]}\b",
                 csrc.mask(sources[c[0]])[fn.body_open:fn.body_close])
                 for fn in csrc.functions(csrc.mask(sources[c[0]])) if fn.name in involved)]
    if len(cands) != 1:
        r.guidance.append("Replace the semaphore that guards the shared data with a pthread_mutex_t "
                          "initialised with PTHREAD_PRIO_INHERIT; keep semaphores for signalling only.")
        if len(cands) > 1:
            r.notes.append("several semaphores qualify; not choosing one automatically")
        return r
    path, name = cands[0]
    text = sources[path]
    n = re.escape(name)
    new = re.sub(rf"\bsem_t(\s+){n}\b", rf"pthread_mutex_t\1{name}", text)
    new = re.sub(rf"\bsem_wait(\s*\(\s*&\s*{n}\b)", r"pthread_mutex_lock\1", new)
    new = re.sub(rf"\bsem_post(\s*\(\s*&\s*{n}\b)", r"pthread_mutex_unlock\1", new)
    new = re.sub(rf"\bsem_destroy(\s*\(\s*&\s*{n}\b)", r"pthread_mutex_destroy\1", new)
    new = re.sub(rf"\bsem_init\s*\(\s*&\s*{n}\s*,[^,]*,\s*1\s*\)(\s*(==\s*-1|<\s*0|!=\s*0))?",
                 lambda mm: f"tracelens_pi_mutex_init(&{name})" + (" != 0" if mm.group(1) else ""), new)
    new = _add_after_includes(new, PI_HELPER)
    new = _ensure_include(_ensure_include(new, "pthread.h"), "errno.h")
    r.automatic, r.changes = True, {path: new}
    r.title = f"Replace semaphore '{name}' (used as a lock) with a priority-inheriting mutex"
    return r


# ============================================================================ fixed-priority-channel
def fixed_priority_channel(f: Finding, sources: dict[str, str]) -> Remedy | None:
    if f.kind != "priority_inversion" or "message channel" not in f.title:
        return None
    r = Remedy("fixed-priority-channel", f.id, f.kind,
               "Let the server inherit its clients' priority: drop _NTO_CHF_FIXED_PRIORITY", False,
               "By default a QNX server thread runs at the priority of the client whose message it "
               "receives, so a high-priority request is served at high priority. _NTO_CHF_FIXED_PRIORITY "
               "turns that off: the server stays at its own low priority and any medium-priority thread "
               "delays the high-priority client's reply.")
    changes = {}
    for path, text in sources.items():
        m = csrc.mask(text)
        edits = []
        for call in re.finditer(r"\bChannelCreate(?:_r)?\s*\(", m):
            p_open = call.end() - 1
            p_close = csrc.match(m, p_open)
            arg = text[p_open + 1:p_close]
            if "_NTO_CHF_FIXED_PRIORITY" not in arg:
                continue
            r.locations.append(_loc(path, text, call.start()))
            parts = [p.strip() for p in arg.split("|")]
            rest = [p for p in parts if p != "_NTO_CHF_FIXED_PRIORITY"]
            if len(rest) == len(parts) or any("_NTO_CHF_FIXED_PRIORITY" in p for p in rest):
                r.notes.append(f"{path}:{csrc.line_of(text, call.start())}: flag expression too complex to edit")
                continue
            edits.append((p_open + 1, p_close, " | ".join(rest) if rest else "0"))
        if edits:
            new = text
            for a, b, rep in sorted(edits, reverse=True):
                new = new[:a] + rep + new[b:]
            changes[path] = new
    if changes:
        r.automatic, r.changes = True, changes
    else:
        r.guidance.append("Create the server channel without _NTO_CHF_FIXED_PRIORITY (or raise the server "
                          "thread to its most urgent client's priority).")
    return r


# ============================================================================ ist-defer-work
IST_HELPER = f"""
{HELPER_TAG}: deferred interrupt work --- */
/* The interrupt thread only acknowledges, unmasks and pulses; the work it used to do with the
 * interrupt masked runs in this worker. Interrupts that arrive while a run is pending are
 * coalesced into it. @@PRIO_WHY@@ */
#define TRACELENS_IRQ_PULSE (_PULSE_CODE_MINAVAIL + 7)
#define TRACELENS_IRQ_WORKER_PRIO @@PRIO@@
static int tracelens_irq_chid = -1, tracelens_irq_coid = -1, tracelens_irq_prio = TRACELENS_IRQ_WORKER_PRIO;
static atomic_int tracelens_irq_pending, tracelens_irq_running = 1;
static pthread_t tracelens_irq_thread;

static void tracelens_irq_work(void)
{{
@@WORK@@
}}

static void *tracelens_irq_worker(void *arg)
{{
    (void)arg;
    struct _pulse p;
    while (atomic_load(&tracelens_irq_running)) {{
        if (MsgReceivePulse(tracelens_irq_chid, &p, sizeof p, NULL) == -1)
            break;
        if (p.code != TRACELENS_IRQ_PULSE)
            continue;
        atomic_store(&tracelens_irq_pending, 0);
        tracelens_irq_work();
    }}
    return NULL;
}}

static int tracelens_irq_worker_start(void)
{{
    struct sched_param sp;
    if ((tracelens_irq_chid = ChannelCreate(0)) == -1)
        return -1;
    if ((tracelens_irq_coid = ConnectAttach(0, 0, tracelens_irq_chid, _NTO_SIDE_CHANNEL, 0)) == -1)
        return -1;
    pthread_attr_t a;
    pthread_attr_init(&a);
    pthread_attr_setinheritsched(&a, PTHREAD_EXPLICIT_SCHED);
    pthread_attr_setschedpolicy(&a, SCHED_FIFO);
    sp.sched_priority = tracelens_irq_prio;
    pthread_attr_setschedparam(&a, &sp);
    int rc = pthread_create(&tracelens_irq_thread, &a, tracelens_irq_worker, NULL);
    pthread_attr_destroy(&a);
    return rc == 0 ? 0 : -1;
}}

static void tracelens_irq_worker_kick(void)
{{
    if (atomic_exchange(&tracelens_irq_pending, 1) == 0)
        MsgSendPulse(tracelens_irq_coid, tracelens_irq_prio, TRACELENS_IRQ_PULSE, 0);
}}

static void tracelens_irq_worker_stop(void)
{{
    atomic_store(&tracelens_irq_running, 0);
    MsgSendPulse(tracelens_irq_coid, tracelens_irq_prio, TRACELENS_IRQ_PULSE + 1, 0);
    pthread_join(tracelens_irq_thread, NULL);
}}
"""
HW_ACCESS = re.compile(r"\b(in8|in16|in32|inle16|inle32|inbe16|inbe32|out8|out16|out32|outle16|outle32|"
                       r"inp|outp|InterruptWait|InterruptUnmask|InterruptMask)\b")


def ist_defer_work(f: Finding, sources: dict[str, str]) -> Remedy | None:
    if f.kind != "irq_handler_overrun":
        return None
    r = Remedy("ist-defer-work", f.id, f.kind,
               "Unmask the interrupt first and move the heavy work out of the interrupt thread", False,
               "With InterruptAttachEvent() the kernel masks the interrupt until the thread calls "
               "InterruptUnmask(). Work done before that keeps the line masked (later interrupts are "
               "delayed or lost) and keeps the highest-priority thread busy. The QNX pattern: acknowledge, "
               "unmask, and hand the rest to a lower-priority worker with a pulse.")
    own, lowest = f.metrics.get("handler_prio"), f.metrics.get("lowest_interrupt_thread_prio")
    cands = [p for p in (own, lowest) if isinstance(p, int)]
    prio = max(1, min(cands) - 1) if cands else 10
    why = (f"Worker priority {prio}: below every interrupt thread seen in the trace (lowest: "
           f"{f.metrics.get('lowest_interrupt_thread')} at {lowest}), so deferred work never delays a "
           f"driver's interrupt." if isinstance(lowest, int) else
           f"Worker priority {prio}: below the interrupt thread.")
    for path, text in sources.items():
        m = csrc.mask(text)
        for fn in csrc.functions(m):
            res = _ist_loop(path, text, m, fn, r, prio, why)
            if res:
                r.automatic, r.changes = True, {path: res}
                return r
    if not r.guidance:
        r.guidance.append("In the interrupt thread, call InterruptUnmask() right after reading/acknowledging "
                          "the device; move further processing to a lower-priority thread (pulse or condvar).")
    return r


def _ist_loop(path: str, text: str, m: str, fn: csrc.Function, r: Remedy, prio: int = 10,
              why: str = "") -> str | None:
    for loop in re.finditer(r"\b(while|for)\s*\(", m[fn.body_open:fn.body_close]):
        lpos = fn.body_open + loop.start()
        p_close = csrc.match(m, fn.body_open + loop.end() - 1)
        brace = m.find("{", p_close)
        if brace < 0 or m[p_close + 1:brace].strip():
            continue
        end = csrc.match(m, brace)
        stmts = csrc.statements(m, brace + 1, end)
        iw = next((i for i, s in enumerate(stmts) if re.search(r"\bInterruptWait\s*\(", m[s.start:s.end])), None)
        iu = next((i for i, s in enumerate(stmts) if re.match(r"\s*InterruptUnmask\s*\(", m[s.start:s.end])), None)
        if iw is None or iu is None or iu <= iw + 1:
            continue
        r.locations += [_loc(path, text, stmts[iw].start), _loc(path, text, stmts[iu].start)]
        between = stmts[iw + 1:iu]
        keep = [s for s in between if HW_ACCESS.search(m[s.start:s.end]) or not csrc.calls(m, s.start, s.end)]
        work = [s for s in between if s not in keep]
        if not work:
            r.notes.append("nothing to defer between InterruptWait() and InterruptUnmask()")
            return None
        if work != between[len(between) - len(work):] and any(between.index(w) < between.index(k)
                                                              for w in work for k in keep):
            r.notes.append("device access follows the heavy work; reordering it is not safe to automate")
            return None
        local_names = _locals(m, fn)
        used = set().union(*(csrc.idents(m, s.start, s.end) for s in work))
        if used & local_names:
            r.notes.append(f"the work uses locals of {fn.name}() ({', '.join(sorted(used & local_names))}); "
                           "a worker thread cannot see them")
            return None
        if any(csrc.CONTROL_EXIT.search(m[s.start:s.end]) for s in work):
            r.notes.append("the work contains return/break/continue; not moving it")
            return None
        body_text = "".join(text[s.lead:_eol(text, s.end)] for s in work)
        body_text = "\n".join("    " + ln.strip() if ln.strip() else "" for ln in body_text.splitlines())
        unmask = stmts[iu]
        last_keep = stmts[iw] if not keep else keep[-1]
        indent = re.match(r"[ \t]*", text[unmask.lead:]).group(0)
        loop_line = text.rfind("\n", 0, lpos) + 1
        lindent = re.match(r"[ \t]*", text[loop_line:]).group(0)
        # Start the worker before the interrupt is attached and stop it after it is detached:
        # creating a thread and a channel are messages to procnto that take milliseconds, and an
        # interrupt arriving meanwhile would wait for them (measured on QNX 8.0: up to 20 ms).
        attach = re.search(r"\bInterruptAttach(?:Event|Thread)?\s*\(", m[fn.body_open:lpos])
        start_at = loop_line
        if attach:
            apos = fn.body_open + attach.start()
            start_at = text.rfind("\n", 0, apos) + 1
            while text[start_at:].lstrip().startswith(("|", "&")):  # continuation of an expression
                start_at = text.rfind("\n", 0, start_at - 1) + 1
        detach = re.search(r"\bInterruptDetach\s*\(", m[end:fn.body_close])
        stop_at = _eol(text, end + detach.start()) if detach else _eol(text, end)
        sindent = re.match(r"[ \t]*", text[start_at:]).group(0)
        # Edits on the original text, applied back to front so offsets stay valid:
        edits = [
            (stop_at, stop_at, f"{lindent}tracelens_irq_worker_stop();  /* TraceLens */\n"),
            (unmask.lead, _eol(text, unmask.end), ""),
            *[(s.lead, _eol(text, s.end), "") for s in work],
            (_eol(text, last_keep.end), _eol(text, last_keep.end),
             f"{indent}{text[unmask.start:unmask.end]}  /* unmask first (TraceLens) */\n"
             f"{indent}tracelens_irq_worker_kick();  /* deferred work (TraceLens) */\n"),
            (start_at, start_at, f"{sindent}if (tracelens_irq_worker_start() == -1)  /* TraceLens */\n"
                                 f"{sindent}    perror(\"tracelens_irq_worker_start\");\n"),
            # the helper goes right above this function, after everything the work refers to
            (fn.start, fn.start, "\n\n" + IST_HELPER.replace("@@WORK@@", body_text.rstrip())
             .replace("@@PRIO@@", str(prio)).replace("@@PRIO_WHY@@", why).strip("\n")),
        ]
        new = text
        for a, b, rep in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
            new = new[:a] + rep + new[b:]
        for h in ("stdatomic.h", "pthread.h", "sys/neutrino.h", "stdio.h"):
            new = _ensure_include(new, h)
        r.title = (f"Unmask IRQ first in {fn.name}() and defer "
                   f"{', '.join(csrc.calls(m, work[0].start, work[-1].end))}() to a worker thread")
        return new
    return None


def _eol(text: str, pos: int) -> int:
    """Index just past the end of the line containing ``pos`` (keeps trailing comments)."""
    j = text.find("\n", pos)
    return len(text) if j < 0 else j + 1


DECL_START = re.compile(r"(?:^|[;{}(])\s*((?:(?:const|static|unsigned|signed|struct|union|enum|volatile|register)"
                        r"\s+)*[A-Za-z_]\w*(?:\s*\*+\s*|\s+)[A-Za-z_]\w*\s*[=;,\[])")


def _locals(m: str, fn: csrc.Function) -> set[str]:
    """Every name declared in the function body (all declarators: ``int a = 0, b;`` gives a and b)."""
    body = m[fn.body_open + 1:fn.body_close]
    names = set()
    for d in DECL_START.finditer(body):
        first = d.group(1)
        if re.match(r"(return|goto|case|else|sizeof)\b", first):
            continue
        start = d.start(1)
        end = start
        depth = 0
        while end < len(body) and not (body[end] == ";" and depth == 0):
            depth += body[end] in "([{"
            depth -= body[end] in ")]}"
            if depth < 0:
                break
            end += 1
        decl = body[start:end]
        type_and_first = re.match(r"((?:\w+\s+)*?\w+)(?:\s*\*+\s*|\s+)(?=[A-Za-z_]\w*\s*(?:[=,\[]|$))", decl)
        rest = decl[type_and_first.end():] if type_and_first else decl
        for part in csrc._split_top(rest, ","):
            lhs = re.sub(r"\[[^\]]*\]", "", part.split("=")[0]).replace("*", " ")
            ids = [x for x in csrc.IDENT.findall(lhs) if x not in csrc.KEYWORDS]
            if ids:
                names.add(ids[-1])
    params = m[m.rfind("(", fn.start, fn.body_open):fn.body_open]
    names |= set(re.findall(r"([A-Za-z_]\w*)\s*(?:\[\s*\])?\s*[,)]", params))
    return names - csrc.KEYWORDS


# ============================================================================ shrink-critical-section
def shrink_critical_section(f: Finding, sources: dict[str, str]) -> Remedy | None:
    if f.kind != "mutex_contention" or f.metrics.get("kernel_space"):
        return None
    r = Remedy("shrink-critical-section", f.id, f.kind,
               "Move work that touches no shared data out of the critical section", False,
               "Every MUTEX wait in a QNX trace is real contention (uncontended mutexes never enter the "
               "kernel). The lock only needs to cover statements that read or write the data it protects; "
               "computation on private buffers inside it serialises the threads for nothing.")
    changes = {}
    for path, text in sources.items():
        m = csrc.mask(text)
        decls = csrc.top_level_decls(text, m)
        mutexes = [n for n, d, _ in decls if re.search(r"\bpthread_mutex_t\b", d)]
        shared = {n for n, _, _ in decls} - set(mutexes)
        extern_globals = any(not st for n, _, st in decls if n not in mutexes)
        fns = csrc.functions(m)
        touching = {fn.name for fn in fns if csrc.idents(m, fn.body_open, fn.body_close) & shared}
        new, edits = text, []
        for fn in fns:
            taint = csrc.tainted_locals(m, fn, shared)
            stmts = csrc.statements(m, fn.body_open + 1, fn.body_close)
            for blk in _blocks(m, fn, stmts):
                edits += _shrink_block(path, text, m, blk, mutexes, shared | taint | touching,
                                       {x.name for x in fns}, extern_globals, r)
        for kind, a, b, at in sorted(edits, key=lambda e: e[1], reverse=True):
            chunk = new[a:b]
            if kind == "before":  # move chunk [a,b) to position `at` (< a)
                new = new[:at] + chunk + new[at:a] + new[b:]
            else:  # "after": move chunk [a,b) to position `at` (> b)
                new = new[:a] + new[b:at] + chunk + new[at:]
        if edits:
            changes[path] = new
    if changes:
        r.automatic, r.changes = True, changes
    else:
        r.guidance.append("Copy data out (or in) under the lock and do the processing outside it; publish "
                          "results with a pointer swap; or split the lock per resource.")
    return r


def _blocks(m: str, fn: csrc.Function, stmts: list[csrc.Stmt]):
    """Every statement list in the function (function body and nested { } blocks)."""
    yield stmts
    for s in stmts:
        i = s.start
        while True:
            j = m.find("{", i, s.end)
            if j < 0:
                break
            close = csrc.match(m, j)
            yield from _blocks(m, fn, csrc.statements(m, j + 1, close))
            i = close + 1


def _shrink_block(path, text, m, stmts, mutexes, shared, local_fns, extern_globals, r):
    edits = []
    for i, s in enumerate(stmts):
        lk = re.fullmatch(r"\s*pthread_mutex_lock\s*\(\s*&\s*([A-Za-z_]\w*)\s*\)\s*;", m[s.start:s.end])
        if not lk or lk.group(1) not in mutexes:
            continue
        name = lk.group(1)
        j = next((k for k in range(i + 1, len(stmts)) if re.fullmatch(
            rf"\s*pthread_mutex_unlock\s*\(\s*&\s*{name}\s*\)\s*;", m[stmts[k].start:stmts[k].end])), None)
        if j is None:
            continue
        inner = stmts[i + 1:j]
        r.locations.append(_loc(path, text, s.start))

        def private(st):
            code = m[st.start:st.end]
            if csrc.CONTROL_EXIT.search(code) or re.search(r"\bpthread_(mutex|cond)_\w+", code):
                return False
            if csrc.idents(m, st.start, st.end) & shared:
                return False
            ext = [c for c in csrc.calls(m, st.start, st.end) if c not in local_fns]
            return not (ext and extern_globals)

        pre = 0
        while pre < len(inner) and private(inner[pre]):
            pre += 1
        post = 0
        while post < len(inner) - pre and private(inner[len(inner) - 1 - post]):
            post += 1
        if pre:  # whole lines, so comments and indentation travel with the code
            edits.append(("before", inner[0].lead, _eol(text, inner[pre - 1].end), s.lead))
        if post:
            edits.append(("after", inner[len(inner) - post].lead, _eol(text, inner[-1].end),
                          _eol(text, stmts[j].end)))
        if pre or post:
            moved = [csrc.calls(m, x.start, x.end) for x in inner[:pre] + inner[len(inner) - post:]]
            r.title = (f"Shrink the '{name}' critical section: move "
                       f"{', '.join(c for cs in moved for c in cs) or 'private statements'} outside the lock")
        else:
            r.notes.append(f"{path}:{csrc.line_of(text, s.start)}: every statement under '{name}' touches "
                           "shared data")
    return edits


# ============================================================================ ipc-cycle (guided)
def ipc_cycle(f: Finding, sources: dict[str, str]) -> Remedy | None:
    if f.kind != "ipc_deadlock":
        return None
    r = Remedy("ipc-cycle", f.id, f.kind, "Break the Send/Reply cycle with a send hierarchy", False,
               "QNX message passing is synchronous: a thread blocked in MsgSend() cannot receive. If two "
               "servers send to each other, each waits for the other to receive. QNX designs avoid this with "
               "a send hierarchy: messages only flow one way; the other direction uses non-blocking "
               "notifications (MsgSendPulse()/MsgDeliverEvent()) and the notified side pulls the data.")
    for path, text in sources.items():
        m = csrc.mask(text)
        r.locations += [_loc(path, text, x.start()) for x in re.finditer(r"\bMsgSendv?(?:_r|nc)?\s*\(", m)]
    r.guidance += [
        f"The trace shows the cycle {f.title.split(': ', 1)[-1]}; these MsgSend() calls are where it closes.",
        "Pick a direction (usually: the more central server never sends to its clients). On the other side, "
        "replace MsgSend() with MsgSendPulse() (or MsgDeliverEvent() from a reply), and let the receiver "
        "fetch what it needs with its own MsgSend() down the hierarchy.",
        "Not automated: the reply carries data, so the new protocol is a design decision.",
    ]
    return r


RULES = [semaphore_as_lock, fixed_priority_channel, ist_defer_work, shrink_critical_section, ipc_cycle]
