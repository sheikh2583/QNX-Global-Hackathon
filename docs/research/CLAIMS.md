# Claims register (seed, 2026-11-25)

A paper may use only rows whose status is **supported**. Number macros come from `research/make_numbers.py` (written 2026-11-25; the table lists
the ones that exist). Statuses are conservative.

| Claim | Evidence | Macro | Status |
|---|---|---|---|
| 4 of 5 planted zoo bugs are fixed automatically and VERIFIED on QNX 8.0 | `docs/results/fix.md` | | **partial**: planted bugs written by the authors, development set |
| All 50 planted-bug captures are detected and 0 of 80 healthy/fixed runs are flagged | `docs/results/detect.md` | | **partial**: development set, rules calibrated on it |
| The learned radar flags 726 of 883 held-out generator captures (rules alone 400) with 0 false alarms on 148 healthy | `docs/ml/results_train.md` | | **partial**: held out within one generator; no transfer shown |
| The radar helps on real programs | memcached daemon, NNG (flagged hang and healthy alike) | | **unsupported** (contradicted) |
| A real fix on third-party teaching code is VERIFIED (inversion 10/10 to 0/10, p99 1,103 to 702 ms) | `docs/results/third_party_fix/` | | **partial**: one teaching exercise, rule matches its shape |
| memcached#1348 is detected and fixed on QNX, VERIFIED 10/10 to 0/10 | `docs/results/memcached_logger/` | | **partial**: case study, rules written after the bug, reduced build |
| NNG nng_close() hang is detected (`stuck_job`) and upstream's fix verified | `docs/results/nng_close/` | | **partial**: missed first; rule written after; upstream wrote the fix |
| TraceLens finds bugs it has not seen | `docs/results/blind_test/` | | **unsupported** (null result: nothing reproduced) |
| The trace oracle rarely accepts a bad patch | (none yet) | | **unsupported** until R2 |
| Guarded transforms avoid breaking code that naive transforms break | (none yet) | | **unsupported** until R5 |
| The capture-as-unit gate keeps A/A false alarms at or below alpha (4.5% at 5v5, 3.2% at 10v10); a job-as-unit comparator alarms in about 30% | `docs/research/gate_study.md` | `	lAACaptureFiveFloorsOff`, `	lAAJobFiveFloorsOff` | **partial**: simulator only, simulator noise far below real, VM part is Phase B |
| Holm holds the 10-metric family-wise false-alarm rate near alpha (4.2% against 37.6% uncorrected) | `docs/research/gate_study.md` | `	lFamilyHolm`, `	lFamilyNone` | **partial**: synthetic independent metrics |
| The gate's power against small slowdowns | `docs/research/gate_study.md` | | **unsupported**: the simulator is too quiet to measure it; needs the VM |
| After a fix with 0 of n clean after-captures, the bug's residual per-capture rate is below a stated bound | `src/tracelens/verdict.py`, `tests/test_verdict.py` | `	lResidualZeroOfFive` etc. | **supported** (exact binomial arithmetic) |
