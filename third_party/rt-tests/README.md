# rt-tests on QNX 8.0 — a third-party real-time workload TraceLens did not write

This directory holds the **Linux real-time test suite `rt-tests`**, ported to QNX Neutrino 8.0 so
that TraceLens can be run end to end on code this project had no hand in writing. Nothing here is a
TraceLens workload: no planted bugs, no `TL_JOB_START`/`TL_META` markers, no changes to make
analysis easier.

Why this program: `rt-tests` is the standard suite for measuring real-time behaviour on Linux, and
`pi_stress` in particular builds the *classic priority-inversion* scenario on purpose — a low
priority thread holds a mutex, a medium priority thread preempts it, and a high priority thread
blocks on the mutex. That is exactly the shape TraceLens's priority-inversion rule looks for, and
it is ground truth written by someone else.

## Provenance

| | |
|---|---|
| Upstream | <https://git.kernel.org/pub/scm/utils/rt-tests/rt-tests.git> |
| Version | **v2.11**, commit `62da2befac98f811af8e56f2b7992fb09faa33d6` (2026-09-16) |
| Fetched | 2026-11-23, shallow clone |
| Licence | **GPL-2.0-or-later** — see [LICENSE](LICENSE) (upstream `COPYING`) |
| Authors | Clark Williams, John Kacur, Thomas Gleixner, Carsten Emde, Daniel Wagner and others |

[PROVENANCE](PROVENANCE) lists the sha256 of every file under `upstream/`. They are byte-for-byte
copies; re-run the hashes to check.

**Licence separation.** TraceLens itself is MIT. `upstream/` is GPL-2.0-or-later and stays a
*separate program*: TraceLens builds it with `qcc`, runs it, and reads the kernel trace it causes.
No upstream code is compiled into, linked with, or derived from any TraceLens source file. The
files under `qnx/` were written for this port and are MIT (each carries its SPDX line).

## The three programs

| Program | What it does | Why it is interesting here |
|---|---|---|
| `pi_stress` | Creates N "inversion groups" of three SCHED_FIFO threads (low/med/high) pinned to one CPU each, which drive the classic priority inversion over a `PTHREAD_PRIO_INHERIT` mutex, over and over. | A real priority-inversion generator written by someone else. |
| `ptsematest` | Pairs of SCHED_FIFO threads ping-pong on two mutexes on a fixed period, measuring wake-up latency. | Periodic RT threads plus lock hand-off. |
| `pmqtest` | The same, over POSIX message queues (`mq_send`/`mq_receive`). | On QNX, POSIX message queues sit on top of QNX message passing, so this exercises the IPC path. |

## Building

```sh
source ~/qnx800/qnxsdp-env.sh
make -C third_party/rt-tests          # -> third_party/rt-tests/out/{pi_stress,ptsematest,pmqtest}
make -C third_party/rt-tests ARCH=aarch64le
```

The [Makefile](Makefile) is ours; upstream's is Linux-only and is not used. Every file under
`upstream/` compiles **unmodified**: all QNX adaptation is force-included
(`qcc -include qnx/qnx_compat.h`) or found on the include path (`-Iqnx/include`) ahead of the
system headers. The build is clean apart from upstream's own `-Wall -Wextra` warnings.

## Every change this port makes

No upstream source file was edited. The port is three things: a Makefile, one compatibility
translation unit, and three shim headers that stand in for Linux headers QNX does not have.

### `qnx/qnx_compat.h` + `qnx/qnx_compat.c` (force-included)

| What | Why | How |
|---|---|---|
| `cpu_set_t`, `CPU_ZERO/SET/CLR/ISSET/COUNT/EQUAL/AND/OR` | QNX has no `cpu_set_t`; it uses a runmask of `unsigned` words with `RMSK_SET` from `<sys/neutrino.h>`. | One 64-bit word (so up to 64 CPUs). |
| `sched_setaffinity()` | Absent on QNX. | `ThreadCtl(_NTO_TCTL_RUNMASK_GET_AND_SET_INHERIT, ...)`, falling back to the older `_NTO_TCTL_RUNMASK` if that fails. Only `pid == 0` ("this thread") is supported, which is all rt-tests asks for. |
| `sched_getaffinity()` | Absent on QNX. | Returns the mask this port last applied to the calling thread, or every online CPU if none was ever applied. **This is tracked in the port, not read back from the kernel** — QNX has no read-only runmask query whose semantics we were willing to guess. |
| `pthread_attr_setaffinity_np()` | Absent on QNX, and QNX cannot carry a runmask in a `pthread_attr_t`. | The mask is parked in a 16-entry table keyed by the attr's address, and `pthread_create` is wrapped (`#define pthread_create qnxrt_pthread_create`) so the new thread applies it *itself* before the upstream start routine runs. |
| `SCHED_BATCH`, `SCHED_IDLE`, `SCHED_DEADLINE` | Linux policies rt-tests names in `switch` statements. QNX already uses 0–9, and upstream's `rt-sched.h` would otherwise make `SCHED_DEADLINE` collide with QNX's `SCHED_ADJTOTAIL` (both 6) — a duplicate `case` label will not compile. | Given values outside QNX's range (`0x7f01`–`0x7f03`). Consequence: `pi_stress --sched policy=batch\|idle\|deadline` parses and is then rejected by the kernel. Everything we run uses `SCHED_FIFO`. |
| `strdupa()` | glibc extension, used by `pi_stress` to parse `--sched`. | glibc's own definition, on QNX's `alloca`. |

### `qnx/include/` — headers QNX does not ship

| File | Why | Contents |
|---|---|---|
| `sys/syscall.h` | QNX has no Linux syscall table. | `SYS_gettid`/`__NR_gettid` and `__NR_getcpu` as local numbers, plus `#define syscall qnxrt_syscall`. `gettid()` returns `pthread_self()`, which *is* the QNX thread id and so matches what `tracelogger` reports. `__NR_getcpu` answers only when the thread is pinned to exactly one CPU, and `ENOSYS` otherwise. Every other number fails with `ENOSYS`, which is how `sched_setattr()`/`sched_getattr()` (used only on upstream's `SCHED_DEADLINE` path) come to be unavailable. |
| `linux/unistd.h` | Included by `ptsematest`/`pmqtest`. | Pulls in the two headers above. |
| `utmpx.h` | Included by `ptsematest`/`pmqtest` (on glibc it is where `sched_getcpu()` comes from). | Deliberately empty. |

### Port limitations, stated plainly

- **`sched_getaffinity()` reports what the port set, not what the kernel holds.** Good enough for
  rt-tests (`pi_stress`'s `verify_cpu()` only asks whether its CPU is in the mask) but it is not a
  general-purpose implementation.
- **`get_cpu()` is unavailable unless the thread is pinned.** `ptsematest`/`pmqtest` only use it to
  label output when run without `-a`; every run recorded here pins threads.
- **`SCHED_DEADLINE` does not exist on QNX**, so `pi_stress --sched policy=deadline` cannot work.
- **`ptsematest`'s own latency figures are degenerate on QNX** — it reports `Min -1 … Avg
  -2147483648`, because its `gettimeofday()` deltas land at or below the clock granularity and
  upstream's averaging then underflows. That is a property of the port and of `ptsematest`, **not
  a TraceLens measurement**; TraceLens reads the kernel trace, not the program's own numbers.
  `pmqtest`, which measures the same way over message queues, does produce sane numbers
  (min 0 µs, max ~436 µs).

## Verified on the target

QNX 8.0.0 (`2026/10/30`), QEMU x86_64, 4 CPUs, `procnto-smp-instr`, 2 GB RAM.

```
# pi_stress -v -D 2
INFO: Admin thread running on processor: 0
INFO: Test threads running on processors:  1-3
INFO: Creating 3 test groups
     Admin thread SCHED_FIFO priority 4
      High thread SCHED_FIFO priority 3
       Med thread SCHED_FIFO priority 2
       Low thread SCHED_FIFO priority 1
Total inversion performed: 839329
```

All nine worker threads passed upstream's own `verify_cpu()` check, so the affinity shim really
pins them. `ptsematest` and `pmqtest` both run and report cycles.

What TraceLens then found is written up in
[docs/results/third_party/README.md](../../docs/results/third_party/README.md).
