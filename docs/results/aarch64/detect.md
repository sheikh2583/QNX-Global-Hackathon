## Detection on QNX (5 runs per build, findings at or above `high`)

| Workload | Expected findings | Buggy build: detected | Reference fix: runs with findings | Lossy runs excluded | Before/after verdict |
|---|---|---|---|---|---|
| `z1_infusion_pump` | priority_inversion, deadline_miss | 4/4 | 0/4 | 12 | INCONCLUSIVE |
| `z2_brake_by_wire` | priority_inversion, deadline_miss | 5/5 | 2/5 (deadline_miss) | 7 | NOT FIXED |
| `z3_sensor_fusion` | ipc_deadlock | 5/5 | 0/5 | 6 | VERIFIED |
| `z4_camera_pipeline` | mutex_contention, deadline_miss | 5/5 | 1/5 (deadline_miss) | 4 | NOT FIXED |
| `z5_motor_encoder` | irq_handler_overrun | skipped: needs --irq (interrupt source) | | | |

### Healthy programs (must stay clean)

| Program | Command | Runs with findings | Lossy runs excluded |
|---|---|---|---|
| pidin_loop | `for i in 1 2 3 4 5 6 7 8 9 10; do pidin > /dev/null; done` | 0/0 | 10 |
| idle_system | `sleep 2` | 0/0 | 10 |
| shell_io | `for i in 1 2 3 4 5; do ls -lR /proc/boot > /dev/null; done` | 0/0 | 10 |
