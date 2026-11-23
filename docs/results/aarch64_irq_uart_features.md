# aarch64le against x86_64, feature by feature

`data/aarch64_irq_u`: 24 of 24 captures succeeded, 23 with the planted problem showing, 24 lossy. Reproduce with `python scripts/arch_compare.py --a data/aarch64_irq_u --b /mnt/x/Hackathons/QNX Global hackathon/data/real --label-a 'aarch64le' --label-b 'x86_64'`.

## Did each planted problem show up?

| Scenario | Label | Showed up on aarch64le | Rules that fired (HIGH+) |
|---|---|---|---|
| `healthy_irq` | healthy | yes | none |
| `healthy_irq` | healthy | yes | none |
| `healthy_irq` | healthy | yes | none |
| `healthy_irq` | healthy | yes | none |
| `healthy_irq` | healthy | yes | none |
| `healthy_irq` | healthy | yes | none |
| `healthy_irq` | healthy | yes | none |
| `healthy_irq` | healthy | yes | none |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun |
| `irq_overrun` | irq_handler_overrun | yes | irq_handler_overrun |
| `healthy_irq_deferred` | healthy | yes | none |
| `healthy_irq_deferred` | healthy | yes | none |
| `healthy_irq_deferred` | healthy | yes | none |
| `healthy_irq_deferred` | healthy | yes | none |
| `healthy_irq_deferred` | healthy | yes | none |
| `healthy_irq_deferred` | healthy | yes | none |
| `healthy_irq_deferred` | healthy | yes | none |
| `healthy_irq_deferred` | healthy | **no** | irq_handler_overrun |

## Median per feature

11 of 36 compared feature/thread pairs agree within 0.10. The widest gaps:

| Scenario | Thread | Feature | aarch64le | x86_64 | Gap |
|---|---|---|---|---|---|
| `healthy_irq_deferred` | ist | `preempts_per_ms` | 0.200 | 2.200 | 2.000 |
| `healthy_irq` | ist | `preempts_per_ms` | 0.250 | 2.250 | 2.000 |
| `healthy_irq_deferred` | ist | `blocks_per_ms` | 0.200 | 1.750 | 1.550 |
| `healthy_irq` | ist | `blocks_per_ms` | 0.250 | 1.700 | 1.450 |
| `healthy_irq_deferred` | worker | `max_run_frac` | 0.080 | 1.000 | 0.920 |
| `healthy_irq_deferred` | worker | `share_running` | 0.307 | 1.000 | 0.693 |
| `healthy_irq_deferred` | worker | `share_sem` | 0.653 | 0.000 | 0.653 |
| `irq_overrun` | ist | `share_intr` | 0.631 | 0.000 | 0.631 |
| `irq_overrun` | ist | `share_running` | 0.345 | 0.726 | 0.381 |
| `healthy_irq` | ist | `share_intr` | 0.917 | 0.588 | 0.329 |
| `irq_overrun` | ist | `intr_masked_frac` | 0.315 | 0.000 | 0.315 |
| `healthy_irq_deferred` | ist | `share_intr` | 0.898 | 0.601 | 0.297 |

## The shipped radar on aarch64le

The radar in `src/tracelens/ml/radar.json` was trained on x86 traces only, so this is a transfer test: it has never seen this machine.

| Scenario | Label | Radar (persistent unusual threads) |
|---|---|---|
| `healthy_irq` | healthy | ist (97/98) |
| `healthy_irq` | healthy | ist (94/95) |
| `healthy_irq` | healthy | ist (95/96) |
| `healthy_irq` | healthy | ist (96/96) |
| `healthy_irq` | healthy | ist (96/97) |
| `healthy_irq` | healthy | ist (95/96) |
| `healthy_irq` | healthy | ist (93/93) |
| `healthy_irq` | healthy | ist (95/95) |
| `irq_overrun` | irq_handler_overrun | ist (95/96) |
| `irq_overrun` | irq_handler_overrun | ist (94/95) |
| `irq_overrun` | irq_handler_overrun | ist (95/95) |
| `irq_overrun` | irq_handler_overrun | ist (93/94) |
| `irq_overrun` | irq_handler_overrun | ist (96/96) |
| `irq_overrun` | irq_handler_overrun | ist (95/96) |
| `irq_overrun` | irq_handler_overrun | ist (94/95) |
| `irq_overrun` | irq_handler_overrun | ist (98/98) |
| `healthy_irq_deferred` | healthy | worker (100/100), ist (94/95) |
| `healthy_irq_deferred` | healthy | worker (100/100), ist (97/97) |
| `healthy_irq_deferred` | healthy | worker (100/100), ist (95/96) |
| `healthy_irq_deferred` | healthy | worker (101/101), ist (96/97) |
| `healthy_irq_deferred` | healthy | worker (99/100), ist (96/97) |
| `healthy_irq_deferred` | healthy | worker (100/100), ist (96/96) |
| `healthy_irq_deferred` | healthy | worker (99/100), ist (93/94) |
| `healthy_irq_deferred` | healthy | worker (100/100), ist (95/95) |

**Radar on aarch64le: 8 of 8 planted-bug traces flagged on the thread that suffers, 16 false alarms on 16 healthy traces.**
