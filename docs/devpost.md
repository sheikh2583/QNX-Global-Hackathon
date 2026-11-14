# Devpost submission draft: TraceLens

> Draft. Fill every `[TBD …]` from real QNX 8.0 runs before submitting; remove any claim we can't reproduce live.
> Category: **Developer Tooling & Host Tools**. Also eligible: Grand Prize, Best use of QNX-specific technologies, Best Codelab (codelab URL goes in its field).

**Tagline:** Find, fix, and prove real-time bugs on QNX.

## Inspiration

Real-time bugs are timing bugs. Every function can be correct while the system is late, because the wrong thread had the CPU at the wrong moment. On QNX the evidence is excellent: the instrumented kernel records every scheduling decision, message and interrupt. But reading that evidence is still manual work for an expert scrolling a timeline. We wanted the trace to tell you what went wrong, why QNX behaved that way, how to fix it, and whether the fix really worked.

## What it does

TraceLens is a host tool for QNX 8.0 that turns a kernel event trace into findings, explanations and verified fixes.

- **Finds** five classes of real-time bugs with deterministic detectors: priority inversion, Send/Reply deadlocks and blocking chains, mutex contention, interrupt-handler overruns, and deadline misses. Every finding cites the exact trace events that prove it.
- **Understands QNX.** QNX mutexes inherit priority by default, so most textbook inversions can't happen. TraceLens looks for the ones that can: ownerless semaphores and `_NTO_CHF_FIXED_PRIORITY` channels. It reads priorities from kernel events over time, so a traced inheritance boost is recognised. Message-passing deadlocks are found per channel, not just per process.
- **Explains** each finding with Claude. Every cited event comes with the thread and state or call it claims to be, and is checked against the trace; a failed check is retried, then shown as unverified.
- **Fixes and proves.** The fix agent patches the workload (only its own files), cross-compiles with `qcc`, runs it on the QNX target five times under `tracelogger`, and compares before and after. VERIFIED requires the finding to vanish in every run, no new findings, and statistically faster response times.
- **Fits the workflow:** HTML/JSON/SARIF reports, CI exit codes (including "inconclusive" for lossy traces), Perfetto export, and an MCP server so Claude Code can query traces.

Results on real QNX 8.0 (held-out run, 10 captures per build): every planted bug was caught in **10 of 10** runs, every reference fix was clean in **10 of 10**, and healthy system programs produced **0 findings in 30 runs**. All five fixes VERIFIED. `[TBD: fix-agent table from tracelens eval fix]`

## How we built it

- **Target:** QNX SDP 8.0 on a QEMU x86_64 VM built with `mkqnximage` (4 CPUs, KVM, in WSL2), `procnto-smp-instr`, `tracelogger` in wide mode, `traceprinter`. Five C workloads with planted bugs, built with `qcc`, with hidden reference fixes.
- **Host:** a dependency-free Python core. The parser handles 32-bit counter wraps, cross-CPU reordering and missing clock rates. The model holds per-thread state and priority timelines, message pairing through COMM events, and integrity checks that detect dropped events.
- **AI:** Claude (`claude-opus-5-5`) through the Anthropic SDK with structured outputs. Detection is never delegated to the model.
- **Verification:** multi-run before/after comparison with a one-sided Mann-Whitney U test, because one run under nested virtualization proves nothing.
- **Hardening:** an internal "judge roast" ran adversarial traces against v0. Six of seven broke something (multi-core false positives, self-reported priorities, counter wraps). Each became a regression test.

## Challenges

- Making priority inversion detection correct on multi-core: interference only counts while the medium thread holds the low thread's CPU and the low thread is ready.
- Telling a semaphore used as a lock from one used as a signal.
- Not trusting one noisy run: the stack is Windows → WSL2 → KVM → QEMU → QNX. Measured noise floor: timer wake-ups 1.1 to 1.4 ms late (the 1 ms tick plus virtualization), interrupt response p99 about 0.3 ms, and rare multi-millisecond host stalls (one 5.3 ms stall in 200 periods).
- The first real traces broke assumptions the synthetic ones never tested: a 64-bit timestamp format, QNX 8.0's own interrupt events (`INT_DELIVER`, `IST_ATTACH`), a release grid that drifted 0.05% against the trace clock, and planted bugs that only reproduced when the 1 ms tick fell in the right place.

## Accomplishments

- A closed loop where the AI proposes and the real QNX kernel decides.
- Checked citations: the explanation can't point at events that don't say what it claims.
- A CI gate that refuses to pass or fail a lossy trace.

## What we learned

- On QNX 8.0, timers fire on tick boundaries, so any race between releases closer than 1 ms is decided by where the tick falls. Reproducible timing bugs need whole-tick spacing.
- `ThreadCtl(_NTO_TCTL_RUNMASK)` on QNX 8.0 accepts one CPU or all CPUs, not a subset.
- Statistics need enough samples: a "p99" of seven waits is the maximum, and a rule built on it flagged healthy system programs.
- An evaluation harness can lie by omission: ours called a fix VERIFIED for a bug that never appeared in the "before" runs. Now the bug must reproduce first.

## What's next

Real-world runs on existing QNX ports (`[TBD: which, and what we found]`), more detectors (condvar misuse, sporadic-server budgets), and a native `.kev` reader so CI needs no license at all.

## Built with

QNX SDP 8.0 · QNX Neutrino (`procnto-smp-instr`, `tracelogger`, `traceprinter`, `qcc`) · QEMU · Python · Claude (Anthropic API) · MCP · Perfetto · GitHub Actions / SARIF

## Links

- Code: https://github.com/sheikh2583/QNX-Global-Hackathon
- Codelab: `[TBD: GitHub Pages URL]`
- Video: `[TBD: YouTube URL]`
