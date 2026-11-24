# TraceLens on real QNX 8.0: the pilot against the simulator

One real capture per scenario (16 of 16 succeeded, 16 with the planted problem showing, 0 lossy), on the QEMU x86_64 guest with 4 CPUs and `procnto-smp-instr`, host idle. Reproduce with `python scripts/real_vs_sim.py --radar data/sim/radar.json` (the radar trained on simulated traces only, which is what this report scored; the radar shipped in `src/tracelens/ml/radar.json` was retrained on real data on 2026-11-16, so the default now gives different window counts).

## Did each planted problem show up on the real target?

| Scenario | Label | Planted problem showed up | Rules that fired (HIGH+) |
|---|---|---|---|
| `healthy_periodic` | healthy | yes | none |
| `healthy_pi_mutex` | healthy | yes | none |
| `healthy_ipc` | healthy | yes | none |
| `healthy_mixed` | healthy | yes | none |
| `sem_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `chan_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `ipc_deadlock` | ipc_deadlock | yes | ipc_deadlock |
| `lock_contention` | mutex_contention | yes | deadline_miss, mutex_contention |
| `condvar_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `cpu_starvation` | cpu_starvation | yes | none |
| `mutex_abba` | mutex_abba | yes | none |
| `lost_wakeup` | lost_wakeup | yes | none |
| `period_overrun` | period_overrun | yes | none |
| `healthy_irq` | healthy | yes | none |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun, irq_latency |
| `healthy_irq_deferred` | healthy | yes | none |

## How close is the simulator? (median per feature, real against simulated)

210 of 274 compared feature/thread pairs agree within 0.10. The widest gaps:

| Scenario | Thread | Feature | Real | Simulated | Gap |
|---|---|---|---|---|---|
| `irq_overrun` | ist | `preempts_per_ms` | 0.000 | 4.850 | 4.850 |
| `healthy_irq` | ist | `preempts_per_ms` | 2.050 | 4.300 | 2.250 |
| `healthy_irq_deferred` | ist | `preempts_per_ms` | 2.100 | 4.200 | 2.100 |
| `healthy_mixed` | tlgen[1] | `cpus_used` | 3.000 | 1.000 | 2.000 |
| `healthy_irq` | ist | `blocks_per_ms` | 1.675 | 3.200 | 1.525 |
| `healthy_irq_deferred` | ist | `blocks_per_ms` | 1.700 | 3.100 | 1.400 |
| `lock_contention` | w6 | `cpus_used` | 2.000 | 1.000 | 1.000 |
| `lock_contention` | w5 | `cpus_used` | 2.000 | 1.000 | 1.000 |
| `lock_contention` | w4 | `cpus_used` | 2.000 | 1.000 | 1.000 |
| `lock_contention` | w3 | `cpus_used` | 2.000 | 1.000 | 1.000 |
| `lock_contention` | w2 | `cpus_used` | 2.000 | 1.000 | 1.000 |
| `healthy_mixed` | client | `cpus_used` | 1.000 | 2.000 | 1.000 |

## The frozen models on the real pilot

Neither model has ever seen a real trace, and these captures did not exist when they were trained.

| Scenario | Label | Radar (persistent unusual threads) | Classifier (thread: cause) |
|---|---|---|---|
| `healthy_periodic` | healthy | quiet | healthy |
| `healthy_pi_mutex` | healthy | quiet | healthy |
| `healthy_ipc` | healthy | quiet | healthy |
| `healthy_mixed` | healthy | quiet | healthy |
| `sem_inversion` | priority_inversion | hi (100/100) | hi: priority_inversion |
| `chan_inversion` | priority_inversion | client (100/101) | client: priority_inversion |
| `ipc_deadlock` | ipc_deadlock | fusion_b (53/104), fusion_a (53/105) | healthy |
| `lock_contention` | mutex_contention | w3 (100/100), w6 (81/100), w4 (72/100) | w6: mutex_contention, w4: mutex_contention |
| `condvar_inversion` | priority_inversion | hi (100/100) | hi: priority_inversion |
| `cpu_starvation` | cpu_starvation | quiet | healthy |
| `mutex_abba` | mutex_abba | ba (51/51), ab (51/51) | ba: mutex_contention, ab: mutex_contention |
| `lost_wakeup` | lost_wakeup | consumer (100/100) | healthy |
| `period_overrun` | period_overrun | logger (127/129) | healthy |
| `healthy_irq` | healthy | quiet | healthy |
| `irq_overrun` | irq_handler_overrun | quiet | healthy |
| `healthy_irq_deferred` | healthy | quiet | healthy |

**Radar: 8 of 10 planted-bug traces flagged on the thread that suffers, 0 false alarms on 6 healthy traces.**
