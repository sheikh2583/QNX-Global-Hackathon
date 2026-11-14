# Find, fix, and prove: your first QNX real-time bug with TraceLens

**Time:** about 45 minutes · **Level:** you know C and basic OS ideas (threads, priorities, locks); no QNX experience needed.

> **Draft.** Steps marked **(verify)** have not yet been run end to end on a QNX 8.0 target. Sample output in sections 4 and 5 is from a real QNX 8.0 capture.

You will run a small infusion-pump controller on QNX 8.0 in a virtual machine, watch it miss its deadlines, find out why from a kernel trace, let an AI agent fix it, and prove the fix on the real kernel. Along the way you'll learn the one QNX rule behind the bug: **semaphores have no owner, so the kernel cannot lend them priority.**

## What you'll learn

- How QNX schedules threads, and what the thread states in a kernel trace mean
- How to capture a trace with `tracelogger` and read it
- Why a priority inversion happens with `sem_t` but not with a `pthread_mutex_t` on QNX
- How TraceLens detects the bug deterministically and cites trace events as evidence
- How the fix loop works: patch, `qcc`, run on QNX, re-trace, verdict over several runs
- How to stop the bug from coming back with a CI gate

## No QNX yet? Start at step 5

TraceLens ships with sample traces. If you just want to see the analysis, install TraceLens (step 2) and jump to step 5 using `fixtures/synthetic/z1_prio_inversion.txt`.

---

## 1. Boot QNX 8.0 in QEMU (10 min) **(verify)**

You need a Linux host with KVM. On Windows, use WSL2 with Ubuntu 24.04.

1. Get the free non-commercial **QNX Everywhere** license at <https://www.qnx.com/products/everywhere/>.
2. Download **QNX Software Center for Linux Hosts** from your myQNX account and run it:
   ```bash
   chmod +x qnx-setup-*-linux.run && ./qnx-setup-*-linux.run
   ~/qnx/qnxsoftwarecenter/qnxsoftwarecenter &
   ```
3. In the Software Center, sign in, add your license key, and install **QNX SDP 8.0** to `~/qnx800`, then **QNX SDP 8.0 Quick Start Target Image for QEMU**.
4. Boot the target:
   ```bash
   source ~/qnx800/qnxsdp-env.sh
   cd ~/qnx800/images/qemu/qemu
   mkqnximage --run
   ```
5. In a second terminal, get its address and log in:
   ```bash
   cd ~/qnx800/images/qemu/qemu && export QNX=$(mkqnximage --getip)
   ssh root@$QNX uname -a
   ```

**Check:** `uname` prints `QNX`. Also check the kernel can trace: `ssh root@$QNX 'ls /proc/boot | grep instr'` should show `procnto-smp-instr` **(verify)**.

## 2. Install TraceLens and build the workloads (5 min)

```bash
git clone https://github.com/sheikh2583/QNX-Global-Hackathon.git tracelens
cd tracelens
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[ai,mcp]"
source ~/qnx800/qnxsdp-env.sh
make -C bugzoo            # out/z1_infusion_pump ... built with qcc   (verify)
```

`bugzoo/z1_infusion_pump/main.c` is the program you'll debug. It has three threads, all pinned to CPU 0:

| Thread | Priority | Every 10 ms |
|---|---|---|
| `control` | 50 | reads the sensor buffer and computes the dose; **must finish within 1 ms** |
| `telemetry` | 20 | compresses and uploads readings (6 ms of CPU) |
| `logger` | 10 | appends the buffer to the black-box log |

Read `main.c` now. Can you spot the bug? Don't worry if not: the trace will show it.

## 3. Capture a kernel trace (5 min) **(verify)**

```bash
tracelens capture bugzoo/out/z1_infusion_pump --host $QNX -c bugzoo/tracelens.toml -- -d 2
```

This copies the binary to the target, records each thread's priority with `pidin`, runs the pump for 2 seconds inside a `tracelogger -w` capture (wide mode: full kernel-call arguments), and brings back three files in `captures/`:

| File | What it is |
|---|---|
| `z1_infusion_pump.kev` | the binary kernel trace |
| `z1_infusion_pump.txt` | the same trace as text, from `traceprinter` |
| `z1_infusion_pump.pidin.txt` | thread priorities at capture start |

## 4. Read the trace (5 min)

Open the `.txt` file. Each line is one kernel event (*synthetic sample*):

```
t:0x00000000 CPU:00 THREAD  :THRUNNING      pid:100 tid:1 prio:10
t:0x00000000 CPU:00 USREVENT:EVENT:100 STR:TL_META name=logger
t:0x000003e8 CPU:00 THREAD  :THREADY        pid:100 tid:1 prio:10
t:0x000003e8 CPU:00 THREAD  :THRUNNING      pid:100 tid:2 prio:20
```

- `t:` is the CPU cycle counter; `CPU:` the core.
- `THREAD` events are state changes: `RUNNING`, `READY` (wants the CPU but a higher-priority thread has it), and blocked states such as `SEM`, `MUTEX`, `SEND`, `REPLY`, `RECEIVE`.
- `KER_CALL` lines are kernel calls, such as `SYNC_SEM_WAIT` on a semaphore address.
- `USREVENT` lines are markers the program wrote with `TraceEvent()`: thread names and job start/end.

Get a per-thread summary:

```bash
tracelens threads captures/z1_infusion_pump.txt | grep -E 'thread |logger|telemetry|control'
```

```
thread                       prio   running     ready   blocked
logger                         10     4.3%    31.0%     0.0%
telemetry                      20    29.9%     0.3%     0.0%
control                        50     0.6%     0.0%    25.2%
```
*(real QNX 8.0 capture: [fixtures/real/z1_infusion_pump.txt.gz](../../fixtures/real/z1_infusion_pump.txt.gz); percentages are of the whole 4 s trace, the pump runs for 2 s)* The highest-priority thread spends 40 times longer **blocked** than running, and the lowest spends seven times longer **ready but not running** than running. Something is wrong.

## 5. Find the bug (5 min)

```bash
tracelens analyze captures/z1_infusion_pump.txt -c bugzoo/tracelens.toml --html z1.html
```

```
[CRITICAL] TL-001 Priority inversion: control waited on logger via a semaphore
    control (prio 50) was blocked 5.36 ms on a semaphore (0x0000005779b88020) released by logger (prio 10);
    for 5.35 ms of that, logger was ready but telemetry (prio 20) held its CPU. Seen 200x.
[CRITICAL] TL-002 Deadline misses in 'control'
    'control' missed its 1000 us budget in 200 of 200 jobs (measured from release); worst response 5.55 ms
    (5.6x budget); ... worst job: 0.00 ms late wake-up, 0.00 ms waiting for the CPU, 5.43 ms blocked, 0.12 ms running.
```
*(real QNX 8.0 capture)* Open `z1.html`: each finding lists the exact trace events that prove it, and the timeline shows the three threads. For a zoomable view, export to Perfetto and open the file at <https://ui.perfetto.dev>:

```bash
tracelens export captures/z1_infusion_pump.txt -c bugzoo/tracelens.toml
```

The deadline miss is listed after the inversion on purpose: it's the symptom, and the inversion is the cause.

## 6. Why QNX didn't save you (5 min)

Read the story in the evidence:

1. `logger` (10) wakes 2 ms before the period and takes the semaphore that guards the sensor buffer.
2. `telemetry` (20) wakes 1 ms later. It outranks `logger`, so it runs for 6 ms. `logger` is READY but never gets the CPU, so it can't release the semaphore.
3. `control` (50) wakes at the period, needs the buffer, and blocks on the semaphore.
4. `control`, the most urgent thread, effectively waits for `telemetry`, which it outranks. That is a **priority inversion**.

QNX prevents this for **mutexes**: `pthread_mutex_t` uses **priority inheritance by default**. While `control` waits, the kernel raises the owner (`logger`) to priority 50, so `telemetry` can't preempt it, and `control` waits only for the short critical section. A **semaphore** has no owner, so there is nobody to raise. Message-passing servers have the same protection (they run at their client's priority) unless the channel is created with `_NTO_CHF_FIXED_PRIORITY`.

**Try it:** what would change in the trace with a mutex? (Answer: `logger`'s THREAD events would show `prio:50` while `control` waits, and `telemetry` would stay READY.)

## 7. Let Claude explain it (optional, 3 min)

```bash
export ANTHROPIC_API_KEY=...        # your own key
tracelens explain captures/z1_infusion_pump.txt -c bugzoo/tracelens.toml \
    --source bugzoo/z1_infusion_pump/main.c --html z1-explained.html
```

Claude only *explains*: the bug was already found by deterministic code. Every claim it makes cites trace events as `{event, thread, observed}`, and TraceLens checks each one against the trace. An explanation that cites an event that isn't in its evidence, or misnames one ("logger released the semaphore" pointing at an interrupt), is rejected and retried, and shown as **NOT verified** if it still fails.

## 8. Fix it and prove it (10 min) **(verify)**

```bash
tracelens fix bugzoo/z1_infusion_pump -c bugzoo/tracelens.toml --host $QNX -- -d 2
```

The agent:

1. captures the original program 5 times; the findings present in most runs become the targets;
2. asks Claude for a patch, given the source, the findings and their trace evidence;
3. applies it to a sandbox copy. It may only change this workload's own `.c`/`.h` files, never the shared header, tests or detectors;
4. compiles it with `qcc`; compiler errors go back to Claude;
5. runs the patched program 5 times on QNX and captures each run;
6. compares before and after with `tracelens compare`: **VERIFIED** only if the inversion is gone in every run, no new findings appear, and `control`'s response times are within budget and significantly faster (Mann-Whitney U test).

Read `fixes/z1_infusion_pump-full/SUMMARY.md` for the diagnosis, the diff and the verdict. One run proves little on a virtual machine, which is why the verdict uses several.

## 9. Keep it fixed with a CI gate (5 min)

Commit a reference trace of the fixed program, and fail the build if a change brings the bug back:

```yaml
# .github/workflows/realtime.yml
name: realtime
on: [push, pull_request]
jobs:
  trace-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install "git+https://github.com/sheikh2583/QNX-Global-Hackathon.git"
      - run: tracelens analyze traces/pump.txt -c tracelens.toml --fail-on high
```

Exit codes: `0` clean, `1` findings at or above `--fail-on`, `2` bad input, `3` inconclusive (the trace dropped events, so no verdict).

## 10. Bonus: ask your trace questions from Claude Code

```bash
claude mcp add tracelens -- tracelens mcp
```

Then ask: *"In captures/z1_infusion_pump.txt, why did control miss its deadline? Cite the events."* Claude Code calls TraceLens's tools (`analyze_trace`, `get_finding`, `thread_states`...) and answers from the detector output.

## What you learned

- A trace shows *time*: who ran, who waited, and for whom. Timing bugs live there, not in the code alone.
- On QNX, use a **mutex** (priority inheritance) to protect shared data; a semaphore is for signalling.
- A fix to a timing bug is only proven by re-measuring on the real kernel, over several runs.

## Clean up

```bash
cd ~/qnx800/images/qemu/qemu && mkqnximage --stop
```
