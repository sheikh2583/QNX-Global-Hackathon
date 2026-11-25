# Gate study, simulator part (R8 / RQ6 / E7)

Run 2026-11-25 with `python research/gate_study.py`; raw numbers in [gate_study.json](gate_study.json); every figure
below is read from that file by `research/make_numbers.py`. Simulator only. The VM part is Phase B, hardware Phase C.

**Setup.** Built-in simulator, scenario `healthy_periodic`, deadline `hi` (budget 2.5 ms), 30 captures per arm (seeds 1-30,
none lossy), `hi` work 300 us as the baseline and +1, 2, 5, 10, 20, 50 % more work as the slowdowns. 1,000 random draws per cell.
Statistical unit: the capture (one p99 per capture). alpha 0.05. Effect floors on = 10 % and 50 us; off = 0 and 0.

## Result 1: false alarms under A/A (nothing changed)

| Comparator | 5 v 5, floors off | 10 v 10, floors off | floors on |
|---|---|---|---|
| capture as unit (the gate) | 4.5 % (95 % CI 3.3-6.0) | 3.2 % (2.2-4.5) | 0 / 1000 |
| job as unit (pool every job) | **30.1 %** (27.3-33.1) | **28.8 %** (26.0-31.7) | 0 / 1000 |

The gate's rank test holds its false-alarm rate at or under alpha (exact test, so slightly conservative). Treating the roughly
200 jobs of each capture as independent samples cries wolf in about three builds out of ten when nothing changed, which is the
reason the gate does not do it. The effect floors suppressed every alarm in both columns, so on this simulator the floors, not
the test, are what keep the job-as-unit comparator quiet. We do not claim the floors fix a bad statistic; they hide it.

## Result 2: several deadlines at once (family-wise false alarms)

Ten metrics, A/A, 5 v 5, 1,000 trials; "any false alarm" means at least one of the ten crossed:

| Correction | any false alarm |
|---|---|
| none | 37.6 % (34.6-40.7) |
| Holm (what the gate uses) | 4.2 % (3.0-5.6) |
| Benjamini-Hochberg | 4.3 % (3.1-5.8) |

Synthetic, and labelled so: each metric's per-capture p99 is a real `hi` p99 drawn independently (a separate draw per metric),
so the ten tests are independent. Real deadlines in one capture are correlated; with positive correlation all three rows move
toward fewer false alarms, so this is the hard case for the correction, not the easy one. Under the global null BH and Holm
behave alike (BH only controls FDR; it differs when some metrics truly regressed, which this study did not test). Keep Holm.

## Result 3: power, and why this simulator cannot answer it

Detection rate at every slowdown from +1 % to +50 % and every N (5, 10, 15 captures per side) was **100 % with the floors off**
and, with the floors on, 0 % at +10 % and below and 100 % from +20 % up. The floors, not N, decide.

This is a limitation of the simulator, not a property of the gate: the baseline p99 varied from 0.3016 to 0.3039 ms across
30 captures (about 0.8 %), so even +1 % (3 us) separates the two arms completely. Real captures on the QNX VM are far noisier
and the power curve will have a shape; it must be measured there (Phase B, with a `TL_EXTRA_WORK_US` knob). **No power claim
should be made from these numbers.** What the simulator does support: the false-alarm control in Results 1 and 2, and the fact
that floors of 10 % and 50 us make +10 % of a 300 us job (30 us) invisible by design.

## Threats to this part

- Simulator timing noise is much lower than real. False-alarm control that holds here must be re-measured on the VM.
- 30 captures give 1,000 overlapping draws, not 1,000 independent ones; the confidence intervals above treat the draws as
  independent and are therefore somewhat too narrow.
- One workload (`healthy_periodic`), one deadline for Results 1 and 3.
