# aarch64le against x86_64, feature by feature

`data/aarch64_irq_b`: 12 of 12 captures succeeded, 4 with the planted problem showing, 12 lossy. Reproduce with `python scripts/arch_compare.py --a data/aarch64_irq_b --b /mnt/x/Hackathons/QNX Global hackathon/data/real --label-a 'aarch64le' --label-b 'x86_64'`.

## Did each planted problem show up?

| Scenario | Label | Showed up on aarch64le | Rules that fired (HIGH+) |
|---|---|---|---|
| `healthy_irq` | healthy | **no** | irq_latency, mutex_contention |
| `healthy_irq` | healthy | **no** | irq_handler_overrun, irq_latency, mutex_contention |
| `healthy_irq` | healthy | **no** | irq_handler_overrun, irq_latency |
| `healthy_irq` | healthy | **no** | irq_handler_overrun, irq_latency |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun, irq_latency, mutex_contention |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun, mutex_contention |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun, irq_latency, mutex_contention |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun, mutex_contention |
| `healthy_irq_deferred` | healthy | **no** | irq_latency, mutex_contention |
| `healthy_irq_deferred` | healthy | **no** | irq_latency, mutex_contention |
| `healthy_irq_deferred` | healthy | **no** | irq_latency, mutex_contention |
| `healthy_irq_deferred` | healthy | **no** | irq_handler_overrun, irq_latency, mutex_contention |

## Median per feature

20 of 38 compared feature/thread pairs agree within 0.10. The widest gaps:

| Scenario | Thread | Feature | aarch64le | x86_64 | Gap |
|---|---|---|---|---|---|
| `healthy_irq` | ist | `preempts_per_ms` | 0.300 | 2.250 | 1.950 |
| `healthy_irq_deferred` | ist | `preempts_per_ms` | 0.500 | 2.200 | 1.700 |
| `healthy_irq_deferred` | ist | `blocks_per_ms` | 0.350 | 1.750 | 1.400 |
| `healthy_irq` | ist | `blocks_per_ms` | 0.300 | 1.700 | 1.400 |
| `healthy_irq_deferred` | worker | `max_block_frac` | 1.000 | 0.000 | 1.000 |
| `healthy_irq_deferred` | ist | `max_block_frac` | 1.000 | 0.024 | 0.976 |
| `healthy_irq_deferred` | worker | `max_run_frac` | 0.200 | 1.000 | 0.800 |
| `irq_overrun` | ist | `intr_masked_frac` | 0.555 | 0.000 | 0.555 |
| `irq_overrun` | ist | `max_block_frac` | 0.520 | 0.000 | 0.520 |
| `healthy_irq_deferred` | worker | `share_running` | 0.485 | 1.000 | 0.515 |

## The shipped radar on aarch64le

The radar in `src/tracelens/ml/radar.json` was trained on x86 traces only, so this is a transfer test: it has never seen this machine.

| Scenario | Label | Radar (persistent unusual threads) |
|---|---|---|
| `healthy_irq` | healthy | ist (56/60) |
| `healthy_irq` | healthy | ist (51/57) |
| `healthy_irq` | healthy | ist (54/60) |
| `healthy_irq` | healthy | ist (51/56) |
| `irq_overrun` | irq_handler_overrun | ist (72/72) |
| `irq_overrun` | irq_handler_overrun | ist (76/76) |
| `irq_overrun` | irq_handler_overrun | ist (88/89) |
| `irq_overrun` | irq_handler_overrun | ist (88/88) |
| `healthy_irq_deferred` | healthy | ist (66/72), worker (82/100) |
| `healthy_irq_deferred` | healthy | ist (63/70), worker (86/100) |
| `healthy_irq_deferred` | healthy | ist (60/71), worker (83/99) |
| `healthy_irq_deferred` | healthy | ist (65/70), worker (88/100) |

**Radar on aarch64le: 4 of 4 planted-bug traces flagged on the thread that suffers, 8 false alarms on 8 healthy traces.**
