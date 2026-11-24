# Devpost submission draft: TraceLens

> Draft. Every number below comes from real QNX 8.0 runs (docs/results/). Remove any claim we can't reproduce live.
> Category: **Developer Tooling & Host Tools**. Also eligible: Grand Prize, Best use of QNX-specific technologies, Best Codelab (codelab URL goes in its field).

**Tagline:** Find, fix, and prove real-time bugs on QNX.

## Inspiration

Real-time bugs are timing bugs. Every function can be correct while the system is late, because the wrong thread had the CPU at the wrong moment. On QNX the evidence is excellent: the instrumented kernel records every scheduling decision, message and interrupt. But reading that evidence is still manual work for an expert scrolling a timeline, and knowing the QNX-specific fix is a second kind of expertise. We wanted the trace to tell you what went wrong, why QNX behaved that way, rewrite the code, and prove on the kernel that the fix worked.

## What it does

TraceLens is a host tool for QNX 8.0 that turns a kernel event trace into findings, code fixes, and a verdict measured on the target. It runs entirely on your machine and your QNX target: no API keys, no cloud, no black box: the rules that prove a bug are deterministic, and the learned radar that catches the bugs no rule knows is a small JSON file read by the standard library. The same trace and source always give the same diagnosis and the same patch.

- **Finds** five classes of real-time bugs with deterministic detectors: priority inversion, Send/Reply deadlocks and blocking chains, mutex contention, interrupt-handler overruns, and deadline misses. Every finding cites the exact trace events that prove it.
- **Understands QNX.** QNX mutexes inherit priority by default, so most textbook inversions can't happen. TraceLens looks for the ones that can: ownerless semaphores and `_NTO_CHF_FIXED_PRIORITY` channels. It reads priorities from kernel events over time, so a traced inheritance boost is recognised. Message-passing deadlocks are found per channel. Locks inside procnto are told apart from yours.
- **Fixes.** Each proven root cause maps to a QNX-specific source transform: a semaphore used as a lock becomes a `PTHREAD_PRIO_INHERIT` mutex; a fixed-priority channel gets its flag dropped; an interrupt thread that works before `InterruptUnmask()` unmasks first and hands the work to a pulse-driven worker at a priority below every interrupt thread in the trace; private work leaves a contended critical section. Each transform checks its safety preconditions in the code (a semaphore used as a signal, a pointer into shared data, an early `return` inside a lock all make it back off) and otherwise gives the exact lines and the fix to make by hand.
- **Proves.** `tracelens fix` captures the program 5 times, patches a sandbox copy, builds it with `qcc`, runs it 5 more times under `tracelogger`, and compares: VERIFIED requires the finding gone in every run, nothing new, and statistically faster response times (Mann-Whitney U). If the verdict is NOT FIXED, it diagnoses the patched build's own traces and fixes again (one fix often uncovers the next cause).
- **Learns what healthy looks like**, for the bugs nobody wrote a rule for. A model trained only on
  healthy QNX traces flags a thread whose scheduling behaviour fits nothing it has seen, says which of
  its labelled patterns the behaviour most resembles, and how loose that match is. It is a small JSON
  file read by the standard library, so this stays key-free, offline and deterministic; a learned
  finding is MEDIUM, never fails a build and never gets an automatic patch. The rules remain the proof.
- **Makes its own training data.** TraceLens ships a model of the QNX 8.0 scheduler (priorities on N
  CPUs, the 1 ms tick, priority-inheriting mutexes, condvars, MsgSend/Receive/Reply with server
  inheritance, shared interrupt lines with per-handler masking) that writes traces in the real
  `traceprinter` format, so 1,920 labelled recordings take five minutes on a laptop and the whole
  pipeline runs on them unchanged. `tracelens simulate <scenario>` gives you one to try without a target.
- **Try it in a browser:** a hosted demo (`tracelens serve`) shows every real QNX trace analyzed, each fix planned from the trace and the source, the before/after reports proven on the VM, and analyzes uploaded traces live.
- **Keeps it fixed.** `tracelens gate` compares a build's timing against a committed baseline and blocks a build that is statistically slower (one-sided Mann-Whitney U on per-capture p99), grew a new kind of finding or went over budget; it says INCONCLUSIVE rather than guess when it cannot tell. A pre-push hook runs lint, tests and the gate before anything leaves the machine.
- **Fits the workflow:** HTML/JSON/SARIF reports, exit codes for scripts (including "inconclusive" for lossy traces), Perfetto export, and `tracelens remedy`, which plans the fix from a trace and the source with no target at all.

**Results on real QNX 8.0** (QEMU VM, 4 CPUs, `procnto-smp-instr`):

- **Fixes:** 4 of 5 planted bugs fixed automatically and **VERIFIED on the target**; the fifth (a Send/Reply deadlock, whose fix changes the protocol) gets the exact `MsgSend()` lines and the send-hierarchy fix.
  - Z1 infusion pump: inversion in 5/5 runs → 0/5; dose-controller p99 5.74 → 1.29 ms (budget 2 ms).
  - Z2 brake-by-wire: deadline misses 1000 → 0; brake p99 6.75 → 0.77 ms.
  - Z4 camera pipeline: contention 5/5 → 0/5; frame p99 7.45 → 2.99 ms (budget 4 ms).
  - Z5 motor encoder: p99 time with the interrupt masked 2.41 → 0.24 ms; p99 interrupt response 2.08 → 0.57 ms.
- **Detection** (held-out run, 10 captures per build): every planted bug caught in **10 of 10** runs, every hand-written reference fix clean in **10 of 10**, healthy system programs **0 findings in 30 runs**.
- **Learned radar**, trained on healthy behaviour only, from **1,920 real QNX 8.0 captures** collected
  in one night on the target plus 1,920 simulated. On held-out real captures it flags **326 buggy
  traces that no rule reports at all**, with **0 false alarms on 148 healthy ones**. The rules alone
  catch 400 of the 883 held-out buggy captures; with the radar, 726. The extra 326 are almost entirely
  the four bug families **no rule exists for**: a lost wake-up and a period overrun **100%** of the
  time, a lock-order deadlock **84%**, and a starved low-priority job never — that one is the same
  behaviour as healthy deferred work unless a deadline is declared.
- **On code we did not write**: `rt-tests` v2.11 (`pi_stress`, `ptsematest`, `pmqtest`), vendored unmodified and ported to QNX 8.0 through a compatibility layer, traced on the target: **0 rule findings in 16 runs**, a clean result and not a bug find, since those programs have no planted bugs. A control we wrote that holds a priority inversion on purpose is flagged in **9 of 9** runs without priority inheritance and **0 of 6** with it. The traces also exposed a real parser bug, now fixed with regression tests.
- **A real fix on code we did not write**: `UnboundedPriorityInversion.c`, a teaching program from NTNU's real-time systems course (TTK4147) that we did not edit apart from a header-level QNX port layer. TraceLens found a CRITICAL priority inversion in **10 of 10** captures, applied its automatic fix in one round, and the fix was **VERIFIED** on QNX 8.0: inversion gone in 10 of 10, the high-priority job's p99 1,103 to 702 ms, Mann-Whitney p = 5.4e-06 on a confirmation run with the configuration frozen first. It is a teaching exercise, not production code, and its upstream repository states no licence, so the file is downloaded by hash rather than copied into our repository.
- **A real bug in production code (a case study, not a blind test: the rules were written after studying this exact bug, so it shows the find, fix and verify pipeline works on real code, not that unseen bugs are found)**: memcached 1.6.45, its own sources unedited, built for QNX 8.0 as the whole daemon, carries the lost wake-up [memcached#1348](https://github.com/memcached/memcached/issues/1348): a stop signal sent while the logger thread is still asleep is thrown away and graceful shutdown hangs. A new deterministic `lost_wakeup` rule names it from the kernel trace (no finding on the healthy shutdown), a new `recheck-before-wait` rule writes the one-line fix, and the fix was **VERIFIED** on QNX 8.0: hung in **10 of 10** runs before, **0 of 10** after on the whole daemon, and the same on the logger thread alone in two independent runs. Stated plainly: the learned radar flagged the hang *and* the healthy control, so on this code it was not useful; the daemon build is reduced (no TLS, SASL, extstore or proxy) and signalled from inside its own process; x86_64 only; the rule was written after seeing this bug, so it is one verified case, not a detection rate. Details: `docs/results/memcached_logger/`.
- **A famous bug, cold**: NNG's `nng_close()` deadlock took three years to close. On QNX 8.0 we reproduced it in 10 of 10 runs; TraceLens first found nothing, which produced a new rule (`stuck_job`). It then flagged 10 of 10 buggy runs and 0 of 10 runs of upstream's fix, and `tracelens compare` called the fix VERIFIED. Stated plainly: upstream wrote that fix, not TraceLens; the learned radar flagged all 20 runs and did not help; the driver and the rule are ours and were written after the first trace. Details: `docs/results/nng_close/`.
- **A pre-registered blind test returned a null result**: with the system frozen, the remaining candidates were dropped for stated reasons or did not reproduce on QNX (Mosquitto#3175, 0 hangs in 39 runs), so we have no blind detection result beyond NNG, where the system missed first. Details: `docs/results/blind_test/`.
- **Not tied to x86**: the suite cross-compiles for QNX 8.0 aarch64 with no source change. On an **emulated** aarch64 guest (QEMU `virt`; not ARM hardware) 65 captures over 13 scenarios show the same rules firing on the same workloads, and the x86-trained radar flags 38 of 45 planted bugs with 0 false alarms on 20 healthy traces. It does not transfer on interrupt traces, which need an optional median-handler rule that is off by default.
- **The simulator is measurably worth having**: trained on the real captures alone the radar gives 2
  false alarms on those 148 healthy traces, and 0 once the simulated traces join training.
- **Said plainly**: on the five bug classes that have rules, the rules are better — they cite the
  kernel events that prove it. And the four rule-less families were written by us, so withholding them
  from training is an honest experiment, not proof the radar will catch an unknown bug in a stranger's
  code. What is measured is this: trained only on healthy behaviour, it flags bug classes it was never
  shown, on real hardware, without crying wolf.

## Where QNX shows

- **Video:** 0:00-0:49 is the fix loop; **0:49-1:04 is a real run on the QNX 8.0 target** (`uname -a` on the QNX machine, then `tracelens fix` on the target, ending VERIFIED); 1:04 onward shows the results measured on that target.
- **Output you can open:** `docs/results/detect.md` and `docs/results/fix.md` (every run captured on QNX 8.0), `fixtures/real/` (raw QNX kernel traces), and the recorded live fix at `/replay/z1_infusion_pump_live` on the demo.
- **Code that builds for or runs on QNX:** the five workloads in `bugzoo/` (QNX C: `MsgSend`, `ChannelCreate`, `InterruptAttachEvent`, `ThreadCtl`, `TraceEvent`), built with `qcc`; the QNX-specific rewrites in `src/tracelens/remedy/`; the capture path `src/tracelens/target/capture.py` (`tracelogger` on `procnto-smp-instr`). The README's "Evidence of QNX use" table lists every QNX API with its file.
- **Build and run:** README "Run it on QNX": SDP 8.0, a QEMU x86_64 VM from `mkqnximage`, `qcc -Vgcc_ntox86_64`; the codelab (`docs/codelab/`) walks it end to end.
- **Built during the submission period:** the repository was created on 2026-11-13, after the 2026-11-02 start, and everything in it was written since.

## How it relates to QNX's own tools

QNX already records the evidence: the instrumented kernel (`procnto-smp-instr`) with `tracelogger` and `traceprinter`, and QNX's graphical trace viewer for reading a timeline (the Momentics System Profiler **(verify: confirm the 8.0 tool name)**). TraceLens does not replace them; it reads the same `traceprinter` output. What it adds is the step after reading: it names the root cause with the kernel events that prove it, writes the QNX-specific source change, rebuilds with `qcc`, re-records on the target and decides with a statistical test whether the fix worked. The QNX-specific part is real: a POSIX semaphore has no owner, so QNX cannot boost the thread that holds it, while a mutex with `PTHREAD_PRIO_INHERIT` can; a fixed-priority channel (`_NTO_CHF_FIXED_PRIORITY`) switches inheritance off on purpose.

## What it does not do, stated plainly

- **All timing is measured on emulators.** The target is QNX 8.0 under QEMU, nested inside WSL2 on Windows, and the aarch64 results are emulated (TCG). Absolute milliseconds are not hardware numbers; every verdict compares builds on the same machine under the same load, with a statistical test. It has not been run on a QNX board.
- **The bugs are planted.** The bug zoo is five small programs we wrote with realistic bugs, and the 16 generated scenarios and the 883 held-out traces come from our own generator. The held-out set is unseen by the models, but it is not independent of its author.
- **Third-party evidence is narrow.** `rt-tests` v2.11 has no bug and TraceLens raised no findings in 16 runs (a clean result); the one genuine third-party fix is a small teaching exercise with exactly the shape of one fix rule, on one VM and x86_64 only. It is not a bug found in production code.
- **Known blind spots.** A starved low-priority job is invisible to the learned radar (the deadline rule catches it only if a deadline is declared); the classifier misses the Send/Reply deadlock (Z3) and the interrupt workload (Z5) on real traces, where the rules catch both; the radar does not transfer to aarch64 interrupt traces; Z3's fix changes the protocol, so it is guided, not automatic.
- **Not a certified tool.** It is a research and productivity tool, not qualified under ISO 26262 or IEC 62304.

## How we built it

- **Target:** QNX SDP 8.0 on a QEMU x86_64 VM built with `mkqnximage` (4 CPUs, KVM, in WSL2), `procnto-smp-instr`, `tracelogger` in wide mode, `traceprinter`. Five C workloads with planted bugs, built with `qcc`, with hand-written reference fixes the fix engine never reads.
- **Host:** a dependency-free Python core. The parser handles 32-bit counter wraps, cross-CPU reordering and missing clock rates. The model holds per-thread state and priority timelines, message pairing through COMM events, interrupt handlers from QNX 8.0's `IST_ATTACH` events, and integrity checks that detect dropped events.
- **Fix engine:** a small C toolkit (comments and strings masked, brace matching, statement and declaration parsing, pointer-alias tracking) under five rules, one per root cause. It applies only what it has checked; every generated patch compiles warning-free with `qcc -Wall -Wextra`.
- **Verification:** multi-run before/after comparison with a one-sided Mann-Whitney U test, because one run under nested virtualization proves nothing; lossy captures are replaced, never scored.
- **Learning:** one thread, one 20 ms window, 19 features of scheduling behaviour and no identities, so
  a model cannot memorise our programs. The simulator was corrected by measuring each feature against
  the real captures, and every correction had to be a QNX behaviour we had not modelled (a shared
  interrupt line, a server that answers before it deadlocks), never a number tuned to one trace.
  Building it found four real bugs in TraceLens itself, including an interrupt rule that crashed on a
  handler attached but never run, and the crash being silently swallowed.
- **Hardening:** an internal "judge roast" ran adversarial traces against v0. Six of seven broke something (multi-core false positives, self-reported priorities, counter wraps). Each became a regression test, as did every bug the real traces exposed.

## Challenges

- Making priority inversion detection correct on multi-core: interference only counts while the medium thread holds the low thread's CPU and the low thread is ready.
- Telling a semaphore used as a lock from one used as a signal, both in the trace (to diagnose) and in the source (to decide whether rewriting it is safe).
- Not trusting one noisy run: the stack is Windows → WSL2 → KVM → QEMU → QNX. Measured noise: timer wake-ups up to ~1.4 ms late, rare multi-millisecond host stalls, and a test suite running on the host inflating a 0.13 ms job to 1.3 ms. Captures are now taken with the host idle.
- Our own first interrupt fix was wrong in two ways the trace exposed: the worker started after `InterruptAttachEvent()` (interrupts waited up to 20 ms on its setup) and ran one priority below the interrupt thread. The trace showed the right priority: below the lowest interrupt thread on the system (virtio, 21).
- The first real traces broke assumptions the synthetic ones never tested: a 64-bit timestamp format, QNX 8.0's interrupt events (`INT_DELIVER`, `IST_ATTACH`), a release grid that drifted 0.05% against the trace clock, and planted bugs that only reproduced when the 1 ms tick fell in the right place.

## Accomplishments

- A closed loop in which nothing is guessed: the trace proves the cause, a QNX-specific rewrite fixes it, and the real kernel decides whether it worked. What a model contributes is clearly marked, never patched automatically, and never part of the proof.
- Fixes that refuse to guess: every automatic rewrite checks its preconditions in the code, and tests prove it backs off when they fail.
- A gate that refuses to pass or fail a lossy trace, a regression gate that says INCONCLUSIVE instead of guessing, and a harness that refuses to verify a bug that never reproduced.
- Honest tests on other people's code and another architecture: a result on unseen code that says only what it shows, and a labelled-emulated aarch64 track whose limits are written next to its numbers.

## What we learned

- On QNX 8.0, timers fire on tick boundaries, so any race between releases closer than 1 ms is decided by where the tick falls. Reproducible timing bugs need whole-tick spacing.
- `ThreadCtl(_NTO_TCTL_RUNMASK)` on QNX 8.0 accepts one CPU or all CPUs, not a subset.
- One fix uncovers the next cause: with a 1 ms budget, Z1's mutex removed the inversion and the re-trace showed a long critical section. Re-trace after every change.
- Deferred interrupt work belongs below every interrupt thread on the system, not just below your own.
- Statistics need enough samples: a "p99" of seven waits is the maximum, and a rule built on it flagged healthy system programs.
- An evaluation harness can lie by omission: ours once called a fix VERIFIED for a bug that never appeared in the "before" runs. Now the bug must reproduce first.

## What's next

Real-time code from more teams (the `rt-tests` run is a first, clean result), a QNX-capable ARM board to move aarch64 from emulated to measured, more remedies (condvar misuse, sporadic-server budgets, automatic send hierarchies for simple request/reply pairs), and a native `.kev` reader so analysis needs no SDP at all.

## Built with

QNX SDP 8.0 (x86_64 and aarch64le) · QNX Neutrino (`procnto-smp-instr`, `tracelogger`, `traceprinter`, `qcc`, `mkqnximage`) · QEMU/KVM · Python · Perfetto · SARIF

## Links

- Code: https://github.com/sheikh2583/QNX-Global-Hackathon
- Live demo: https://qnx-global-hackathon.onrender.com/ (`tracelens serve`: real QNX traces analyzed, fixes planned, uploads)
- Codelab: `[TBD: GitHub Pages URL]`
- Video: `[TBD: YouTube URL]`
