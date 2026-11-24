# NTNU TTK4147 priority-inversion exercise on QNX 8.0: a program TraceLens did not write

A teaching program from the NTNU course TTK4147 *Real-time Systems*, ported to QNX 8.0 through a
compatibility layer so that `tracelens fix` can be run on code this project had no hand in. Results:
[docs/results/third_party_fix/README.md](../../docs/results/third_party_fix/README.md).

## Provenance

| | |
|---|---|
| Upstream | <https://github.com/TTK4147/ttk4147-2026-exercise-4-concurrency> (GitHub org `TTK4147`, "course TTK4147 - Real-time Systems given at NTNU") |
| File | `UnboundedPriorityInversion.c` (4,490 bytes) |
| Commit | `8b4ba232abd89988ff9ec38ec17e4f0749696d85` ("Initial commit", 2026-09-17), the only commit |
| sha256 | `49a59a88ac51eb3608a8caa7e2a28e3cf7b5d8f64b5a2ce5eeaefa03352e8abd` |
| Licence | **none**: the repository has no licence file and no licence in the GitHub metadata |
| Fetched | 2026-11-24 |

**Because upstream states no licence, the file is not redistributed here.** `./fetch.sh` downloads it
from the pinned commit, checks the sha256 and writes it to `ttk4147_inversion/`, which `.gitignore`
keeps out of version control. The files in `qnx/` and the configs are ours (MIT). The evidence bundle in
`docs/results/third_party_fix/` contains a unified diff of the fix, which quotes a few upstream lines as
context; whoever commits it should decide whether that is acceptable without a licence.

## What the upstream program is, and where its bug is documented

Three `SCHED_RR` threads (priorities 1, 2, 3) pinned to one CPU. A global **`sem_t sem`**, initialised
to 1 and used as a lock, guards a critical section. Low takes it first and works inside it; medium
wakes and burns CPU without ever touching it; high wakes later and waits for it. Upstream documents
the problem itself, three times:

- the course README (task D) tells students to run it and verify the symptoms of unbounded priority
  inversion, and its text says mutexes, unlike semaphores, have priority inheritance built in (task E:
  replace the semaphore with a priority-inheriting mutex);
- `main()` contains a `TODO set up priority inheritance` block with the pseudo-code of that fix;
- the file name is `UnboundedPriorityInversion.c`.

So the bug is not ours and not planted by us: it is the *subject* of a published exercise, which is also
why this is a teaching program and not production code, and the fix `tracelens fix` writes is the
exercise's own task E answer. Nothing was added to or removed from upstream's logic.

## Every change this port makes

**No upstream source line is edited.** The upstream file is compiled as published; all adaptation is
three headers on the include path, found ahead of the system ones (`#include_next`):

| File | What | Why |
|---|---|---|
| `qnx/include/sched.h` | QNX `<sched.h>` plus `qnxrt_compat.h` | upstream uses Linux `cpu_set_t` |
| `qnx/include/pthread.h` | QNX `<pthread.h>` plus `pthread_setaffinity_np()` and a wrapper for `pthread_create()` | QNX has no `pthread_setaffinity_np`; the wrapper adds job markers (below) |
| `qnx/include/qnxrt_compat.h` | `cpu_set_t`, `CPU_ZERO/CPU_SET/...`; affinity through `ThreadCtl(_NTO_TCTL_RUNMASK)`; **assembler macros `isb` and `mrs`** | upstream's `busy_wait_ms()` runs `isb; mrs %0, cntvct_el0` inline: the aarch64 virtual counter of the Raspberry Pi the upstream comment names (54 MHz). On x86_64 the macros make that text assemble: `isb` is empty, `mrs` reads the TSC scaled to 54 MHz. Measured on the target: `busy_wait_ms(100)` takes 100.10 ms, three times. |

**Job markers (instrumentation we added, not upstream behaviour).** Upstream emits no TraceLens markers,
so the `pthread_create()` wrapper makes each thread report its whole run as one job named after its
priority (`TL_JOB_START/END name=task_p<prio>`) and names the thread. That gives the deadline check
something to measure; it changes nothing the program does, but it is a tracing call at thread entry and
exit. Without it the verdict would rest on finding kinds alone.

Port limitations, stated plainly:
- **x86_64 only** (the counter emulation is `rdtsc`); the aarch64 build was not tried (verify).
- The `mrs` macro saves and restores `rax`, `rdx`, `rcx` and skips the red zone; it was exercised only
  through this one program with the SDP 8.0 qcc and is not a general aarch64-to-x86 translation.
- `pthread_setaffinity_np()` works only for the calling thread, which is all upstream asks of it, and
  QNX 8.0 only accepts a single CPU or all CPUs as a runmask (measured earlier in this project).
- Upstream's `printf` calls (`print_pri`) go to the capture's stdout and add real, unmeasured jitter.

## Files

| File | |
|---|---|
| `fetch.sh` | download + verify the upstream file |
| `Makefile` | builds `out/ttk4147_inversion` with the same `qcc` line `tracelens fix` uses |
| `qnx/include/*.h` | the compatibility layer above |
| `tracelens.toml` | the config the verdict uses: **no threshold changed**; one deadline, `task_p3` (the high thread), budget 1.2 s |
| `tracelens.bound.toml` | the same deadline with budget 0.8 s, used only to re-read the confirmation traces |

## Run it

```sh
source ~/.venvs/tracelens/bin/activate && source ~/qnx800/qnxsdp-env.sh
export TRACELENS_TARGET=127.0.0.1:2222
third_party/ttk4147_pi/fetch.sh
tracelens fix third_party/ttk4147_pi/ttk4147_inversion \
    --include third_party/ttk4147_pi/qnx/include \
    -c third_party/ttk4147_pi/tracelens.toml --runs 10 --seconds 4 --out /tmp/fix_ttk4147
```
