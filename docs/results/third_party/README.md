# TraceLens on a real-time program we did not write: rt-tests on QNX 8.0

**Question a judge will ask:** every earlier result was on workloads this project wrote, with bugs
this project planted. Does TraceLens say anything sensible about real-time code it has never seen?

**Answer, in short:** on the standard Linux real-time test suite `rt-tests` v2.11, ported to QNX 8.0
and traced on the real target, **the rule detectors reported nothing on any of 16 runs** (one of
them a lossy capture the tool itself refused to judge). The only output was a MEDIUM, learned-radar note on one
of the three programs, and by the program's design that note is **not a bug**. No rule fired, so
there was nothing for `remedy` or `fix` to act on. This is a clean result on unseen code, not a
demonstration that the tool finds bugs; it also does not show the tool *would* find an inversion in
this kind of program (see "What this does not show").

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

The full pytest suite passes. I did **not** run `scripts/check.sh gate` or re-run the earlier
real-trace evaluations (`docs/ml/results_*.md`), so I have not shown the change leaves them untouched.

## 5. What this does not show

- **Not that TraceLens finds real bugs in third-party code.** It found none because (as far as
  these three programs go) there were none to find. A clean result on code that is correct says the
  false-alarm side holds up; it says nothing about the detection side.
- **No negative control.** I did not run a variant of `pi_stress` with priority inheritance turned
  off, which is the experiment that would show the inversion rule firing on this exact unmodified
  program. `pi_stress` has no option for it; it would need a one-line source change and so a
  separately labelled, modified copy. This is the most valuable next step.
- **Three programs, 16 short runs, one machine** (QEMU VM, 4 virtual CPUs). The ping-pong radar
  alert is one program's behaviour repeated four times, not four independent samples.
- **The port shims are ours.** Thread-pinning goes through our `sched_setaffinity` emulation;
  upstream's own `verify_cpu()` accepted every worker, so pinning worked, but this is a port, not
  the upstream program on its native OS. `ptsematest`'s own latency numbers are degenerate on QNX
  (a measurement artefact of its `gettimeofday` deltas); TraceLens does not use them.
- **`remedy` / `fix` were not exercised:** they only act on a rule finding, and none occurred.
