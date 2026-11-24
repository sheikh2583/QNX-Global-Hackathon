# Threats to validity (seed, 2026-11-25)

Each threat names the workstream that addresses it, or says "not addressed". Honest status first.

## Construct validity

| Threat | Addressed by |
|---|---|
| Planted bugs were written by the authors to match the detectors' categories | R3 (blind real bugs), R2 (mutants) |
| "VERIFIED" measures absence of a finding kind plus a latency statistic, not functional correctness (a data race is invisible to it) | R2 (Z4-racy preregistered as an expected failure), R5 (functional tests) |
| The radar's labels come from the generator's scenario names, not from independent ground truth | R6 |

## Internal validity

| Threat | Addressed by |
|---|---|
| Detectors were calibrated on the bug zoo and tuned during development | R3 (frozen tag), the old zoo numbers stay labelled "development set" |
| Rules for memcached (`lost_wakeup`, `recheck-before-wait`) and NNG (`stuck_job`) were written after seeing those bugs | R3.3 (post-hoc table reported separately, leave-one-out); labelled as case studies today |
| Drivers and job markers for third-party code are ours | R3 (symptom oracle independent of TraceLens: exit code, watchdog) |
| QEMU/KVM under WSL2/Hyper-V adds timing noise | R4 (hardware), A/A noise floor in every comparison |
| Tracing perturbs the program (probe effect) | R4.2 |
| Budgets and thresholds chosen after a first look at one trace (NNG 0.5 s, memcached 3 s) | listed per result; R3 fixes them before the blind run |

## External validity

| Threat | Addressed by |
|---|---|
| One OS (QNX 8.0), one VM, one host | R4 (hardware), R9 (portability, stretch) |
| aarch64 is emulated (QEMU TCG), not Cortex-A hardware | R4 |
| Small number of real third-party bugs (3 reproduced so far: NTNU exercise, memcached, NNG; Mosquitto did not reproduce) | R3 (target 20-30) |
| The memcached daemon build is reduced (no TLS, SASL, extstore, proxy) and signalled from inside its own process | stated in the result; R3 |

## Conclusion validity

| Threat | Addressed by |
|---|---|
| Small N per side (5-10 captures); a 0-of-10 result only bounds the residual rate to about 26% | R1 (bound reported), R2 (N curve) |
| Periods or jobs inside one capture are not independent | the unit of every claim is the capture; per-period numbers are descriptive only |
| Multiple comparisons across metrics | Holm in the gate and the verdict; R8 compares with none and BH |
| Many findings reported only when favourable | negative results kept: Mosquitto null result, NNG initial miss, radar failing on real programs |
| The first blind test produced no result (Mosquitto did not reproduce on QNX) | `docs/results/blind_test/`; R3 widens the candidate pool |
