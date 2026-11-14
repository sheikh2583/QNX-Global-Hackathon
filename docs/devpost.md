# Devpost submission draft: TraceLens

> Draft. Every number below comes from real QNX 8.0 runs (docs/results/). Remove any claim we can't reproduce live.
> Category: **Developer Tooling & Host Tools**. Also eligible: Grand Prize, Best use of QNX-specific technologies, Best Codelab (codelab URL goes in its field).

**Tagline:** Find, fix, and prove real-time bugs on QNX.

## Inspiration

Real-time bugs are timing bugs. Every function can be correct while the system is late, because the wrong thread had the CPU at the wrong moment. On QNX the evidence is excellent: the instrumented kernel records every scheduling decision, message and interrupt. But reading that evidence is still manual work for an expert scrolling a timeline, and knowing the QNX-specific fix is a second kind of expertise. We wanted the trace to tell you what went wrong, why QNX behaved that way, rewrite the code, and prove on the kernel that the fix worked.

## What it does

TraceLens is a host tool for QNX 8.0 that turns a kernel event trace into findings, code fixes, and a verdict measured on the target. It runs entirely on your machine and your QNX target: no API keys, no cloud, no model. The same trace and source always give the same diagnosis and the same patch.

- **Finds** five classes of real-time bugs with deterministic detectors: priority inversion, Send/Reply deadlocks and blocking chains, mutex contention, interrupt-handler overruns, and deadline misses. Every finding cites the exact trace events that prove it.
- **Understands QNX.** QNX mutexes inherit priority by default, so most textbook inversions can't happen. TraceLens looks for the ones that can: ownerless semaphores and `_NTO_CHF_FIXED_PRIORITY` channels. It reads priorities from kernel events over time, so a traced inheritance boost is recognised. Message-passing deadlocks are found per channel. Locks inside procnto are told apart from yours.
- **Fixes.** Each proven root cause maps to a QNX-specific source transform: a semaphore used as a lock becomes a `PTHREAD_PRIO_INHERIT` mutex; a fixed-priority channel gets its flag dropped; an interrupt thread that works before `InterruptUnmask()` unmasks first and hands the work to a pulse-driven worker at a priority below every interrupt thread in the trace; private work leaves a contended critical section. Each transform checks its safety preconditions in the code (a semaphore used as a signal, a pointer into shared data, an early `return` inside a lock all make it back off) and otherwise gives the exact lines and the fix to make by hand.
- **Proves.** `tracelens fix` captures the program 5 times, patches a sandbox copy, builds it with `qcc`, runs it 5 more times under `tracelogger`, and compares: VERIFIED requires the finding gone in every run, nothing new, and statistically faster response times (Mann-Whitney U). If the verdict is NOT FIXED, it diagnoses the patched build's own traces and fixes again (one fix often uncovers the next cause).
- **Fits the workflow:** HTML/JSON/SARIF reports, exit codes for scripts (including "inconclusive" for lossy traces), Perfetto export, and `tracelens remedy`, which plans the fix from a trace and the source with no target at all.

**Results on real QNX 8.0** (QEMU VM, 4 CPUs, `procnto-smp-instr`):

- **Fixes:** 4 of 5 planted bugs fixed automatically and **VERIFIED on the target**; the fifth (a Send/Reply deadlock, whose fix changes the protocol) gets the exact `MsgSend()` lines and the send-hierarchy fix.
  - Z1 infusion pump: inversion in 5/5 runs → 0/5; dose-controller p99 5.74 → 1.29 ms (budget 2 ms).
  - Z2 brake-by-wire: deadline misses 1000 → 0; brake p99 6.75 → 0.77 ms.
  - Z4 camera pipeline: contention 5/5 → 0/5; frame p99 7.45 → 2.99 ms (budget 4 ms).
  - Z5 motor encoder: p99 time with the interrupt masked 2.41 → 0.24 ms; p99 interrupt response 2.08 → 0.57 ms.
- **Detection** (held-out run, 10 captures per build): every planted bug caught in **10 of 10** runs, every hand-written reference fix clean in **10 of 10**, healthy system programs **0 findings in 30 runs**.

## How we built it

- **Target:** QNX SDP 8.0 on a QEMU x86_64 VM built with `mkqnximage` (4 CPUs, KVM, in WSL2), `procnto-smp-instr`, `tracelogger` in wide mode, `traceprinter`. Five C workloads with planted bugs, built with `qcc`, with hand-written reference fixes the fix engine never reads.
- **Host:** a dependency-free Python core. The parser handles 32-bit counter wraps, cross-CPU reordering and missing clock rates. The model holds per-thread state and priority timelines, message pairing through COMM events, interrupt handlers from QNX 8.0's `IST_ATTACH` events, and integrity checks that detect dropped events.
- **Fix engine:** a small C toolkit (comments and strings masked, brace matching, statement and declaration parsing, pointer-alias tracking) under five rules, one per root cause. It applies only what it has checked; every generated patch compiles warning-free with `qcc -Wall -Wextra`.
- **Verification:** multi-run before/after comparison with a one-sided Mann-Whitney U test, because one run under nested virtualization proves nothing; lossy captures are replaced, never scored.
- **Hardening:** an internal "judge roast" ran adversarial traces against v0. Six of seven broke something (multi-core false positives, self-reported priorities, counter wraps). Each became a regression test, as did every bug the real traces exposed.

## Challenges

- Making priority inversion detection correct on multi-core: interference only counts while the medium thread holds the low thread's CPU and the low thread is ready.
- Telling a semaphore used as a lock from one used as a signal, both in the trace (to diagnose) and in the source (to decide whether rewriting it is safe).
- Not trusting one noisy run: the stack is Windows → WSL2 → KVM → QEMU → QNX. Measured noise: timer wake-ups up to ~1.4 ms late, rare multi-millisecond host stalls, and a test suite running on the host inflating a 0.13 ms job to 1.3 ms. Captures are now taken with the host idle.
- Our own first interrupt fix was wrong in two ways the trace exposed: the worker started after `InterruptAttachEvent()` (interrupts waited up to 20 ms on its setup) and ran one priority below the interrupt thread. The trace showed the right priority: below the lowest interrupt thread on the system (virtio, 21).
- The first real traces broke assumptions the synthetic ones never tested: a 64-bit timestamp format, QNX 8.0's interrupt events (`INT_DELIVER`, `IST_ATTACH`), a release grid that drifted 0.05% against the trace clock, and planted bugs that only reproduced when the 1 ms tick fell in the right place.

## Accomplishments

- A closed loop with no model in it: the trace proves the cause, a QNX-specific rewrite fixes it, and the real kernel decides whether it worked.
- Fixes that refuse to guess: every automatic rewrite checks its preconditions in the code, and tests prove it backs off when they fail.
- A gate that refuses to pass or fail a lossy trace, and a harness that refuses to verify a bug that never reproduced.

## What we learned

- On QNX 8.0, timers fire on tick boundaries, so any race between releases closer than 1 ms is decided by where the tick falls. Reproducible timing bugs need whole-tick spacing.
- `ThreadCtl(_NTO_TCTL_RUNMASK)` on QNX 8.0 accepts one CPU or all CPUs, not a subset.
- One fix uncovers the next cause: with a 1 ms budget, Z1's mutex removed the inversion and the re-trace showed a long critical section. Re-trace after every change.
- Deferred interrupt work belongs below every interrupt thread on the system, not just below your own.
- Statistics need enough samples: a "p99" of seven waits is the maximum, and a rule built on it flagged healthy system programs.
- An evaluation harness can lie by omission: ours once called a fix VERIFIED for a bug that never appeared in the "before" runs. Now the bug must reproduce first.

## What's next

Runs on existing QNX software beyond the bug zoo, more remedies (condvar misuse, sporadic-server budgets, automatic send hierarchies for simple request/reply pairs), and a native `.kev` reader so analysis needs no SDP at all.

## Built with

QNX SDP 8.0 · QNX Neutrino (`procnto-smp-instr`, `tracelogger`, `traceprinter`, `qcc`, `mkqnximage`) · QEMU/KVM · Python · Perfetto · SARIF

## Links

- Code: https://github.com/sheikh2583/QNX-Global-Hackathon
- Codelab: `[TBD: GitHub Pages URL]`
- Video: `[TBD: YouTube URL]`
