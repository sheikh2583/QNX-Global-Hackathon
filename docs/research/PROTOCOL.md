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
- **Mutants:** 21 (7 good controls, 14 bad) in `research/mutants/<workload>/<id>/{patch.diff,README.md,expected.toml}`, generated
  by `research/mutants/make_mutants.py` (`--check` keeps them in step). Third-party controls TP-ttk-ref and MC-ref and the
  memcached MC-wrong mutant are listed but run by hand from existing harnesses; the five zoo workloads are automated by
  `research/mutants/run.py`. Z4-partial uses 2 locked workers of 4 (the brief's 3-of-4 variant leaves one locker and so no
  contention, i.e. a full fix).
- **Oracles** (`research/oracles.py`, unit-tested): O1 single capture, O2 deadline-only (vacuous accept when no deadline is
  declared), O3 findings-only, **O4 the shipped verdict** (its deadline test pools every job of every capture into one rank
  test), **O4c the same verdict with that test on one p99 per capture** (the gate's unit, exact test), O5 = O4 plus a 95%
  residual-rate bound of at most 0.2 (needs 14 clean after-captures). `src/tracelens/verdict.py` is NOT changed by this study.
- **Expected outcomes:** one line per mutant per oracle in each `expected.toml` (`[predicted]`, with `confidence`), written
  before any mutant capture. Summary: O1/O2/O3 accept the symptom-masking mutants only where the finding rule is silent on the
  small window (low confidence, stated per file); O2 accepts Z1-mask, Z2-mask, Z3-* (no deadline), Z4-partial; Z1-rare is
  accepted by O1 about 80% of the time and by O3 with probability 0.8^N, falling with N; O4 and O5 reject every bad mutant
  except the **expected false accepts Z4-racy (data race, invisible to timing) and, with low confidence, Z5-hist and
  Z5-unmaskonly**; all oracles accept the good controls at N=20, and O5 answers INCONCLUSIVE below 14 clean captures.
- **O4 versus O4c (coordinator finding, 2026-11-25):** the shipped deadline test is subject to the same inflation the gate study
  measured for job pooling (30.1% against 4.5% under A/A). Expected: O4 and O4c agree on every mutant at N=20; they can disagree
  at small N and small effects (a synthetic pair in `tests/test_research_oracles.py` shows O4 accepting where O4c rejects). If
  they disagree on any real mutant, that is reported as an oracle-design result; whether the product switches is a separate decision.
- **Metric:** false-accept rate, false-reject rate, INCONCLUSIVE rate per oracle and N in {1,3,5,10,20}; 1,000 seeded subsets
  (`oracles.sweep`). Subsets overlap, so the full-20 result is the headline and the subsampling a curve.
- **Sample size:** 20 clean captures per mutant and per unpatched build (shared by the mutants of a workload); lossy captures
  are kept and counted and replaced up to 40 attempts; host idle (`run.py` stops above load 0.5 and logs it). Z1-rare's realised
  per-capture inversion rate is measured and reported with its interval, not assumed to be 20%.
- **Exclusions:** a mutant that fails to build is a result (listed), not dropped.
- frozen: (to be filled by the commit that records the freeze: the sha is that of the commit containing every `expected.toml`,
  `research/oracles.py` and `research/mutants/run.py`)

## E3 (RQ2, R3): blind benchmark

- **Hypothesis:** with the tool frozen, detection and repair on real bugs are far below the zoo's 50/50; some classes are missed.
- **Expected (write the numbers here before the run):** (to be written; honest prior: detection of a minority of bugs, most
  misses in classes with no rule, radar not discriminating.)
- **Inclusion criteria and rubric:** `bench/RUBRIC.md` (written 2026-11-25, frozen with the tool). **Metrics:** S0, D1-D3, F0, R1-R5, RA. **Sample size:** 10 buggy and 10
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
- **Simulator part run 2026-11-25** (`research/gate_study.py`, results in [gate_study.md](gate_study.md)). A/A: the capture-unit gate
  alarmed in 4.5% (5v5) and 3.2% (10v10) of 1,000 splits with the floors off; the job-unit comparator in 30.1% and 28.8%.
  Ten-metric family, floors off: none 37.6%, Holm 4.2%, BH 4.3%. Power could not be measured: simulator noise (p99 spread
  about 0.8%) separates even a +1% slowdown completely, so the floors decide. The expectation written beforehand (capture unit
  near alpha, job unit well above it) held; the power expectation was untestable here. VM part: Phase B, not run.

## Amendments

- 2026-11-25: E7 simulator part was run before its VM part; this is allowed because it needs no target, and it is recorded here
  rather than edited into E7's hypothesis. E7 power at small effect sizes is deferred to the VM.
- 2026-11-25: E3 gained `bench/RUBRIC.md` (see above) and the manifest criteria; no bug has been reproduced under a freeze yet.
