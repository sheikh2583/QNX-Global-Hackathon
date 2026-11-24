# memcached on QNX 8.0: a real bug in code TraceLens did not write

memcached 1.6.45, unedited, compiled for QNX 8.0 two ways: just the logger thread driven through its public API
(`harness.c`), and the **whole daemon** (`daemon_repro.c`, built by `build_daemon.sh`). The bug
is [memcached/memcached#1348](https://github.com/memcached/memcached/issues/1348), an open lost wake-up that
hangs graceful shutdown. Results: [docs/results/memcached_logger/](../../docs/results/memcached_logger/README.md).

## Provenance

| | |
|---|---|
| Upstream | <https://github.com/memcached/memcached> (BSD-3-Clause) |
| Commit | `2d51e364799bc9698bd4b11728ea978cea12da6e` (tag 1.6.45), the commit the issue names |
| Files used, unedited | `logger.c`, `bipbuffer.c`, `globals.c`, `util.c` |
| Fetched | 2026-11-25 with `./fetch.sh`, which copies them into `work/` (gitignored: not redistributed) |

## What the bug is (upstream's own analysis, confirmed in the source above)

`logger_thread()` loops `while (do_run_logger_thread)`. Inside, after `usleep()` (up to 1 s once idle), it takes
`logger_stack_lock` and, `if (watcher_count == 0)`, calls `pthread_cond_wait()` **without looking at
`do_run_logger_thread` again**. `stop_logger_thread()` sets the flag to 0 and signals, but a signal only wakes a
thread that is already waiting. If the stop lands while the logger is still in that last `usleep()`, the signal
is lost, the logger then waits forever and `pthread_join()` never returns.

## Every change this port makes

No upstream line is edited. Four files are ours:

| File | What | Why |
|---|---|---|
| `harness.c` | `main()`: starts the logger, adds one watcher through `logger_add_watcher()`, lets it idle, disconnects it, waits until the logger has reaped it (`watcher_count == 0`), waits 0.3 s, calls `logger_stop()`. Also defines `STATS_LOCK/UNLOCK`, `thread_setname`, `sidethread_conn_close`, which live in `thread.c` / `memcached.c` in the daemon | the issue's reproducer, minus the network daemon |
| `qnx/include/config.h` | a hand-written stand-in for the autoconf-generated header | no configure run here |
| `qnx/include/event.h` | types only, no libevent code | `memcached.h` names libevent types; `logger.c` never calls libevent |
| `tracelens.toml` | `[build]` flags (`-DHAVE_CONFIG_H`, `-lsocket`) and one deadline: `logger_stop` within 1 s | nothing else is tuned |

`--healthy` is the control: no watcher, so the logger is parked in `pthread_cond_wait()` when the stop arrives,
which is the normal path.

## The whole daemon

`build_daemon.sh` builds libevent 2.1.12-stable (commit `5df3037d`, BSD-3) and memcached's 26 own `.c` files for
QNX 8.0 x86_64, then links them with `daemon_repro.c`. memcached's `main()` is renamed with `-Dmain=memcached_main`
so the driver can run it in a thread; the driver then does the issue's steps (connect, `watch`, idle, disconnect,
SIGUSR1) and exits 3 if the daemon is still running 6 s later. Changes needed to build on QNX, all outside upstream's
files: `-DSA_RESTART=0` (QNX has no `SA_RESTART`; both libevent and memcached use it only to restart interrupted
calls), `qnx/daemon/sysexits.h` (QNX does not ship it, standard BSD values), `qnx/daemon/limits.h` (QNX's own
`limits.h` undefines `IOV_MAX`; this defines it as 16, the POSIX minimum), and `qnx/daemon/config.h`, the output of
memcached's own `configure` for `x86_64-pc-nto-qnx8.0.0` with `--disable-extstore --disable-tls --disable-sasl
--disable-proxy --disable-docs` (so no TLS, SASL, external storage or proxy). `tracelens.daemon.toml` carries the build
flags and one deadline, `graceful_shutdown`.

## Limits, stated plainly

- The daemon build has TLS, SASL, extstore and the proxy turned off, and the driver stops it with SIGUSR1 from
  inside the same process, not from another one.
- The reproduction is deterministic because the driver waits for `watcher_count == 0` and then 0.3 s, which is
  the timing the reporter achieved by hand.
- x86_64 only (verify on aarch64).
