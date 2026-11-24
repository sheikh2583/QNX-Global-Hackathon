## Detection on QNX (5 runs per build, findings at or above `high`)

| Workload | Expected findings | Buggy build: detected | Reference fix: runs with findings | Lossy runs excluded | Before/after verdict |
|---|---|---|---|---|---|
| `z5_motor_encoder` | irq_handler_overrun | 5/5 | 2/5 (irq_handler_overrun) | 0 excluded, 9 kept | NOT FIXED |
