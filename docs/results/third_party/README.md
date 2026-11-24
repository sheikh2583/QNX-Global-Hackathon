# TraceLens on a real-time program we did not write: rt-tests on QNX 8.0

**Question a judge will ask:** every earlier result was on workloads this project wrote, with bugs
this project planted. Does TraceLens say anything sensible about real-time code it has never seen?

**Answer, in short:** on the standard Linux real-time test suite `rt-tests` v2.11, ported to QNX 8.0
and traced on the real target, **the rule detectors reported nothing on any of 16 runs** (one of
them a lossy capture the tool itself refused to judge). The only output was a MEDIUM, learned-radar note on one
of the three programs, and by the program's design that note is **not a bug**. No rule fired, so
there was nothing for `remedy` or `fix` to act on. This is a clean result on unseen code, not a
demonstration that the tool finds bugs. A separate, labelled control of our own (section 7) shows
the inversion rule does fire on a sustained inversion on QNX 8.0 (9 of 9 runs) and stays silent
with priority inheritance on (6 of 6), but it is our program, written to have a known answer.

Parsing real third-party traces did expose one **parser bug, now fixed with a regression test**
(section 4).

## 1. The program and its provenance

`rt-tests` v2.11 (`git.kernel.org/.../rt-tests.git`, commit `62da2bef…`, GPL-2.0-or-later), by Clark
Williams, John Kacur, Thomas Gleixner, Carsten Emde and others. Three programs, vendored byte for
byte under [`third_party/rt-tests/upstream/`](../../../third_party/rt-tests/upstream/) with their
licence and hashes; the QNX port is a compatibility layer, **no upstream file edited**. Every change
is itemised in [`third_party/rt-tests/README.md`](../../../third_party/rt-tests/README.md).

| Program | What it does |
|---|---|
| `pi_stress` | three SCHED_FIFO threads (low 1 / med 2 / high 3) per group, driving the classic priority inversion over a **priority-inheritance** mutex, repeatedly; 3 groups on 4 CPUs |
| `ptsematest` | pairs of SCHED_FIFO threads (prio 80 / 79) hand a mutex back and forth on a fixed period |
| `pmqtest` | the same over POSIX message queues |

No bugs were planted, and no TraceLens markers were added: there are **no `TL_JOB_START` markers, so
the deadline rule had nothing to measure on these programs**. That is a finding about the tool: on
code without markers or a configured deadline, the deadline rule contributes nothing, and only the
inversion, mutex, IPC and interrupt rules plus the radar can speak.

## 2. Exact commands

Target: QNX 8.0.0, QEMU x86_64, 4 CPUs, `procnto-smp-instr`; VM on QEMU's own network
(`tracelens target up --user-net`); host otherwise idle.

```bash
source ~/qnx800/qnxsdp-env.sh
make -C third_party/rt-tests                      # qcc -Vgcc_ntox86_64
export TRACELENS_TARGET=127.0.0.1:2222
# four runs of each of four configurations:
tracelens capture third_party/rt-tests/out/pi_stress  --seconds 4 --name pi_stress_default_N  -- -q -i 700
tracelens capture third_party/rt-tests/out/pi_stress  --seconds 4 --name pi_stress_uniproc_N  -- -q -u -i 300
tracelens capture third_party/rt-tests/out/ptsematest --seconds 4 --name ptsematest_N         -- -q -t 2 -p 80 -i 1000 -l 1500
tracelens capture third_party/rt-tests/out/pmqtest    --seconds 4 --name pmqtest_N            -- -q -t 2 -p 80 -i 1000 -l 1000
tracelens analyze <trace>.txt --radar --json <trace>.json
```

Built binaries: [`binaries.sha256`](binaries.sha256). `-i` bounds the work so each program finishes
inside the 4 s trace window. No configuration file was passed to `analyze`, so default thresholds
applied, and **no detector was changed or tuned** for this experiment.

## 3. What TraceLens said

| Config | Runs | Rule findings | Radar | Trace integrity |
|---|---|---|---|---|
| `pi_stress` default (3 groups x 3 threads) | 4 | **0 / 4** | quiet | run 2: one "CPU switched threads without the previous one leaving" warning |
| `pi_stress -u` (all on one CPU) | 4 | **0 / 4** | quiet | clean |
| `ptsematest` | 4 | **0 / 4** | MEDIUM on both worker threads, **4 / 4 runs** | clean |
| `pmqtest` | 4 | **0 / 4** | quiet | run 1: *lossy* ("thread RUNNING on two CPUs at once"), verdict INCONCLUSIVE; runs 2-4 clean |

Committed evidence (7 of the 16 traces, gzipped, 4.7 MB; JSON for all 16):
[`traces/`](traces/), [`json/`](json/). The run numbers above match the file names.

**Judgement of each finding**

- **`pi_stress`: zero findings: correct.** `pi_stress` creates the inversion on purpose, but over a
  `PTHREAD_PRIO_INHERIT` mutex, which is the *fix*. The low thread is boosted, so the high thread's
  wait is bounded. The inversion rule is not meant to fire on a boosted wait. I read this as a true
  negative; it is evidence the rule is not firing on the mere *shape* "high blocks on a lock held by
  low", which is the precision claim in the README. It is not proof the rule works in this setting
  (see section 5).
- **`ptsematest`: radar MEDIUM on both threads, 4/4 runs: not a bug, a radar false positive on a
  benchmark shape.** The two threads exist to trade a mutex on a fixed period, so they are blocked
  on a mutex most of the time by design. The radar says exactly that: "time blocked on a mutex
  (higher than healthy)", "time asleep (lower than healthy)", and that the nearest known pattern
  ("many threads serialised on one mutex") matches only loosely. Per the project's rules
  (rules prove, models suggest) it is MEDIUM, cannot fail the gate, and triggers no patch. It is
  consistent with a lesson already in `docs/HANDOFF.md` section 8: **every false alarm so far was a missing
  healthy *shape***. A mutex ping-pong benchmark is one the healthy training set does not cover.
  I did **not** retrain or retune on it; doing so with this evidence would be tuning to the test.
- **`pmqtest` run 1: INCONCLUSIVE: the tool did the right thing.** It flagged its own capture as
  lossy and declined a verdict rather than guess.
- **`pi_stress` default run 2:** one integrity warning, no verdict change. Not investigated further.

## 4. A real bug this exposed, fixed

The first `pi_stress` capture printed `warning: 1 lines not recognised`. The cause was in
`traceprinter` output: a quoted message payload containing a newline (the program printing a status
line to its console) is printed across several lines (`msg[0]:"`, then `Test Du" (0x73…)`). The
parser treated the continuation as unparseable. It is now handled in
[`src/tracelens/ingest/traceprinter.py`](../../../src/tracelens/ingest/traceprinter.py): the open
quote is tracked, continuation text is attached to the owning event, and a following event line
always wins, so an unterminated quote can never swallow the rest of a trace. Two regression tests
were added in `tests/test_parser.py`; the full suite passes (166 tests).

The full pytest suite passes, and `scripts/check.sh gate` passes: every real buggy capture is still
caught, every reference fix and healthy trace still clean. **ML evaluations, re-checked against the fixed parser (2026-11-24).** The fix changes no feature
the models see. Feature rows re-extracted with the pre-fix parser and with the fixed parser are
**byte-identical**: 4,334 of 4,334 rows for the 16-scenario real pilot, and 490,951 of 490,951 rows for
the 1,920-trace real training set. Only the text of a message payload argument (`msg[0]` was `"`, is now
`"
`) differs on 787 of the 1,979 real, pilot and fixture traces, and no analysis code reads those
arguments. The frozen-model evaluation (`scripts/real_vs_sim.py`) on the fixed-parser pilot features
reproduces the same report as on the stored features: radar 8 of 10 planted-bug traces flagged, 0 false
alarms on 6 healthy traces. **Training and the classifier were then re-run** (scikit-learn 1.9.1
installed in the WSL venv; `scripts/train_eval.py --sim data/sim --real <fixed-parser rows> --test-on <same>`).
The report matches the committed `docs/ml/results_train.md` apart from two things: the training window
count (988,704, committed 988,702) and one cell (`mutex_contention` classifier F1 0.87, committed 0.88).
Every other table, including the radar's 726-of-883 caught and 0 false alarms on the 148 healthy
captures, is identical, and the radar threshold (3.4563) and persistence cut-off match the shipped
`radar.json`. The two differences are **not caused by the parser**: training on the *stored* feature
file with the current code gives the same 988,704 and 0.87. They come from drift between the code that
produced the committed report and today's code (the stored rows also carry a `lossy` column the current
extractor no longer writes, and 202 pilot rows have a different `triggered` flag); I did not chase it
further and did not overwrite `docs/ml/results_train.md`. The simulated-data experiment
(`scripts/sim_experiment.py`) was not re-run.

## 5. What this does not show

- **Not that TraceLens finds real bugs in third-party code.** It found none because (as far as
  these three programs go) there were none to find. A clean result on code that is correct says the
  false-alarm side holds up; it says nothing about the detection side.
- **The negative control did not settle it.** I built `pi_stress` with priority inheritance off
  (`make -C third_party/rt-tests control`: a `sed` of one token into a copy under `out/`, so
  `upstream/` is untouched; the build checks the diff is exactly one line) and traced it 3 times
  (section 6). TraceLens found nothing, and I cannot say that is a miss. Reading the code, the
  program's barriers make the inversion *transient*: low always regains the CPU once med parks at
  its barrier, so even without inheritance the high thread's wait stays short, and the program
  completed all 51 inversions of a smoke run without the deadlock its header comment describes. A
  control that never produces a sustained inversion cannot test whether the rule would fire on one.
  (Section 7 adds a control that does, and it settles the rule's behaviour on that case.)
- **Three programs, 16 short runs, one machine** (QEMU VM, 4 virtual CPUs). The ping-pong radar
  alert is one program's behaviour repeated four times, not four independent samples.
- **The port shims are ours.** Thread-pinning goes through our `sched_setaffinity` emulation;
  upstream's own `verify_cpu()` accepted every worker, so pinning worked, but this is a port, not
  the upstream program on its native OS. `ptsematest`'s own latency numbers are degenerate on QNX
  (a measurement artefact of its `gettimeofday` deltas); TraceLens does not use them.
- **`remedy` / `fix` were not exercised on the rt-tests runs:** they only act on a rule finding,
  and none occurred there. `remedy` was tried on the section 7 control; `fix` was not run.

## 6. The negative control, as run

`pi_stress_nopi` = upstream `pi_stress.c` with `PTHREAD_PRIO_INHERIT` replaced by
`PTHREAD_PRIO_NONE` (line 972, nothing else). Same command as `pi_stress_default` (`-q -i 700`),
3 runs.

| Run | Rule findings | Radar | Integrity |
|---|---|---|---|
| 1 | 0 | quiet | lossy ("CPU switched threads without the previous one leaving" x5): INCONCLUSIVE |
| 2 | 0 | quiet | clean |
| 3 | 0 | quiet | lossy (x4): INCONCLUSIVE |

Evidence: [`json/pi_stress_nopi_*.json`](json/), [`traces/pi_stress_nopi_1.txt.gz`](traces/) (the
lossy run 1; the clean run 2 was not committed). **Judgement:** TraceLens was silent on a program
that, as far as I can tell, does not sustain an inversion, so this is neither a pass nor a failure
of the inversion rule. Two of three captures being lossy is also worth noting: the unmodified
`pi_stress` was lossy in 1 of 4 runs; I have not investigated the cause (target-side buffer
pressure at ~40k events/s is my guess, unverified).

A control that *would* test the rule needs a program whose medium thread keeps the CPU busy while
the low thread holds the lock, which `pi_stress` does not do. That is section 7.

## 7. A control that does sustain the inversion: `busy_medium`

**This is our own program, not third-party code**, and it is a control, so read it as such: we
wrote it to have a known answer. [`third_party/rt-tests/control/busy_medium.c`](../../../third_party/rt-tests/control/busy_medium.c)
(MIT, about 200 lines, no TraceLens markers, no use of the port shims) puts three SCHED_FIFO
threads on **one CPU**: low (prio 10) takes a lock and works for `-c` us; one tick later high
(prio 30) wants the lock and a medium thread (prio 20) spins for `-b` us. It **measures the high
thread's wait itself**, so the ground truth does not rely on TraceLens. One flag picks the lock:

| `-m` | Lock | Expected high-thread wait |
|---|---|---|
| `pi` | mutex, `PTHREAD_PRIO_INHERIT` | about the critical section |
| `none` | mutex, `PTHREAD_PRIO_NONE` | about the medium thread's burst |
| `sem` | `sem_t` used as a lock (ownerless) | about the medium thread's burst |

**Ground truth (the program's own clock, 40 rounds, same VM).** `-c 4000 -b 20000`: `pi` median
wait 3.1 ms, `none` 20.1 ms, `sem` 20.0 ms. `-c 1500 -b 20000`: `pi` 0.6 ms, `none` 20.1 ms. So
the inversion is real and sustained without inheritance, and inheritance removes it. The program
also reads the mutex protocol back after setting it (`PTHREAD_PRIO_NONE` = 1, accepted by QNX 8.0),
which settles the earlier doubt about whether the `pi_stress` control had really turned
inheritance off: it had; that program's barriers were what kept the inversion short.

**What TraceLens said** (3 runs per cell, `tracelens capture ... -- -m <mode> -d 2 [-c 1500]`, then
`analyze --radar`, defaults, nothing tuned, all captures clean, none lossy):

| Variant | Rule findings (all 3 runs agree) | Radar |
|---|---|---|
| `none`, `-c 4000` | **CRITICAL priority inversion** (`bm_high` waited on `bm_low` via a mutex) + HIGH mutex contention | MEDIUM on both threads |
| `none`, `-c 1500` | **CRITICAL priority inversion** + HIGH mutex contention | MEDIUM on both threads |
| `sem`, `-c 4000` | **CRITICAL priority inversion** (via a semaphore) | MEDIUM on both threads |
| `pi`, `-c 4000` | **no inversion**; HIGH mutex contention (3 of 3) | MEDIUM on both threads |
| `pi`, `-c 1500` | **no inversion**; no contention finding in 2 of 3 runs, MEDIUM contention in 1 | MEDIUM on `bm_low` only (3 of 3) |

Evidence: [`control/json/`](control/json/) (all 15 runs), [`control/traces/`](control/traces/) (5
traces), [`control/remedy_output.txt`](control/remedy_output.txt), [`control/binary.sha256`](control/binary.sha256).

**Judgement.**

- **The inversion rule detects a sustained inversion on code it was not written for, and stays
  silent on the same program with inheritance on.** That is 9 of 9 true positives and 6 of 6 true
  negatives on the rule that matters, on a binary compiled once, with the lock type as the only
  difference. This answers the question section 6 left open. It is still one program of ours on
  one VM: the control was written knowing the rule's shape, so it shows the rule is *not blind to
  this textbook case*, not that it generalises to inversions in code we have not seen.
- **The `pi` / `-c 4000` HIGH contention finding is the rule doing what it is documented to do, and
  it is a real limitation.** The rule raises HIGH on 3 or more waits of 2 ms or longer; this
  program's high thread waits about 3 ms on every one of 40 rounds *by construction*, with
  inheritance working. A gate that treats HIGH as failure would fail the fixed program. The rule
  cannot tell a long, bounded critical section from an unbounded one; the inversion rule can, and
  does. I did not change the rule: doing so on this evidence would be tuning to the test. With the
  shorter critical section (`-c 1500`, waits well under 2 ms) the false HIGH disappears, which is
  consistent with that reading.
- **The radar fires MEDIUM on both threads in every variant, including the fixed one.** As with
  `ptsematest`, this is a periodic lock hand-off shape the healthy training set does not cover. It
  is not evidence for or against the inversion, and by design cannot fail the gate.
- **`remedy` was exercised for the first time on third-party-style code, with mixed results.** On
  the semaphore variant it pointed at the real lock and unlock lines (`busy_medium.c:88`, `:94`)
  with the right explanation, but declined to patch automatically because the semaphore is not
  used "strictly as a lock" (my wrapper selects mutex or semaphore at run time). That refusal is
  correct and the safe side. On the `PTHREAD_PRIO_NONE` mutex variant it produced **no remedy for
  the inversion** (only a generic "move work out of the critical section" for the contention
  finding), although the fix is a one-line protocol change. I treat that as a missing remedy, not
  a detector bug, and did not add one here. `fix` (which needs an API key the user sets) was not run.
