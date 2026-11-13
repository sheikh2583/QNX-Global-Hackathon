# Video script: TraceLens (under 3:00)

Recording: OBS screen capture at 1920×1080, terminal font 18 pt, browser zoom 125%. Every shot is a real run. If a shot can't be reproduced live on the QNX target, it isn't in the video. Voiceover is about 150 words per minute; the lines below come to about 2:50.

| Time | Shot | Voiceover |
|---|---|---|
| 0:00–0:10 | QNX 8.0 booting in QEMU (`tracelens target up`), then the TraceLens logo | "Real-time bugs on QNX are found today by an engineer staring at a timeline. TraceLens finds them, fixes them, and proves the fix on the real kernel." |
| 0:10–0:25 | A raw `traceprinter` dump scrolling: thousands of lines | "This is two seconds of an infusion pump's life, as the QNX kernel saw it. The bug is in here somewhere." |
| 0:25–0:55 | `tracelens capture … --analyze` on Z1; the CRITICAL finding; HTML report with the timeline | "One command captures the trace on QNX and analyzes it. Priority inversion: the dose controller, priority 50, waited `[TBD]` milliseconds on a semaphore held by the logger, while telemetry held the logger's CPU. Every claim links to the trace events that prove it." |
| 0:55–1:10 | Report: the QNX note; zoom on the timeline (logger READY, telemetry RUNNING) | "QNX mutexes inherit priority, so this can't happen with a mutex. A semaphore has no owner, so the kernel has nobody to boost." |
| 1:10–1:50 | `tracelens fix bugzoo/z1_infusion_pump`: Claude's diagnosis, the diff, qcc, five runs on QNX, then **VERIFIED**; `SUMMARY.md` | "Now the fix. Claude proposes a patch. TraceLens builds it with qcc, runs it on the QNX target five times, and compares before and after. VERIFIED means the inversion is gone in every run, nothing new appeared, and response times dropped from `[TBD]` to `[TBD]`. The AI proposes; the kernel decides." |
| 1:50–2:15 | Z3: `analyze` finds the Send/Reply deadlock; Perfetto view of both servers blocked | "QNX is built on synchronous message passing. Two servers that message each other deadlock. TraceLens builds the wait-for graph from the kernel's message events, per channel." |
| 2:15–2:35 | GitHub: a PR fails the TraceLens gate (SARIF alert on the trace line); Claude Code asking the MCP server "why did control miss its deadline?" | "It runs in CI and blocks a regression with a code-scanning alert. Claude Code can query your traces directly." |
| 2:35–2:52 | Real-world run on a QNX port `[TBD]`; the trust rules (deterministic detection, checked citations, no verdict on lossy traces) | "`[TBD: real-world result]`. Detection is deterministic, every citation is checked, and a lossy trace gets no verdict at all." |
| 2:52–3:00 | Repo URL, codelab URL | "TraceLens. Open source, with a forty-five minute codelab. Links below." |

## Before recording

- [ ] Every `[TBD]` filled from a real run, and the numbers match the on-screen output
- [ ] Each command run once off camera, so caches are warm (explanations are cached; the fix loop isn't)
- [ ] Terminal history cleared; no API key or account details visible
- [ ] Duration measured under 3:00 after editing
