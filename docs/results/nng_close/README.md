# NNG's famous `nng_close()` deadlock, measured on QNX 8.0

**The first cold test of TraceLens on a famous project's hard bug.** [NNG](https://github.com/nanomsg/nng)'s
`nng_close()` deadlock ([#1543](https://github.com/nanomsg/nng/issues/1543), reopened as
[#1813](https://github.com/nanomsg/nng/issues/1813)) took three years to close. Port, provenance and our driver:
[third_party/nng_close/](../../../third_party/nng_close/README.md).

## What happened

| Step | Result |
|---|---|
| Build NNG `v1.7.3` for QNX 8.0 and run the reporter's scenario | the hang reproduces on QNX, 10 of 10 runs |
| TraceLens as it was (rules and radar) | **found nothing** (0 findings). The memcached `lost_wakeup` rule does not apply: there is no earlier signal that woke nobody. The radar raised 3 vague MEDIUM findings with wrong closest-pattern labels (priority inversion, deadlock between processes) |
| New rule `stuck_job` (written after this first failure) | a job that started and never finished, with a snapshot of what every thread of the process was blocked on |
| `stuck_job` on the runs | **10 of 10 buggy runs flagged, 0 of 10 fixed runs flagged** ([runs/](runs/)) |
| `tracelens compare`, buggy `v1.7.3` against upstream's fix `aac4dc36` | **VERIFIED**: `stuck_job` in 100% of runs before, 0% after, no new finding kind, `close_cycle` p99 13.2 to 11.9 ms ([compare.json](compare.json)); 3 of the 10 fixed runs were lossy and skipped, 7 counted |
| The learned radar | **flagged all 20 runs, hung or not**: no signal here |

Exit codes agree with the kernel-trace verdict: the driver's watchdog exited 3 on 10 of 10 buggy runs and 0 of 10 fixed.

## What TraceLens did not do

**It did not write the fix.** The fix that was verified is upstream's, merged in 2024 (a missing cancel function in the
aio shutdown path); TraceLens has no rule that could write it. The new `stuck_job` finding lists what each thread was
blocked on, which is the evidence a developer would want, but turning it into a patch is a design decision. This is a
detect-and-verify result, not a fix result. The fix results are on [memcached](../memcached_logger/README.md) and
the [NTNU exercise](../third_party_fix/README.md).

## Limits

- **The driver is ours**, written from the reporter's description (the linked gist is the unmodified demo), and the
  job markers it emits are what lets TraceLens measure a cycle. Code without markers would need the same.
- **The rule was written after seeing this bug's first trace** and the 0.5 s budget was chosen after looking at one hang
  trace, before the 10-run comparison. This is one verified case, not a measured detection rate.
- **The trace window is short**: this workload produces about 22 MB/s of kernel events and the target disk holds
  about 58 MB, so a capture covers roughly 2.6 s of cycling. Three of the fixed runs were lossy and were discarded by
  the tool.
- x86_64 only.

## An observation we did not chase

In a first batch of captures the client started before the server was up (so the first `nng_close()` ran against a
socket still dialing). There the **upstream-fixed commit also hung in 2 of 7 runs**, with the same all-threads-waiting
shape, while `v1.7.3` hung in 8 of 8. We changed the driver to wait for the server, as in the report, and did not
investigate further. It may be a different, separate bug, or a gap in the fix; we have not claimed either.
