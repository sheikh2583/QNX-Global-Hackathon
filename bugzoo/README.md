# Bug zoo

Small, realistic QNX 8.0 workloads with **planted real-time bugs**. TraceLens must catch every one, stay silent on the reference fixes, and (from v0.2) fix each bug autonomously and prove it by re-tracing.

| Workload | Story | Planted bug | Detector |
|---|---|---|---|
| `z1_infusion_pump` | 1 kHz-class dose controller sharing a sensor buffer | Semaphore as a lock → priority inversion (no inheritance) | `priority_inversion`, `deadline_miss` |
| `z2_brake_by_wire` | Brake controller → arbiter server, plus diagnostics | `_NTO_CHF_FIXED_PRIORITY` channel → server runs below its client | `priority_inversion` (message channel), `deadline_miss` |
| `z3_sensor_fusion` | Two fusion servers that occasionally call each other | Mutual `MsgSend()` → Send/Reply deadlock (broken by a 1 s timeout) | `ipc_deadlock` |
| `z4_camera_pipeline` | 4 workers publishing tiles every 4 ms | 0.6 ms of work inside one global mutex (4 workers, 2 CPUs) | `mutex_contention`, `deadline_miss` |
| `z5_motor_encoder` | Encoder interrupt service thread | 2 ms of work before `InterruptUnmask()` | `irq_handler_overrun` |

Ground-truth fixes live in [`reference/`](reference/) (hidden from the fix agent).

## Build (host, QNX SDP 8.0)

```bash
source ~/qnx800/qnxsdp-env.sh
make            # out/<name> (buggy) and out/<name>_fixed (reference)
```

## Run under a trace (on the QNX target)

```bash
scp out/* run_traced.sh root@<qemu-ip>:/tmp/zoo/
ssh root@<qemu-ip> 'cd /tmp/zoo && ./run_traced.sh ./z1_infusion_pump -d 2'
scp root@<qemu-ip>:/tmp/tracelens/z1_infusion_pump.kev .
traceprinter -f z1_infusion_pump.kev > z1_infusion_pump.txt
tracelens analyze z1_infusion_pump.txt -c tracelens.toml --html z1.html
```

`z5_motor_encoder` needs `-i <irq>`. Plan: give QEMU a dedicated serial port, stop its `devc-ser*` driver on the target, attach to that port's IRQ, and stream bytes into it from the host at a fixed rate. Not the NIC: virtio-net likely uses MSI-X, shares work with io-sock, and WSL2 networking limits the packet rate. *(verify on the QEMU image, and whether QNX 8.0 prefers `InterruptAttachThread()`)*

## Notes

- Every thread is pinned (`ThreadCtl(_NTO_TCTL_RUNMASK)`) and runs `SCHED_FIFO`, so scheduling is reproducible on the 8-CPU QEMU guest.
- Workloads announce themselves with `TraceEvent()` user string events (`TL_META`, `TL_JOB_START`, `TL_JOB_END`). TraceLens uses them for thread names and deadlines only; priorities always come from kernel events.
- `main.c` comments describe what each program does, never the bug: the fix agent must find it from the trace.
- Status: all sources pass a host syntax check (`gcc -fsyntax-only -Wall -Wextra` against QNX API stubs). **Not yet built with `qcc` or run on QNX.**
