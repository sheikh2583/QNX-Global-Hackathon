# TraceLens

**Find, fix, and prove real-time bugs on QNX.** TraceLens reads a QNX Neutrino kernel event trace, finds timing bugs with deterministic detectors (priority inversion, Send/Reply deadlocks, mutex contention, interrupt-handler overruns, deadline misses), rewrites the code with the QNX-specific fix for the root cause it proved, rebuilds it with `qcc`, re-runs it on the QNX target, and accepts the fix only if repeated re-traces show the bug is gone.

No API keys, no cloud, no black box: the rules that prove a bug are deterministic, and the learned radar that catches the bugs no rule knows is a small JSON file read by the standard library. The same trace and source always give the same diagnosis and the same patch. The core is pure Python 3.11 standard library.

## Try it in one minute (no QNX needed)

```bash
git clone https://github.com/sheikh2583/QNX-Global-Hackathon.git tracelens && cd tracelens
python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e .
tracelens analyze fixtures/real/z1_infusion_pump.txt.gz -c fixtures/real/tracelens.toml --html z1.html
tracelens remedy  fixtures/real/z1_infusion_pump.txt.gz --source bugzoo/z1_infusion_pump -c fixtures/real/tracelens.toml
```

```
[CRITICAL] TL-001 Priority inversion: control waited on logger via a semaphore
    control (prio 50) was blocked 5.36 ms on a semaphore (0x0000005779b88020) released by logger (prio 10);
    for 5.35 ms of that, logger was ready but telemetry (prio 20) held its CPU. Seen 200x.
[CRITICAL] TL-002 Deadline misses in 'control'

[AUTO] Replace semaphore 'buf_lock' (used as a lock) with a priority-inheriting mutex
    main.c:36  sem_wait(&buf_lock);   main.c:41  sem_post(&buf_lock);   ...
  patch: tracelens-fix.patch
```

That trace is a real QNX 8.0 capture, committed in [fixtures/real/](fixtures/real/). Or run the whole tour: `demo/run_demo.sh` (Linux/WSL).

No QNX target? TraceLens ships a **model of the QNX 8.0 scheduler** that writes traces in the real
`traceprinter` format, so you can make your own labelled recordings on a laptop:

```bash
tracelens simulate lost_wakeup -o my_trace.txt.gz            # 16 scenarios, see fixtures/sim/
tracelens analyze my_trace.txt.gz -c bugzoo/gen/tlgen.toml --radar
```

`--radar` adds what a **learned model** sees, next to what the rules prove: it was trained only on
healthy traces, so it can flag a thread whose behaviour no rule has a name for, and it names the
labelled pattern that behaviour most resembles. It is a small JSON file read by the standard library:
no API key, no network, and the same answer every time.

## Hosted demo

`tracelens serve` is the TraceLens web app, written for people who want their program fixed rather
than for tool builders:

| Page | What it is |
|---|---|
| `/` | What TraceLens solves, the three steps to use it, and the measured before/after chart |
| `/demo` | **Guided demo for judges:** one real QNX 8.0 recording from bug to proven fix (the program, the raw kernel events, the findings with a zoomed timeline of the moment each happened, the patch, two rounds of proof on the kernel), then reliability across all five programs |
| `/analyze` | Upload a recording (plus, optionally, C source and deadlines) and get a plain-language report and a patch; how to record a trace on a QNX target |
| `/examples` | The five real QNX programs, each with its report and its before/after proof |
| `/guide` | How to read a report: severity, the timeline, patches, when a fix is real |

Reports put each problem in plain words (what happened, why it matters, why QNX behaves that way, what
to do) with the moment it happened; raw events, metrics and recording diagnostics sit under
"Technical details". The full engineer's report stays at `/trace/<name>`. Standard library only.

```bash
tracelens serve --prebuild && tracelens serve        # http://127.0.0.1:8000
```

**Deploy on Render** (free plan): push this repository to GitHub, then in the Render dashboard choose
**New → Blueprint** and pick the repository. [render.yaml](render.yaml) builds with `pip install .`,
pre-renders the committed traces' pages at deploy time (one trace per process: the largest needs about
380 MB to analyze, under the free plan's 512 MB), and starts `tracelens serve --host 0.0.0.0` on
Render's `$PORT`. Measured in a simulation of that flow: build 45 s, server 23 MB of memory, pages
in under 10 ms. The QNX VM stays on your machine, so proving a fix on the kernel is shown from the
recorded runs; Render's `PYTHON_VERSION` value is **(verify)** on first deploy.

## How it works

```
QNX 8.0 target (QEMU x86_64)                        Host (Linux / WSL2)
  workload built with qcc                             capture   deploy, pidin snapshot, tracelogger, fetch
  procnto-smp-instr kernel  -- ssh/scp -->            ingest    traceprinter text -> events (sorted, unwrapped)
  tracelogger -> .kev                                 model     thread states, priority timelines, IPC map
                                                      detect    5 deterministic detectors -> findings + event IDs
                                                      remedy    root cause -> QNX-specific source transform
                                                      fix       patch -> qcc -> 5 runs -> compare -> next round
                                                      report    terminal, HTML, JSON, SARIF, Perfetto
```

| Command | What it does |
|---|---|
| `tracelens target up \| check \| ip \| down` | Boot the QNX QEMU VM (`mkqnximage`), preflight it (ssh, instrumented kernel, a 1 s test trace) |
| `tracelens capture BIN -- args` | Copy a `qcc` binary to the target, snapshot priorities with `pidin`, run it under `tracelogger -w`, fetch and decode the trace (`--command` traces a program already on the target) |
| `tracelens analyze TRACE` | Run every detector; terminal summary, `--html`, `--json`, `--sarif`; exit codes for scripts |
| `tracelens remedy TRACE --source DIR` | The QNX fix for each proven root cause, with source locations; writes a patch. No target needed |
| `tracelens fix WORKLOAD` | Find, fix and prove: before-runs, remedy, `qcc`, after-runs, `compare`; re-diagnose and fix again if needed (up to 3 rounds); evidence bundle with a before/after `report.html` |
| `tracelens fix-report BUNDLE --before … --after …` | Re-render a bundle's before/after page from its traces |
| `tracelens compare --before … --after …` | VERIFIED / NOT FIXED / INCONCLUSIVE over ≥ 5 clean runs (Mann-Whitney U on response times) |
| `tracelens eval detect \| fix` | Bug-zoo evaluation on the target: detection and false-positive table; proven-fix table |
| `tracelens serve [--prebuild]` | The demo website (see Hosted demo) |
| `tracelens export TRACE` | Chrome Trace JSON for [ui.perfetto.dev](https://ui.perfetto.dev): states, markers, IRQs, findings |
| `tracelens threads` / `dump` / `synth` | Per-thread summary, normalized events as JSONL, regenerate the test traces |

## What it detects, and the QNX semantics behind it

| Detector | QNX-specific behaviour it encodes |
|---|---|
| **Priority inversion** | Mutexes inherit priority by default, so most textbook inversions can't happen on QNX. The real ones come from **ownerless semaphores** and **`_NTO_CHF_FIXED_PRIORITY` channels**. Priorities come from kernel events over time, so a traced inheritance boost suppresses the finding. Medium-priority work counts only while it held the low thread's CPU and the low thread was READY. A semaphore used as a lock is told apart from one used as a signal. |
| **Send/Reply deadlock & chains** | A wait-for graph over QNX's synchronous message passing. Servers are resolved from COMM events (rcvid pairing), so connections made before the capture count. A process can only break a cycle if a thread is receiving **on the channel being called**. |
| **Mutex contention** | An uncontended QNX mutex never enters the kernel, so every `MUTEX`-state interval is real contention. Locks inside procnto (kernel addresses) are reported at LOW: not yours to fix. |
| **IRQ latency / handler overrun** | `InterruptAttachEvent()` → `InterruptWait()` → `InterruptUnmask()`: the interrupt stays masked while the handler thread works. Shared vectors keep all their handlers. |
| **Unusual behaviour** (learned) | Trained on healthy QNX traces only, per thread and 20 ms window: 19 features of scheduling behaviour, no names or absolute priorities, so it cannot memorise a program. On held-out real captures it flags 326 buggy traces that no rule reports, with 0 false alarms on 148 healthy ones. Reported MEDIUM, never gates a build and never gets an automatic patch. It also names the closest labelled pattern it has seen, and how loose that match is. |
| **Deadline misses** | Measured from the job's **release** (fitted period grid or `TL_RELEASE` marker), with a breakdown of every late job: late wake-up, waiting for the CPU, blocked, running. A late wake-up while nothing of equal or higher priority held the CPU is platform timer latency, not the program. |

## How it fixes

Each remedy is a source transform for one root cause the trace proved. It is applied only when its safety preconditions hold in the code; otherwise TraceLens gives the exact source lines and the fix to make by hand.

| Root cause (from the trace) | Remedy | Applied automatically when |
|---|---|---|
| Semaphore used as a lock (inversion "via a semaphore") | `sem_t` → `pthread_mutex_t` with `PTHREAD_PRIO_INHERIT`; wait/post → lock/unlock | it starts at 1, every function that waits also posts, no trywait/timedwait/other uses |
| `_NTO_CHF_FIXED_PRIORITY` server channel | drop the flag: the server runs at its client's priority | the flag appears in a `ChannelCreate()` flag expression |
| Interrupt thread works before `InterruptUnmask()` | unmask first; move the work to a worker thread fed by a coalescing pulse, **at a priority below every interrupt thread in the trace**, started before `InterruptAttach*()` and stopped after `InterruptDetach()` | the work uses no locals of the loop's function and no device access follows it |
| Mutex contention with private work inside the lock | move the leading/trailing statements that touch no shared data out of the critical section | the statements use no file-scope data, no pointer that may alias it, and contain no return/break/goto |
| Mutual `MsgSend()` (Send/Reply deadlock) | guided: a send hierarchy, one direction becomes `MsgSendPulse()` | never: the reply carries data, so the protocol change is a design decision |

**Trust rules.** Detection is deterministic and tested, and every finding lists the trace events that prove it. A trace that looks lossy (a thread running on two CPUs, a CPU switching threads without the old one leaving) gets **exit code 3: no verdict**. A trace without a clock rate is rejected rather than guessed. A fix is accepted only over several runs, never one, and only if the bug reproduced before it.

## The bug zoo

Five small QNX C programs with planted, realistic bugs (`bugzoo/`). Hand-written reference fixes live in `bugzoo/reference/`; the fix engine never reads them.

| Workload | Story | Planted bug |
|---|---|---|
| `z1_infusion_pump` | dose controller sharing a sensor buffer | `sem_t` used as a lock: no owner, no inheritance |
| `z2_brake_by_wire` | brake controller → arbiter server | channel created with `_NTO_CHF_FIXED_PRIORITY` |
| `z3_sensor_fusion` | two fusion servers | mutual `MsgSend()`: Send/Reply deadlock |
| `z4_camera_pipeline` | 4 workers, one frame store | work inside one global mutex |
| `z5_motor_encoder` | encoder interrupt service thread | heavy work before `InterruptUnmask()` |

## Results on real QNX 8.0

All numbers are from a QNX SDP 8.0 QEMU x86_64 VM (4 CPUs, KVM, `procnto-smp-instr`).

### Fixes, proven on the target

`tracelens eval fix --runs 5 --irq 4`: for each workload, 5 captures of the buggy build, the remedy
TraceLens chose from them, a `qcc` build, and 5 captures of the patched build, judged by `compare`.
Full table: [docs/results/fix.md](docs/results/fix.md); each workload's patch, traces and verdict
are in its evidence bundle.

| Workload | Root cause proven by the trace | Fix TraceLens applied | Verdict on QNX | Before → after |
|---|---|---|---|---|
| Z1 infusion pump | semaphore used as a lock | `sem_t` → priority-inheriting `pthread_mutex_t` ([patch](docs/results/fixes/z1_infusion_pump/patch.diff)) | **VERIFIED** | inversion in 5/5 runs → 0/5; `control` p99 5.74 → 1.29 ms (budget 2 ms) |
| Z2 brake-by-wire | `_NTO_CHF_FIXED_PRIORITY` channel | flag dropped: the arbiter inherits its client's priority ([patch](docs/results/fixes/z2_brake_by_wire/patch.diff)) | **VERIFIED** | inversion 5/5 → 0/5; misses 1000 → 0; `brake` p99 6.75 → 0.77 ms (budget 2 ms) |
| Z3 sensor fusion | mutual `MsgSend()` deadlock | guided: the two `MsgSend()` lines and the send-hierarchy fix ([summary](docs/results/fixes/z3_sensor_fusion/SUMMARY.md)) | **GUIDED** | not automated by design: the protocol change is a design decision |
| Z4 camera pipeline | private work inside one global lock | work moved out of the critical section; the shared copy stays locked ([patch](docs/results/fixes/z4_camera_pipeline/patch.diff)) | **VERIFIED** | contention 5/5 → 0/5; misses 5/5 → 0/5; `frame` p99 7.45 → 2.99 ms (budget 4 ms) |
| Z5 motor encoder | 2 ms of work before `InterruptUnmask()` | unmask first; work moved to a pulse-driven worker at priority 20, below every interrupt thread in the trace ([patch](docs/results/fixes/z5_motor_encoder/patch.diff)) | **VERIFIED** | overrun 5/5 → 0/5; p99 time masked 2.41 → 0.24 ms; p99 response 2.08 → 0.57 ms |

**4 of 5 planted bugs fixed automatically and verified on the target; the fifth gets exact guidance.**
Each bundle has a `report.html`: the program's threads before and after the fix on the same time
scale, the verdict numbers, why the remedy applies on QNX, and the patch (download and open it in a
browser). In the [codelab](docs/codelab/index.md)'s fresh-clone run the infusion pump needed two
rounds ([bundle](docs/results/fixes/z1_infusion_pump_codelab_2_rounds/SUMMARY.md)): the mutex removed
the inversion (p99 7.18 → 2.48 ms, still over budget), and round 2 moved the logger's flash write out of
the lock (p99 0.54 ms, VERIFIED).
Every patch compiles warning-free with `qcc -Wall -Wextra`. The fix engine never reads the
hand-written reference fixes. Z1's budget is 2 ms, not the original 1 ms: its 0.12 ms job left
less than the 2 ms of slack the bug zoo keeps over measured VM noise (PLAN.md §15), and at 1 ms a
single late job from VM jitter decided the verdict. Z1 detection was re-run at 2 ms (still 10/10
caught, 0/10 false alarms). Under the 1 ms budget the engine needed two rounds: the mutex removed
the inversion, the re-trace showed the next cause, and round 2 shrank both critical sections.

### Detection: 10 runs per build, held out

`tracelens eval detect --runs 10 --irq 4` captures every buggy build and every reference fix 10 times
and counts findings at or above `high`. The detectors were calibrated on three earlier 5-run
evaluations; this run was captured afterwards and not used for tuning. Full table:
[docs/results/detect.md](docs/results/detect.md).

| Workload | Planted bug | Buggy build caught | Reference fix flagged | Before/after verdict |
|---|---|---|---|---|
| Z1 infusion pump | `sem_t` used as a lock (no priority inheritance) | **10/10** | 0/10 | VERIFIED |
| Z2 brake-by-wire | `_NTO_CHF_FIXED_PRIORITY` server channel | **10/10** | 0/10 | VERIFIED |
| Z3 sensor fusion | two servers `MsgSend` to each other | **10/10** | 0/10 | VERIFIED |
| Z4 camera pipeline | 4 workers behind one global mutex | **10/10** | 0/10 | VERIFIED |
| Z5 motor encoder | heavy work before `InterruptUnmask()` | **10/10** | 0/10 | VERIFIED |
| Healthy system programs (`pidin` loop, idle, `ls -lR`) | none | | 0/30 | |

Lossy captures (a dropped kernel event) are excluded and replaced with a fresh capture, never
scored: 3 of 133 in this run. VERIFIED means the bug appeared in at least 60% of the "before" runs,
in none of the "after" runs, nothing new appeared, and response times improved significantly
(one-sided Mann-Whitney U, p < 0.01).

### One capture per build, committed

One buggy and one fixed capture of each workload, plus one of each healthy program, is committed in
[fixtures/real/](fixtures/real/) (8.9 MB) and re-checked by `scripts/check.sh`: every buggy build
must exit 1, every fix and every healthy program exit 0.

| Workload | Buggy build | Reference fix |
|---|---|---|
| Z1 infusion pump | **CRITICAL** priority inversion in 200 of 200 periods: control (50) blocked 5.36 ms while telemetry (20) held logger's CPU; **CRITICAL** deadline misses 200/200 | **0 findings** |
| Z2 brake-by-wire | **CRITICAL** inversion through the message channel in 200 of 200 periods: brake_ctrl (60) blocked 6.42 ms while the arbiter (10) sat READY behind diagnostics (30) | **0 findings** |
| Z3 sensor fusion | **CRITICAL** Send/Reply deadlock fusion_a → fusion_b → fusion_a for 1001 ms, broken by the timeout | **0 findings** |
| Z4 camera pipeline | **HIGH** mutex contention (23% of the time, p99 wait 4.8 ms) + **CRITICAL** deadline misses | only a LOW lock inside procnto (kernel address, not the program's) |
| Z5 motor encoder, driven on IRQ 4 | **HIGH** handler overrun: IRQ 4 masked up to 2.38 ms; p99 response 2.05 ms | **0 findings** (median response 63 µs) |

### What real QNX taught the tool

Each of these was found on real traces, fixed, and pinned by a regression test:

- **A user string event is not always a string.** Some `traceprinter` builds print one only as its
  raw payload words (`d0:0x4d5f4c54 d1:...`), with no decoded `STR:` field: 8 of 3,954 user events in
  a host-decoded capture, and exactly the `TL_META` markers that name the threads. Every check that
  reads a thread name silently failed. The parser now decodes the words itself, four characters each.
- **The 1 ms tick decides races.** QNX 8.0 timers fire on tick boundaries (the tick is fixed;
  `ClockPeriod()` cannot change it), so two releases less than a tick apart wake in a random order.
  Planted bugs that depended on sub-tick offsets reproduced in 1 to 4 runs out of 5; spaced by whole
  ticks (or a shared barrier, for Z3) they reproduce every time.
- **The release grid drifts.** The trace clock and the workload clock drift 0.05% apart on
  QEMU/KVM; a rigid grid turned that into 127/200 false misses. The grid is now fitted per stream
  (Theil-Sen), and one job that starts more than half a period late no longer shifts it.
- **One fix uncovers the next cause.** On Z1 (1 ms budget), the priority-inheriting mutex removed
  the inversion and the re-trace then showed `control` waiting ~1 ms every period on the logger's
  long critical section. The fix engine therefore diagnoses the patched build's own traces and
  fixes again, up to 3 rounds.
- **Deferred interrupt work must sit below every driver.** The first Z5 remedy ran the worker one
  priority below the interrupt thread and started it after `InterruptAttachEvent()`; the trace
  showed interrupts waiting up to 20 ms on its setup. The worker now runs below the lowest
  interrupt thread the trace shows (virtio at 21) and starts before the attach.
- **Not every lock is yours.** Waits on procnto's own mutexes (kernel addresses) are reported at
  LOW and never fail the gate.
- **A p99 of 7 samples is the maximum.** Contention, deadline and interrupt-handler severities
  require a pattern: rare, small outliers are reported at MEDIUM. `deadline_marginal_rate = 0`
  restores "any miss is HIGH" for hard real-time.
- **A late wake-up while only lower-priority threads ran is the platform**, not the program.
- **Measure on a quiet host.** QEMU's virtual CPUs share the host's cores: running a test suite on
  the host during a capture inflated a 0.13 ms job to 1.3 ms "running". Captures for the tables
  above were taken with the host idle.
- **The harness must not verify a bug that never happened.** A fix is only VERIFIED if the bug
  reproduced first.

### Learning from traces, when no rule exists

Rules cannot find what nobody wrote a rule for. TraceLens also learns what healthy QNX scheduling looks
like and reports threads that do not fit. The training data is **1,920 real QNX 8.0 captures** (one
night on the target) plus 1,920 from its own simulator: 16 scenarios, four of which no rule can see.

**What the learned radar adds, on held-out real traces it never trained on:**

| On 883 held-out buggy captures | |
|---|---|
| Caught by the rules, missed by the radar | 16 |
| Caught by both | 384 |
| **Caught by the radar with no rule firing** | **326** |
| Caught by neither | 157 |
| False alarms on the 148 held-out **healthy** captures | **0** |

The rules alone find 400 of 883; with the radar, 726. Those 326 extra are almost all the four bug
families **no rule exists for**: a lost wake-up and a period overrun caught **100%** of the time, a
lock-order deadlock **84%**, and a starved low-priority job **never** — starvation and healthy
deferred work are the same behaviour unless a deadline is declared, which is what the deadline rule
is for. On the families that do have rules, the rules remain better: they cite the kernel events
that prove the bug, where the radar only says "unlike anything healthy".

Two things worth saying plainly. The simulated traces are not filler: trained on the real captures
alone, the radar gives 2 false alarms on those 148 healthy traces, and 0 once the simulated ones join
training — breadth of healthy behaviour is what they buy. And the four rule-less families were
written by us: withholding them from training is an honest experiment, but it is not proof that the
radar will catch an unknown bug in someone else's program. The defensible claim is the measured one —
trained only on healthy behaviour, it flags bug classes it was never shown, on real hardware, without
crying wolf. Details: [results_train.md](docs/ml/results_train.md), [results_real.md](docs/ml/results_real.md).

The protocol was fixed before the data existed, the held-out families are never trained on, and every
number here comes from a recorded run — `python scripts/train_eval.py --sim data/sim --real data/real
--test-on data/real` for the table above, `scripts/sim_experiment.py` for the simulated-only ones
([docs/ml/](docs/ml/), method in [docs/ml/DESIGN.md](docs/ml/DESIGN.md)).

## Evidence of QNX use

| QNX technology | Where |
|---|---|
| QNX SDP 8.0, `qcc` cross-compiler (`-Vgcc_ntox86_64`, gcc 12.2.0); bug zoo and every generated patch build warning-free with `-Wall -Wextra` | [bugzoo/Makefile](bugzoo/Makefile), [src/tracelens/fix/build.py](src/tracelens/fix/build.py) |
| QEMU VM built with `mkqnximage` (4 CPUs, KVM) | [src/tracelens/target/qemu.py](src/tracelens/target/qemu.py), [scripts/qnx_vm.sh](scripts/qnx_vm.sh) |
| Instrumented kernel `procnto-smp-instr`, `tracelogger -w`, `traceprinter` | [src/tracelens/target/capture.py](src/tracelens/target/capture.py), [src/tracelens/target/check.py](src/tracelens/target/check.py), [src/tracelens/ingest/traceprinter.py](src/tracelens/ingest/traceprinter.py) |
| `TraceEvent()` user events (`_NTO_TRACE_INSERTUSRSTREVENT`) | [bugzoo/common/tl.h](bugzoo/common/tl.h) |
| `ChannelCreate`, `ConnectAttach`, `MsgSend`/`MsgReceive`/`MsgReply`, `MsgSendPulse`, `MsgReceivePulse`, `_NTO_CHF_FIXED_PRIORITY`, `TimerTimeout` | [bugzoo/](bugzoo/), [src/tracelens/detectors/ipc_chain.py](src/tracelens/detectors/ipc_chain.py), [src/tracelens/remedy/rules.py](src/tracelens/remedy/rules.py) |
| `InterruptAttachEvent`, `InterruptWait`, `InterruptUnmask`, `InterruptDetach`, `ThreadCtl(_NTO_TCTL_IO)`; QNX 8.0 `INT_DELIVER` / `IST_ATTACH` trace events | [bugzoo/z5_motor_encoder](bugzoo/z5_motor_encoder/main.c), [src/tracelens/detectors/irq_latency.py](src/tracelens/detectors/irq_latency.py), [src/tracelens/remedy/rules.py](src/tracelens/remedy/rules.py) |
| `ThreadCtl(_NTO_TCTL_RUNMASK)`, SCHED_FIFO, `PTHREAD_PRIO_INHERIT` | [bugzoo/common/tl.h](bugzoo/common/tl.h), [src/tracelens/detectors/prio_inversion.py](src/tracelens/detectors/prio_inversion.py), [src/tracelens/remedy/rules.py](src/tracelens/remedy/rules.py) |
| `pidin` thread snapshot | [src/tracelens/ingest/pidin.py](src/tracelens/ingest/pidin.py) |
| Real QNX 8.0 captures | [fixtures/real/](fixtures/real/), [docs/results/](docs/results/), [tests/test_real_qnx.py](tests/test_real_qnx.py) |

## Run it on QNX

Linux host (or WSL2 Ubuntu 24.04 on Windows) with KVM, and a free [QNX Everywhere](https://www.qnx.com/products/everywhere/) license:

```bash
pip install -e .
source ~/qnx800/qnxsdp-env.sh                 # QNX SDP 8.0
scripts/qnx_vm.sh                             # build + boot a QEMU VM with mkqnximage (instrumented kernel)
export TRACELENS_TARGET=$(tracelens target ip)
tracelens target check                        # ssh, instrumented kernel, a 1 s test trace
make -C bugzoo                                # qcc builds buggy + reference binaries into bugzoo/out/
tracelens capture bugzoo/out/z1_infusion_pump -c bugzoo/tracelens.toml --analyze -- -d 2
tracelens fix bugzoo/z1_infusion_pump -c bugzoo/tracelens.toml -- -d 2
```

The step-by-step tutorial is [docs/codelab](docs/codelab/index.md).

## Exit codes

`tracelens analyze` exits `0` when clean, `1` when findings reach `--fail-on` (default `high`), `2` on usage or input errors, and `3` when the trace is lossy, so no verdict is given. `tracelens compare` exits `0` VERIFIED, `1` NOT FIXED, `3` INCONCLUSIVE. `tracelens fix` exits `0` VERIFIED (or nothing to fix, or guided), `1` NOT FIXED or build failed, `3` INCONCLUSIVE. Use them from a Makefile, a pre-commit hook or any build script.

## Development

```bash
pip install -e ".[dev]"
scripts/check.sh                  # unit tests, bug-zoo compile check against QNX API stubs, every real trace's verdict
```

## License

MIT
