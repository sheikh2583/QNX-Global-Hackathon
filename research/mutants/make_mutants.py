"""Generate every R2 mutant: patch.diff, README.md and expected.toml under research/mutants/<workload>/<id>/.

    python research/mutants/make_mutants.py          # write
    python research/mutants/make_mutants.py --check  # fail if the committed files differ from a fresh run

Each patch is a unified diff against the *buggy* workload source (bugzoo/<workload>/main.c, `a/main.c` -> `b/main.c`), so
applying it to a copy of that file yields the mutant. Two third-party mutants (TTK4147, memcached) are diffs against
upstream files fetched by hash; their patches are copies of the committed TraceLens output or written against the pinned file.

The predictions in expected.toml are written BEFORE any mutant is captured (docs/research/PROTOCOL.md, E2). `confidence` says
how sure the reasoning is, not how likely the outcome. Where a prediction hinges on a detector threshold we have not
measured, it is marked low and the reason is stated; the outcome is reported next to it either way.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import difflib
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "mutants"
ZOO = ROOT / "bugzoo"

ORACLES = ("O1", "O2", "O3", "O4", "O4c", "O5")


def sub(src: str, old: str, new: str, count: int = 1) -> str:
    assert src.count(old) >= 1, f"pattern not found: {old!r}"
    return src.replace(old, new) if count == 0 else src.replace(old, new, count)


@dataclass
class Mutant:
    workload: str          # directory under research/mutants/
    id: str
    base: str              # path of the base file, relative to the repo root
    truth: str             # "good" | "bad"
    summary: str
    why: str
    tests: str
    verdict: str           # expected O4 verdict at the full 20 captures: VERIFIED | NOT FIXED | INCONCLUSIVE
    pred: dict[str, str]   # per oracle at full N: "accept" | "reject"
    confidence: str        # high | medium | low
    rationale: str
    new_text: str | None = None      # full text of the mutant file (diffed against the base)
    patch_from: str | None = None    # or a committed patch to copy
    note: str = ""
    extra: dict[str, str] = field(default_factory=dict)


def zsrc(w: str) -> str:
    return (ZOO / w / "main.c").read_text(encoding="utf-8")


def zref(w: str) -> str:
    return (ZOO / "reference" / f"{w}.c").read_text(encoding="utf-8")


def mutexify(src: str, protocol: str) -> str:
    """Replace Z1's sem_t buf_lock with a pthread mutex of the given protocol."""
    src = sub(src, "static sem_t buf_lock;", "static pthread_mutex_t buf_lock;")
    src = sub(src, "sem_wait(&buf_lock);", "pthread_mutex_lock(&buf_lock);", 0)
    src = sub(src, "sem_post(&buf_lock);", "pthread_mutex_unlock(&buf_lock);", 0)
    src = sub(src, "sem_destroy(&buf_lock);", "pthread_mutex_destroy(&buf_lock);")
    src = sub(src, '    if (sem_init(&buf_lock, 0, 1) == -1)\n        tl_die("sem_init");',
              "    pthread_mutexattr_t ma;\n    pthread_mutexattr_init(&ma);\n"
              f"    pthread_mutexattr_setprotocol(&ma, {protocol});\n"
              '    if ((errno = pthread_mutex_init(&buf_lock, &ma)) != 0)\n        tl_die("pthread_mutex_init");')
    return src


def build() -> list[Mutant]:
    z1, z2, z3, z4, z5 = (zsrc(w) for w in ("z1_infusion_pump", "z2_brake_by_wire", "z3_sensor_fusion",
                                            "z4_camera_pipeline", "z5_motor_encoder"))
    B = {"z1": "bugzoo/z1_infusion_pump/main.c", "z2": "bugzoo/z2_brake_by_wire/main.c",
         "z3": "bugzoo/z3_sensor_fusion/main.c", "z4": "bugzoo/z4_camera_pipeline/main.c",
         "z5": "bugzoo/z5_motor_encoder/main.c"}
    ACC = dict.fromkeys(ORACLES, "accept")
    REJ = dict.fromkeys(ORACLES, "reject")
    M: list[Mutant] = []

    # ------------------------------------------------------------------ Z1
    M.append(Mutant("z1_infusion_pump", "Z1-ref", B["z1"], "good",
                    "The hand-written reference fix: a priority-inheriting mutex, flash write outside the lock.",
                    "It removes the cause (no inheritance through a semaphore) and keeps the lock short.",
                    "Positive control: a good patch must be accepted.", "VERIFIED", ACC, "high",
                    "Shipped as a VERIFIED fix on QNX 8.0 (docs/results/fix.md).", new_text=zref("z1_infusion_pump")))
    M.append(Mutant("z1_infusion_pump", "Z1-noop", B["z1"], "bad",
                    "A comment line is added; no behaviour changes.",
                    "Nothing was fixed.", "Trivial false accept: does any oracle accept an unchanged build?", "NOT FIXED", REJ,
                    "high", "The bug shows in every capture of the unchanged build (rate 1.0), so even a single capture "
                            "rejects. The study checks that the oracles do not accept on noise.",
                    new_text="/* tracelens mutant: comment only */\n" + z1))
    M.append(Mutant("z1_infusion_pump", "Z1-noPI", B["z1"], "bad",
                    "The semaphore becomes a mutex whose protocol is set explicitly to PTHREAD_PRIO_NONE.",
                    "QNX mutexes inherit priority by default, so the patch must say PRIO_NONE to keep the inversion. "
                    "It looks like the reference fix and is not.",
                    "Does the oracle catch an inversion through a non-inheriting mutex?", "NOT FIXED", REJ, "medium",
                    "The scheduling is that of the original (no inheritance). Medium, not high: (verify) that the "
                    "priority_inversion rule fires on a mutex wait as it does on a semaphore wait.",
                    new_text=mutexify(z1, "PTHREAD_PRIO_NONE")))
    t = sub(z1, "tl_spin_us(6000); /* compression + upload */", "tl_spin_us(300); /* compression + upload, trimmed */")
    M.append(Mutant("z1_infusion_pump", "Z1-mask", B["z1"], "bad",
                    "The semaphore stays; telemetry's work drops from 6 ms to 0.3 ms.",
                    "Control now meets its deadline because the preemption window shrank, but the inversion cause is untouched.",
                    "Symptom masking: deadline met, cause still there.", "NOT FIXED",
                    {"O1": "reject", "O2": "accept", "O3": "reject", "O4": "reject", "O5": "reject"}, "low",
                    "Predicted: the deadline oracle (O2) accepts; findings-based oracles reject IF the inversion rule "
                    "fires on a 0.3 ms window. That depends on the rule's minimum duration, which we have not measured "
                    "for this window; if the rule stays silent, O1/O3/O4/O5 accept too and the mutant is a false accept "
                    "for TraceLens itself, which is a result.", new_text=t))
    t = sub(z1, "static uint64_t t0;", "static uint64_t t0;\nstatic uint64_t tele_shift_ns; /* 0: inverted; 2 ms: clear */")
    t = sub(t, "tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US - 1000 * TL_NS_PER_US);\n        tl_spin_us(6000);",
            "tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US - 1000 * TL_NS_PER_US + tele_shift_ns);\n"
            "        tl_spin_us(6000);")
    t = sub(t, "    pthread_t th[3] =", "    tele_shift_ns = ((tl_now_ns() / TL_NS_PER_MS) % 5 == 0) ? 0 : 2000 * TL_NS_PER_US;\n    pthread_t th[3] =")
    M.append(Mutant("z1_infusion_pump", "Z1-rare", B["z1"], "bad",
                    "The semaphore stays; telemetry is released after control finishes in about 80% of captures, "
                    "decided once per run from the start time.",
                    "The inversion still happens, in roughly 20% of captures (every period of those captures).",
                    "Rare race: false accepts should fall as N grows.", "NOT FIXED",
                    {"O1": "reject", "O2": "reject", "O3": "reject", "O4": "reject", "O5": "reject"}, "medium",
                    "At the full N=20 each oracle sees about 4 inverted captures and rejects (the chance that none of 20 "
                    "is inverted is 0.8^20 = 1%). At N=1 O1 accepts about 80% of the time and O3 at N=3 about 51%. The "
                    "20% rate is the design; (verify) the realised rate in the pilot before E2 is frozen if time allows.",
                    new_text=t, note="Realised inversion rate per capture is measured, not assumed: reported with its CI."))
    t = mutexify(z1, "PTHREAD_PRIO_INHERIT")
    t = sub(t, "tl_spin_us(2500); /* write to flash */", "tl_spin_us(3000); /* write to flash, still under the lock */")
    M.append(Mutant("z1_infusion_pump", "Z1-newbug", B["z1"], "bad",
                    "A correct priority-inheriting mutex, but the logger holds it across a 3 ms flash write.",
                    "The inversion is gone and a new cause appears: control waits for the lock.",
                    "A fix that introduces a new cause.", "NOT FIXED",
                    {"O1": "accept", "O2": "reject", "O3": "accept", "O4": "reject", "O5": "reject"}, "low",
                    "The target kind (priority_inversion) disappears, so O1 and O3 accept. O4 rejects through a new "
                    "kind (mutex_contention) or the budget. O2 is borderline: the estimated control response is about "
                    "2.1 ms against a 2 ms budget, so the deadline-only prediction is low confidence.", new_text=t))

    # ------------------------------------------------------------------ Z2
    M.append(Mutant("z2_brake_by_wire", "Z2-ref", B["z2"], "good",
                    "The reference fix: ChannelCreate(0), so the server inherits the client's priority.",
                    "Removes the fixed-priority flag that caused the inversion.", "Control.", "VERIFIED", ACC, "high",
                    "VERIFIED on QNX 8.0 (docs/results/fix.md).", new_text=zref("z2_brake_by_wire")))
    t = sub(z2, "ChannelCreate(_NTO_CHF_FIXED_PRIORITY)", "ChannelCreate(0)")
    t = sub(t, "            continue; /* pulse */\n",
            "            continue; /* pulse */\n        pthread_setschedprio(pthread_self(), 10); /* back to the idle priority */\n")
    M.append(Mutant("z2_brake_by_wire", "Z2-selfprio", B["z2"], "bad",
                    "The flag is dropped, but the server sets its own priority back to 10 after every MsgReceive().",
                    "Fixed priority by another route: the message's priority boost is undone.",
                    "Does the oracle see through an equivalent of the original bug?", "NOT FIXED", REJ, "medium",
                    "The scheduling is that of the original during the 200 us validation, so the inversion should "
                    "persist. Medium: (verify) the effect of pthread_setschedprio on a thread that holds an inherited "
                    "priority on QNX 8.0.", new_text=t))
    t = sub(z2, "tl_spin_us(6000); /* self-test sweep */", "tl_spin_us(200); /* self-test sweep, trimmed */")
    M.append(Mutant("z2_brake_by_wire", "Z2-mask", B["z2"], "bad",
                    "Diagnostics' load drops from 6 ms to 0.2 ms.", "The deadline passes; the fixed-priority channel remains.",
                    "Symptom masking in an IPC bug.", "NOT FIXED",
                    {"O1": "reject", "O2": "accept", "O3": "reject", "O4": "reject", "O5": "reject"}, "low",
                    "Same structure as Z1-mask: O2 accepts; findings-based oracles reject only if the inversion rule "
                    "fires on a 0.2 ms preemption window (unmeasured).", new_text=t))

    # ------------------------------------------------------------------ Z3
    M.append(Mutant("z3_sensor_fusion", "Z3-ref", B["z3"], "good",
                    "The reference fix: a strict send hierarchy (fusion_b notifies with a pulse).",
                    "Removes the send cycle.", "Control.", "VERIFIED", ACC, "high",
                    "GUIDED rather than auto-fixed in the shipped tool, but the reference removes the cycle, so the "
                    "build must read as fixed.", new_text=zref("z3_sensor_fusion")))
    t = sub(z3, "uint64_t timeout = 1 * TL_NS_PER_S;", "uint64_t timeout = 50 * TL_NS_PER_MS;")
    M.append(Mutant("z3_sensor_fusion", "Z3-timeout", B["z3"], "bad",
                    "The send timeout drops from 1 s to 50 ms.", "The deadlock breaks sooner; the cycle still forms.",
                    "Masking a deadlock with a timeout.", "NOT FIXED",
                    {"O1": "reject", "O2": "accept", "O3": "reject", "O4": "reject", "O5": "reject"}, "low",
                    "Z3 declares no deadline, so O2 accepts vacuously (nothing to violate); this is a property of "
                    "the oracle and is reported as such. The others reject if the ipc_deadlock rule fires on a 50 ms "
                    "cycle; (verify) its minimum duration.", new_text=t))
    M.append(Mutant("z3_sensor_fusion", "Z3-noop", B["z3"], "bad", "A comment line is added.", "Nothing was fixed.",
                    "Trivial false accept for a deadlock.", "NOT FIXED",
                    {"O1": "reject", "O2": "accept", "O3": "reject", "O4": "reject", "O5": "reject"}, "high",
                    "The deadlock forms in every capture. O2 accepts vacuously: no deadline is declared for Z3.",
                    new_text="/* tracelens mutant: comment only */\n" + z3))

    # ------------------------------------------------------------------ Z4
    M.append(Mutant("z4_camera_pipeline", "Z4-ref", B["z4"], "good",
                    "The reference fix: work on a private double-buffered tile, publish a pointer under the lock.",
                    "Hold times drop from about 1.5 ms to well under a microsecond.", "Control.", "VERIFIED", ACC, "high",
                    "VERIFIED on QNX 8.0 (docs/results/fix.md).", new_text=zref("z4_camera_pipeline")))
    t = sub(z4, "        pthread_mutex_lock(&store_lock);\n        /* Demosaic + colour-correct the tile, then publish it. */\n"
                "        memset(tile, (int)(k + id), TILE_BYTES);\n        tl_spin_us(1500);\n"
                "        memcpy(frame_store[id], tile, TILE_BYTES);\n        pthread_mutex_unlock(&store_lock);\n",
            "        /* Demosaic + colour-correct the tile privately, then publish it into the one shared slot. */\n"
            "        memset(tile, (int)(k + id), TILE_BYTES);\n        tl_spin_us(1500);\n"
            "        memcpy(frame_store[0], tile, TILE_BYTES); /* shared, unlocked: a data race */\n")
    t = sub(t, "    pthread_t th[WORKERS];\n", "    pthread_t th[WORKERS];\n    (void)&store_lock;\n")
    M.append(Mutant("z4_camera_pipeline", "Z4-racy", B["z4"], "bad",
                    "The lock is removed and all four workers copy into one shared frame slot.",
                    "Contention disappears because the publish is now a data race (torn tiles).",
                    "EXPECTED ORACLE FAILURE: a timing oracle cannot see a data race, so every oracle should accept. "
                    "Preregistered as a false accept; it motivates the precondition suite and functional checks (R5).",
                    "VERIFIED", ACC, "high",
                    "Contention and the frame deadline both go away; none of O1-O5 looks at data, so all accept. The "
                    "mutant is functionally wrong (concurrent memcpy into frame_store[0]).", new_text=t,
                    note="truth is 'bad' because of data corruption, not timing."))
    t = sub(z4, "        pthread_mutex_lock(&store_lock);\n", "        if (id >= 2)\n            pthread_mutex_lock(&store_lock);\n")
    t = sub(t, "        pthread_mutex_unlock(&store_lock);\n        tl_job_end", "        if (id >= 2)\n            pthread_mutex_unlock(&store_lock);\n        tl_job_end")
    M.append(Mutant("z4_camera_pipeline", "Z4-partial", B["z4"], "bad",
                    "Workers 0 and 1 work lock-free; workers 2 and 3 still hold the lock for the whole tile.",
                    "A partial fix: contention is halved, not removed. (The brief's variant, 3 of 4 lock-free, would leave "
                    "one locker and no contention, i.e. a complete fix; 2 of 4 keeps a real remainder.)",
                    "Partial fix.", "NOT FIXED",
                    {"O1": "reject", "O2": "accept", "O3": "reject", "O4": "reject", "O5": "reject"}, "low",
                    "Two workers still contend, so mutex_contention should persist. O2 accepts if the worst response "
                    "(about two 1.5 ms holds) stays under the 4 ms frame budget: low confidence.", new_text=t))

    # ------------------------------------------------------------------ Z5
    M.append(Mutant("z5_motor_encoder", "Z5-ref", B["z5"], "good",
                    "The reference fix: the IST acks and unmasks at once; a worker below it recomputes.",
                    "Removes the long mask window.", "Control.", "VERIFIED", ACC, "high",
                    "VERIFIED on QNX 8.0 (docs/results/fix.md).", new_text=zref("z5_motor_encoder")))
    r = zref("z5_motor_encoder")
    t = sub(r, "#define WORKER_PRIO 20", "#define WORKER_PRIO 59")
    t = sub(t, "    pthread_t worker = tl_spawn(velocity_worker, NULL);\n\n", "\n")
    t = sub(t, '    if (id == -1)\n        tl_die("InterruptAttachEvent");\n',
            '    if (id == -1)\n        tl_die("InterruptAttachEvent");\n    pthread_t worker = tl_spawn(velocity_worker, NULL);\n')
    M.append(Mutant("z5_motor_encoder", "Z5-hist", B["z5"], "bad",
                    "The historical bad remedy: the worker runs at IST priority minus one and is started after "
                    "InterruptAttachEvent().", "Measured earlier to delay interrupts by about 20 ms (PLAN section 14, 2026-11-14).",
                    "A real past mistake of our own tool: does the oracle catch it?", "NOT FIXED",
                    {"O1": "accept", "O2": "accept", "O3": "accept", "O4": "reject", "O5": "reject"}, "low",
                    "irq_handler_overrun (the target kind) disappears, so O1/O3 accept; Z5 declares no deadline so O2 "
                    "accepts vacuously. Whether O4 rejects depends on a new finding or the interrupt-to-handler latency "
                    "distribution moving: that is unmeasured, and a false accept here would be a reportable weakness.",
                    new_text=t))
    t = sub(z5, "        count++; /* read + ack the encoder */\n        recompute_velocity_profile();\n        InterruptUnmask(irq, id);\n",
            "        count++; /* read + ack the encoder */\n        InterruptUnmask(irq, id);\n        recompute_velocity_profile();\n")
    M.append(Mutant("z5_motor_encoder", "Z5-unmaskonly", B["z5"], "bad",
                    "The interrupt is unmasked before the 2 ms recompute, which still runs in the IST at priority 60.",
                    "Edge case, truth preregistered after reasoning: the line is masked for less time, but at about "
                    "2,700 interrupts/s (one per 0.37 ms) a 2 ms recompute in the IST still cannot keep up, so events "
                    "coalesce and the thread still starves everything below 60 on CPU 0. Judged 'bad' (a partial fix at best).",
                    "Edge case where the finding definition (masked time) and the real harm (IST starvation) differ.",
                    "NOT FIXED", {"O1": "accept", "O2": "accept", "O3": "accept", "O4": "reject", "O5": "reject"}, "low",
                    "If irq_handler_overrun is defined by masked time alone, the finding vanishes and findings oracles "
                    "accept; if it is defined by handler duration, it stays. Not measured: low confidence either way.",
                    new_text=t))

    # ------------------------------------------------------------------ third party
    M.append(Mutant("ttk4147", "TP-ttk-ref", "third_party/ttk4147_pi (UnboundedPriorityInversion.c, fetched by hash)", "good",
                    "TraceLens's own patch: the semaphore used as a lock becomes a priority-inheriting mutex.",
                    "It is the shape the exercise's own task E asks for.", "Third-party control.", "VERIFIED", ACC, "high",
                    "VERIFIED 10/10 to 0/10 (docs/results/third_party_fix/).",
                    patch_from="docs/results/third_party_fix/confirmation/patch.diff"))
    M.append(Mutant("memcached", "MC-ref", "memcached 1.6.45 logger.c (fetched by hash, third_party/memcached_logger)", "good",
                    "TraceLens's one-line recheck-before-wait patch.",
                    "The waiter re-checks the stop flag under the same mutex before waiting.", "Third-party control.",
                    "VERIFIED", ACC, "high", "VERIFIED 10/10 to 0/10 on the real daemon (docs/results/memcached_logger/).",
                    patch_from="docs/results/memcached_logger/confirmation/patch.diff"))
    src = (ROOT / "third_party" / "memcached_logger" / "src" / "logger.c")
    if src.exists():
        base = src.read_text(encoding="utf-8")
        t = sub(base, "    pthread_cond_signal(&logger_stack_cond);\n    pthread_mutex_unlock(&logger_stack_lock);\n    pthread_join(logger_tid, NULL);",
                "    pthread_cond_signal(&logger_stack_cond);\n    pthread_mutex_unlock(&logger_stack_lock);\n"
                "    pthread_cond_signal(&logger_stack_cond); /* belt and braces */\n    pthread_join(logger_tid, NULL);")
        M.append(Mutant("memcached", "MC-wrong", "memcached 1.6.45 logger.c (fetched by hash, third_party/memcached_logger)", "bad",
                        "stop_logger_thread() signals a second time after unlocking instead of the waiter re-checking the flag.",
                        "A plausible wrong fix for a lost wake-up: the second signal is also lost whenever the logger has not "
                        "yet reached its wait, which is the bug.", "A plausible wrong fix for a lost wake-up.", "NOT FIXED", REJ,
                        "medium", "The lost wake-up depends on the waiter checking only watcher_count; a second signal does "
                                  "not change that. Medium: the second signal may land in the window and unblock some runs, "
                                  "lowering the hang rate without removing it, which is the point of the mutant.",
                        new_text=t, extra={"base_file": "third_party/memcached_logger/src/logger.c"}))
    return M


def unified(base_rel: str, base_text: str, new_text: str) -> str:
    name = "logger.c" if base_rel.endswith("logger.c") else "main.c"
    return "".join(difflib.unified_diff(base_text.splitlines(True), new_text.splitlines(True),
                                        fromfile=f"a/{name}", tofile=f"b/{name}", n=3))


def render(m: Mutant) -> dict[str, str]:
    if m.patch_from:
        patch = (ROOT / m.patch_from).read_text(encoding="utf-8")
    else:
        base_rel = m.extra.get("base_file", m.base)
        patch = unified(base_rel, (ROOT / base_rel).read_text(encoding="utf-8"), m.new_text or "")
    readme = (f"# {m.id}\n\n**Truth: {m.truth}.** {m.summary}\n\n**Why.** {m.why}\n\n**Tests.** {m.tests}\n\n"
              f"**Base.** {m.base}. Apply `patch.diff` with `patch -p1` to a copy of the base file.\n"
              + (f"\n**Note.** {m.note}\n" if m.note else "")
              + "\nGenerated by `research/mutants/make_mutants.py`; do not edit by hand.\n")
    pred = chr(10).join(f'{o} = "{m.pred.get(o) or m.pred["O4"]}"' for o in ORACLES)
    tom = (f'# Preregistered before any capture of this mutant (docs/research/PROTOCOL.md, E2).\n'
           f'id = "{m.id}"\nworkload = "{m.workload}"\ntruth = "{m.truth}"\n'
           f'expected_verdict = "{m.verdict}"   # O4 (TraceLens full) at the full 20 captures\n'
           f'confidence = "{m.confidence}"\n'
           f'rationale = """{m.rationale}"""\n\n'
           f'# What each oracle should say at the full 20 after-captures. accept = the oracle calls the patch a fix.\n'
           f'[predicted]\n{pred}\n')
    return {"patch.diff": patch, "README.md": readme, "expected.toml": tom}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    muts = build()
    ids = [m.id for m in muts]
    assert len(set(ids)) == len(ids)
    stale = []
    for m in muts:
        d = OUT / m.workload / m.id
        for name, text in render(m).items():
            f = d / name
            if args.check:
                if not f.exists() or f.read_text(encoding="utf-8") != text:
                    stale.append(str(f.relative_to(ROOT)))
            else:
                d.mkdir(parents=True, exist_ok=True)
                f.write_text(text, encoding="utf-8", newline="\n")
    if args.check:
        print("mutants up to date" if not stale else "stale: " + ", ".join(stale))
        return 1 if stale else 0
    good = sum(m.truth == "good" for m in muts)
    print(f"wrote {len(muts)} mutants ({good} good controls, {len(muts) - good} bad)")
    return 0


if __name__ == "__main__":
    if shutil.which("patch") is None:
        print("note: `patch` not found on PATH; only needed by run.py", file=sys.stderr)
    sys.exit(main())
