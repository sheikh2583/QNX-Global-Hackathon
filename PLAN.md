# TraceLens — Master Plan

> **The anchor document for this project.** Every work session starts by reading this file and ends by updating the **Status Log** (§14). If reality diverges from the plan, change the plan here — don't let it drift silently.

| | |
|---|---|
| **Hackathon** | QNX Global Hackathon 2026 (Devpost) |
| **Hard deadline** | **Dec 15, 2026 2:00 PM ET = Dec 16, 2026 1:00 AM Dhaka** |
| **Our submit target** | **Dec 10, 2026** (5 days of safety margin) |
| **Build window** | Nov 13 → Nov 30 (Claude builds; user ~5 h total) |
| **Category** | Developer Tooling & Host Tools |
| **Also targeting** | Grand Prize · Best use of QNX-specific Technologies · Best Codelab/Tutorial |
| **Target platform** | QNX SDP 8.0 (QNX Everywhere, non-commercial) on **QEMU x86_64**, host = Windows 11 + WSL2 Ubuntu |
| **Commitment** | One project. No exit. Blockers get rerouted (§11), never "stop". |

---

## 1. North Star

**TraceLens is an autonomous real-time debugging agent for QNX.**
It reads a QNX kernel event trace, **finds** the timing bug deterministically, **explains** it in plain English with evidence, **writes the fix**, rebuilds with `qcc`, redeploys to the QNX target, **re-traces, and proves the bug is gone** — then guards against its return in CI.

**Pitch (say this in the first 10 seconds of the video):**
> *"Real-time bugs on QNX are found today by an engineer staring at a timeline. TraceLens finds them automatically, fixes them, and proves the fix by re-tracing on the real QNX kernel."* (No duration claim until the loop is timed end to end on the target.)

**Why this wins** — one sentence per judging criterion:

| Criterion | Our answer |
|---|---|
| Technological implementation | Built on QNX-only internals: kernel event tracing (`tracelogger`/`.kev`), microkernel message passing (Send/Receive/Reply), thread states, priority inheritance semantics, `qcc`, `procnto-smp-instr`. The detectors encode QNX semantics that Linux tooling (sched_switch, PI futexes) does not model: ownerless semaphores, `_NTO_CHF_FIXED_PRIORITY` channels, IST interrupt masking, Send/Receive/Reply chains. |
| Design (complete product) | CLI + HTML report + CI gate + MCP server + Perfetto export + tutorial + one-command demo. Installs with `pip`. |
| Potential impact | QNX runs in 255M+ vehicles **(verify latest figure)**, medical devices, robots. Timing bugs there are safety bugs. Claim about System Profiler's analysis views **(verify in Momentics before saying anything)**; our pitch is the closed loop and the CI gate, not "nobody else analyzes". |
| Innovation & AI creativity | Closed-loop agent: AI proposes, **the real QNX kernel verifies**. AI never invents findings — detectors are deterministic; explanations may only cite events from their evidence pack (checked), and typed claim checks (thread/state/object per citation) are on the backlog — until then say "citations checked", not "verified". |

---

## 2. Prize Map

| Prize | Cash | How we compete for it |
|---|---|---|
| Grand Prize | $10,000 | The full closed loop, filmed end to end |
| Dev Tooling — winner / runner-up | $4,000 / $2,000 | The product itself |
| Best use of QNX-specific Tech | $3,500 | Message-passing wait-for graphs, priority-inheritance-aware detection, instrumented kernel, `qcc` loop |
| Best Codelab/Tutorial | $3,500 | "Find and fix your first QNX real-time bug with TraceLens" codelab (§8) |
| Honorable mention | $1,000 | Floor if we place but don't win |

**Open questions (user):** prize stacking rules (paste rules text) · prize payout setup (user, private).

---

## 3. Definition of Done (submission checklist)

Every item maps to a Devpost requirement or a judging criterion. Nothing ships until all are ✅.

- [ ] Public GitHub repo, **MIT license visible in the About panel**
- [ ] README names **QNX SDP 8.0, target QEMU x86_64, toolchain qcc / gcc 12 (verify exact)**, with build + run steps that a judge can follow (rewritten; run steps still (verify))
- [ ] README "**Evidence of QNX use**" section pointing at exact files, APIs and sample output (section written; add real capture output)
- [ ] `tracelens analyze` detects all 5 bug-zoo bugs **on real QNX captures** (committed as fixtures), **0 false positives** on the reference fixes and on a negative corpus of healthy QNX programs (sshd, io-sock, `pidin` loop). Synthetic traces are unit tests only, never headline numbers.
- [ ] `tracelens fix` autonomously fixes ≥ 4 of 5 bug-zoo bugs, each **verified by re-trace on QNX**
- [ ] HTML report, JSON output, CI exit codes, `tracelens compare` (multi-run before/after; replaces `diff`)
- [ ] GitHub Actions workflow green on committed fixture traces
- [ ] MCP server usable from Claude Code (built: `tracelens mcp`, 6 tools, stdio smoke-tested; register with `claude mcp add tracelens -- tracelens mcp` and demo on a real trace)
- [ ] Perfetto export opens in ui.perfetto.dev (built: `tracelens export`; open one file in the UI to confirm)
- [ ] Real-world run on an existing QNX port, written up
- [ ] Codelab published at a public URL (draft: `docs/codelab/index.md`; replace synthetic output with real captures, then enable GitHub Pages)
- [ ] YouTube video **< 3:00**, shows it running on the QNX target
- [ ] Devpost form submitted (category: Developer Tooling; codelab URL filled)

---

## 4. Architecture

```
┌──────────────────────── QNX 8.0 target (QEMU x86_64, procnto-smp-instr) ────────────────────────┐
│  bug-zoo workloads (C, qcc)        tracelogger  ──►  /tmp/run.kev                               │
│  TraceEvent() user markers         (ring / time-limited capture)                                │
│  sshd  ◄──────────────────────────────────────────────────────────────────────────────┐          │
└───────────────────────────────────────────────────────────────────────────────────────┼──────────┘
                                                                                        │ ssh / scp
┌──────────────────────────────── Host (WSL2 Ubuntu / Windows) ─────────────────────────┼──────────┐
│                                                                                       │          │
│  target/      ── QEMU lifecycle (mkqnximage), ssh, deploy, run, capture  ─────────────┘          │
│  ingest/      ── traceprinter → text  →  normalized Event stream (JSONL)                         │
│                  (fallbacks: on-target traceprinter, traceparser C helper, native .kev reader)    │
│  model/       ── per-thread state timeline, channel/connection map, mutex/sem ownership, IRQs    │
│  detectors/   ── deterministic rules → Findings (with evidence event IDs)                        │
│  explain/     ── Claude: Finding + evidence excerpt + source → explanation (citations validated)  │
│  fix/         ── agent loop: patch → qcc build → deploy → re-run → re-trace → re-detect → verdict│
│  report/      ── HTML (timeline + findings), JSON, SARIF*, exit codes, diff                      │
│  export/      ── Perfetto (Chrome trace JSON) exporter                                           │
│  mcp/         ── MCP server exposing traces, findings, target queries                            │
│  cli.py       ── tracelens analyze | explain | fix | diff | export | capture | mcp               │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
* SARIF = stretch; lets GitHub show findings as code-scanning alerts.
```

### Repo layout (target)

```
tracelens/
├─ README.md            LICENSE (MIT)        PLAN.md        CLAUDE.md
├─ pyproject.toml       (Python 3.11+, pip install -e .)
├─ src/tracelens/
│  ├─ cli.py
│  ├─ target/   qemu.py  ssh.py  capture.py  build.py
│  ├─ ingest/   traceprinter.py  events.py  kev_native.py (fallback)
│  ├─ model/    timeline.py  ipc.py  sync.py  irq.py
│  ├─ detectors/ base.py  prio_inversion.py  ipc_chain.py  mutex_contention.py
│  │             irq_latency.py  deadline.py
│  ├─ explain/  claude.py  prompts.py  citations.py
│  ├─ fix/      agent.py  patcher.py  verify.py  guardrails.py
│  ├─ report/   html.py  json_out.py  diff.py  templates/
│  ├─ export/   perfetto.py
│  └─ mcp/      server.py
├─ bugzoo/              C workloads with planted bugs + clean baseline + Makefile (qcc)
├─ fixtures/            committed .kev + traceprinter text for CI (no license needed in CI)
├─ tests/               pytest, runs on fixtures
├─ docs/codelab/        the tutorial
├─ demo/                one-command demo script, video storyboard
└─ .github/workflows/   ci.yml (analyze fixtures, fail on regression)
```

### Key technical decisions

| Decision | Choice | Why |
|---|---|---|
| Host language | Python 3.11 | Fast to build, judges can `pip install`, rich ecosystem (MCP SDK, Jinja2) |
| Target language | C, built with `qcc` | Native QNX; makes the fix loop real |
| Trace ingest | `traceprinter` text first | Already verified to exist on Win/Linux; fallbacks in §11 |
| Normalized format | JSONL `Event{id, t_ns, cpu, class, type, pid, tid, prio, state, args}` | Every finding cites `Event.id`s |
| Detection | Deterministic rules | Trustworthy, testable; AI can't hallucinate a bug that isn't in the trace |
| AI model | Claude via Anthropic SDK; model id configurable, default to the latest Claude model (`claude-opus-5-5` for explain and fix, effort `medium` for explain; `--model` overrides; explanations cached on disk so reruns and demos cost nothing) | Quality where it matters, cost where it doesn't |
| Report | Static HTML (Jinja2, inline SVG timeline) | Zero-server, attaches to CI artifacts, looks good in video |
| CI | GitHub Actions on committed fixtures | No QNX license needed in CI |

---

## 5. The Bug Zoo (planted, realistic, QNX-specific)

Each workload is a small C program modeled on a real embedded scenario, with a **buggy** variant, a **fixed** variant (ground truth), and `TraceEvent()` user markers for period start/end.

> **QNX nuance (verify on target):** QNX mutexes use **priority inheritance by default**, and message-passing servers **inherit the client's priority** unless the channel is created with `_NTO_CHF_FIXED_PRIORITY`. So naive "classic" inversion often *won't* happen on QNX — the realistic inversions come from **semaphores** (no owner → no inheritance) and **fixed-priority channels**. Detecting *that distinction* is exactly the QNX-specific depth judges reward.

| # | Workload (story) | Planted bug | Detector | Expected auto-fix |
|---|---|---|---|---|
| Z1 | **Infusion pump control loop** — 1 kHz high-prio control thread shares a sensor buffer with a low-prio logger, guarded by `sem_t`; a medium-prio telemetry thread hogs CPU | Priority inversion via semaphore (no inheritance) | `prio_inversion` | Replace `sem_t` with a `pthread_mutex_t` (inheritance on) |
| Z2 | **Brake-by-wire message chain** — controller → arbiter → actuator servers via MsgSend | Arbiter's channel created with `_NTO_CHF_FIXED_PRIORITY` at low prio → high-prio client starves behind it | `ipc_chain` (+ inversion over IPC) | Remove the flag / restore client-driven priority |
| Z3 | **Sensor fusion server pair** — two servers that each MsgSend to the other under a rare condition | Send/Reply deadlock cycle | `ipc_chain` (cycle in wait-for graph) | Break the cycle: reply-before-send / pulse instead of send |
| Z4 | **Camera frame pipeline** — 4 worker threads contend on one global mutex around a slow copy | Mutex contention hotspot causing missed frame deadlines | `mutex_contention` + `deadline` | Shrink critical section / per-worker buffers |
| Z5 | **Motor encoder ISR** — interrupt event handler thread does heavy work before re-arming | Interrupt-to-handler latency / handler overrun | `irq_latency` | Move work to a lower-prio worker; handler only acks + pulses |
| Z0 | **Clean baseline** — all of the above, fixed | none | all | must produce **zero findings** |

Deadlines are declared in `bugzoo/periods.yaml` (thread name → period, budget), and measured from `TraceEvent()` start/end markers.

---

## 6. Detector Specifications

All thresholds configurable in `tracelens.toml`. Every finding carries: `id, kind, severity, t_start, t_end, threads[], evidence_event_ids[], metrics{}`.

| Detector | Rule (sketch) | Key metric |
|---|---|---|
| **prio_inversion** | Thread H (prio pH) blocked (SEM / MUTEX / SEND / REPLY state) on a resource whose holder/server L has pL < pH, while some thread M with pL < pM < pH is RUNNING during the block, for > threshold | Inversion duration; M's preemption time |
| **ipc_chain** | Build a wait-for graph from SEND/REPLY-blocked states and channel→server mapping (ConnectAttach/ChannelCreate events, pid/chid). Report chains longer than N and any **cycle** (deadlock) | Chain depth, blocked time, cycle members |
| **mutex_contention** | Per sync-object: waiters, time spent in MUTEX state, hold times of owners | Wait time p50/p99, top contenders |
| **irq_latency** | INT_ENTR → handler-thread READY → RUNNING; handler run time before re-arm (InterruptUnmask) | Latency p50/p99/max, overruns |
| **deadline** | From period markers + `periods.yaml`: job release → completion vs budget | Miss count, worst lateness, jitter |

Validation: each detector has unit tests on fixture traces; Z0 baseline must stay clean (false-positive guard).

---

## 7. AI Design (trust is the feature)

**Explain**
- Input: one Finding + ±N surrounding events + relevant source snippet (if available).
- Output (JSON schema): `root_cause`, `mechanism`, `impact`, `fix_suggestion`, `citations[]` (event IDs).
- **Citation validator:** every cited ID must exist and be in the finding's evidence window; uncited causal claims → rejected and retried once, then marked "low confidence".

**Fix agent loop** (`tracelens fix --workload Z1`)
```
1. analyze  → findings F0
2. Claude   → unified diff restricted to bugzoo/<workload>/  (guardrail)
3. qcc build on host (cross-compile)          → fail? feed compiler errors back (max 3 tries)
4. deploy via scp, run workload on QNX, tracelogger capture
5. analyze  → findings F1
6. verdict: VERIFIED if target finding gone AND no new findings AND deadlines met
            else iterate (max 3), else REPORT-ONLY
7. emit evidence bundle: before/after report, diff, before/after metrics
```
Guardrails: patch scope allow-list, no changes to tests/detectors, max iterations, max tokens, full transcript saved for the video.

---

## 8. Codelab (Best Codelab/Tutorial — $3,500)

**Title:** *"Find, fix, and prove: your first QNX real-time bug with TraceLens"* — ~45 minutes.

1. Boot QNX 8.0 in QEMU (QNX Everywhere)
2. Build & run the infusion-pump workload (Z1) with `qcc`
3. Capture a kernel trace with `tracelogger`
4. Read it with `traceprinter`; understand thread states
5. `tracelens analyze` → priority inversion found; read the evidence
6. Learn *why* QNX's mutex priority inheritance would have prevented it
7. `tracelens fix` → watch the agent patch, rebuild, re-trace, verify
8. Add the CI gate to your own repo

Published as `docs/codelab/` (GitHub Pages) — URL goes in the Devpost form.

---

## 9. Schedule

Day 1 = Fri Nov 13. Milestones are **releases**: each is a complete, demoable product.

| Days | Dates | Phase | Deliverables | Exit criteria |
|---|---|---|---|---|
| 1–2 | Nov 13–14 | **P0 Foundation** | WSL2 Ubuntu on X:, QNX SDP 8.0 + QEMU image, QNX boots, ssh works, first `.kev` captured, `traceprinter` output on host, repo scaffold + MIT + CI skeleton | A real trace from QNX is readable as text on the host |
| 3–4 | Nov 15–16 | **P1 Trace pipeline** | `target/` (qemu, ssh, capture, build), `ingest/` → normalized JSONL, `model/` timelines + IPC map | `tracelens capture && tracelens dump` round-trips a live trace |
| 5–6 | Nov 17–18 | **P2 Bug zoo + detectors** | Z0–Z5 workloads (buggy + fixed), 5 detectors, pytest on fixtures | All 5 bugs detected, Z0 clean |
| 7 | Nov 19 | **P3 Explain + report → v0.1 "Floor"** | Claude explanations w/ citation validator, HTML report, JSON, exit codes, CI workflow green | **v0.1 tagged: a complete Dev Tooling entry** |
| 8–10 | Nov 20–22 | **P4 Autonomous fix loop → v0.2** | `fix/` agent with guardrails, verified fixes on ≥4/5 bugs, evidence bundles | **v0.2 tagged: Grand-Prize-class entry** |
| 11 | Nov 23 | **P5 Ecosystem** | MCP server, Perfetto export, `tracelens diff` | Claude Code can query a trace via MCP; trace opens in Perfetto |
| 12 | Nov 24 | **P6 Real-world hunt** | Run on an existing qnx-ports project (candidate: mosquitto under load), write-up | Real-world section in README |
| 13–14 | Nov 25–26 | **P7 Launch kit** | Codelab, README polish, demo script, video storyboard + recording, Devpost text draft | All Definition-of-Done items green except upload/submit |
| — | Nov 27 – Dec 9 | **Buffer / polish** | Absorb reroutes, harden, rehearse demo | — |
| — | **Dec 10** | **Submit** | User uploads video + submits | Devpost confirmation |
| — | Dec 16 01:00 Dhaka | Hard deadline | — | — |

---

## 10. Video Storyboard (< 3:00)

| Time | Shot | Line |
|---|---|---|
| 0:00–0:10 | Title over QNX booting in QEMU | The pitch (§1) |
| 0:10–0:30 | System Profiler-style raw timeline, confusing | "This is how real-time bugs are found today." |
| 0:30–1:00 | `tracelens analyze` on the infusion pump → finding + HTML report | "Priority inversion, 4.2 ms, here's the evidence." |
| 1:00–1:50 | `tracelens fix` live: patch → qcc → deploy → re-trace → **VERIFIED** | "The fix is proven on the real QNX kernel." |
| 1:50–2:15 | Deadlock cycle (Z3) graph + fix | QNX message-passing depth |
| 2:15–2:35 | CI run fails on a regression; MCP from Claude Code; Perfetto view | Product completeness |
| 2:35–2:55 | Real-world run on a QNX port; impact line | Impact |
| 2:55–3:00 | Repo URL, codelab URL | — |

Recording: screen capture (OBS) + AI or user voiceover. User uploads to YouTube.

---

## 11. Risk Register — reroutes, not exits

| Risk | Likelihood | Reroute | Cost |
|---|---|---|---|
| QEMU image won't run under WSL2 | Low | `mkqnximage` VMware/VirtualBox image on Windows | ½ day |
| Kernel isn't instrumented | Low–Med | Rebuild image with `procnto-smp-instr` | hours |
| `traceprinter` rejects license on host | Med | Run `traceprinter` on target, scp text back | 1 h |
| `traceprinter` blocked everywhere | Low | `traceparser` C helper built with `qcc` | 1 day |
| …and that too | Very low | Native `.kev` reader from `sys/trace.h` (bonus: license-free CI) | 2–3 days |
| QEMU timing too noisy for latency claims | Med | Make bugs gross (ms, not µs); report relative before/after; pin CPUs (runmask) | hours |
| Fix agent flaky on some bugs | Med | Narrow to reliable classes; human-approve mode for the rest | 1 day |
| Real-world hunt finds nothing | Med | Plant a regression in the real port; show the CI gate catching it | ½ day |
| API cost overrun | Low | Cache explanations, Sonnet for explain, cap iterations | — |
| Someone submits a similar idea | Med | Our moat is the verified closed loop + QNX-specific semantics; lead with it | — |
| Last-night submission failure | Med | Submit Dec 10 | — |

---

## 12. Roles

| Claude (autonomous) | User (~5 h total) |
|---|---|
| All code, workloads, tests, CI, docs, codelab, video script, Devpost text | myQNX account + **QNX Everywhere license** (30 min) |
| WSL/QEMU setup commands, target automation | Approve Windows admin prompts (5 min) |
| Running traces, debugging, iterating | QNX Software Center sign-in + installs, guided (1 h) |
| Keeping this PLAN.md current | `gh auth login` (5 min) |
| | Anthropic API key + $20–30 credit, set `ANTHROPIC_API_KEY` yourself (15 min) |
| | Approve repo going public (1 min) |
| | Record/approve voiceover, upload to YouTube (1 h) |
| | Submit Devpost form (30 min) |
| | Payout setup (private) + rules check (30 min) |

---

## 13. Working Agreement

- **Start of every session:** read `PLAN.md` → check §14 → continue from the first unchecked item of the current phase.
- **End of every session:** append to §14 (date, done, blocked, next).
- **Decisions** go in §15 with a one-line why.
- Commit small, commit often; tag `v0.1`, `v0.2`, `v1.0` at milestones.
- Anything unverified about QNX is marked **(verify)** until proven on the target.
- Ambitious but honest: no claim in the video or README that the tool can't reproduce live.

---

## 14. Status Log

| Date | Done | Blocked on | Next |
|---|---|---|---|
| 2026-11-13 | Idea locked (TraceLens, ambitious scope). Feasibility research: System Profiler only visualizes, no auto-detection or CI mode; `traceprinter` runs on Win/Linux with license key; QNX QEMU image needs Linux host → WSL2. Machine audited (C: low on space → everything on X:). PLAN.md written. | User: myQNX account + QNX Everywhere license | P0: install WSL2 Ubuntu on X: |
| 2026-11-13 | **Host core built ahead of P0** (user: skip install, build architecture first). Stdlib-only package `src/tracelens`: traceprinter parser (generic key:value, CPU attribution, 32-bit counter unwrap), TraceModel (state timelines, coid→server map, sync-object index), 5 detectors (priority inversion incl. semaphore / fixed-priority channel cases, Send/Reply deadlock + chains, mutex contention, IRQ latency/overrun, deadline misses), CLI (`analyze`/`dump`/`threads`/`synth`, CI exit codes), JSON + HTML report with state timeline. Synthetic twins of bug zoo Z0–Z5 + `fixtures/synthetic/`. **14/14 tests pass.** | Real traceprinter format still **(verify)** — parser built from docs; first real capture may need tweaks | P0 install (WSL2 + SDP + QEMU) to get a real trace; meanwhile: bugzoo C sources, GitHub Actions workflow |
| 2026-11-13 | **Bug zoo + CI.** `bugzoo/`: shared `common/tl.h` (runmask pinning, SCHED_FIFO, TraceEvent markers, cycle-accurate spin), 5 buggy workloads (Z1 semaphore inversion, Z2 `_NTO_CHF_FIXED_PRIORITY` channel, Z3 mutual MsgSend deadlock w/ 1 s TimerTimeout, Z4 global-mutex contention, Z5 IST work before InterruptUnmask) + 5 reference fixes (`bugzoo/reference/`, hidden from the fix agent), Makefile (qcc, x86_64 default), `run_traced.sh` (tracelogger -w), `tracelens.toml` deadlines. All 10 C files pass `gcc -fsyntax-only -Wall -Wextra` against QNX API stubs. **Detector upgrade:** deadlocks now found anywhere in the trace (time-overlapping wait-for cycles), incl. ones broken by timeouts. `.github/workflows/ci.yml`: tests on py3.11–3.13, fixture drift check, trace gate (clean passes, every bug fails), report artifacts. Gate simulated locally: all correct. 15/15 tests. | Not yet compiled with `qcc` or run on QNX; Z5 needs a suitable IRQ on QEMU **(verify)**; CI not yet run on GitHub (no repo yet) | P0 install → first real capture of Z1; then P3 explain (Claude) |
| 2026-11-13 | **Reference-fix timing audit + repo.** Checked each reference fix against the detector thresholds; three would not have produced a clean trace on QNX and are fixed: Z1 logger held the PI mutex 600 µs → control waited ~300 µs every period (200 waits / 2 s = `mutex_contention`) → snapshot under lock, flash write outside; Z4 4×1.4 ms of work on 2 CPUs → workers 3–4 finish ~2.6 ms after release even when fixed → work cut to 0.6 ms, `frame` budget 1.5 ms (buggy still misses: serialized 2.4 ms/period, ~75% contention share); Z5 pulse sent with priority -1 carried the IST's prio 60 to a worker on the IST's own CPU → 2 ms recompute would delay the next IRQ → explicit pulse prio 20, worker on CPU 1, coalesced pulses. Makefile rebuilt (`out/`, `ARCH=`, `hostcheck`); QNX API stubs committed in `bugzoo/hostcheck/`, new CI job type-checks all 10 C files (`-Wall -Wextra -Werror`, passes locally). git repo initialised, first commit. 15/15 tests. | Same as before: not compiled with `qcc` or run on QNX; pulse-priority semantics **(verify)**; synthetic Z4 twin still models 1.4 ms holds (shape only) | User: myQNX account + QNX Everywhere license → P0 install (WSL2 Ubuntu on X:, SDP 8.0, QEMU), first real Z1 capture. Meanwhile: P3 explain (Claude + citation validator) on synthetic traces |
| 2026-11-13 | **P0 host up + P3 explain built.** WSL2 Ubuntu 24.04 installed at `X:\WSL\Ubuntu-24.04` (WSL 2.7.3, `/dev/kvm` present, 24 vCPU, 7 GB RAM); `scripts/wsl_prep.sh` installed QEMU 8.2.2, libvirt, bridge-utils, JRE + SWT (Software Center GUI), build tools. `tracelens explain`: evidence packs (detector events + neighbours, tagged `[E<id>]`), `claude-opus-5-5` with JSON-schema output, cached system prompt, server-side refusal fallbacks; citation validator (ids must be in the pack, every causal step cites, at least one detector event) with one corrective retry; unverified explanations are shown and flagged, never hidden; disk cache by prompt hash. HTML report shows the explanation with clickable citations to the exact event lines; JSON carries it. 22/22 tests (fake client, no network). Not yet run against the real API. | User: myQNX account + QNX Everywhere license; QNX Software Center (Linux .run) inside WSL, install SDP 8.0 + `com.qnx.qnx800.quickstart.qemu`; create the WSL default user (own password); set `ANTHROPIC_API_KEY`. WSL RAM 7 GB vs VM default 4 GB **(verify enough)** | After install: `mkqnximage --run`, ssh in, check `procnto-smp-instr` + `tracelogger`, first real Z1 trace, tune parser. Meanwhile: run explain on all 5 synthetic bugs once a key is set, review output, tag v0.1 |
| 2026-11-13 | **Judge-roast hardening (fix order 1–4 + more).** Parser: stable time sort, wrap detection on any real backwards step (1.5 s gap across a wrap now parses as 1500 ms), CONTROL TIME high bits, missing clock rate is an error (`--cycles-per-sec` override), scheduler state-machine checks (thread on two CPUs, CPU switching without the old thread leaving) → lossy trace = exit 3 INCONCLUSIVE (`--allow-lossy`). Model: per-thread priority timeline from kernel THREAD/SCHED_SET events (+ snapshot seed); TL_META carries names only. Inversion: M counts only while RUNNING on L's CPUs with L READY, union of intervals (ratio ≤ 1), priorities compared at that instant (traced inheritance boost = no finding), semaphore lock vs signal. Contention: union share + p99, not absolute counts (2 s of the clean pattern = 0 findings). Deadlines: release-based (period grid or TL_RELEASE), jitter, overruns, skipped periods. Shared IRQ vectors. Explain: only verified results cached; context from same thread/object/CPU. Bug-zoo comments neutralised. 37/37 tests incl. 15 adversarial regressions. Overclaims removed from PLAN §1/§3. | Real-trace field names for every (verify); everything still synthetic | Same as before (user's QNX install), then the judge-roast backlog below |
| 2026-11-13 | **P1 capture pipeline + multi-run verdict (built ahead of QNX).** `target/`: SSH/SCP `Target` (throwaway-VM host-key handling, injectable runner), `capture()`: deploy binary → `pidin` snapshot → `tracelogger -w -s N -f` with the workload inside the window → fetch `.kev` → `traceprinter` on host if on PATH else on target. `tracelens capture BIN -- args --host IP [--analyze]` (host also from TRACELENS_TARGET or `[target]` in tracelens.toml). `ingest/pidin.py` tolerant parser; analyze/explain auto-load `<trace>.pidin.txt` (`--snapshot`); snapshot seeds base priority only for threads in the trace. `tracelens compare`: VERIFIED / NOT FIXED / INCONCLUSIVE (exit 0/1/3) over ≥5 clean runs a side. 49/49 tests incl. a fake-target end-to-end: a Z1 trace with no kernel prio and no TL_META is detected only with the snapshot. | All target commands **(verify)** on real QNX; user's QNX install | User: QNX install (steps given in chat). Then boot VM, `mkqnximage --getip`, `make` bug zoo with qcc, `tracelens capture … --analyze` on Z1 |
| 2026-11-13 | **P4 fix agent built (ahead of QNX); WSL finished.** `fix/`: `Workspace` sandbox + guardrails (only existing .c/.h files of the workload; no new files, no paths outside; all-or-nothing apply), `QccBuilder` (qcc -Vgcc_nto<arch>) and `HostCheckBuilder` (gcc + QNX stubs), `FixAgent` loop: N before-captures → targets = kinds in most runs → Claude (`claude-opus-5-5`, effort high, JSON schema: diagnosis + complete replacement files, cached system prompt, refusal fallbacks) → guardrails → build → N after-captures → `compare` verdict; compile errors, guardrail rejections and NOT FIXED reasons are fed back (max 4 attempts); INCONCLUSIVE stops (needs runs, not patches). Evidence bundle: before/after traces, per-attempt patch.diff, build.log, verdict.json, transcript, SUMMARY.md. `tracelens fix bugzoo/<w> --host IP [--context source-only] [--runs 5] -- args`. 57 tests (Linux) incl. fake closed loop: reference fix VERIFIED, compile error fed back, edit to ../common rejected, cosmetic patch NOT FIXED, source-only prompt hides findings, already-fixed workload makes no model call. WSL: libvirtd enabled, WSLg OK, TraceLens venv for user sheikh, tests + hostcheck pass on Linux. GitHub CI did not run: the GitHub account is locked for billing (user to fix). | QNX license not yet issued (myQNX License Manager empty); GitHub billing lock | User: wait for the QNX Everywhere license, download QNX Software Center 2.0.4 Linux, install SDP 8.0 + QEMU quick-start image; clear GitHub billing. Then: boot VM, qcc bug zoo, first real Z1 capture, first real `fix` run |
| 2026-11-13 | **P5 ecosystem + typed citations (ahead of QNX).** `tracelens export` → Chrome Trace JSON for ui.perfetto.dev: per-thread state slices with CPU and effective priority, TL markers and kernel calls as instants, per-CPU IRQ track, a 'TraceLens findings' track (severity, summary, metrics, evidence IDs). `service.py` query layer + `tracelens mcp` (MCP SDK 2.3 `MCPServer`, stdio): analyze_trace, get_finding, list_threads, thread_states, events, compare_traces; analyses cached per trace mtime; verified over real stdio with an MCP client. Explain now cites typed claims {event, thread, observed}; the validator checks thread and event class/kind against the model; evidence lines state each event's class/kind (prompt v2, old cache invalidated). 63 tests (+1 Linux-only). | Perfetto UI load not yet eyeballed; QNX license; GitHub billing lock (CI deferred by user) | Same QNX steps. Next build: COMM-event IPC pairing, codelab draft, demo script |
| 2026-11-13 | **COMM-event IPC + codelab draft.** Model: `message_target()` resolves a MsgSend* to (server pid, server thread, channel) from COMM SND_MESSAGE (rcvid, pid) + REC_MESSAGE (rcvid), falling back to in-trace ConnectAttach; `receive_channel()` tags RECEIVE waits with their MsgReceive chid; ConnectAttach chid kept. Detector: a cycle is a deadlock only if no member has a thread receiving on the channel the cycle calls. 3 new regressions (deadlock with no ConnectAttach in the trace; pool thread on another channel; REPLY-blocked client resolved to the exact server thread). `docs/codelab/index.md`: 10-step, ~45 min tutorial (boot QNX, build, capture, read, analyze, why inheritance, explain, fix + verdict, CI gate, MCP), QNX steps marked (verify), a no-QNX path from step 5. | COMM field names and all target commands unverified; QNX license; GitHub billing | QNX install; then replace codelab samples with real output; demo script |
| 2026-11-13 | **Target ops, SARIF, demo, README, launch drafts.** `tracelens target up|ip|check|down` (mkqnximage detached + IP polling; preflight over ssh: QNX uname, CPU count, instrumented kernel, tracelogger/pidin/traceprinter, a 1 s wide-mode test trace). `analyze --sarif` (SARIF 2.1.0, results at evidence trace lines, fingerprints). HTML report banner for lossy traces and parse notes. `demo/run_demo.sh` (offline tour on fixtures, verified in WSL; `--live` boots, checks, builds, captures, fixes). README rewritten (one-minute try, command table, QNX semantics, trust rules, bug zoo, Evidence of QNX use, run-on-QNX steps). Drafts: `docs/devpost.md`, `docs/video_script.md` with [TBD] slots for real numbers. pyproject licence → SPDX. 72 tests (+1 Linux-only). | QNX license; GitHub billing; all target paths (verify) | QNX install → `tracelens target up && target check`, then first real capture; fill [TBD]s |

### Judge-roast backlog (2026-11-13)

A technical roast ran 7 adversarial traces; 6 broke v0. Items 1–4 of its fix order are done (status log
row of 2026-11-13); the rest, in prize-money-per-hour order:

- [x] Parser: stable sort, any-backwards-step wrap detection + CONTROL TIME high bits **(verify field names)**,
      missing CYCLES_PER_SEC is an error, scheduler state-machine checks → lossy traces exit 3 (no verdict)
- [x] SMP-correct inversion (M RUNNING on L's CPUs while L READY, union of intervals); semaphore lock vs signal
- [x] Priority timeline from kernel events (THREAD `prio`, SCHED_SET) + optional snapshot; TL_META = names only
- [x] Rate/p99-based mutex contention with union share; release-based deadlines (period grid / TL_RELEASE),
      skipped periods, overruns; shared IRQ vectors
- [x] Bug-zoo sources neutralised (no comment names the bug); reference fixes stay hidden
- [x] `pidin` thread snapshot at capture start, auto-loaded as `<trace>.pidin.txt` (base priorities + names)
- [ ] **Real-trace check of every (verify)**: THREAD event `prio` field in wide mode, SCHED_SET args, CONTROL TIME
      fields, COMM event names, `pidin` column layout, `tracelogger -w -s -f` flags
- [ ] Fix-rate **ablation**: source only vs source + findings + trace. The switch exists (`tracelens fix --context source-only`); run both on all 5 workloads on QNX and publish the table
- [x] **N-run statistical verdict**: `tracelens compare --before … --after …` (≥5 clean runs a side, lossy runs
      skipped, findings must vanish in every after-run, no new kinds, one-sided Mann-Whitney U on per-job response)
- [ ] Measure the reference fixes' noise floor under WSL2→KVM→QEMU (`compare` of one build against itself) and
      set thresholds above it
- [x] Typed-claim citation checks: each citation = {event, thread, observed}; thread and event class/kind are checked against the trace (a claimed SEM that is really an IRQ is rejected and retried)
- [x] IPC pairing from COMM events: SND_MESSAGE rcvid/pid → REC_MESSAGE names the server thread; works for
      connections made before the capture; RECEIVE waits carry their channel, so a pool thread on another
      channel no longer hides a deadlock **(verify COMM field names)**
- [ ] Z5 interrupt source: dedicated QEMU serial port (stop its devc-ser driver), host streams bytes at a fixed rate;
      check whether QNX 8.0 prefers InterruptAttachThread() **(verify)**
- [ ] Negative corpus of healthy QNX programs, committed as real fixtures; must yield zero findings
- [ ] Time the fix loop end to end before any duration claim

---

## 15. Decision Log

| Date | Decision | Why |
|---|---|---|
| 2026-11-13 | Build TraceLens; single entry | Highest expected prize value; no hardware; 4 prizes from 1 entry |
| 2026-11-13 | QEMU only, no physical hardware | Speed; user in Dhaka; host tool category doesn't need hardware |
| 2026-11-13 | Ambitious scope: autonomous fix + verify loop | Aim at Grand Prize; floor protected by v0.1 milestone |
| 2026-11-13 | No exits — blockers are rerouted | User's call: full commitment |
| 2026-11-13 | Everything installs on X: | C: has ~8 GB free |
| 2026-11-13 | Detection deterministic, AI only explains/fixes, citations validated | Judge trust; avoids "AI wrapper" critique |
| 2026-11-13 | Core package is stdlib-only (AI/MCP as optional extras) | Judges and CI can run it anywhere with zero installs |
| 2026-11-13 | Synthetic traceprinter-format scenarios for every bug-zoo workload | Build and test detectors before QNX is installed; become regression fixtures |
| 2026-11-13 | Findings grouped per (victim, culprit, object), root causes sorted before symptoms | Readable reports; deadline misses point back to their cause |
| 2026-11-13 | Reference fixes must produce **zero** findings, checked by hand against detector thresholds until real traces exist | They define Z0 and score the fix agent; a noisy reference makes every verdict meaningless |
| 2026-11-13 | Bug-zoo C is type-checked in CI against committed QNX API stubs | Catches broken C (incl. agent patches) without a QNX license in CI |
| 2026-11-13 | Ubuntu 24.04 (not 22.04) as the WSL host | Supported SDP 8.0.2+ host and listed by the QEMU quick-start docs; newest LTS |
| 2026-11-13 | Explain uses `claude-opus-5-5` (effort medium) for every finding, cached | Explanations are short; the best model makes the demo; cache keeps reruns free |
| 2026-11-13 | Unverified explanations are rendered with a red 'NOT verified' tag instead of dropped | Honesty is the trust story; judges see the validator working |
| 2026-11-13 | Priorities come only from kernel events or a pidin snapshot, never from workload markers | Real programs don't print TL_META; inheritance is a priority change over time |
| 2026-11-13 | A lossy trace gets exit 3 (inconclusive), not pass/fail | A dropped event fakes a long wait; a wrong verdict on camera is worse than none |
| 2026-11-13 | Synthetic traces are unit tests only; headline accuracy comes from real captures + a negative corpus | Self-generated traces only prove the code agrees with our own model of QNX |
| 2026-11-13 | TraceLens runs inside WSL for capture (ssh/scp/qcc live there); Windows venv for analysis only | The QEMU guest is reachable from WSL; keeps the target tooling on one OS |
| 2026-11-13 | `compare` replaces `diff`; INCONCLUSIVE when before-runs show no problem | A fix is proven by distributions over runs, not one before/after pair; a noise-floor run must not read as a pass |
| 2026-11-13 | Fix agent returns complete replacement files, not unified diffs | Small files; whole files apply reliably; we generate the diff ourselves for the bundle |
| 2026-11-13 | Each fix attempt patches the ORIGINAL source, with feedback from earlier attempts | No compounding of bad edits; the transcript still carries what was tried |
| 2026-11-13 | MCP tools live in a plain `service.py`; the server is a thin MCPServer wrapper | Testable without the SDK; the same queries can back a future web UI or the codelab |
