# Benchmark rubric (R3, written 2026-11-25, before any blind run)

Frozen with the tool: a change to this file after `research-freeze-1` is an appended, dated amendment, never an edit.
One row per bug in `docs/research/bench_blind.md`. Misses, false positives and non-reproductions are rows, not omissions.

## Bug inclusion (from `bench/manifest.toml` header, repeated so the rubric stands alone)

C or C++ using threads, semaphores, condition variables, message queues, timers or QNX APIs; builds with `qcc` for QNX 8.0
through headers and shims only, with **no edits to upstream lines**; the bug is scheduling-observable (hang, deadlock,
priority inversion, lost wake-up, starvation, deadline or latency regression, interrupt overrun); ground truth exists (an
upstream issue or commit, ideally the developer fix); the licence allows redistribution or the file is fetched by hash.
Re-injections (reverting a developer fix on current code) are a separate labelled category and never counted as found bugs.

## Procedure per bug

1. Write the driver. It must show the symptom by its own exit code (hang watchdog, missed-deadline counter, latency
   histogram), independent of TraceLens. The driver may be written by someone who has read the bug; the tool is frozen first.
2. 10 captures of the buggy build and 10 of the upstream-fixed build, host idle, load logged. Lossy captures are replaced and
   counted. A bug whose driver cannot show the symptom within 10 + 10 attempts per cycle budget is **excluded** with the
   reason, not dropped.
3. `tracelens analyze` (with and without `--radar`) on every capture, then `tracelens fix --runs 10` on the buggy build.

## Columns

| Code | Question | Pass condition |
|---|---|---|
| S0 | Did the driver's own symptom appear on the buggy build and not on the fixed one? | Symptom in >=1 of 10 buggy captures and 0 of 10 fixed (else the bug is excluded) |
| D1 | Any finding of severity high or above on the buggy build? | In at least half of the clean buggy captures |
| D2 | Correct class? | The finding's kind equals the class in the upstream report, judged against the issue text, by the rater, before reading TraceLens's remedy |
| D3 | Correct threads and objects named? | The finding's cited threads or sync object match the upstream explanation |
| F0 | False positive on the upstream-fixed build? | Any finding of severity high or above in any clean fixed capture counts as a false positive (lower is better) |
| R1 | Remedy | `auto` (a patch was produced), `guidance` (text only), or `none` |
| R2 | Patch compiles with `qcc` | yes/no (only when R1 is `auto`) |
| R3 | Oracle verdict | VERIFIED, NOT FIXED or INCONCLUSIVE, with n before and after and the residual bound |
| R4 | The driver's own symptom is gone after the patch | 0 of 10 patched captures show it, and the driver's exit code is the evidence |
| R5 | Patch semantically equivalent to the developer fix | The agent proposes a judgement, the **user** confirms; record disagreements. `not applicable` if no developer fix exists |
| RA | Radar | flagged buggy yes/no; flagged fixed yes/no |

D1 is judged on the *detection* only; a high finding of the wrong class scores D1 yes, D2 no, and says so.

## Reporting

- Per-column rate with an exact (Clopper-Pearson) interval, **denominator = bugs that reproduced**; also the count excluded.
- Misses and false positives are listed by name with the reason.
- Case studies (worked on before the freeze) are shown in a separate table, never pooled with the blind rows.
- Post-hoc rules (written after seeing a miss) go in an "after adaptation" table and are scored leave-one-out.
