# aarch64le against x86_64, feature by feature

`data/aarch64_irq`: 9 of 9 captures succeeded, 3 with the planted problem showing, 9 lossy. Reproduce with `python scripts/arch_compare.py --a data/aarch64_irq --b /mnt/x/Hackathons/QNX Global hackathon/data/real --label-a 'aarch64le' --label-b 'x86_64'`.

## Did each planted problem show up?

| Scenario | Label | Showed up on aarch64le | Rules that fired (HIGH+) |
|---|---|---|---|
| `healthy_irq` | healthy | **no** | irq_handler_overrun, irq_latency, mutex_contention |
| `healthy_irq` | healthy | **no** | irq_handler_overrun, irq_latency |
| `healthy_irq` | healthy | **no** | irq_handler_overrun, irq_latency |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun, irq_latency, mutex_contention |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun, irq_latency, mutex_contention |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun, irq_latency |
| `healthy_irq_deferred` | healthy | **no** | irq_handler_overrun, irq_latency, mutex_contention |
| `healthy_irq_deferred` | healthy | **no** | irq_latency, mutex_contention |
| `healthy_irq_deferred` | healthy | **no** | irq_handler_overrun, irq_latency |

## Median per feature

18 of 38 compared feature/thread pairs agree within 0.10. The widest gaps:

| Scenario | Thread | Feature | aarch64le | x86_64 | Gap |
|---|---|---|---|---|---|
| `healthy_irq` | ist | `preempts_per_ms` | 0.300 | 2.250 | 1.950 |
| `healthy_irq_deferred` | ist | `preempts_per_ms` | 0.325 | 2.200 | 1.875 |
| `healthy_irq_deferred` | ist | `blocks_per_ms` | 0.200 | 1.750 | 1.550 |
| `healthy_irq` | ist | `blocks_per_ms` | 0.200 | 1.700 | 1.500 |
| `healthy_irq_deferred` | worker | `max_block_frac` | 1.000 | 0.000 | 1.000 |
| `healthy_irq_deferred` | worker | `max_run_frac` | 0.084 | 1.000 | 0.916 |
| `healthy_irq_deferred` | worker | `share_running` | 0.144 | 1.000 | 0.856 |
| `healthy_irq_deferred` | worker | `share_sem` | 0.750 | 0.000 | 0.750 |
| `healthy_irq_deferred` | ist | `max_block_frac` | 0.454 | 0.024 | 0.430 |
| `irq_overrun` | ist | `intr_masked_frac` | 0.404 | 0.000 | 0.404 |
| `healthy_irq` | ist | `max_block_frac` | 0.412 | 0.024 | 0.388 |
| `irq_overrun` | ist | `max_block_frac` | 0.309 | 0.000 | 0.309 |
| `irq_overrun` | ist | `share_intr` | 0.300 | 0.000 | 0.300 |
| `irq_overrun` | ist | `preempts_per_ms` | 0.300 | 0.000 | 0.300 |

## The shipped radar on aarch64le

The radar in `src/tracelens/ml/radar.json` was trained on x86 traces only, so this is a transfer test: it has never seen this machine.

| Scenario | Label | Radar (persistent unusual threads) |
|---|---|---|
| `healthy_irq` | healthy | ist (55/60) |
| `healthy_irq` | healthy | ist (53/59) |
| `healthy_irq` | healthy | ist (50/56) |
| `irq_overrun` | irq_handler_overrun | ist (53/58) |
| `irq_overrun` | irq_handler_overrun | ist (64/67) |
| `irq_overrun` | irq_handler_overrun | ist (75/75) |
| `healthy_irq_deferred` | healthy | ist (55/60), worker (90/100) |
| `healthy_irq_deferred` | healthy | worker (89/100), ist (51/60) |
| `healthy_irq_deferred` | healthy | worker (97/106), ist (54/62) |

**Radar on aarch64le: 3 of 3 planted-bug traces flagged on the thread that suffers, 6 false alarms on 6 healthy traces.**
