# Video script: TraceLens (under 3:00)

Recording: OBS screen capture at 1920×1080, terminal font 18 pt, browser zoom 125%. Every shot is a real run. If a shot can't be reproduced live on the QNX target, it isn't in the video. Voiceover is about 150 words per minute; the lines below come to about 2:50.

| Time | Shot | Voiceover |
|---|---|---|
| 0:00–0:10 | QNX 8.0 booting in QEMU (`tracelens target up`), then the TraceLens logo | "Real-time bugs on QNX are found today by an engineer staring at a timeline. TraceLens finds them, fixes the code, and proves the fix on the real kernel. No API keys, no cloud." |
| 0:10–0:25 | A raw `traceprinter` dump scrolling: thousands of lines | "This is two seconds of an infusion pump's life, as the QNX kernel saw it. The bug is in here somewhere." |
| 0:25–0:55 | `tracelens capture … --analyze` on Z1; the CRITICAL finding; HTML report with the timeline | "One command captures the trace on QNX and analyzes it. Priority inversion in 200 of 200 periods: the dose controller, priority 50, waited 5.4 milliseconds on a semaphore held by the logger, while telemetry held the logger's CPU. Every claim links to the trace events that prove it." |
| 0:55–1:10 | Report: the QNX note; zoom on the timeline (logger READY, telemetry RUNNING) | "QNX mutexes inherit priority, so this can't happen with a mutex. A semaphore has no owner, so the kernel has nobody to boost." |
| 1:10–1:50 | `tracelens fix bugzoo/z1_infusion_pump`: the remedy, the patch (`sem_t` → `PTHREAD_PRIO_INHERIT` mutex), qcc, five runs on QNX, **VERIFIED**; then the Z5 patch scrolling (unmask first, worker at priority 20) | "Now the fix. TraceLens knows the QNX remedy for each cause it proved: here, an owned, priority-inheriting mutex. It rewrites the code only after checking the semaphore really is used as a lock, builds it with qcc, runs it five times on QNX and compares. The inversion is gone in every run; p99 drops from 5.7 to 1.3 milliseconds. Four of five planted bugs, fixed and verified on the kernel." |
| 1:50–2:15 | Z3: `analyze` finds the Send/Reply deadlock; Perfetto view of both servers blocked | "QNX is built on synchronous message passing. Two servers that message each other deadlock. TraceLens builds the wait-for graph from the kernel's message events, per channel." |
| 2:15–2:35 | `tracelens remedy` on Z3: the two `MsgSend()` lines and the send-hierarchy guidance; then `scripts/check.sh` passing | "When a fix changes the protocol, TraceLens doesn't guess: it points at the exact lines and the QNX pattern. And every result is a committed real QNX trace you can re-check with one command." |
| 2:35–2:52 | The results table (README); the trust rules | "Ten of ten bugs caught per build, zero false alarms in eighty clean runs (fixed builds and healthy system programs). Detection is deterministic, a lossy trace gets no verdict, and a fix only counts if the kernel says so." |
| 2:52–3:00 | Repo URL, codelab URL | "TraceLens. Open source, with a forty-five minute codelab. Links below." |

## Before recording

- [ ] Every `[TBD]` filled from a real run, and the numbers match the on-screen output
- [ ] Each command run once off camera; the host idle while capturing (VM timing)
- [ ] Terminal history cleared; no account details visible
- [ ] Duration measured under 3:00 after editing
