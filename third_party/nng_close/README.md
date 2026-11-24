# NNG's `nng_close()` deadlock on QNX 8.0: a famous bug in code TraceLens did not write

[NNG](https://github.com/nanomsg/nng) (nanomsg-next-gen, MIT) is a widely used messaging library. Its
`nng_close()` deadlock was reported in [#1543](https://github.com/nanomsg/nng/issues/1543) (2021, closed 2024),
came back as [#1813](https://github.com/nanomsg/nng/issues/1813), and was fixed by PR #1824 (merge `aac4dc36`,
2024-04-24, titled "macOS - fix deadlock on reqrep socket close"). Results:
[docs/results/nng_close/](../../docs/results/nng_close/README.md).

| | |
|---|---|
| Buggy build | NNG tag `v1.7.3` (the version #1813 names) |
| Fixed build | upstream commit `aac4dc360faca9ccece487ba16371d20d90e6406` |
| Built with | CMake and `qcc` for `x86_64` (`build_nng.sh`); `-DSA_RESTART=0` on the compile line, nothing in NNG edited |
| Not redistributed | NNG is cloned at build time into `deps/`, which is gitignored |

`nng_repro.c` is **our driver**, written from the reporter's description of #1813 (the linked gist is the unmodified
demo): a REQ socket dials a REP server over `ipc://`, sends a request, and just before `nng_recv()` a second thread
calls `nng_close()` on the same socket; repeated for 40 cycles. Two additions of ours: a 3 s wait so the server is up
first (the capture tool starts both together), and `TL_JOB_START/END` markers around each cycle plus a watchdog that
exits 3 after 6 s (the markers are what lets TraceLens measure a cycle at all).

`tracelens.toml` declares one job, `close_cycle`, with a 0.5 s budget (a healthy cycle takes about 12 ms here). The
budget was set after looking at one hang trace and before the 10-run comparison.
