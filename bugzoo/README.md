# Bug zoo

Small, realistic QNX 8.0 workloads with **planted real-time bugs**. TraceLens must catch every one, stay silent on the reference fixes, and (from v0.2) fix each bug autonomously and prove it by re-tracing.

| Workload | Story | Planted bug | Detector |
|---|---|---|---|
| `z1_infusion_pump` | 1 kHz-class dose controller sharing a sensor buffer | Semaphore as a lock → priority inversion (no inheritance) | `priority_inversion`, `deadline_miss` |
| `z2_brake_by_wire` | Brake controller → arbiter server, plus diagnostics | `_NTO_CHF_FIXED_PRIORITY` channel → server runs below its client | `priority_inversion` (message channel), `deadline_miss` |
| `z3_sensor_fusion` | Two fusion servers that occasionally call each other | Mutual `MsgSend()` → Send/Reply deadlock (broken by a 1 s timeout) | `ipc_deadlock` |
| `z4_camera_pipeline` | 4 workers publishing tiles every 10 ms | 1.5 ms of work inside one global mutex (4 workers, 4 CPUs) | `mutex_contention`, `deadline_miss` |
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

`z5_motor_encoder` needs `-i <irq>`. Verified on the mkqnximage QEMU VM: use **IRQ 4**, the console UART (`/dev/ser1`), and drive it by writing to the console during the run (about 2,700 interrupts/s); `tracelens capture … --background '<writer loop>' -- -i 4 -d 2`, or `tracelens eval detect --irq 4` which takes the loop from `zoo.toml`. `/dev/ser2` (IRQ 3) produces no interrupts: QEMU has no second UART backend. The encoder IST shares IRQ 4 with `devc-ser8250`, so masking it also delays the console: the realistic cost of a slow handler.

## Notes

- Every thread is pinned (`ThreadCtl(_NTO_TCTL_RUNMASK)`) and runs `SCHED_FIFO`, so scheduling is reproducible on the 8-CPU QEMU guest.
- Workloads announce themselves with `TraceEvent()` user string events (`TL_META`, `TL_JOB_START`, `TL_JOB_END`). TraceLens uses them for thread names and deadlines only; priorities always come from kernel events.
- `main.c` comments describe what each program does, never the bug: the fix agent must find it from the trace.
- Status: all sources pass a host syntax check (`gcc -fsyntax-only -Wall -Wextra` against QNX API stubs). **Not yet built with `qcc` or run on QNX.**
