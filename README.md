# TraceLens

**Autonomous real-time debugging for QNX.** TraceLens reads a QNX kernel event trace, finds timing bugs deterministically (priority inversion, Send/Reply deadlocks, mutex contention, interrupt handler overruns, deadline misses), explains them with evidence, and — coming in v0.2 — fixes them and proves the fix by re-tracing on the QNX target.

> Status: **v0.1 in development** for the QNX Global Hackathon 2026. The analysis core runs today on synthetic traces in `traceprinter` format; real QNX 8.0 captures are next. See [PLAN.md](PLAN.md).

## Quick start

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip
tracelens synth --out fixtures/synthetic   # generate the bug-zoo traces
tracelens analyze fixtures/synthetic/z1_prio_inversion.txt \
    -c fixtures/synthetic/tracelens.toml --html report.html
```

The core has **no dependencies** beyond Python 3.11.

## What it detects

| Detector | QNX-specific angle |
|---|---|
| Priority inversion | Priorities come from kernel events over time, so traced inheritance boosts suppress false alarms; counts medium-priority work only while it held the low thread's CPU; tells a semaphore used as a lock from one used as a signal; covers `_NTO_CHF_FIXED_PRIORITY` channels |
| Send/Reply deadlock & chains | Wait-for graph built from QNX message passing, servers resolved via `ConnectAttach()` coids |
| Mutex contention | Every `MUTEX`-state interval is real contention (uncontended QNX mutexes never enter the kernel); judged by share of time and p99 wait, not raw counts |
| IRQ latency / handler overrun | `InterruptAttachEvent()` → `InterruptWait()` → `InterruptUnmask()` timing |
| Deadline misses | Measured from the job's release (period grid or `TL_RELEASE` marker), so wake-up jitter counts; also overruns and skipped periods |

## CI contract

`tracelens analyze` exits `0` when clean, `1` when findings reach `--fail-on` (default `high`), `2` on usage or input errors (including a trace without a clock rate), and `3` when the trace is lossy (the scheduler state machine is broken, which usually means dropped events): no verdict is better than a wrong one.

## Target

QNX SDP 8.0 (QNX Everywhere), QEMU x86_64, traces captured with `tracelogger` and decoded with `traceprinter`. *(Build and run instructions for the target land with Phase 1.)*

## License

MIT
