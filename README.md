# TraceLens

**Find, fix, and prove real-time bugs on QNX.** TraceLens reads a QNX Neutrino kernel event trace and finds timing bugs with deterministic detectors: priority inversion, Send/Reply deadlocks, mutex contention, interrupt handler overruns, and deadline misses. Claude explains each finding, citing trace events that are checked against the trace. The fix agent then patches the program, rebuilds it with `qcc`, re-runs it on the QNX target, and accepts the fix only if repeated re-traces prove the bug is gone.

> **Status (QNX Global Hackathon 2026, Developer Tooling & Host Tools).** The host toolchain is complete and tested: 70+ tests, including adversarial traces. Everything that touches the QNX target is implemented but not yet run on real QNX 8.0. Those steps and trace field names are marked **(verify)** until proven, and the headline results will come only from real captures. Progress log: [PLAN.md §14](PLAN.md).

## Try it in one minute (no QNX needed)

```bash
git clone https://github.com/sheikh2583/QNX-Global-Hackathon.git tracelens && cd tracelens
python3 -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
tracelens analyze fixtures/synthetic/z1_prio_inversion.txt -c fixtures/synthetic/tracelens.toml --html z1.html
```

```
[CRITICAL] TL-001 Priority inversion: control waited on logger via a semaphore
    control (prio 50) was blocked 8.20 ms on a semaphore (0x00008040) released by logger (prio 10);
    for 8.00 ms of that, logger was ready but telemetry (prio 20) held its CPU. Seen 3x.
[CRITICAL] TL-002 Deadline misses in 'control'
```

Or run the whole tour: `demo/run_demo.sh` (Linux/WSL). The core needs nothing beyond Python 3.11.

## How it works

```
QNX 8.0 target (QEMU x86_64)                        Host (Linux / WSL2)
  workload built with qcc                             capture   deploy, pidin snapshot, tracelogger, fetch
  procnto-smp-instr kernel  -- ssh/scp -->            ingest    traceprinter text -> events (sorted, unwrapped)
  tracelogger -> .kev                                 model     thread states, priority timelines, IPC map
                                                      detect    5 deterministic detectors -> findings + event IDs
                                                      explain   Claude, citations checked against the trace
                                                      fix       Claude patch -> qcc -> 5 runs -> compare verdict
                                                      report    terminal, HTML, JSON, SARIF, Perfetto, MCP
```

| Command | What it does |
|---|---|
| `tracelens target up \| check \| ip \| down` | Boot the QNX QEMU image (`mkqnximage`), preflight it (ssh, instrumented kernel, a 1 s test trace) |
| `tracelens capture BIN -- args` | Copy a `qcc` binary to the target, snapshot priorities with `pidin`, run it under `tracelogger -w`, fetch and decode the trace (`--command` traces a program already on the target) |
| `tracelens analyze TRACE` | Run every detector; terminal summary, `--html`, `--json`, `--sarif`; CI exit codes |
| `tracelens explain TRACE` | Claude explains each finding; every cited event is checked (thread, state or call) |
| `tracelens fix WORKLOAD` | Claude patches, `qcc` builds, the target re-runs N times, `compare` decides; evidence bundle |
| `tracelens compare --before … --after …` | VERIFIED / NOT FIXED / INCONCLUSIVE over ≥ 5 clean runs (Mann-Whitney U on response times) |
| `tracelens eval detect \| fix` | Bug-zoo evaluation on the target: detection and false-positive table (buggy vs reference builds, healthy programs), and the fix-rate ablation (full context vs source only) |
| `tracelens export TRACE` | Chrome Trace JSON for [ui.perfetto.dev](https://ui.perfetto.dev): states, markers, IRQs, findings |
| `tracelens mcp` | MCP server: `claude mcp add tracelens -- tracelens mcp`, then ask Claude Code about your traces |
| `tracelens threads` / `dump` / `synth` | Per-thread summary, normalized events as JSONL, regenerate the test traces |

## What it detects, and the QNX semantics behind it

| Detector | QNX-specific behaviour it encodes |
|---|---|
| **Priority inversion** | Mutexes inherit priority by default, so most textbook inversions can't happen on QNX. The real ones come from **ownerless semaphores** and **`_NTO_CHF_FIXED_PRIORITY` channels**. Priorities come from kernel events over time, so a traced inheritance boost suppresses the finding. Medium-priority work counts only while it held the low thread's CPU and the low thread was READY. A semaphore used as a lock is told apart from one used as a signal. |
| **Send/Reply deadlock & chains** | A wait-for graph over QNX's synchronous message passing. Servers are resolved from COMM events (rcvid pairing), so connections made before the capture count. A process can only break a cycle if a thread is receiving **on the channel being called**. |
| **Mutex contention** | An uncontended QNX mutex never enters the kernel, so every `MUTEX`-state interval is real contention. Judged by share of time and p99 wait, not raw counts. |
| **IRQ latency / handler overrun** | `InterruptAttachEvent()` → `InterruptWait()` → `InterruptUnmask()`: the interrupt stays masked while the handler thread works. Shared vectors keep all their handlers. |
| **Deadline misses** | Measured from the job's **release** (period grid or `TL_RELEASE` marker), so wake-up jitter counts; also overruns and skipped periods. |

**Trust rules.** The AI never decides that a bug exists. Detection is deterministic and tested, and every finding lists the trace events that prove it. A trace that looks lossy (a thread running on two CPUs, a CPU switching threads without the old one leaving) gets **exit code 3: no verdict**. A trace without a clock rate is rejected rather than guessed. A fix is accepted only over several runs, never one.

## The bug zoo

Five small QNX C programs with planted, realistic bugs (`bugzoo/`). Hidden reference fixes live in `bugzoo/reference/` and are never shown to the fix agent.

| Workload | Story | Planted bug |
|---|---|---|
| `z1_infusion_pump` | dose controller sharing a sensor buffer | `sem_t` used as a lock: no owner, no inheritance |
| `z2_brake_by_wire` | brake controller → arbiter server | channel created with `_NTO_CHF_FIXED_PRIORITY` |
| `z3_sensor_fusion` | two fusion servers | mutual `MsgSend()`: Send/Reply deadlock |
| `z4_camera_pipeline` | 4 workers, one frame store | work inside one global mutex |
| `z5_motor_encoder` | encoder interrupt service thread | heavy work before `InterruptUnmask()` |

## Results on real QNX 8.0

All numbers are from a QNX SDP 8.0 QEMU x86_64 VM (4 CPUs, KVM, `procnto-smp-instr`).

### Detection: 10 runs per build, held out

`tracelens eval detect --runs 10 --irq 4` captures every buggy build and every reference fix 10 times
and counts findings at or above `high` (the CI gate). The detectors were calibrated on three earlier
5-run evaluations; this run was captured afterwards and not used for tuning. Full table:
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

### One capture per build, in CI

One buggy and one fixed capture of each workload, plus one of each healthy program, is committed in
[fixtures/real/](fixtures/real/) (8.9 MB) and re-analyzed by CI on every push: every buggy build must
exit 1, every fix and every healthy program exit 0.

| Workload | Buggy build | Reference fix |
|---|---|---|
| Z1 infusion pump | **CRITICAL** priority inversion in 200 of 200 periods: control (50) blocked 5.36 ms while telemetry (20) held logger's CPU; **CRITICAL** deadline misses 200/200 | **0 findings** |
| Z2 brake-by-wire | **CRITICAL** inversion through the message channel in 200 of 200 periods: brake_ctrl (60) blocked 6.42 ms while the arbiter (10) sat READY behind diagnostics (30) | **0 findings** |
| Z3 sensor fusion | **CRITICAL** Send/Reply deadlock fusion_a → fusion_b → fusion_a for 1001 ms, broken by the timeout | **0 findings** |
| Z4 camera pipeline | **HIGH** mutex contention (23% of the time, p99 wait 4.8 ms) + **CRITICAL** deadline misses | only a LOW lock inside procnto (kernel address, not the program's) |
| Z5 motor encoder, driven on IRQ 4 | **HIGH** handler overrun: IRQ 4 masked up to 2.38 ms; p99 response 2.05 ms | **0 findings** (median response 63 µs) |

### What real QNX taught the tool

Each of these was found on real traces, fixed, and pinned by a regression test:

- **The 1 ms tick decides races.** QNX 8.0 timers fire on tick boundaries (the tick is fixed;
  `ClockPeriod()` cannot change it), so two releases less than a tick apart wake in a random order.
  Planted bugs that depended on sub-tick offsets reproduced in 1 to 4 runs out of 5; spaced by whole
  ticks (or a shared barrier, for Z3) they reproduce every time.
- **The release grid drifts.** The trace clock and the workload clock drift 0.05% apart on
  QEMU/KVM; a rigid grid turned that into 127/200 false misses. The grid is now fitted per stream
  (Theil-Sen), and one job that starts more than half a period late no longer shifts it (that
  produced 199/200 false misses from a single 5.3 ms host stall).
- **Not every lock is yours.** Waits on procnto's own mutexes (kernel addresses) are reported at
  LOW and never fail the gate.
- **A p99 of 7 samples is the maximum.** Contention, deadline and interrupt-handler severities now
  require a pattern: rare, small outliers are reported at MEDIUM. `deadline_marginal_rate = 0`
  restores "any miss is HIGH" for hard real-time.
- **A late wake-up while only lower-priority threads ran is the platform**, not the program: a
  lower-priority thread cannot delay a timer wake-up.
- **The harness must not verify a bug that never happened.** A fix is only VERIFIED if the bug
  reproduced first.

## Evidence of QNX use

| QNX technology | Where |
|---|---|
| QNX SDP 8.0, `qcc` cross-compiler (`-Vgcc_ntox86_64`, gcc 12.2.0); all bug-zoo programs build warning-free | [bugzoo/Makefile](bugzoo/Makefile), [src/tracelens/fix/build.py](src/tracelens/fix/build.py) |
| QEMU Quick Start target image, `mkqnximage --run/--getip/--stop` | [src/tracelens/target/qemu.py](src/tracelens/target/qemu.py) |
| Instrumented kernel `procnto-smp-instr`, `tracelogger -w`, `traceprinter` | [src/tracelens/target/capture.py](src/tracelens/target/capture.py), [src/tracelens/target/check.py](src/tracelens/target/check.py), [src/tracelens/ingest/traceprinter.py](src/tracelens/ingest/traceprinter.py) |
| `TraceEvent()` user events (`_NTO_TRACE_INSERTUSRSTREVENT`) | [bugzoo/common/tl.h](bugzoo/common/tl.h) |
| `ChannelCreate`, `ConnectAttach`, `MsgSend`/`MsgReceive`/`MsgReply`, `MsgSendPulse`, `_NTO_CHF_FIXED_PRIORITY`, `TimerTimeout` | [bugzoo/z2_brake_by_wire](bugzoo/z2_brake_by_wire/main.c), [bugzoo/z3_sensor_fusion](bugzoo/z3_sensor_fusion/main.c), [src/tracelens/detectors/ipc_chain.py](src/tracelens/detectors/ipc_chain.py) |
| `InterruptAttachEvent`, `InterruptWait`, `InterruptUnmask`, `ThreadCtl(_NTO_TCTL_IO)` | [bugzoo/z5_motor_encoder](bugzoo/z5_motor_encoder/main.c), [src/tracelens/detectors/irq_latency.py](src/tracelens/detectors/irq_latency.py) |
| `ThreadCtl(_NTO_TCTL_RUNMASK)`, SCHED_FIFO, priority inheritance semantics | [bugzoo/common/tl.h](bugzoo/common/tl.h), [src/tracelens/detectors/prio_inversion.py](src/tracelens/detectors/prio_inversion.py) |
| `pidin` thread snapshot | [src/tracelens/ingest/pidin.py](src/tracelens/ingest/pidin.py) |
| Real QNX 8.0 captures (QEMU VM, 4 CPUs, `procnto-smp-instr`) | [fixtures/real/](fixtures/real/), checked by [tests/test_real_qnx.py](tests/test_real_qnx.py) and the CI gate: all 5 buggy builds exit 1, all 5 reference fixes exit 0; held-out 10-run evaluation in [docs/results/detect.md](docs/results/detect.md) |

## Run it on QNX (verify)

Linux host (or WSL2 Ubuntu 24.04 on Windows) with KVM, and a free [QNX Everywhere](https://www.qnx.com/products/everywhere/) license:

```bash
pip install -e ".[ai,mcp]"
source ~/qnx800/qnxsdp-env.sh                 # SDP 8.0 + QEMU Quick Start image installed via QNX Software Center
tracelens target up && export TRACELENS_TARGET=$(tracelens target ip)
tracelens target check                        # ssh, instrumented kernel, a 1 s test trace
make -C bugzoo                                # qcc builds buggy + reference binaries into bugzoo/out/
tracelens capture bugzoo/out/z1_infusion_pump -c bugzoo/tracelens.toml --analyze -- -d 2
tracelens fix bugzoo/z1_infusion_pump -c bugzoo/tracelens.toml -- -d 2   # needs ANTHROPIC_API_KEY
```

The step-by-step tutorial is [docs/codelab](docs/codelab/index.md).

## CI contract

`tracelens analyze` exits `0` when clean, `1` when findings reach `--fail-on` (default `high`), `2` on usage or input errors, and `3` when the trace is lossy, so no verdict is given. `tracelens compare` exits `0` VERIFIED, `1` NOT FIXED, `3` INCONCLUSIVE. Use `--sarif` and GitHub's `upload-sarif` action to show findings as code-scanning alerts.

## Development

```bash
pip install -e ".[dev,ai,mcp]"
pytest -q                         # 70+ tests; one needs Linux gcc
make -C bugzoo hostcheck          # type-check the C workloads against QNX API stubs (no QNX needed)
```

## License

MIT
