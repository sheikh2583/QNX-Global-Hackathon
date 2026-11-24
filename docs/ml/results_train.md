# TraceLens models: training run

Trained on 988,704 windows from 1,920 traces (qnx, sim); evaluated on 1,909 traces from data/real. Reproduce: `python scripts/train_eval.py --sim data/sim --real data/real --test-on data/real`.

## Radar on held-out QNX traces

Window threshold 3.46 (99.5th percentile of healthy training windows); a thread is flagged when more than 29% of its windows (and at least 3) pass it, a cut-off calibrated on healthy training traces only.

| Family | Label | Split | Traces | Flagged | Planted problem showed up |
|---|---|---|---|---|---|
| `chan_inversion` | priority_inversion | test | 61 | 61 (100%) | 61/61 |
| `condvar_inversion` | priority_inversion | test | 59 | 59 (100%) | 59/59 |
| `healthy_ipc` | healthy | test | 28 | 0 (0%) | 28/28 |
| `healthy_irq` | healthy | test | 22 | 0 (0%) | 22/22 |
| `healthy_irq_deferred` | healthy | test | 30 | 0 (0%) | 30/30 |
| `healthy_mixed` | healthy | test | 20 | 0 (0%) | 11/20 |
| `healthy_periodic` | healthy | test | 23 | 0 (0%) | 23/23 |
| `healthy_pi_mutex` | healthy | test | 25 | 0 (0%) | 25/25 |
| `ipc_deadlock` | ipc_deadlock | test | 69 | 69 (100%) | 69/69 |
| `irq_overrun` | irq_handler_overrun | test | 80 | 68 (85%) | 80/80 |
| `lock_contention` | mutex_contention | test | 73 | 51 (70%) | 53/73 |
| `sem_inversion` | priority_inversion | test | 65 | 65 (100%) | 65/65 |
| `cpu_starvation` | cpu_starvation | test_unseen | 120 | 0 (0%) | 120/120 |
| `lost_wakeup` | lost_wakeup | test_unseen | 120 | 120 (100%) | 120/120 |
| `mutex_abba` | mutex_abba | test_unseen | 116 | 97 (84%) | 104/116 |
| `period_overrun` | period_overrun | test_unseen | 120 | 120 (100%) | 120/120 |

False alarms on held-out healthy traces: **0 of 148**.

## Classifier on parameter region B

| Class | Precision | Recall | Windows |
|---|---|---|---|
| healthy | 0.96 | 0.99 | 78361 |
| ipc_deadlock | 1.00 | 1.00 | 14397 |
| irq_handler_overrun | 1.00 | 1.00 | 10968 |
| mutex_contention | 0.96 | 0.87 | 27005 |
| priority_inversion | 1.00 | 1.00 | 18495 |

## What the radar adds to the rules

On 883 held-out buggy captures and 148 healthy ones:

| | Traces |
|---|---|
| Caught by the rules, missed by the radar | 16 |
| Caught by both | 384 |
| **Caught by the radar with no rule firing** | **326** |
| Caught by neither | 157 |
| False alarms on the healthy captures | **0** |

The rules alone find 400 of 883; with the radar, 726. A rule finding cites the kernel events that prove it, so on the families it knows the rule is the better answer; the radar's contribution is the families no rule exists for.
