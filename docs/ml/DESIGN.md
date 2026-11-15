# TraceLens ML: design and analysis

Phase 6 of [PLAN.md](../../PLAN.md). Status (2026-11-15): scaffold built; QNX scheduling simulator built; the simulator was then measured against the real captures feature by feature and corrected; both models are trained and evaluated on 1,920 simulated traces, explain each finding by the labelled pattern it resembles, and are wired into the product ([results_sim.md](results_sim.md)). Next: the real tlgen pilot on the QNX VM.

## 1. What ML is for here (and what it is not)

TraceLens already finds the five bug classes it has rules for, on real QNX 8.0 traces, with no false
alarms in 80 clean runs. Rules cannot find what nobody wrote a rule for. ML adds two things:

| Piece | Job | Learns from | Ships as |
|---|---|---|---|
| **Radar** (unsupervised) | Flag thread behaviour unlike anything healthy, including bug classes with no rule; point at the thread and the moment | healthy traces only | `radar.json`, read by the stdlib |
| **Classifier** (supervised) | Second opinion on the root cause; ranks causes, so a rule and the model can be compared | labelled variants of known classes | `classifier.json` (tree ensemble), read by the stdlib |

Non-goals, unchanged from the no-AI decision: no API keys, no network, no model at runtime that is
not a small deterministic file; no automatic patch from a model-only finding. A radar finding is
"unusual behaviour, worth investigating" (MEDIUM, never fails the gate by default).

## 2. Data: why we generate it instead of scraping

There is no public corpus of labelled QNX kernel traces: traces come from private systems, and source
code scraped from the web has neither traces nor labels (and mixed licences). We own the hard part
already, a real QNX 8.0 target and a capture pipeline, so we generate labelled data:

- **One generator program**, `bugzoo/gen/tlgen.c`, built once with `qcc`. Each run picks a scenario and
  its parameters on the command line, so 2,000 variants cost 2,000 runs, not 2,000 builds.
- **The label is free**: the scenario is what we planted. Each trace is also checked after capture
  (lossy? did the planted bug actually trigger?) and that check is stored next to the label.
- **Scenario families** (`src/tracelens/ml/dataset.py`, `SCENARIOS`):

  | Family | Label | Rule exists? | Role in evaluation |
  |---|---|---|---|
  | `healthy_periodic`, `healthy_pi_mutex`, `healthy_ipc`, `healthy_mixed` | healthy | n/a | radar training; false-alarm test |
  | `sem_inversion` | priority_inversion | yes | classifier training |
  | `chan_inversion` | priority_inversion | yes | classifier training |
  | `ipc_deadlock` | ipc_deadlock | yes | classifier training |
  | `lock_contention` | mutex_contention | yes | classifier training |
  | `condvar_inversion` | priority_inversion (through a condition variable) | yes (found by the simulator: the inversion rule follows condvars) | classifier training |
  | `cpu_starvation` | (unseen) a periodic task starved by a busy higher-priority thread | **no** | radar test, held out |
  | `mutex_abba` | (unseen) lock-order deadlock between two mutexes | **no** | radar test, held out |
  | `lost_wakeup` | (unseen) signal sent before the wait; the consumer sleeps to its timeout | **no** | radar test, held out |
  | `period_overrun` | (unseen) a job's work exceeds its period; a low-priority thread starves | **no** | radar test, held out |
  | `healthy_irq` | healthy (interrupt thread, unmask first) | n/a | radar training; false-alarm test |
  | `healthy_irq_deferred` | healthy (unmask, then a lower-priority worker: the pattern TraceLens's own remedy writes) | n/a | radar training; false-alarm test |
  | `irq_overrun` | irq_handler_overrun | yes | classifier training |

- **Parameters** are sampled per run (seeded): priorities, period, work and critical-section
  lengths, number of workers, CPU pinning, run length. A region of the parameter space is held out
  for the classifier's test.
- **Volume and cost**: ~10 s per capture on the VM; 2,000 traces ≈ 6 h, one overnight run with the
  host idle (host load distorts guest timing: measured, PLAN §15). Collection is resumable.
- **Simulated twin** (section 9): the same plan through a QNX scheduling simulator, 1,920 traces in ~6 min
  on a laptop. Unseen families use job names with no declared deadline, so no rule can see them.
- **Labels per thread**: only the planted victim thread's windows carry the bug's label
  (`dataset.TRUTH`, `window_label`); every other thread's windows are normal behaviour.
- **Data-engine config**: `bugzoo/gen/tlgen.toml` (tlgen's period varies per run, so its deadlines declare
  no period; the zoo's `frame` deadline assumed 10 ms and produced false misses on generated data).

## 3. Unit of learning and features

Unit: **one thread, one 20 ms window** (two periods of a 10 ms loop). Features are computed from the
TraceModel (`src/tracelens/ml/features.py`), normalised by window length so traces of any length mix:

- time shares: running, ready (preempted), blocked on SEM / MUTEX / CONDVAR, SEND / REPLY, INTR, sleep
- longest single block, longest ready wait, **longest unbroken CPU burst**, number of blocks and preemptions
- **time spent holding an interrupt masked** (from InterruptWait() returning to InterruptUnmask()):
  the only thing that separates a handler doing its work on the device's time from one that unmasked
  first and deferred, since both can hold a CPU for milliseconds
- **priority context**: blocked while a lower-priority thread of another process ran on its CPU
  (the generic inversion signal, independent of the sync object type), the thread's priority rank
- CPU migrations, distinct CPUs
- interrupt handling: masked time per interrupt (for IST threads)

Thread identity, names and absolute priorities are deliberately not features: the model must not
memorise our programs.

## 4. Models

- **Radar v0** (implemented): robust z-scores per feature against healthy windows (median, per-side
  tail scale), window score = mean of the 3 largest clipped |z|; threshold = 99.5th percentile of
  healthy scores. **Persistence rule**: a thread is reported only when more than a calibrated share of
  its windows (and at least 3) are unusual; the share is the 99th percentile over healthy *training*
  traces. Bugs repeat every period; noise does not. Pure stdlib to train and to run; bundled as
  `src/tracelens/ml/radar.json` (trained on simulated healthy traces only).
- **Radar v1** (planned): Isolation Forest trained with scikit-learn offline, exported as JSON trees,
  scored by the stdlib. Kept only if it beats v0 on the held-out families.
- **Classifier** (planned): gradient-boosted or random-forest trees trained with scikit-learn offline
  (`pip install -e ".[ml]"`, dev only), exported to the same JSON tree format; inference in
  `src/tracelens/ml/model.py` is pure stdlib and already tested.

## 5. Evaluation protocol (decided before the data exists)

| Question | Split | Metric |
|---|---|---|
| Does the radar catch bug classes it never saw? | train on healthy; test on the 3 unseen families + held-out healthy | detection rate per family at the healthy-window threshold; false-alarm rate on held-out healthy traces |
| Does the radar add anything to the rules? | known families | traces the rules miss but the radar flags (and vice versa) |
| Does the classifier generalise? | train on parameter region A, test on region B | per-class precision/recall, confusion matrix |
| Is it the same on real programs? | the committed real bug-zoo traces (never used for training) | radar flags the buggy builds, not the reference fixes |

Every number in the README comes from a run recorded after the model was frozen.

## 6. Integration

- `tracelens analyze --radar` adds `unusual_behavior` findings (MEDIUM, `source: radar`) with the thread,
  the window and the features that stand out most.
- The web app's report shows a "Radar" note under the rule findings; the live fix view can show
  radar scores per run (planned).
- `tracelens data plan | collect | features` and `tracelens ml train-radar | eval` drive the pipeline.

## 7. First experiment (2026-11-15, before any generated data)

Radar v0 fitted only on healthy real QNX 8.0 traces already in the repository (the four reference
fixes Z1-Z4 and the `ls -lR` loop: 2,090 windows), then scored on traces it never saw:

| Trace (never used for fitting) | Expected | Windows flagged | Top finding |
|---|---|---|---|
| Z1 infusion pump, buggy | flag | 100 / 304 | `control`: semaphore time, blocked while a lower-priority thread held its CPU |
| Z2 brake-by-wire, buggy | flag | 101 / 303 | `brake_ctrl`: blocked while a lower-priority thread held its CPU |
| Z3 sensor fusion, buggy | flag | 105 / 209 | `fusion_a/b`: blocked waiting for a server |
| Z4 camera pipeline, buggy | flag | 301 / 401 | `worker4`: mutex time |
| `pidin` loop, healthy | quiet | **0 / 1,420** | none |
| Z5 motor encoder **fix**, healthy | quiet | **99 / 198 (false alarm)** | `encoder_ist`: interrupt waits |

What it taught us, before the data engine existed:
- **The inversion signal is generic.** One feature (blocked while a lower-priority thread held the
  CPU) separates buggy from fixed for a semaphore (0.52 vs 0.00) and a message channel (0.57 vs 0.00).
- **A plain MAD scale fails** on sparse features (semaphore time is zero in almost every healthy
  window): every threshold saturated. v0 now scales each side of the median by the healthy tail.
- **The radar is only as good as its healthy coverage**: with no healthy interrupt-driven program in
  training, a healthy interrupt handler looked alien. Hence `healthy_irq` / `irq_overrun` in the generator.
- Thread start and exit look unusual and mean nothing: each thread's first and last window is skipped.

These are early numbers on 5 training traces, not results; the held-out evaluation of section 5 is.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Generated programs look alike; the model learns the generator, not QNX | vary work shapes and timing; never use names/priorities as features; test on the real bug-zoo traces |
| A planted bug does not trigger on some runs (timing) | store the post-capture check; evaluate on "triggered" runs, report the trigger rate |
| VM time | ~6 h per 2,000 traces; resumable; overnight with the host idle |
| Radar false alarms on unusual-but-healthy programs | MEDIUM severity, never gates by default; threshold fixed on held-out healthy data |
| Overclaiming | evaluation protocol fixed in advance; report misses and false alarms, not only wins |
| The simulator teaches the model the simulator | domain randomisation (clock rate, kernel-call cost, tick lateness, background load); never trust a sim number alone: every model is checked on real QNX traces; the real tlgen pilot measures the gap per feature |
| Using the real zoo traces to fix the simulator turns them into training data in disguise | declared: since 2026-11-15 they are a development set; clean tests are the real tlgen pilot and any new zoo program |

## 9. The simulator: unlimited labelled traces without a target (2026-11-15)

`src/tracelens/sim/` is a discrete-event model of the QNX 8.0 scheduler that writes `traceprinter`
text in the real QNX 8.0 format (header, 64-bit cycle stamps, continuation lines, COMM events), so the
parser, detectors, features and models run on it unchanged. It models: preemptive priority scheduling
on N CPUs (FIFO among equals, preempted threads to the head of their queue, run masks, idle threads);
timers on 1 ms tick boundaries through the clock interrupt thread, optionally whole ticks late;
semaphores, priority-inheriting mutexes (kernel calls only when contended), condition variables, timed
waits; MsgSend/Receive/Reply with server priority inheritance unless `_NTO_CHF_FIXED_PRIORITY`; shared
interrupt lines with per-handler masking (the serial driver at priority 254 shares IRQ 4 with the
program, as on the VM); background system threads; wall-clock busy loops like `tl_spin_us()`. Every
tlgen scenario is a Python program that mirrors `tlgen.c` (same threads, priorities, tick offsets,
markers). Each run draws its platform (clock rate, kernel-call cost, tick lateness, background load)
at random. Commands: `tracelens simulate <scenario> -o t.txt.gz`, `tracelens data simulate`,
`python scripts/sim_experiment.py`. Samples: `fixtures/sim/`.

**What building it found in TraceLens itself** (all fixed, with tests):
- the interrupt rule crashed when a handler thread was attached but never ran in the capture (e.g. an
  idle CPU's clock thread), and the crash was silently swallowed; the data engine now records detector errors
- the interrupt rule counted deliveries from before the program attached as its latency (a healthy
  handler looked 100 ms late on a busy shared line); only post-attach interrupts count now
- `condvar_inversion` was planned as an unseen family, but the inversion rule already follows
  condition variables; it is a known family now, and two genuinely unseen ones were added
- `cpu_starvation` could never trigger: without release markers a constant late start is invisible to a
  deadline rule; it is checked by READY time instead (and is the radar's documented blind spot)
- features: a block longer than the window scored up to 50; whole-window waits for a reply or an
  interrupt (idle I/O) are no longer scored, whole-window waits on a sync object (a deadlock) are

**Sim-to-real, step by step** (radar trained on simulated healthy traces only, scored on the real zoo):

| Version | Gap found on real traces | Fix (general, not tuned per trace) |
|---|---|---|
| 1 | every window of healthy shell/`pidin` traces flagged | feature hygiene above (idle I/O windows) |
| 1 | fixed Z5's interrupt thread flagged | shared IRQ line + driver interrupt thread + per-CPU clock threads (read off the real trace) |
| 1 | fixed Z1's logger flagged (waits for the CPU 60% of the time) | healthy coverage: long low-priority critical sections behind PI mutexes, medium loads up to 70% of a core |
| 2 | random single windows flag long healthy traces | persistence rule (calibrated on healthy training traces) |
| 3 | classifier blamed fixed Z1's logger | per-thread labels (victim only) |
| 4 | a measured gap table (`median` per feature, real victim thread vs its simulated family) showed the simulated interrupt thread preempted 4.75x/ms where the real one was never preempted, and the simulated `ipc_deadlock` threads only ever sat in SEND | a driver on a shared line now only does work when its own device raised the interrupt; `ipc_deadlock` serves its peer in a MsgReceive loop first, like the real Z3; healthy handler work narrowed to the measured ~7 us |
| 4 | nothing in the feature set saw a handler's 2.4 ms of masked work | `max_run_frac` and `intr_masked_frac` |
| 5 | adding the deferred-worker scenario (the correct pattern) taught the radar that long CPU bursts are normal, and the interrupt-overrun detection collapsed | `intr_masked_frac`: the worker's burst is not masked time, the overrunning handler's is |
| 5 | the busy logger of the real Z1 *fix* flagged again after the healthy set changed | parameters drawn as fractions of the period, so heavily loaded healthy programs are common instead of a rare corner; healthy training traces that miss deadlines are dropped from training |

**Results** ([results_sim.md](results_sim.md), one recorded run of the final code):
- held-out simulated data: radar false alarms on 4 of 124 healthy traces; unseen families `lost_wakeup`,
  `mutex_abba`, `period_overrun` 100%; `cpu_starvation` 3% (a starved lowest-priority job behaves like a
  healthy deferred thread: only a declared deadline separates them, which is the deadline rule's job).
  Classifier on parameter region B: priority inversion 1.00 / 1.00, interrupt overrun 1.00 / 1.00,
  contention 0.91 / 0.98, healthy 0.99 / 0.97 (precision / recall).
- real QNX 8.0 zoo (development set): the radar flags Z1-Z4 buggy on the victim thread and stays quiet on
  all five fixes and the three healthy system traces; it misses Z5 buggy (the interrupt rule catches it).
  The classifier names the right cause on the right thread for Z1, Z2, Z4, says healthy for all 8
  healthy/fixed traces, and misses Z3 and Z5.

## 10. Retrieval: what does this behaviour resemble?

"Unlike anything healthy" is true but thin, so each radar finding also names the labelled pattern it most
resembles (`src/tracelens/ml/retrieve.py`). A handful of exemplar windows per scenario ride with the radar
model; the distance is measured in the radar's own z-space, so it compares *deviations from healthy*
rather than raw timings, and the report says whether the match is inside that pattern's usual radius:

> `ab` behaved unlike healthy QNX programs in 51 of its 100 time windows ... The closest pattern
> TraceLens has seen is a lock-order (ABBA) deadlock between two mutexes, but only loosely
> (distance 1.4 against 1.2 typical for it): treat this as behaviour of its own.

Rules that keep it honest: exemplars come from training-split windows only (so the held-out families have
none, and a finding on one of them reports its nearest *known* pattern with an explicit distance), only the
planted victim's windows represent a bug, and a match beyond the pattern's radius is reported as loose.

## 11. In the product

| Where | What it shows |
|---|---|
| `tracelens analyze --radar` | learned findings after the rules' own, numbered with them |
| the web app (`/analyze` uploads, the example reports) | the same findings, MEDIUM, in plain language: "A thread behaved unlike anything healthy" |
| `tracelens fix --watch` and the hosted replay | a "Second opinion" block per round, marked *Learned*, next to the rules' findings |

The boundary is visible everywhere: a learned finding is MEDIUM, never fails the gate, never becomes a fix
target and never gets a patch. The bundled `radar.json` makes this work offline with no key and no network;
a corrupt or missing model costs the report nothing (it is reported as an error and the rules carry on).

## 12. Roadmap

1. **Real pilot** (needs WSL + the VM): build `tlgen` with qcc, one run per scenario; compare each feature's
   distribution real vs simulated (per-feature gap table); recalibrate the simulator's knobs from it.
2. **Clean real test**: overnight collection; train on simulated + real-train, test on real held-out.
   README/Devpost numbers come only from that run.
3. **Close the two misses**: Z3 (deadlock across processes: add multi-process healthy IPC so a long SEND
   wait is learnable) and Z5 (real interrupt bursts: drive the simulated line from the real
   inter-arrival distribution).
4. **A second real target**: everything here is one QEMU guest with four CPUs. Hardware, or a different
   CPU count, is the next honest test of the features' independence from the platform.
5. **Retrieval beyond the nearest exemplar**: show the exemplar's own timeline next to the finding's.

