## Deterministic fixes proven on QNX (5 runs before, 5 after)

| Workload | Remedy (chosen from the trace) | Verdict on the target | Evidence |
|---|---|---|---|
| `z1_infusion_pump` | auto: Replace semaphore 'buf_lock' (used as a lock) with a priority-inheriting mutex | **VERIFIED** | deadline_miss 100% -> 0% of runs; priority_inversion 100% -> 0% of runs; 'control' p99 5.74 -> 1.29 ms (budget 2.0) |
| `z2_brake_by_wire` | auto: Let the server inherit its clients' priority: drop _NTO_CHF_FIXED_PRIORITY | **VERIFIED** | deadline_miss 100% -> 0% of runs; priority_inversion 100% -> 0% of runs; 'brake' p99 6.75 -> 0.77 ms (budget 2.0) |
| `z3_sensor_fusion` | guided: Break the Send/Reply cycle with a send hierarchy | **GUIDED** | - |
| `z4_camera_pipeline` | auto: Shrink the 'store_lock' critical section: move memset, tl_spin_us outside the lock | **VERIFIED** | deadline_miss 100% -> 0% of runs; mutex_contention 100% -> 0% of runs; 'frame' p99 7.45 -> 2.99 ms (budget 4.0) |
| `z5_motor_encoder` | auto: Unmask IRQ first in main() and defer recompute_velocity_profile() to a worker thread | **VERIFIED** | irq_handler_overrun 100% -> 0% of runs; irq_latency 100% -> 0% of runs |

Automatic remedy for 4 of 5 workloads; **4 of 5 verified on the target**. Guided remedies list the exact source lines and the QNX fix.
