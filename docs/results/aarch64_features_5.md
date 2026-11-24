# aarch64le against x86_64, feature by feature

`data/aarch64_5`: 65 of 65 captures succeeded, 56 with the planted problem showing, 61 lossy. Reproduce with `python scripts/arch_compare.py --a data/aarch64_5 --b /mnt/x/Hackathons/QNX Global hackathon/data/real --label-a 'aarch64le' --label-b 'x86_64'`.

## Did each planted problem show up?

| Scenario | Label | Showed up on aarch64le | Rules that fired (HIGH+) |
|---|---|---|---|
| `healthy_periodic` | healthy | yes | none |
| `healthy_periodic` | healthy | yes | none |
| `healthy_periodic` | healthy | yes | none |
| `healthy_periodic` | healthy | yes | none |
| `healthy_periodic` | healthy | yes | none |
| `healthy_pi_mutex` | healthy | yes | none |
| `healthy_pi_mutex` | healthy | yes | none |
| `healthy_pi_mutex` | healthy | yes | none |
| `healthy_pi_mutex` | healthy | yes | none |
| `healthy_pi_mutex` | healthy | yes | none |
| `healthy_ipc` | healthy | **no** | deadline_miss |
| `healthy_ipc` | healthy | yes | none |
| `healthy_ipc` | healthy | yes | none |
| `healthy_ipc` | healthy | **no** | deadline_miss |
| `healthy_ipc` | healthy | yes | none |
| `healthy_mixed` | healthy | **no** | deadline_miss |
| `healthy_mixed` | healthy | **no** | deadline_miss |
| `healthy_mixed` | healthy | **no** | deadline_miss |
| `healthy_mixed` | healthy | **no** | deadline_miss |
| `healthy_mixed` | healthy | **no** | deadline_miss |
| `sem_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `sem_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `sem_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `sem_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `sem_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `chan_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `chan_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `chan_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `chan_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `chan_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `ipc_deadlock` | ipc_deadlock | yes | ipc_deadlock |
| `ipc_deadlock` | ipc_deadlock | yes | ipc_deadlock |
| `ipc_deadlock` | ipc_deadlock | yes | ipc_deadlock |
| `ipc_deadlock` | ipc_deadlock | yes | ipc_deadlock |
| `ipc_deadlock` | ipc_deadlock | yes | ipc_deadlock |
| `lock_contention` | mutex_contention | yes | deadline_miss, mutex_contention |
| `lock_contention` | mutex_contention | **no** | none |
| `lock_contention` | mutex_contention | yes | deadline_miss, mutex_contention |
| `lock_contention` | mutex_contention | **no** | none |
| `lock_contention` | mutex_contention | yes | deadline_miss, mutex_contention |
| `condvar_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `condvar_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `condvar_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `condvar_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `condvar_inversion` | priority_inversion | yes | deadline_miss, priority_inversion |
| `cpu_starvation` | cpu_starvation | yes | none |
| `cpu_starvation` | cpu_starvation | yes | none |
| `cpu_starvation` | cpu_starvation | yes | none |
| `cpu_starvation` | cpu_starvation | yes | none |
| `cpu_starvation` | cpu_starvation | yes | none |
| `mutex_abba` | mutex_abba | yes | none |
| `mutex_abba` | mutex_abba | yes | none |
| `mutex_abba` | mutex_abba | yes | none |
| `mutex_abba` | mutex_abba | yes | none |
| `mutex_abba` | mutex_abba | yes | none |
| `lost_wakeup` | lost_wakeup | yes | none |
| `lost_wakeup` | lost_wakeup | yes | priority_inversion |
| `lost_wakeup` | lost_wakeup | yes | none |
| `lost_wakeup` | lost_wakeup | yes | none |
| `lost_wakeup` | lost_wakeup | yes | none |
| `period_overrun` | period_overrun | yes | none |
| `period_overrun` | period_overrun | yes | none |
| `period_overrun` | period_overrun | yes | none |
| `period_overrun` | period_overrun | yes | none |
| `period_overrun` | period_overrun | yes | none |

## Median per feature

243 of 263 compared feature/thread pairs agree within 0.10. The widest gaps:

| Scenario | Thread | Feature | aarch64le | x86_64 | Gap |
|---|---|---|---|---|---|
| `healthy_pi_mutex` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `healthy_periodic` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `healthy_mixed` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `healthy_ipc` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `healthy_pi_mutex` | tlgen[1] | `share_sleep` | 0.275 | 0.559 | 0.284 |
| `healthy_mixed` | tlgen[1] | `share_running` | 0.283 | 0.050 | 0.233 |
| `healthy_ipc` | tlgen[1] | `share_sleep` | 0.282 | 0.471 | 0.189 |
| `lock_contention` | w6 | `share_sleep` | 0.784 | 0.601 | 0.183 |
| `healthy_mixed` | tlgen[1] | `share_sleep` | 0.245 | 0.428 | 0.183 |
| `lock_contention` | w6 | `share_mutex` | 0.116 | 0.279 | 0.163 |
| `ipc_deadlock` | fusion_a | `share_sleep` | 0.732 | 0.892 | 0.160 |
| `healthy_pi_mutex` | tlgen[1] | `preempts_per_ms` | 0.450 | 0.300 | 0.150 |
| `healthy_periodic` | tlgen[1] | `share_sleep` | 0.407 | 0.260 | 0.147 |
| `healthy_pi_mutex` | tlgen[1] | `share_running` | 0.179 | 0.037 | 0.142 |
| `healthy_periodic` | tlgen[1] | `share_running` | 0.176 | 0.037 | 0.139 |
| `ipc_deadlock` | fusion_a | `max_block_frac` | 0.134 | 0.000 | 0.134 |
| `healthy_ipc` | tlgen[1] | `share_running` | 0.166 | 0.037 | 0.129 |
| `healthy_periodic` | tlgen[1] | `migrations_per_ms` | 0.175 | 0.050 | 0.125 |
| `healthy_mixed` | tlgen[1] | `preempts_per_ms` | 0.575 | 0.450 | 0.125 |
| `lock_contention` | w6 | `max_block_frac` | 0.115 | 0.232 | 0.116 |
| `healthy_mixed` | lo | `preempts_per_ms` | 0.200 | 0.100 | 0.100 |
| `healthy_pi_mutex` | tlgen[1] | `migrations_per_ms` | 0.150 | 0.050 | 0.100 |
| `healthy_pi_mutex` | mid | `share_running` | 0.277 | 0.360 | 0.083 |
| `healthy_mixed` | lo | `share_ready` | 0.105 | 0.023 | 0.082 |
| `cpu_starvation` | job | `share_sleep` | 0.748 | 0.670 | 0.077 |

## The shipped radar on aarch64le

The radar in `src/tracelens/ml/radar.json` was trained on x86 traces only, so this is a transfer test: it has never seen this machine.

| Scenario | Label | Radar (persistent unusual threads) |
|---|---|---|
| `healthy_periodic` | healthy | quiet |
| `healthy_periodic` | healthy | quiet |
| `healthy_periodic` | healthy | quiet |
| `healthy_periodic` | healthy | quiet |
| `healthy_periodic` | healthy | quiet |
| `healthy_pi_mutex` | healthy | quiet |
| `healthy_pi_mutex` | healthy | quiet |
| `healthy_pi_mutex` | healthy | quiet |
| `healthy_pi_mutex` | healthy | quiet |
| `healthy_pi_mutex` | healthy | quiet |
| `healthy_ipc` | healthy | quiet |
| `healthy_ipc` | healthy | quiet |
| `healthy_ipc` | healthy | quiet |
| `healthy_ipc` | healthy | quiet |
| `healthy_ipc` | healthy | quiet |
| `healthy_mixed` | healthy | quiet |
| `healthy_mixed` | healthy | quiet |
| `healthy_mixed` | healthy | quiet |
| `healthy_mixed` | healthy | quiet |
| `healthy_mixed` | healthy | quiet |
| `sem_inversion` | priority_inversion | hi (101/101) |
| `sem_inversion` | priority_inversion | hi (93/100) |
| `sem_inversion` | priority_inversion | hi (100/101) |
| `sem_inversion` | priority_inversion | hi (96/100) |
| `sem_inversion` | priority_inversion | hi (100/100) |
| `chan_inversion` | priority_inversion | client (100/101) |
| `chan_inversion` | priority_inversion | client (100/100) |
| `chan_inversion` | priority_inversion | client (100/100) |
| `chan_inversion` | priority_inversion | client (100/101) |
| `chan_inversion` | priority_inversion | client (101/101) |
| `ipc_deadlock` | ipc_deadlock | fusion_a (54/107), fusion_b (52/104) |
| `ipc_deadlock` | ipc_deadlock | fusion_a (54/107), fusion_b (51/104) |
| `ipc_deadlock` | ipc_deadlock | fusion_a (53/106), fusion_b (51/104) |
| `ipc_deadlock` | ipc_deadlock | fusion_a (53/107), fusion_b (51/104) |
| `ipc_deadlock` | ipc_deadlock | fusion_a (54/106), fusion_b (51/104) |
| `lock_contention` | mutex_contention | w3 (54/100), w1 (54/100), w2 (52/100) |
| `lock_contention` | mutex_contention | quiet |
| `lock_contention` | mutex_contention | w5 (74/100), w4 (68/100), w2 (65/100) |
| `lock_contention` | mutex_contention | quiet |
| `lock_contention` | mutex_contention | w2 (48/100), w1 (38/100) |
| `condvar_inversion` | priority_inversion | hi (100/100) |
| `condvar_inversion` | priority_inversion | hi (101/101) |
| `condvar_inversion` | priority_inversion | hi (100/100) |
| `condvar_inversion` | priority_inversion | hi (100/100) |
| `condvar_inversion` | priority_inversion | hi (100/100) |
| `cpu_starvation` | cpu_starvation | quiet |
| `cpu_starvation` | cpu_starvation | quiet |
| `cpu_starvation` | cpu_starvation | quiet |
| `cpu_starvation` | cpu_starvation | quiet |
| `cpu_starvation` | cpu_starvation | quiet |
| `mutex_abba` | mutex_abba | ba (51/51), ab (51/51) |
| `mutex_abba` | mutex_abba | ba (52/52), ab (52/52) |
| `mutex_abba` | mutex_abba | ba (51/52), ab (51/52) |
| `mutex_abba` | mutex_abba | ba (52/52), ab (52/52) |
| `mutex_abba` | mutex_abba | ba (51/51), ab (51/51) |
| `lost_wakeup` | lost_wakeup | consumer (98/100) |
| `lost_wakeup` | lost_wakeup | consumer (96/100) |
| `lost_wakeup` | lost_wakeup | consumer (99/100) |
| `lost_wakeup` | lost_wakeup | consumer (100/100) |
| `lost_wakeup` | lost_wakeup | consumer (98/100) |
| `period_overrun` | period_overrun | logger (115/118) |
| `period_overrun` | period_overrun | logger (138/139), tlgen[1] (3/4) |
| `period_overrun` | period_overrun | logger (125/128) |
| `period_overrun` | period_overrun | logger (141/142) |
| `period_overrun` | period_overrun | logger (138/138) |

**Radar on aarch64le: 38 of 45 planted-bug traces flagged on the thread that suffers, 0 false alarms on 20 healthy traces.**
