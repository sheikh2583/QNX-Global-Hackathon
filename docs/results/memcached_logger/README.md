# A real bug in memcached, found and fixed on QNX 8.0

> **Read this first: this is a case study, not a blind test.** The `lost_wakeup` rule and the `recheck-before-wait` fix
> rule were written *after* studying this exact bug (its issue, its source and its first trace), and the fix rule matches
> this code's shape. The runs and the verdict are real, and the pipeline (record, name, patch, rebuild, re-record,
> statistical verdict) did work on a real project. What it does not show is that TraceLens finds bugs it has not seen.
> The blind test is NNG ([../nng_close/](../nng_close/README.md)): there the system missed the bug at first.

**memcached 1.6.45, the real daemon with its own sources unedited. TraceLens named the hang from the kernel trace,
wrote the fix, and the fix was verified on the QNX target: hung in 10 of 10 runs before, 0 of 10 after (one lossy
run skipped, as the verdict says). The same result on the logger thread alone, twice.** The bug is
[memcached/memcached#1348](https://github.com/memcached/memcached/issues/1348), still open upstream when this was
run. Port, provenance and every line we added: [third_party/memcached_logger/](../../../third_party/memcached_logger/README.md).

## What the bug is

`stop_logger_thread()` sets the run flag and signals a condition variable. A signal only wakes a thread that is
already waiting. If it lands while the logger thread is still in its last `usleep()`, nobody is waiting and the
signal is lost. The logger then reaches `pthread_cond_wait()` without looking at the flag again, sleeps forever,
and `pthread_join()` never returns: a graceful shutdown hangs.

## Two experiments, same bug, same fix

| | Whole daemon ([daemon/](daemon/)) | Logger thread alone ([confirmation/](confirmation/)) |
|---|---|---|
| What runs | memcached's 26 `.c` files plus libevent, built for QNX 8.0; the driver connects, sends `watch`, disconnects, sends SIGUSR1 | `logger.c` and 3 helper files, driven through `logger_init` / `logger_add_watcher` / `logger_stop` |
| Rules | `lost_wakeup` HIGH on the hang, none on the healthy shutdown | same |
| Fix | the same one line, automatic | the same one line, automatic |
| Verdict | **VERIFIED**, 10/10 hung before, 0/10 after, 1 lossy run skipped | **VERIFIED**, 10/10 before, 0/10 after, run twice |

## What TraceLens did (logger-only run, in detail)

| Step | Result |
|---|---|
| Record on QNX 8.0 (x86_64, QEMU, 4 CPUs) | the driver exits with the hang watchdog (code 3); the kernel trace has 55,953 events |
| **Rules** (new `lost_wakeup` detector) | **HIGH**: `mc-log` waits on a signal that already came. The signaller signalled condition variable `0x51cd514018` at 9669.54 ms when nobody was waiting, then joined `mc-log`; `mc-log` began its wait 696.53 ms later and was still blocked 3630.78 ms on, with no further signal |
| Same rules on the healthy control | 0 findings |
| **Fix** (new `recheck-before-wait` rule, automatic) | one line, below |
| **Verdict**, 10 runs before and 10 after | **VERIFIED**: `lost_wakeup` in 10/10 runs before, 0/10 after, no new finding kinds. Run twice: a development run and an independent confirmation, same result |

```diff
-        if (watcher_count == 0) {
+        if ((watcher_count == 0) && do_run_logger_thread) {
```

Files: [confirmation/SUMMARY.md](confirmation/SUMMARY.md), [confirmation/verdict.json](confirmation/verdict.json),
[confirmation/patch.diff](confirmation/patch.diff), [confirmation/events.jsonl](confirmation/events.jsonl),
[confirmation/report.html](confirmation/report.html). The raw traces (about 180 MB) are not in git.

After the fix `logger_stop()` returned in 694 to 696 ms in the measured runs: the logger finishes the sleep it was
already in, sees the flag, and leaves the loop. Bounded, where the unfixed program was not.

## The learned radar on this code: an honest negative result

The radar was run on both traces ([radar/](radar/), and [daemon/radar/](daemon/radar/) for the daemon). On the logger
it raised a MEDIUM "unusual behaviour" finding on `mc-log` in the **hang** trace, and **the same finding on the
healthy control**, where the logger is correctly parked on a condition variable with nothing to do. On the whole
daemon it raised three such findings on the hang and three on the healthy shutdown. So on this program the radar could not tell the hang from normal parking,
and its closest-pattern label (priority inversion while waiting on a condition variable) was wrong. It is a second
opinion, and here it was not a useful one. What named the bug was a deterministic rule, written after seeing what
the kernel events of this hang look like (the signal with no waiter, then a join on the stuck thread).

## Limits

- **The daemon build is reduced**: TLS, SASL, external storage and the proxy are turned off; libevent 2.1.12 was
  built for QNX with `SA_RESTART` defined as 0 (QNX has none) and `IOV_MAX` as 16, the POSIX minimum. The driver sends
  SIGUSR1 from inside the same process and runs memcached's `main()` in a thread, so this is not a deployment test
  of the daemon. One run in the daemon loop was lossy and was discarded by the tool; the verdict records it.
- The logger-only driver reproduces the issue's timing by waiting for the last watcher to be reaped, then 0.3 s.
- **The new rule is narrow on purpose.** It reports only a signal that woke nobody, followed by a wait that is still
  blocked at the end of the trace, **and** another thread joined on the waiter. Without the join the same pattern
  is an idle worker, which is normal. A lost wake-up that ends in a timeout, or that nobody joins, is not caught
  by it (the radar catches 120 of 120 of the generator's `lost_wakeup` traces, but is not a diagnosis).
- **The fix rule is narrow too.** It handles `while (run) { lock; if (idle) cond_wait; }` with a stopper that sets
  `run` and signals under the same mutex. It checks that shape in the source and refuses (guidance only) when the
  stopper does not hold the lock.
- The rule and the fix were written after seeing this bug, so this is one verified case, not a measured detection
  rate. x86_64 only (verify on aarch64). Not sent upstream.
