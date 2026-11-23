# x86_64 pilot against x86_64 overnight, feature by feature

`data/pilot`: 16 of 16 captures succeeded, 16 with the planted problem showing, 0 lossy. Reproduce with `python scripts/arch_compare.py --a data/pilot --b data/real --label-a 'x86_64 pilot' --label-b 'x86_64 overnight'`.

## Did each planted problem show up?

| Scenario | Label | Showed up on x86_64 pilot | Rules that fired (HIGH+) |
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

## Median per feature

238 of 275 compared feature/thread pairs agree within 0.10. The widest gaps:

| Scenario | Thread | Feature | x86_64 pilot | x86_64 overnight | Gap |
|---|---|---|---|---|---|
| `lock_contention` | w1 | `cpus_used` | 1.000 | 2.000 | 1.000 |
| `healthy_periodic` | tlgen[1] | `cpus_used` | 1.000 | 2.000 | 1.000 |
| `healthy_mixed` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `healthy_ipc` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `irq_overrun` | ist | `max_run_frac` | 1.000 | 0.025 | 0.975 |
| `cpu_starvation` | job | `share_sleep` | 0.323 | 0.670 | 0.347 |
| `healthy_pi_mutex` | tlgen[1] | `share_sleep` | 0.238 | 0.559 | 0.321 |
| `cpu_starvation` | job | `share_ready` | 0.596 | 0.297 | 0.300 |
| `irq_overrun` | ist | `share_running` | 1.000 | 0.726 | 0.274 |
| `irq_overrun` | ist | `share_ready` | 0.000 | 0.273 | 0.273 |
| `healthy_pi_mutex` | mid | `share_sleep` | 0.801 | 0.587 | 0.214 |
| `healthy_ipc` | tlgen[1] | `share_sleep` | 0.266 | 0.471 | 0.205 |
| `healthy_periodic` | tlgen[1] | `share_sleep` | 0.058 | 0.260 | 0.202 |
| `healthy_irq` | ist | `preempts_per_ms` | 2.050 | 2.250 | 0.200 |
| `healthy_pi_mutex` | lo | `share_sleep` | 0.759 | 0.575 | 0.184 |

## The shipped radar on x86_64 pilot

The radar in `src/tracelens/ml/radar.json` was trained on x86 traces only, so this is a transfer test: it has never seen this machine.

| Scenario | Label | Radar (persistent unusual threads) |
|---|---|---|
| `healthy_periodic` | healthy | quiet |
| `healthy_pi_mutex` | healthy | quiet |
| `healthy_ipc` | healthy | quiet |
| `healthy_mixed` | healthy | quiet |
| `sem_inversion` | priority_inversion | hi (100/100) |
| `chan_inversion` | priority_inversion | client (100/101) |
| `ipc_deadlock` | ipc_deadlock | fusion_a (53/105), fusion_b (52/104) |
| `lock_contention` | mutex_contention | w3 (100/100), w4 (83/100), w6 (81/100) |
| `condvar_inversion` | priority_inversion | hi (100/100) |
| `cpu_starvation` | cpu_starvation | quiet |
| `mutex_abba` | mutex_abba | ba (51/51), ab (51/51) |
| `lost_wakeup` | lost_wakeup | consumer (100/100) |
| `period_overrun` | period_overrun | logger (126/129) |
| `healthy_irq` | healthy | quiet |
| `irq_overrun` | irq_handler_overrun | quiet |
| `healthy_irq_deferred` | healthy | quiet |

**Radar on x86_64 pilot: 8 of 10 planted-bug traces flagged on the thread that suffers, 0 false alarms on 6 healthy traces.**
