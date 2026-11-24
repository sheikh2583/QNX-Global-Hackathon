# aarch64le against x86_64, feature by feature

`data/aarch64`: 13 of 16 captures succeeded, 13 with the planted problem showing, 11 lossy. Reproduce with `python scripts/arch_compare.py --a data/aarch64 --b /mnt/x/Hackathons/QNX Global hackathon/data/real --label-a 'aarch64le' --label-b 'x86_64'`.

## Did each planted problem show up?

| Scenario | Label | Showed up on aarch64le | Rules that fired (HIGH+) |
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
| `healthy_irq` | healthy | **no** | none |
| `irq_overrun` | irq_handler_overrun | **no** | none |
| `healthy_irq_deferred` | healthy | **no** | none |

## Median per feature

222 of 256 compared feature/thread pairs agree within 0.10. The widest gaps:

| Scenario | Thread | Feature | aarch64le | x86_64 | Gap |
|---|---|---|---|---|---|
| `healthy_periodic` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `healthy_mixed` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `healthy_ipc` | tlgen[1] | `cpus_used` | 3.000 | 2.000 | 1.000 |
| `healthy_pi_mutex` | tlgen[1] | `share_sleep` | 0.041 | 0.559 | 0.518 |
| `healthy_periodic` | tlgen[1] | `share_sleep` | 0.633 | 0.260 | 0.373 |
| `cpu_starvation` | job | `share_sleep` | 0.304 | 0.670 | 0.367 |
| `cpu_starvation` | job | `share_ready` | 0.618 | 0.297 | 0.322 |
| `healthy_mixed` | tlgen[1] | `share_sleep` | 0.124 | 0.428 | 0.303 |
| `ipc_deadlock` | fusion_a | `share_sleep` | 0.592 | 0.892 | 0.300 |
| `healthy_pi_mutex` | tlgen[1] | `share_running` | 0.284 | 0.037 | 0.247 |
| `healthy_pi_mutex` | tlgen[1] | `preempts_per_ms` | 0.525 | 0.300 | 0.225 |
| `healthy_pi_mutex` | mid | `share_sleep` | 0.796 | 0.587 | 0.209 |
| `healthy_mixed` | tlgen[1] | `share_running` | 0.241 | 0.050 | 0.191 |
| `healthy_pi_mutex` | lo | `share_sleep` | 0.761 | 0.575 | 0.186 |
| `healthy_pi_mutex` | mid | `share_running` | 0.177 | 0.360 | 0.183 |
| `chan_inversion` | client | `share_sleep` | 0.492 | 0.673 | 0.181 |
| `ipc_deadlock` | fusion_b | `share_sleep` | 0.693 | 0.869 | 0.176 |
| `chan_inversion` | client | `inversion_frac` | 0.473 | 0.298 | 0.175 |
| `chan_inversion` | client | `share_reply` | 0.474 | 0.299 | 0.175 |
| `healthy_mixed` | tlgen[1] | `share_reply` | 0.196 | 0.023 | 0.174 |
| `healthy_pi_mutex` | lo | `share_ready` | 0.205 | 0.373 | 0.168 |
| `lock_contention` | w6 | `share_sleep` | 0.742 | 0.601 | 0.141 |
| `healthy_periodic` | lo | `share_ready` | 0.129 | 0.009 | 0.120 |
| `lock_contention` | w6 | `share_mutex` | 0.161 | 0.279 | 0.117 |
| `healthy_periodic` | lo | `max_ready_frac` | 0.123 | 0.007 | 0.116 |

## The shipped radar on aarch64le

The radar in `src/tracelens/ml/radar.json` was trained on x86 traces only, so this is a transfer test: it has never seen this machine.

| Scenario | Label | Radar (persistent unusual threads) |
|---|---|---|
| `healthy_periodic` | healthy | quiet |
| `healthy_pi_mutex` | healthy | quiet |
| `healthy_ipc` | healthy | quiet |
| `healthy_mixed` | healthy | quiet |
| `sem_inversion` | priority_inversion | hi (97/101) |
| `chan_inversion` | priority_inversion | client (100/101) |
| `ipc_deadlock` | ipc_deadlock | fusion_a (57/107), fusion_b (51/104) |
| `lock_contention` | mutex_contention | w2 (82/101), w4 (79/101), w6 (72/101) |
| `condvar_inversion` | priority_inversion | hi (100/101) |
| `cpu_starvation` | cpu_starvation | quiet |
| `mutex_abba` | mutex_abba | ba (51/51), ab (51/51) |
| `lost_wakeup` | lost_wakeup | consumer (100/101) |
| `period_overrun` | period_overrun | logger (128/131) |

**Radar on aarch64le: 8 of 9 planted-bug traces flagged on the thread that suffers, 0 false alarms on 4 healthy traces.**
