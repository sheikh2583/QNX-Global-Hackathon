# TraceLens finds, fixes and proves a priority inversion in code it did not write

**Question a judge will ask.** Earlier results were on workloads this project wrote (the bug zoo) or on
programs with nothing wrong (`rt-tests`: 0 findings, [docs/results/third_party/](../third_party/README.md)).
Can TraceLens detect a real bug in someone else's code, fix it, and prove the fix on the QNX kernel?

**Answer, in short.** On `UnboundedPriorityInversion.c`, a teaching program from NTNU's course TTK4147
that we did not write and did not edit (only a header-level port layer, section 2), built with `qcc` and
run on QNX 8.0.0 in QEMU:

- `tracelens` reported a **CRITICAL priority inversion** ("`task_p3` waited on `task_p1` via a semaphore") in
  **10 of 10** captures, then `tracelens fix` applied its **automatic** `semaphore-as-lock` remedy
  (semaphore to priority-inheriting mutex) in **one round**, and the patched build was **VERIFIED**: the
  inversion was gone in **10 of 10** captures, no new finding kind appeared, and the high-priority
  thread's job time fell from p99 **1,103 ms to 702 ms** (typical run 1,003 ms to 602 ms), Mann-Whitney
  one-sided **p = 5.4e-06** (exact test, 10 against 10 runs).
- A development run with the same configuration gave the same verdict (5 + 5 runs, p = 0.004). The
  confirmation above is a separate, fresh run with the configuration frozen beforehand.

This is **not** a claim about production code: the program is a teaching exercise whose purpose is to
show this inversion, and the fix is the exercise's own intended answer. What it settles is narrower and
real: the detector and the fix engine, unchanged, work end to end on code that was not shaped around
them. Section 5 lists what it does not show.

## 1. The program, and why the bug is not ours

Provenance, licence status and every port change: [third_party/ttk4147_pi/README.md](../../../third_party/ttk4147_pi/README.md).

- Upstream: <https://github.com/TTK4147/ttk4147-2026-exercise-4-concurrency>, file
  `UnboundedPriorityInversion.c`, commit `8b4ba232abd89988ff9ec38ec17e4f0749696d85`, sha256
  `49a59a88...e8abd`.
- **Licence: none stated. The file is therefore not copied into this repository**; `fetch.sh`
  downloads it and checks the hash (decision for the main session, section 6).
- Three `SCHED_RR` threads, priorities 1 / 2 / 3, one CPU. A global `sem_t`, initial value 1, used as a lock.
  The bug is documented upstream: the course README asks students to run it and verify the symptoms of
  unbounded priority inversion, says mutexes (unlike semaphores) have priority inheritance, and asks them to
  replace the semaphore with such a mutex; `main()` carries a `TODO set up priority inheritance` block.

Why it is not circular: the program was written for Linux on a Raspberry Pi by course staff. What we wrote
is the layer that lets it compile and run on QNX x86_64, plus the job markers (below).

## 2. What we added, in one paragraph

No upstream line is edited. Three headers on the include path (`sched.h`, `pthread.h`, `qnxrt_compat.h`)
give QNX the Linux `cpu_set_t` and `pthread_setaffinity_np` it lacks, make upstream's inline aarch64
`isb; mrs ..., cntvct_el0` assemble on x86_64 (assembler macros reading the TSC scaled to 54 MHz;
`busy_wait_ms(100)` measured at 100.10 ms), and wrap `pthread_create()` so that each thread reports its run
as one TraceLens job (`TL_JOB_START/END name=task_p<prio>`). **Upstream emits no markers; these are ours,**
and the deadline part of the verdict depends on them (section 4).

## 3. Exact commands

```bash
source ~/.venvs/tracelens/bin/activate && source ~/qnx800/qnxsdp-env.sh
export TRACELENS_TARGET=127.0.0.1:2222          # QNX 8.0.0, 4 CPUs, procnto-smp-instr, own VM
third_party/ttk4147_pi/fetch.sh
tracelens fix third_party/ttk4147_pi/ttk4147_inversion \
    --include third_party/ttk4147_pi/qnx/include \
    -c third_party/ttk4147_pi/tracelens.toml --runs 10 --seconds 4 \
    --out docs/results/third_party_fix/confirmation          # confirmation run, 2026-11-24 16:44-16:45 UTC
# afterwards, on the saved traces:
tracelens compare --before before-*.txt --after after-*.txt -c third_party/ttk4147_pi/tracelens.toml         # primary
tracelens compare --before ... --after ...               -c third_party/ttk4147_pi/tracelens.bound.toml      # 0.8 s budget
tracelens compare (first 5 against last 5 of one side)   # noise floor, twice
tracelens analyze <trace> --radar --json <trace>.json    # all 20 traces
tracelens remedy <trace> --source third_party/ttk4147_pi/ttk4147_inversion -c third_party/ttk4147_pi/tracelens.toml
```

Configuration frozen before the confirmation run (sha256 of `tracelens.toml` `44ee77b6...`, shims
`aab1659a...` / `d4f180c3...` / `f0911db6...`, unchanged afterwards). **No detector, fix rule or threshold was
changed or tuned**: `tracelens.toml` sets no threshold, only the deadline. `src/tracelens/` was not edited.
Built binaries: [`binaries.sha256`](binaries.sha256).

## 4. Results

**Every run made** (all captures clean, none lossy, none discarded):

| Run | Captures | Result |
|---|---|---|
| Smoke (one capture of the unfixed build, to check the port) | 1 | CRITICAL inversion found. This cold first execution ran the high thread's job in 2,431 ms (later runs about 1,003 ms); not investigated, probably first-run page-in (unverified). |
| Development run (summary in [`development_run/`](development_run/)) | 5 + 5 | **VERIFIED**, 1 round, inversion 100% to 0%, p99 1,003 to 603 ms, p = 0.004 |
| **Confirmation** ([`confirmation/`](confirmation/)) | **10 + 10** | **VERIFIED**, 1 round, inversion 100% to 0%, p99 1,103 to 702 ms, p = 5.4e-06 |

**Confirmation, run by run** (high-priority thread's job, ms; from `confirmation/events.jsonl`):

| | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| before (semaphore) | 1003.7 | 1003.5 | 1103.0 | 1002.3 | 1003.0 | 1002.1 | 1004.3 | 1002.4 | 1002.1 | 1002.5 |
| after (PI mutex) | 601.9 | 604.0 | 602.7 | 602.1 | 602.3 | 601.7 | 602.1 | 702.0 | 601.4 | 602.2 |

Each side has one run about 100 ms slower than the rest (before run 2, after run 7); cause not
investigated. The p99 over ten runs is therefore that outlier, which is why the typical value is given too.

**The patch** ([`confirmation/patch.diff`](confirmation/patch.diff), 87 lines): `sem_t sem` becomes
`pthread_mutex_t sem` initialised with `PTHREAD_PRIO_INHERIT` through a small helper; the two
`sem_wait/sem_post` pairs become `pthread_mutex_lock/unlock`; `sem_init/destroy` become the helper and
`pthread_mutex_destroy`. The engine pointed at the four lock and unlock lines (118, 125, 161, 170) and chose
this rule on its own. It is what the exercise's task E asks a student to write.

**Re-reading the same traces** ([`compare/`](compare/)):

| Check | Result |
|---|---|
| Primary config, budget 1.2 s, 10 v 10 | VERIFIED. The deadline is not missed on either side (before p99 1,103 ms is inside 1.2 s), so the decisive evidence is the finding kind going from 100% to 0% plus the significant speed-up, p = 5.4e-06. |
| Strict budget 0.8 s ([`tracelens.bound.toml`](../../../third_party/ttk4147_pi/tracelens.bound.toml)), 10 v 10 | VERIFIED: before misses **10 of 10**, after **0 of 10**, p = 5.4e-06. Declared before the run, from the program's own constants; evaluated only here. |
| Noise floor, first 5 against last 5 *before* runs (same build) | NOT FIXED (inversion still present; speed-up p = 0.11, not significant): the tool does not claim an improvement between two batches of the unfixed build. |
| Noise floor, first 5 against last 5 *after* runs | INCONCLUSIVE, "nothing to verify"; p = 0.21. |

**Where the deadline numbers come from.** Upstream's own constants give, with inheritance, a job of
about 0.8 s: start-up barrier about 0.1 s, the high thread's sleep 0.2 s, at most 0.3 s of the low
thread's critical section, its own 0.2 s of work. The primary budget is that plus 50% (1.2 s); the strict
reading uses 0.8 s. Both were written down before the development run. The measured fixed job (0.60 s)
is under the bound, so the bound is conservative, not tight. Both budgets are analyst choices; the
finding-kind criterion needs none.

**Other TraceLens output.** The learned radar printed MEDIUM "unusual behaviour" notes on the program's
threads in **every** run, before and after (3 per run), as it does on the other lock hand-off programs
([`json/`](json/)). It cannot fail a gate and is not evidence about this fix. The offline
`tracelens remedy` on one trace gives the same remedy ([`remedy_output.txt`](remedy_output.txt)).

**Timing.** The whole confirmation (build, 10 before captures, patch, build, 10 after captures, verdict)
took about 1 min 45 s wall-clock. One measurement, not a benchmark.

## 5. What this does and does not show

- **Does show:** the unmodified detector and fix engine, never run on this program before, find and
  repair the textbook semaphore-as-lock inversion in third-party source and prove it on QNX with a
  statistical test, in two independent runs; and the noise-floor controls behave.
- **Does not show a bug found in the wild.** The inversion is the declared subject of a course exercise.
  The program is one small file, easy to analyse, and its bug has exactly the shape one of our five rules
  was built for. A judge may fairly call that favourable. We did not search for a harder case after this
  one succeeded, and the earlier candidate search turned up no production code with this shape.
- **The deadline half of the verdict rests on markers we added** (section 2). The finding-kind half
  (inversion gone in 10 of 10, nothing new) does not: detection used the kernel trace alone, and the
  finding names the right threads and the semaphore.
- **The port layer is ours**, and the `mrs` assembler macro is a hack that only this program has
  exercised; x86_64 only, aarch64 not tried (verify). Thread pinning goes through our `ThreadCtl` code.
- **Licence:** upstream has none, so the source is fetched, not shipped.
- **One program, one VM, one day.** 31 captures in total, all clean. The 100 ms outliers and the 2.4 s
  smoke run are unexplained.
- **The rt-tests "0 findings" result is unchanged:** that was a clean negative on correct code; this is a
  positive on a program with a known defect.
- **Out of reach of the engine:** `PTHREAD_PRIO_NONE` mutexes. Other open-source inversion demos found
  while searching (for example `Pradeepcbk/QNX-Priority-Inversion`, `automatica-cluj/rt-labs-linux`,
  `Halo201417/MarsPathfinder`) put the inversion on a *mutex* with inheritance off or left at the default,
  which none of the five rules rewrites; the engine would say GUIDED or nothing, as for the earlier
  `busy_medium` mutex control. Not run here.

## 6. Decisions for the main session

1. Licence: upstream has none. Keep "fetch, do not ship", or ask NTNU before quoting more of it. The diff in
   `confirmation/patch.diff` carries upstream lines as context.
2. Wording: "a program we did not write" is accurate; so is "a teaching exercise". The README leads with
   both.
3. The evidence bundle is trimmed: traces gzipped under [`traces/`](traces/) (20 files), `.kev` files and
   the engine's copies of the upstream source removed.
