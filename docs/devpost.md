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

Results on the bug zoo: `[TBD: detected 5/5 on real captures; 0 findings on reference fixes; fixed and verified N/5; fix rate with vs without the trace (ablation)]`

## How we built it

- **Target:** QNX SDP 8.0, the QEMU x86_64 Quick Start image, `procnto-smp-instr`, `tracelogger` in wide mode, `traceprinter`. Five C workloads with planted bugs, built with `qcc`, with hidden reference fixes.
- **Host:** a dependency-free Python core. The parser handles 32-bit counter wraps, cross-CPU reordering and missing clock rates. The model holds per-thread state and priority timelines, message pairing through COMM events, and integrity checks that detect dropped events.
- **AI:** Claude (`claude-opus-5-5`) through the Anthropic SDK with structured outputs. Detection is never delegated to the model.
- **Verification:** multi-run before/after comparison with a one-sided Mann-Whitney U test, because one run under nested virtualization proves nothing.
- **Hardening:** an internal "judge roast" ran adversarial traces against v0. Six of seven broke something (multi-core false positives, self-reported priorities, counter wraps). Each became a regression test.

## Challenges

- Making priority inversion detection correct on multi-core: interference only counts while the medium thread holds the low thread's CPU and the low thread is ready.
- Telling a semaphore used as a lock from one used as a signal.
- Not trusting one noisy run: the stack is Windows → WSL2 → KVM → QEMU → QNX. `[TBD: measured noise floor]`
- `[TBD: whatever the first real traces teach us]`

## Accomplishments

- A closed loop where the AI proposes and the real QNX kernel decides.
- Checked citations: the explanation can't point at events that don't say what it claims.
- A CI gate that refuses to pass or fail a lossy trace.

## What we learned

`[TBD after real runs]`

## What's next

Real-world runs on existing QNX ports (`[TBD: which, and what we found]`), more detectors (condvar misuse, sporadic-server budgets), and a native `.kev` reader so CI needs no license at all.

## Built with

QNX SDP 8.0 · QNX Neutrino (`procnto-smp-instr`, `tracelogger`, `traceprinter`, `qcc`) · QEMU · Python · Claude (Anthropic API) · MCP · Perfetto · GitHub Actions / SARIF

## Links

- Code: https://github.com/sheikh2583/QNX-Global-Hackathon
- Codelab: `[TBD: GitHub Pages URL]`
- Video: `[TBD: YouTube URL]`
