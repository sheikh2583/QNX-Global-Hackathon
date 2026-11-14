## Detection on QNX (10 runs per build, findings at or above `high`)

| Workload | Expected findings | Buggy build: detected | Reference fix: runs with findings | Lossy runs excluded | Before/after verdict |
|---|---|---|---|---|---|
| `z1_infusion_pump` | priority_inversion, deadline_miss | 10/10 | 0/10 | 0 | VERIFIED |
| `z2_brake_by_wire` | priority_inversion, deadline_miss | 10/10 | 0/10 | 0 | VERIFIED |
| `z3_sensor_fusion` | ipc_deadlock | 10/10 | 0/10 | 0 | VERIFIED |
| `z4_camera_pipeline` | mutex_contention, deadline_miss | 10/10 | 0/10 | 1 | VERIFIED |
| `z5_motor_encoder` | irq_handler_overrun | 10/10 (also: irq_latency) | 0/10 | 0 | VERIFIED |

### Healthy programs (must stay clean)

| Program | Command | Runs with findings | Lossy runs excluded |
|---|---|---|---|
| pidin_loop | `for i in 1 2 3 4 5 6 7 8 9 10; do pidin > /dev/null; done` | 0/10 | 1 |
| idle_system | `sleep 2` | 0/10 | 0 |
| shell_io | `for i in 1 2 3 4 5; do ls -lR /proc/boot > /dev/null; done` | 0/10 | 1 |
