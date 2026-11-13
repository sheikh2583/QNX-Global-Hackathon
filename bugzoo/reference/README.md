# Reference fixes (ground truth)

Known-good versions of each bug-zoo workload. They are used to:

1. produce the **clean baseline traces** (Z0) that must yield zero findings, and
2. score the autonomous fixer: an agent fix counts as *verified* only when its re-trace is as clean as the reference.

**The fix agent never sees this directory.** Its patch scope is limited to `bugzoo/<workload>/`.

| Workload | Bug | Reference fix |
|---|---|---|
| z1_infusion_pump | Semaphore used as a lock: no owner, so no priority inheritance | `pthread_mutex_t` (priority inheritance is the QNX default) |
| z2_brake_by_wire | Server channel created with `_NTO_CHF_FIXED_PRIORITY` | Default channel: the server inherits the client's priority |
| z3_sensor_fusion | Both servers `MsgSend()` to each other | Strict send hierarchy: B notifies A with `MsgSendPulse()` |
| z4_camera_pipeline | 0.6 ms of work inside one global lock | Work on a private tile, lock only to publish (pointer swap) |
| z5_motor_encoder | 2 ms of work before `InterruptUnmask()` | Unmask immediately; pulse a lower-priority worker |
