# Simulated QNX 8.0 traces (sample data)

One trace per data-engine scenario, 1 second each, written by TraceLens's QNX scheduling simulator
(`src/tracelens/sim/`) in the exact `traceprinter` text format of a real QNX 8.0 capture. Every file
says it is simulated (`TRACE_SIMULATED` header line). They are for trying TraceLens without a QNX
target and for tests; the real captures in `../real/` stay the ground truth.

```bash
tracelens analyze fixtures/sim/sem_inversion.txt.gz -c bugzoo/gen/tlgen.toml
tracelens analyze fixtures/sim/mutex_abba.txt.gz -c bugzoo/gen/tlgen.toml --radar
tracelens simulate lost_wakeup -o my_trace.txt.gz --param mid_us=4000     # make your own
tracelens data simulate --per-scenario 120 --out data/sim                 # a labelled dataset
```

| File | Planted problem | Who should be blamed |
|---|---|---|
| `healthy_*` | none (6 healthy program shapes) | nobody |
| `healthy_irq_deferred` | none: the correct interrupt pattern (unmask, then a lower-priority worker) | nobody |
| `sem_inversion` | priority inversion through a semaphore | `hi` blocked, `lo` holds it, `mid` runs |
| `chan_inversion` | inversion through a `_NTO_CHF_FIXED_PRIORITY` channel | `client` waits on `server` |
| `condvar_inversion` | inversion through a condition variable | `hi` waits on `lo` |
| `lock_contention` | workers serialised on one mutex | `w1`..`wN` |
| `irq_overrun` | interrupt thread works with the line masked | `ist` |
| `ipc_deadlock` | two servers serve each other, then both send | `fusion_a`, `fusion_b` |
| `cpu_starvation` | a busy higher-priority thread delays a periodic job (no rule) | `job` starved by `hog` |
| `mutex_abba` | lock-order deadlock between two mutexes (no rule) | `ab`, `ba` |
| `lost_wakeup` | signal sent before the wait; consumer sleeps to its timeout (no rule) | `consumer` |
| `period_overrun` | job work exceeds its period; logger starves (no rule) | `ctl`, `logger` |
