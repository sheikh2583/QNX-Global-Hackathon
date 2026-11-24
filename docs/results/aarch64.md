# Does TraceLens work on QNX 8.0 on aarch64?

Measured 2026-11-23 on the project machine (WSL2 Ubuntu 24.04, QNX SDP 8.0, host x86_64).

## Verdict

**Nothing tested is x86-specific in the code. On a QNX 8.0 `aarch64le` guest the rules and the x86-trained
radar carry over for the non-interrupt workloads; the interrupt rules carry over once a handler is judged
by its *median* time; and the radar does not carry over on interrupt traces.** The guest is QEMU `virt`
(cortex-a57, 4 CPUs), emulated — see the limits.

- the workload suite cross-compiles for aarch64 with **no source change** (§2);
- **5 runs of each of 13 non-interrupt scenarios** (65 captures, §3, §5): every rule that fires on x86
  fires on aarch64, on the right workload; the radar, **trained entirely on x86 traces**, flags **38 of 45**
  planted bugs on the thread that suffers with **0 false alarms on 20 healthy traces** (the 7 misses are
  `cpu_starvation` 5/5, the radar's documented blind spot on x86 too, and `lock_contention` 2/5); the
  per-feature medians agree on **243 of 263 pairs (92.4%)**, against 86.5% for two x86 collections
  compared with each other;
- **the interrupt workloads are ported** (§6). The x86 recipe (an `echo` flood on the serial port) raises
  no interrupt on a PL011; large writes do. With the x86 *tail* budget the rules false-alarm under
  emulation (1 of 16 up to 5 of 6 healthy traces); the **median handler time against x86's own 500 µs
  budget, no calibration, flags all 34 planted overruns and 0 of 49 healthy handlers** across six batches
  and two interrupt sources, z5 included;
- **the radar flags the interrupt thread in every interrupt trace** (24 of 24, 16 of them healthy). It
  does not transfer there — because the interrupt thread's rate features follow the interrupt rate
  (about 290/s here against ~2,700/s on x86), which is a property of the source, not the architecture.

The limits:

1. **This is emulated aarch64, not ARM hardware.** An x86 host has no KVM for ARM, so QEMU interprets
   every instruction (TCG). Timing is emulated timing, and the jitter it adds is what breaks the tail
   budgets and the deadline budgets below. The right claim is "the tool does not depend on x86"; it is
   *not* "validated on a Cortex-A part". That needs a board. (A phone does not count: it runs Android, not
   QNX, and TraceLens reads QNX kernel traces. A QNX-capable board — QNX 8.0 ships BSPs for the
   Raspberry Pi 4/5 among others — is the real test.)
2. **Five runs per scenario** (x86: 120). Enough to see the pattern and to reproduce the x86 misses; not
   enough for tight per-scenario rates.
3. **The median rule's 500 µs was chosen after seeing one batch** (the 24-trace UART batch); the other
   five batches were scored with it afterwards, so they are the independent evidence. The `tlgen` deadline
   budget (2.5 ms on the `job` deadline) was **not** recalibrated: with x86's value `healthy_mixed` fires
   `deadline_miss` on 5 of 5 aarch64 runs and `healthy_ipc` on 2 of 5 (§3, §7).
4. **61 of 65 non-interrupt traces were flagged lossy** by the integrity check, against 0 of 16 on the x86
   pilot (§4): a real cross-machine difference, and a property of the check, not of the rules.

## 1. What it took to get a guest (so this can be repeated)

`mkqnximage --arch=aarch64le` needs two SDP packages that a default install does not have, both
downloadable only with a myQNX login (done in QNX Software Center by the user):

| Missing | Symptom | Package |
|---|---|---|
| `startup-qemu-virt` | `ifs.build:23 Host file 'startup-qemu-virt' not available` — only the boot image fails, both filesystem partitions build | `com.qnx.qnx800.target.qemuvirt` ("QEMU Virtualization Drivers (Startup)", 138 KB) |
| `devb-virtio` | image builds, kernel boots, then `Unable to access /dev/hd0 … No system file system, giving up` — no sshd, no tracelogger | installed as dependencies of `com.qnx.qnx800.bsp.hypervisor_guest_arm` ("BSP for Hypervisor guest for generic ARM virtual machines", Software Center → Available → Board Support Packages); brings `driver.virtio.devb/.devc/.startup` and `libhyp` (99 MB) |

The virtio drivers do not appear as their own entry in Software Center; they come with that BSP.
After both: `mkqnximage --clean --type=qemu --arch=aarch64le --cpu=4 --ram=2G ...` builds a 9.8 MB
`ifs.bin`, and `tracelens target check` passes on the guest:

```
[PASS] ssh / os   QNX tracelens-a64 8.0.0 ... QEMU_virt aarch64le
[PASS] cpus 4 / instrumented kernel procnto-*-instr / tracelogger / pidin
[PASS] trace capture   1 s wide-mode trace: 136974 bytes
[WARN] traceprinter    not found -> decoded on the host (same as the x86 guest)
```

The x86 image in `~/qnx-vm` was never touched; the aarch64 guest runs from `~/qnx-vm-aarch64` with
ssh forwarded to `127.0.0.1:2223` (the x86 guest uses 2222).

## 2. The workloads build for aarch64 unchanged

```
make -C bugzoo ARCH=aarch64le OUT=out-aarch64le
```

All five planted-bug workloads, their five reference fixes and the 16-scenario generator `tlgen`
compile with `qcc -Vgcc_ntoaarch64le -O2 -g -Wall -Wextra -std=gnu11`: **eleven binaries, zero
warnings, zero edits.** The QNX API surface they use (`pthread`, `sem_*`, `ChannelCreate`/`MsgSend`,
`InterruptAttach*`, `TraceEvent`, `ClockCycles`) is architecture-neutral.

## 3. Rules on aarch64

**Five runs of each non-interrupt `tlgen` scenario** (`data plan --per-scenario 5`, 65 captures, x86 budgets
in `bugzoo/gen/tlgen.toml`; lossy traces kept, see §4). Runs in which a HIGH+ rule fired:

| Scenario | Rules fired (runs of 5) | Expected |
|---|---|---|
| `sem_inversion`, `chan_inversion`, `condvar_inversion` | `priority_inversion` 5/5 + `deadline_miss` 5/5, each | same as x86 |
| `ipc_deadlock` | `ipc_deadlock` 5/5 | same |
| `lock_contention` | `mutex_contention` + `deadline_miss` 3/5; **2/5 quiet** | detected on x86 |
| `cpu_starvation`, `mutex_abba`, `period_overrun` | none | none: no rule exists for these families |
| `lost_wakeup` | none, except one stray `priority_inversion` (1/5) | none |
| `healthy_periodic`, `healthy_pi_mutex` | none (0/10) | quiet |
| `healthy_ipc` | **`deadline_miss` 2/5** | quiet |
| `healthy_mixed` | **`deadline_miss` 5/5** | quiet (x86 misses 22%: 26 of 120 runs) |

The two healthy rows are the deadline budget again (§7): `healthy_mixed` already misses its 2.5 ms job
budget on one x86 run in five because wake-ups land 1.1–1.4 ms late; emulated jitter makes it every run.
`bugzoo/gen/tlgen.toml` was not recalibrated for aarch64 — a budget fitted to these traces would be
circular, and §7 already shows the effect for the bug zoo.

The bug-zoo workloads (`tracelens eval detect --bin-dir bugzoo/out-aarch64le`, 5 runs per build, lossy
runs excluded, committed x86 budgets):

| Workload | Buggy build: detected | Reference fix: runs with findings | Verdict |
|---|---|---|---|
| z1 infusion pump | 4/4 | 0/4 | INCONCLUSIVE (only 4 clean fixed runs; the rule needs 5) |
| z2 brake-by-wire | 5/5 | 2/5 (`deadline_miss`) | NOT FIXED |
| z3 sensor fusion | 5/5 | 0/5 | VERIFIED |
| z4 camera pipeline | 5/5 | 1/5 (`deadline_miss`) | NOT FIXED |
| z5 motor encoder | 5/5 on the UART source (§6) | 2/5 with x86's tail budget; **0/5 with the aarch64 config** | `eval detect --allow-lossy`: NOT FIXED with the x86 tail budget, see §6 for the median rule |

x86 detected 10/10 on all five. The NOT FIXED rows are a budget effect, not a detector failure (§7, §6).
The three healthy shell programs (`pidin_loop`, `idle_system`, `shell_io`) produced **no usable traces**:
all 10 runs of each were lossy, so that run says nothing about false alarms on them.

## 4. Why so many traces are lossy — and what was not changed

The `tlgen` traces have 15–40 thousand events and **1 to 5 scheduler-order violations each**, of two
kinds: "thread RUNNING on two CPUs at once" and "CPU switched threads without the previous one
leaving". That is the signature of timestamps that disagree slightly between CPUs (reordering), not of
bulk dropped events. `LOSSY_MIN_EVENTS = 100,000` makes any violation void a trace smaller than that,
and the rate limit `LOSSY_RATE = 1e-5` voids larger ones above ~5 violations per 500k events (the
bug-zoo traces, 320–530k events, are lossy about half the time).

I did **not** loosen the check: it was calibrated on x86 and a looser one would change what every
published number means. Two things were added instead, both opt-in and tested:

- `tracelens data features --include-lossy` featurises lossy traces too (each row tagged `lossy`);
  training never sets it. Without it the cross-architecture comparison had **2 of 16 scenarios**.
- the rule results above are reported with the lossy exclusions stated, never silently.

The later batches were no different: 61 of 65 non-interrupt traces and all 24 UART interrupt traces were
flagged lossy.

Whether the rules should be trusted on a trace with a handful of such slips is a separate question this
data cannot settle: a slip distorts one interval, but the check cannot say which.

## 5. The radar and the features, against x86

`scripts/arch_compare.py` — `real_vs_sim.py`'s gap table pointed at two real collections. The reference is
the 120-runs-per-scenario x86 collection (`data/real`) every published number comes from.

**Control first**, because a cross-architecture gap means nothing without knowing how far two x86 runs
already differ ([arch_control.md](arch_control.md): the x86 pilot, one run per scenario, against the same
reference):

| Comparison | Pairs within 0.10 | Radar: bugs flagged on the right thread | False alarms |
|---|---|---|---|
| x86 pilot (1 run per scenario) vs x86 reference — the control | 238 of 275 (86.5%) | 8 of 10 | 0 of 6 healthy |
| aarch64, 1 run per scenario, 13 scenarios | 222 of 256 (86.7%) | 8 of 9 | 0 of 4 healthy |
| **aarch64, 5 runs per scenario, 13 non-interrupt scenarios** ([aarch64_features_5.md](aarch64_features_5.md)) | **243 of 263 (92.4%)** | **38 of 45** | **0 of 20 healthy** |

Radar on the 5-run batch, per scenario (shipped `src/tracelens/ml/radar.json`, which never saw aarch64):

| Scenario | Flagged on the right thread | |
|---|---|---|
| `sem_inversion`, `chan_inversion`, `condvar_inversion` | 5/5 each | `hi` / `client` 93–101 of 100–101 windows |
| `ipc_deadlock` | 5/5 | `fusion_a` and `fusion_b`, ~51–54 of ~104–107 |
| `mutex_abba`, `lost_wakeup`, `period_overrun` | 5/5 each | `ba`/`ab` 51/51; `consumer` 96–100/100; `logger` 115–141/118–142 |
| `lock_contention` | **3/5** | two runs quiet; x86 reaches ~70% on this family |
| `cpu_starvation` | **0/5** | the radar's documented blind spot on x86 too: a starved low-priority job looks like healthy deferred work, and the deadline rule is what catches it |
| the 4 healthy scenarios | quiet, 20/20 | |

The widest per-feature gaps are on the main thread `tlgen[1]` of the healthy scenarios — `cpus_used` 3 vs 2
(four scenarios), `share_sleep` 0.28 vs 0.56 on `healthy_pi_mutex` — and the same threads show the same
kind of gap in the x86 control (`cpus_used` 1.0, `share_sleep` 0.32 on `healthy_pi_mutex`): the scheduler
spreads a thread over more CPUs under emulation, and one run of one thread is noisy on either
architecture. No other feature moves systematically. More runs tightened the agreement from 86.7% to
92.4%, which is what noise (not a real difference) does.

Why the transfer holds (the design argument, now with a measurement behind it): all 19 features are
shares, fractions, ranks, per-millisecond rates or counts; none carries an absolute time, a clock rate or
a pointer width, and the parser takes the clock from the trace header. The exception is visible in §6: a
*rate* feature follows the workload's event rate, so a thread whose events come 8× less often (the
interrupt thread here) looks unusual to a radar trained on the faster x86 source. `KERNEL_SPACE =
0xFFFF_8000_0000_0000` in `detectors/mutex_contention.py` is the one architecture-flavoured constant; this
data does not exercise it (no kernel-space mutex finding appeared), so its aarch64 comment stays
**(verify)**.

## 6. The interrupt workloads, ported — and what they show

`healthy_irq`, `irq_overrun`, `healthy_irq_deferred` and z5 attach with `InterruptAttachEvent(irq, …)` and
block in `InterruptWait`. On x86 the interrupt is COM1 (4), driven by a loop of `echo` writes to
`/dev/ser1`. On the QEMU `virt` machine that hangs, and finding out why took a probe
([`bugzoo/gen/irqprobe.c`](../../bugzoo/gen/irqprobe.c): it attaches the same way but gives up each wait
after 250 ms, so it reports "0 interrupts" instead of hanging):

| Source tried (3 s) | Interrupts seen |
|---|---|
| interrupt 4, as on x86 | the program waits forever: nothing raises it |
| UART, interrupt 33 (`devc-serpl011 -F 0x9000000,33`), `echo` flood | **0** |
| **UART, interrupt 33, large writes (`dd` 4 KB blocks to `/dev/ser1`)** | **859 (286/s), steady** |
| virtio-net, interrupt 78 | 134 (45/s) |
| virtio-blk, interrupt 79, a write-and-sync loop | 333 (111/s) |

**Why the `echo` flood raises nothing:** the PL011 has a transmit FIFO and the driver only needs a
transmit interrupt to refill it. A 65-byte `echo` fits in the FIFO, which QEMU drains instantly, so no
interrupt is ever needed. A 4 KB write overflows it and the driver relies on the interrupt. (I first read
this as "the UART's interrupt never reaches a second listener" and ported the workloads to the disk
instead; that was wrong, and the disk source is what made the results look worse than they are.) The
load is now `while :; do dd if=/dev/zero of=/dev/ser1 bs=4k count=64; done`, passed with
`tracelens data plan --irq 33 --irq-load '<it>'` and `tracelens eval detect --irq 33 --irq-load '<it>'`
(x86 defaults unchanged, tested).

### The tail budget is what emulation breaks

On the aarch64 guest a healthy handler doing 50 µs of work reaches p99 **260–500 µs** on the UART source
and **450–1,360 µs** on the disk source, against x86's p99 81 µs: the tail of "time masked" is emulation
jitter. x86's tail budget (500 µs) therefore fires on healthy handlers, and raising it loses real
overruns. A budget calibrated from six healthy disk-source traces by a rule written down in advance
(1.25 × the worst p99 → 2,400 µs) removed the false alarms and then **missed the planted overruns on a
second batch (0 of 4)**; the worst healthy trace in the calibration batch was an outlier that pushed it too
high. The **median** handler time is not jitter: a systematic overrun moves it, a stall does not.

| Batch (interrupt source) | Healthy median `p50` | Overrun median `p50` | x86 tail budget: healthy / overrun flagged | **Median > 500 µs: healthy / overrun flagged** |
|---|---|---|---|---|
| U, 24 traces, seed 12 (UART) | ≤ 37 µs | ≥ 770 µs | 1/16 · 8/8 | **0/16 · 8/8** |
| UART pilot, 8 traces, seed 11 | ≤ 44 µs | ≥ 841 µs | 0/4 · 4/4 | 0/4 · 4/4 |
| calibration batch, 9 traces, seed 7 (disk) | ≤ 83 µs | ≥ 990 µs | 5/6 · 3/3 | 0/6 · 3/3 |
| test batch, 12 traces, seed 8 (disk) | ≤ 66 µs | ≥ 1,098 µs | 4/8 · 4/4 | 0/8 · 4/4 |
| z5, 10 buggy + 10 reference (disk) | ≤ 55 µs | ≥ 2,163 µs | 10/10 · 10/10 | 0/10 · 10/10 |
| z5, 5 buggy + 5 reference (UART) | ≤ 41 µs | ≥ 2,051 µs | 2/5 · 5/5 | 0/5 · 5/5 |
| **all six** | **≤ 83 µs** | **≥ 770 µs** | **22/49 · 34/34** | **0/49 · 34/34** |

The threshold is x86's own handler budget (500 µs), **not calibrated**; the healthy and overrun medians are
about 9× apart. It was chosen after seeing batch U, so U is not an independent test of it; the other
five batches are. `irq_median_handler_us` is a new, optional threshold (0 = off, so every x86 number is
unchanged) and `bugzoo/tracelens.aarch64.toml` sets it to 500 and switches the tail rule off for this
machine. Re-scored with that config through the real detector, not a re-implementation: the same
0/49 and 34/34. Planted overruns here are 700 µs of handler work and up; whether a smaller one is caught
was not tested.

### The radar on interrupt traces

It flags the interrupt thread `ist` in **every** interrupt trace on the UART source: all 8 planted overruns
and all 16 healthy ones (the deferred scenario's `worker` too), and the same on the disk batches (7 of 7
bugs, 14 of 14 healthy). It does not transfer. The gap table says why
([aarch64_irq_uart_features.md](aarch64_irq_uart_features.md)): `ist` `preempts_per_ms` is 0.25 against
2.25 on x86 and `blocks_per_ms` 0.25 against 1.7, because the UART here delivers ~290 interrupts a second
and x86's serial flood ~2,700. A rate feature follows the workload's rate. That is a property of the
interrupt *source* — a faster source, or a radar trained on this rate, would change it — not evidence
about the architecture. 11 of 36 interrupt feature/thread pairs agree within 0.10, against 92.4% for the
non-interrupt scenarios.

### What this settles and what it does not

Settled: the interrupt workloads run on aarch64; the x86 *tail* budget does not survive emulation but a
median rule at the same budget does, on two interrupt sources; the radar needs an interrupt rate like the
one it was trained on. Not settled: interrupt behaviour on ARM hardware (where the tail may be as tight as
x86's, making the median rule unnecessary), overruns smaller than 700 µs, and why the PL011's rate is
~290/s here (a faster guest or driver setting, `-T`, may raise it).

## 7. Deadline budgets under emulation

The committed `bugzoo/tracelens.toml` is calibrated for the KVM x86 guest and is **unchanged**. On the
aarch64 guest the reference fixes still miss a rare job (traces in `docs/results/aarch64/traces/`):

| Workload | Reference: jobs missing | Worst reference response | p99 release jitter | Committed budget | Buggy build: jobs missing |
|---|---|---|---|---|---|
| z1 | 1 of 200 in 1 of 10 runs | 2.83 ms | 0.78 ms | 2 ms | 96–100% |
| z2 | 1–2 of 200 in 3 of 9 runs | 2.84 ms | 0.83–0.84 ms | 2 ms | 100% |
| z4 | 1 of 800 in 1 of 5 runs | 5.12 ms | 1.24 ms | 4 ms | 52–63% |

The planted bugs miss by a very wide margin (p99 response 5.9–8.4 ms), so detection does not depend
on the budget. The misses on the reference are isolated wake-up jitter above a budget with only ~2 ms
of slack, which emulation eats.

A separate config, [`bugzoo/tracelens.aarch64.toml`](../../bugzoo/tracelens.aarch64.toml), changes the
three deadline budgets (3.5 / 3.5 / 6 ms: the worst reference response plus ~0.7 ms) and the interrupt-handler
rule (§6), and says why in its header. Re-scoring the same saved traces with it:

| Workload | Buggy detected | Reference with findings | Verdict (x86 budgets) | Verdict (aarch64 budgets) |
|---|---|---|---|---|
| z1 | 4/4 | 0/4 | INCONCLUSIVE | INCONCLUSIVE (4 clean fixed runs) |
| z2 | 5/5 | 2/5 → 0/5 | NOT FIXED | VERIFIED |
| z3 | 5/5 | 0/5 | VERIFIED | VERIFIED |
| z4 | 5/5 | 1/5 → 0/5 | NOT FIXED | VERIFIED |

**This is not an independent test**: the budgets were derived from the same reference traces they are
scored on. It shows that the bug/fix separation survives a budget that allows for emulated jitter; it
does not validate the budgets. A fair check would pick budgets on one batch of captures and score
another.

The same effect hits `tlgen`'s own `job` deadline (2.5 ms): `healthy_mixed` fires `deadline_miss` on 5 of 5
aarch64 runs and `healthy_ipc` on 2 of 5 (§3). `bugzoo/gen/tlgen.toml` is left at x86's value rather than
fitted to those same traces.

## 8. What changed in the code (x86 defaults unchanged, tests and lint pass)

- `tracelens target up --ssh-port`, and reuse of a running VM only if it is *this* image directory's
  (live `output/qemu.pid`) — so a second VM never adopts the first.
- `user_net_argv` keeps the architecture's own NIC (`virtio-net-device` on aarch64).
- The ssh readiness probe now waits for the **`SSH-` banner**. QEMU's port forward accepts TCP before
  the guest has booted, so `target up` reported "VM answering ssh" for a VM that was still starting;
  that bug existed on x86 too and is invisible there only because x86 boots fast.
- `tracelens fix --arch` / `eval --arch`: `QccBuilder` was hardcoded to `x86_64` at every call site, so
  a fix "proven on the target" was rebuilt for x86 whatever the target was.
- `tracelens eval detect|fix --bin-dir`; `tracelens data features --include-lossy`;
  `tracelens data plan --irq --irq-load` and `tracelens eval detect|fix --irq-load` (the interrupt
  source is a parameter; the x86 `echo` flood stays the default); `bugzoo/gen/irqprobe.c`, which reports
  "0 interrupts" instead of hanging.
- `irq_median_handler_us` (a new optional threshold, 0 = off) and a `p50_handler_us` metric on interrupt
  findings: judge a handler by its median time masked as well as its tail. Off by default; tested.
- `tracelens eval detect --allow-lossy`: keep traces the integrity check called lossy and report how many
  were kept (the table format is unchanged without the flag). Without it z5 had no data at all.
- `scripts/arch_compare.py` and `scripts/aarch64_pilot.sh` (the whole run, resumable).

## 9. Reproduce

```bash
# prerequisites: the two SDP packages in §1; qemu-system-aarch64 on PATH (Ubuntu: qemu-system-arm)
# interrupt scenarios: scripts/aarch64_pilot.sh step 8 (interrupt 33, the `dd` loop of §6)
source ~/qnx800/qnxsdp-env.sh && source ~/.venvs/tracelens/bin/activate
scripts/aarch64_pilot.sh                       # build, boot on 2223, collect, compare, bug zoo
python scripts/arch_compare.py --a data/pilot --b data/real \
    --label-a "x86 pilot" --label-b "x86 overnight"       # the control
```

Open follow-ups, in order of value: (1) run on ARM hardware, which separates "aarch64" from "emulated"
and shows whether the tail budgets and the deadline budgets need machine-specific values at all; (2) more
than five runs per scenario, and a `tlgen` deadline budget picked on one batch and scored on another;
(3) overruns smaller than 700 µs, and a faster interrupt source (the radar needs a rate like x86's);
(4) decide, on data from a second batch, whether the lossy check needs a per-machine calibration.
