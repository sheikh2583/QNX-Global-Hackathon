# Research protocol (preregistration skeleton)

Written 2026-11-25. **Status: skeleton.** Each experiment section must be completed and frozen (`frozen: <git sha> <date>`)
**before any data for it is collected.** After freezing, changes are appended as dated amendments, never edited in place.
Research questions RQ1-RQ6 are defined in [BUILD_AGENT_BRIEF.md](BUILD_AGENT_BRIEF.md); use those labels everywhere.

Global rules: the statistical unit is the **capture**; lossy captures are excluded and counted; failed builds are excluded
and counted; every table reports misses and false positives; the host is idle during captures and load is logged.

## Freeze record

| Freeze | Tag | `tracelens --version` | config SHA-256 | radar/classifier JSON SHA-256 | Date |
|---|---|---|---|---|---|
| research-freeze-1 | (not created; ask before pushing a tag) | | | | |

Earlier, informal freeze (2026-11-25, blind test of Mosquitto/jemalloc/libzmq): `src/tracelens/` hash `24fec05b8f9f7746`,
see [../results/blind_test/PREREGISTRATION.md](../results/blind_test/PREREGISTRATION.md). That test produced a null result.

## E1 (RQ1, R1): the residual-rate bound

- **Hypothesis:** the one-sided Clopper-Pearson bound is a correct, conservative statement about residual per-capture rate.
- **Expected:** for k=0 the bound is 45.1% at n=5, 25.9% at n=10, 13.9% at n=20 (95%); `runs_needed(0.1)=29`.
- **Metric / test:** exact binomial; unit tests against closed form and tabulated values. **Status:** implemented
  2026-11-25 (`src/tracelens/verdict.py`), tests in `tests/test_verdict.py`. frozen: (n/a, deterministic arithmetic)

## E2 (RQ1, R2): oracle mutation study

- **Hypothesis:** single-capture and deadline-only oracles falsely accept symptom-masking and rare-race patches; the full
  oracle rejects them; false accepts of rare-race patches fall as N grows.
- **Expected outcomes (to be written before capture, one line per mutant, in each `expected.toml`):** O1/O2 accept Z1-mask,
  Z1-rare, Z2-mask often; O4 rejects them; Z4-racy is accepted by every timing oracle (a timing oracle cannot see data races).
- **Metric:** false-accept rate, false-reject rate, INCONCLUSIVE rate per oracle and N in {1,3,5,10,20}; 1,000 seeded subsets.
- **Sample size:** 20 clean captures per mutant and per unpatched build. **Exclusions:** lossy captures (replaced and counted).
- frozen: (not frozen)

## E3 (RQ2, R3): blind benchmark

- **Hypothesis:** with the tool frozen, detection and repair on real bugs are far below the zoo's 50/50; some classes are missed.
- **Expected (write the numbers here before the run):** (to be written; honest prior: detection of a minority of bugs, most
  misses in classes with no rule, radar not discriminating.)
- **Metrics:** rubric D1-D3, F0, R1-R5, radar flags (see `bench/RUBRIC.md`, not yet written). **Sample size:** 10 buggy and 10
  fixed captures per bug. **Exclusions:** bugs that do not reproduce are listed as excluded with the reason.
- frozen: (not frozen; requires the freeze tag above)

## E4 (RQ3, R5): repair ablations

- **Hypothesis:** naive (unguarded) transforms break the precondition-violation suite and introduce new findings; guarded
  transforms back off with guidance; multi-round fixes a minority of cases that single-round misses.
- **Metrics:** compile failures, functional failures, new findings, VERIFIED rate; rounds needed. frozen: (not frozen)

## E5 (RQ4, R6): radar versus baselines

- **Hypothesis:** simple baselines match the radar on generator families; none transfers to real bugs.
- **Metrics:** per-family recall, false alarms per hour, leave-one-family-out, transfer to blind bench bugs. frozen: (not frozen)

## E6 (RQ5, R4): hardware and probe effect

- **Hypothesis:** the VM agrees with hardware on verdict categories but not on absolute latencies; tracing shifts latencies and
  can hide some planted bugs. **Expected:** (to be written). frozen: (not frozen; needs hardware)

## E7 (RQ6, R8): gate false alarms and power

- **Hypothesis:** the capture-as-unit gate holds its false-alarm rate near alpha under A/A; a job-as-unit comparator does not.
- **Metrics:** A/A false-alarm rate over 1,000 random splits; detection rate for +5/10/20/50% slowdowns versus N. frozen: (not frozen)

## Amendments

(none yet)
