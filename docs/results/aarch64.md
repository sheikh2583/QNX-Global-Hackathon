# Does TraceLens work on QNX 8.0 on aarch64?

Measured 2026-11-23 on the project machine (WSL2 Ubuntu 24.04, QNX SDP 8.0, host x86_64).

## Verdict

**Nothing tested is x86-specific in the code, and for the non-interrupt workloads the x86-trained radar
transfers. For the interrupt workloads it does not, and the interrupt rules need machine-specific
thresholds — with three limits that decide how far any of this goes.** On a QNX 8.0 `aarch64le` guest
(QEMU `virt`, cortex-a57, 4 CPUs):

- the workload suite cross-compiles for aarch64 with **no source change**;
- every rule that fires on x86 fires on aarch64, on the right workload, and the healthy programs stay
  clean — for the 13 non-interrupt scenarios (§3). The interrupt rules also fire on the planted overruns
  but, with x86's thresholds, on healthy handlers too (§6);
- the radar, **trained entirely on x86 traces**, flags **8 of 9** planted non-interrupt bugs on the thread
  that suffers with **0 false alarms** on 4 healthy traces (§5) — the same result as on x86 (8 of 10 on
  the pilot). On the interrupt scenarios it flags every trace, healthy or not (§6);
- the per-feature medians agree between architectures as well as two x86 collections agree with each
  other: **86.7%** of feature/thread pairs within 0.10, against **86.5%** for x86 against x86 (§5).

The limits:

1. **This is emulated aarch64, not ARM hardware.** An x86 host has no KVM for ARM, so QEMU interprets
   every instruction (TCG). Timing is emulated timing. The right claim is "the tool does not depend on
   x86"; it is *not* "the tool is validated on a Cortex-A part". That needs a board.
2. **One run per scenario** (the x86 numbers are 120 per scenario). The agreement figures above show
   nothing is badly broken; they do not show it is tight.
3. **The interrupt workloads are ported, and the result is mixed (§6).** They needed a different
   interrupt source (the virtio disk, not the serial port). With the x86 thresholds the rules false-alarm
   on healthy handlers; thresholds calibrated on six healthy traces then missed the planted overruns on a
   test batch (0 of 4); and the radar does not transfer on interrupt traces (8 of 8 healthy flagged). Only
   z5's large overrun (p99 3-4.6 ms) is detected cleanly (10/10, 0 false alarms).

A negative result worth stating as plainly: **11 of 13 captured traces were flagged lossy** by the
integrity check, against 0 of 16 on x86 (§4). That is a real cross-machine difference, and it is a
property of the check, not of the rules.

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

One capture per scenario (`tlgen`), `scripts/aarch64_pilot.sh`; 13 of 16 completed.

| Scenario | Rules that fired (HIGH+) on aarch64 | On x86 pilot |
|---|---|---|
| `sem_inversion`, `chan_inversion`, `condvar_inversion` | `priority_inversion` + `deadline_miss` | same |
| `ipc_deadlock` | `ipc_deadlock` | same |
| `lock_contention` | `mutex_contention` + `deadline_miss` | same |
| `cpu_starvation`, `mutex_abba`, `lost_wakeup`, `period_overrun` | none (no rule exists for these families) | same |
| `healthy_periodic`, `healthy_pi_mutex`, `healthy_ipc`, `healthy_mixed` | none | same |
| `healthy_irq`, `irq_overrun`, `healthy_irq_deferred` | on the virtio-disk interrupt (§6): `irq_overrun` fires `irq_handler_overrun` + `irq_latency`, **but so do the healthy ones** under the x86 thresholds | `irq_overrun`: `irq_handler_overrun` + `irq_latency`; healthy quiet |

The bug-zoo workloads (`tracelens eval detect --bin-dir bugzoo/out-aarch64le`, 5 runs per build, lossy
runs excluded, committed x86 budgets):

| Workload | Buggy build: detected | Reference fix: runs with findings | Verdict |
|---|---|---|---|
| z1 infusion pump | 4/4 | 0/4 | INCONCLUSIVE (only 4 clean fixed runs; the rule needs 5) |
| z2 brake-by-wire | 5/5 | 2/5 (`deadline_miss`) | NOT FIXED |
| z3 sensor fusion | 5/5 | 0/5 | VERIFIED |
| z4 camera pipeline | 5/5 | 1/5 (`deadline_miss`) | NOT FIXED |
| z5 motor encoder | 10/10 buggy flagged on the virtio-disk interrupt (§6) | 0/10 with aarch64 interrupt thresholds, 10/10 with x86's | not scored by the eval (all 20 runs lossy) |

x86 detected 10/10 on all five. The two NOT FIXED rows are a budget effect, not a detector failure
(§7). The three healthy shell programs (`pidin_loop`, `idle_system`, `shell_io`) produced **no usable
traces**: all 10 runs of each were lossy, so this run says nothing about false alarms on them.

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

Whether the rules should be trusted on a trace with a handful of such slips is a separate question this
data cannot settle: a slip distorts one interval, but the check cannot say which.

## 5. The radar and the features, against x86

`scripts/arch_compare.py` — `real_vs_sim.py`'s gap table pointed at two real collections. The
reference is the 120-runs-per-scenario x86 collection (`data/real`) every published number comes from.
aarch64 is one run per scenario, 13 scenarios with the planted problem showing (lossy included).

**Control first**, because a cross-architecture gap means nothing without knowing how far two x86 runs
already differ ([arch_control.md](arch_control.md): the x86 pilot, also 1 run per scenario, against the
same reference):

| Comparison | Pairs within 0.10 | Radar: bugs flagged on the right thread | False alarms |
|---|---|---|---|
| x86 pilot (1 run) vs x86 reference — the control | 238 of 275 (86.5%) | 8 of 10 | 0 of 6 healthy |
| **aarch64 (1 run) vs x86 reference** | **222 of 256 (86.7%)** | **8 of 9** | **0 of 4 healthy** |

Per scenario (radar, shipped `src/tracelens/ml/radar.json`, never saw aarch64):

| Scenario | Radar on aarch64 |
|---|---|
| `sem_inversion` | `hi` 97/101 windows |
| `chan_inversion` | `client` 100/101 |
| `condvar_inversion` | `hi` 100/101 |
| `ipc_deadlock` | `fusion_a` 57/107, `fusion_b` 51/104 |
| `lock_contention` | `w2` 82/101, `w4` 79/101, `w6` 72/101 |
| `mutex_abba` | `ba` 51/51, `ab` 51/51 |
| `lost_wakeup` | `consumer` 100/101 |
| `period_overrun` | `logger` 128/131 |
| `cpu_starvation` | **quiet** — the radar's documented blind spot on x86 too (a starved low-priority job looks like healthy deferred work; the deadline rule is what catches it) |
| the 4 healthy scenarios | quiet |

The widest per-feature gaps (full table in [aarch64_features.md](aarch64_features.md)) are on the
single-run `tlgen[1]` main thread of the healthy scenarios — `cpus_used` 3 vs 2, `share_sleep` 0.04 vs
0.56 on `healthy_pi_mutex` — and the **same threads show the same kind of gap in the x86 control**
(`cpus_used` 1.0, `share_sleep` 0.32 on `healthy_pi_mutex`). One run of one thread is noisy on either
architecture; no feature moves systematically. The one gap that is not just noise-shaped is
`cpu_starvation`'s `share_sleep` 0.30 vs 0.67 / `share_ready` 0.62 vs 0.30 — a single emulated run
against 120, and exactly the scenario the radar cannot see anyway.

Why the transfer is plausible (design argument, now with a measurement behind it): all 19 features are
shares, fractions, ranks, per-millisecond rates or counts; none carries an absolute time, a clock rate
or a pointer width, and the parser takes the clock from the trace header. `KERNEL_SPACE =
0xFFFF_8000_0000_0000` in `detectors/mutex_contention.py` is the one architecture-flavoured constant;
this data does not exercise it (no kernel-space mutex finding appeared), so its aarch64 comment stays
**(verify)**.

## 6. The interrupt workloads, ported — and what they show

`healthy_irq`, `irq_overrun`, `healthy_irq_deferred` and z5 attach with `InterruptAttachEvent(irq, …)`
and block in `InterruptWait`. On x86 the interrupt is COM1 (4), driven by flooding `/dev/ser1`. That does
not work on the QEMU `virt` machine, for two separate reasons (both measured with
[`bugzoo/gen/irqprobe.c`](../../bugzoo/gen/irqprobe.c), which attaches the same way but gives up each wait
after 250 ms, so it reports "0 interrupts" instead of hanging):

| Source tried | Interrupts seen by a second listener in 3 s |
|---|---|
| x86 default, interrupt 4, serial flood | the program waits forever on an interrupt nothing raises |
| UART, interrupt 33 (`devc-serpl011 -F 0x9000000,33`), with and without the flood | **0** |
| virtio-net, interrupt 78 (`io-sock`), traffic through the guest's own ssh | 134 (45/s) |
| **virtio-blk, interrupt 79 (`devb-virtio`), a guest write-and-sync loop** | **333 (111/s), steady** |

I did not establish why the PL011's interrupt never reaches a second attacher (it is owned by a driver
that attaches by pulse, and QEMU's PL011 may not raise TX interrupts the way a 16550 does); the answer
needs a look at the guest's interrupt controller. Interrupt 79 works, so the workloads were ported to it:
`tracelens data plan --irq 79 --irq-load '<disk loop>'` and `tracelens eval detect --irq 79 --irq-load
'<disk loop>'` (tested; x86 defaults unchanged), with the load
`while :; do dd if=/dev/zero of=/data/irqload bs=64k count=32; sync; done`.

**This is a different interrupt source, not just a different architecture.** 111 bursty disk interrupts
a second against x86's ~2,700 steady serial ones; any difference below mixes the two, and this
experiment cannot separate them.

### Rules, with the x86 thresholds

On the aarch64 guest a healthy handler doing 50 µs of work measures **p99 450–1,360 µs** wake-to-unmask and
**1.1–3.0 ms** interrupt-to-wake, against x86's p99 81 µs. The committed thresholds (500 µs handler, 1,000
µs latency) sit inside that, so they fire on healthy handlers: `irq_handler_overrun` on **4 of 8** healthy
`tlgen` traces in the test batch (5 of 6 in the first batch) and on **10 of 10** z5 reference-fix runs.
The planted overruns are flagged 4/4, 3/3 and 10/10: the rule fires, but cannot be trusted to be quiet.
(All of these traces are lossy by §4's check; results are reported regardless, as in §3.)

### Calibration, fixed before the test, and where it failed

`bugzoo/tracelens.aarch64.toml` raises the two interrupt thresholds by a rule written down **before** the
test batch was captured: 1.25 × the worst healthy per-trace p99 in a calibration batch (6 healthy
traces, seed 7), rounded up to 100 µs → handler **2,400 µs**, latency **3,700 µs**. Then a second batch
(seed 8; 4 traces of each scenario, different parameters) that played no part in choosing them:

| | Healthy flagged | Planted overrun flagged |
|---|---|---|
| calibration batch, x86 thresholds | 5/6 | 3/3 |
| calibration batch, aarch64 thresholds *(circular: chosen from these)* | 0/6 | 3/3 |
| **test batch, x86 thresholds** | **4/8** | **4/4** |
| **test batch, aarch64 thresholds** | **0/8** | **0/4** |
| z5 motor encoder (10 buggy + 10 reference), x86 thresholds | 10/10 | 10/10 |
| z5 motor encoder, aarch64 thresholds | 0/10 | 10/10 |

**The calibrated thresholds removed the false alarms and lost the planted bugs on the test batch.** The
four test-batch overruns do 1.0–1.9 ms of work and measure p99 1.6–2.4 ms; the calibration batch's worst
healthy trace (p99 1,881 µs) was an outlier that pushed the threshold above them. Six healthy traces are
too few to calibrate a tail on this machine. The honest reading: **on emulated aarch64 with this
interrupt source, a handler overrun is detectable when it is large against the jitter (z5's p99 3.1–4.6
ms: 10/10 at 2,400 µs with no false alarm) and not when it is 1–2 ms.** That is a noise floor of about
2.4 ms, against x86's 0.5 ms. A more jitter-robust statistic (the median handler time, which a systematic
overrun moves and a tail spike does not) would probably separate the cases; the rule does not use it
and I did not change it.

### The radar on interrupt traces

It flags the interrupt thread (`ist`) in **every** interrupt trace: 4 of 4 and 3 of 3 planted overruns, but
also **8 of 8** and **6 of 6** healthy ones (the deferred-work scenario's `worker` too). The overrun
traces do persist more (72/72, 88/88 windows against 51–66 of 57–72 for healthy), so a signal is there,
but the radar's threshold was calibrated on a different interrupt source. **The radar does not transfer on
interrupt traces**, which is the opposite of §5; the cause is the interrupt source, not established to be
the architecture.

### What this settles and what it does not

Settled: the interrupt workloads run on aarch64 with a working source; the x86 interrupt thresholds are
too tight for an emulated machine; a machine-specific threshold needs more than six healthy traces.
Not settled: how the interrupt rules behave on ARM hardware (where the jitter should be nearer x86's), or
with a faster interrupt source. Still open: why the UART's interrupt does not reach a second listener.

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

A separate config, [`bugzoo/tracelens.aarch64.toml`](../../bugzoo/tracelens.aarch64.toml), changes
**only** the three deadline budgets (3.5 / 3.5 / 6 ms: the worst reference response plus ~0.7 ms) and
says why in its header. Re-scoring the same saved traces with it:

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
  source is a parameter; the x86 serial flood stays the default); `bugzoo/gen/irqprobe.c`, which
  reports "0 interrupts" instead of hanging.
- `scripts/arch_compare.py` and `scripts/aarch64_pilot.sh` (the whole run, resumable).

## 9. Reproduce

```bash
# prerequisites: the two SDP packages in §1; qemu-system-aarch64 on PATH (Ubuntu: qemu-system-arm)
source ~/qnx800/qnxsdp-env.sh && source ~/.venvs/tracelens/bin/activate
scripts/aarch64_pilot.sh                       # build, boot on 2223, collect, compare, bug zoo
python scripts/arch_compare.py --a data/pilot --b data/real \
    --label-a "x86 pilot" --label-b "x86 overnight"       # the control
```

Open follow-ups, in order of value: (1) run on ARM hardware or a KVM ARM host, which separates "aarch64"
from "emulated"; (2) rerun the interrupt scenarios on hardware, or find why the UART's interrupt does not reach a second
listener and use the serial source as on x86; (3) calibrate interrupt thresholds from far more than six
healthy traces, and try a median-based handler statistic; (4) more than one run per scenario; (5) decide, on
data from a second batch, whether the lossy check needs a per-machine calibration.
