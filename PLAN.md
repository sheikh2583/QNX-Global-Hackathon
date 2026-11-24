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

**TraceLens finds, fixes and proves real-time bugs on QNX, with no API keys and no cloud** (user decision 2026-11-14). Phase 6 added learning from traces, within that rule: the models are JSON files scored by the standard library, they never fail a build and never write a patch (docs/ml/DESIGN.md).
It reads a QNX kernel event trace, **finds** the timing bug deterministically, maps the proven root cause to a **QNX-specific source fix** (applied only when its safety preconditions hold, otherwise exact guidance), rebuilds with `qcc`, redeploys to the QNX target, **re-traces, and proves the bug is gone** over several runs, fixing again if the re-trace shows a next cause.

**Pitch (say this in the first 10 seconds of the video):**
> *"Real-time bugs on QNX are found today by an engineer staring at a timeline. TraceLens finds them, fixes the code, and proves the fix on the real QNX kernel. No API keys, no cloud."* (No duration claim until the loop is timed end to end on the target.)

**Why this wins** — one sentence per judging criterion:

| Criterion | Our answer |
|---|---|
| Technological implementation | Built on QNX-only internals: kernel event tracing (`tracelogger`/`.kev`), microkernel message passing (Send/Receive/Reply), thread states, priority inheritance semantics, `qcc`, `procnto-smp-instr`. The detectors encode QNX semantics that Linux tooling (sched_switch, PI futexes) does not model: ownerless semaphores, `_NTO_CHF_FIXED_PRIORITY` channels, IST interrupt masking, Send/Receive/Reply chains. |
| Design (complete product) | CLI + HTML/JSON/SARIF reports + exit codes + Perfetto export + `remedy` (fix without a target) + tutorial + one-command demo. Installs with `pip`, stdlib only. |
| Potential impact | QNX runs in 255M+ vehicles **(verify latest figure)**, medical devices, robots. Timing bugs there are safety bugs. Claim about System Profiler's analysis views **(verify in Momentics before saying anything)**; our pitch is the closed loop and the CI gate, not "nobody else analyzes". |
| Innovation | A closed loop in which nothing is guessed: the trace proves the cause, a QNX-specific rewrite fixes it (preconditions checked in the code), and **the real QNX kernel decides** over several runs. Real result: 4/5 planted bugs fixed automatically and VERIFIED on QNX 8.0; the 5th gets exact guidance. |

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
- [ ] README names **QNX SDP 8.0, target QEMU x86_64, toolchain qcc / gcc 12.2.0 (verified)**, with build + run steps that a judge can follow (rewritten; run steps still (verify))
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

## 7. Fix design (trust is the feature)

> Superseded the AI design on 2026-11-14 (user: "I don't want to depend on an API key ... solve real problems").
> Claude/Gemini explain + fix, the MCP server and the CI configs were deleted.

**Remedies** (`src/tracelens/remedy/`): one rule per root cause the detectors prove. Automatic only when
the rule has checked its preconditions in the source; otherwise guidance with exact file:line.

| Root cause | Remedy | Automatic when |
|---|---|---|
| semaphore used as a lock | `sem_t` → `PTHREAD_PRIO_INHERIT` mutex | init 1, wait+post in the same functions, no other uses |
| `_NTO_CHF_FIXED_PRIORITY` | drop the flag | flag in a `ChannelCreate()` expression |
| IST work before `InterruptUnmask()` | unmask first; pulse-driven worker below every interrupt thread in the trace; start before attach, stop after detach | work uses no locals, no device access after it |
| private work in a contended lock | move statements touching no shared data (incl. aliasing pointers) out | no return/break/goto; static data only |
| mutual `MsgSend()` | guided: send hierarchy | never (protocol change) |

**Fix loop** (`tracelens fix`, `src/tracelens/fix/engine.py`)
```
1. N before-captures → targets = finding kinds in >= 60% of runs
2. remedies on a sandbox copy (only the workload's own .c/.h)
3. qcc build
4. N after-captures → compare: VERIFIED / NOT FIXED / INCONCLUSIVE
5. NOT FIXED → diagnose the patched build's traces (incl. MEDIUM findings), fix again (max 3 rounds)
6. evidence bundle: per-round patch.diff, build.log, verdict.json, before/after traces, SUMMARY.md
```

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
| 2026-11-13 | **Evaluation harness.** `bugzoo/zoo.toml` manifest (expected finding kinds and args per workload, z5 `{irq}`, `[negative.*]` healthy target commands). `tracelens eval detect`: buggy and reference builds × N runs, healthy commands × N; per workload recall, unexpected kinds, reference false positives, lossy exclusions, before/after verdict → `docs/results/detect.md|json`. `tracelens eval fix`: FixAgent per workload × {full, source-only} sharing one before-set → `docs/results/fix.md|json` with a Verified totals row. `capture --command` traces programs already on the target. 5 tests with a fake target (incl. a reference that still has the bug → NOT FIXED). | QNX license | After QNX: `make -C bugzoo`, `tracelens eval detect --runs 5`, then `eval fix`; numbers go into README/Devpost/video [TBD]s |
| 2026-11-14 | **QNX SDP 8.0 installed; first real qcc build.** QNX Software Center 2.0.4 (Linux) installed at `~/qnx/qnxsoftwarecenter` (makeself MD5 verified); GUI unusable under WSLg copy mode, so `scripts/qnx_install.sh` drives `qnxsoftwarecenter_clt` (hidden password prompt; Named-User license needs the key via `-addLicenseKey`, `-syncLicenseKeys` fetched nothing). SDP 8.0 at `~/qnx800` (3.6 GB). **Verified:** qcc targets gcc **12.2.0** (`gcc_ntox86_64`); `mkqnximage` at `host/common/bin`; host-side `traceprinter` present; **all 10 bug-zoo programs (5 buggy + 5 reference) compile with `-Wall -Wextra` and zero warnings** into QNX ELF binaries (`ldqnx-64.so.2`), confirming the APIs used (TraceEvent, MsgSendPulse, InterruptAttachEvent, _NTO_CHF_FIXED_PRIORITY, ThreadCtl...). | QEMU Quick Start image still installing | `tracelens target up` + `target check`, first real Z1 capture |
| 2026-11-14 | **FIRST REAL QNX TRACES.** Own QEMU VM via `mkqnximage` (4 CPU, 2 GB, KVM, default image = `procnto-smp-instr` + tracelogger + pidin + sshd, root SSH key) instead of the 4-part Quick Start download (part 0 only; CLI crash). Host fixes (user ran the sudo parts): bridge helper setuid, libvirt `default` net restarted after a stale virbr0. `tracelens target check` PASS (4 CPUs, instr kernel, 1 s wide trace 120 KB). **Real-target findings fixed:** header `TRACE_CYCLES_PER_SEC`; quoted `STR:"…"`; `sync_p` (alias to sync); column-0 continuation keys; `key = value` args; PROCTHREAD_NAME thread names; base prio = longest held (threads start at 10 then setschedparam); tracelogger needs `-n 0` (default 32 iterations) + `-k 32`; `pidin info` lists ProcessorN lines; `wc -c` for size; CLI `--` split (options after the binary); `capture --analyze` sarif bug; IP from libvirt lease file (`mkqnximage --getip` hangs). **Deadline false positive found and fixed:** rigid release grid + 0.05% clock drift gave 127/200 misses; Theil-Sen-fitted grid gives the true 3/200. Late jobs now broken down (late wake-up / ready / blocked / running); misses that are all late wake-ups on an idle CPU = platform timer latency → MEDIUM. **Result:** real Z1 buggy → CRITICAL semaphore inversion (8.05 ms block, telemetry held logger's CPU 8.04 ms) + HIGH deadline (worst job 8.05 ms blocked), exit 1; real Z1 reference fix → no inversion, one MEDIUM 1.26 ms late wake-up on idle CPU (noise floor ≈ 1/200), exit 0. Real fixtures `fixtures/real/*.txt.gz` + pidin snapshots; `tests/test_real_qnx.py`; CI gate runs them. `scripts/qnx_vm.sh`. 82 tests. | Quick Start image incomplete (not needed); Z2–Z5 not yet captured | Capture Z2–Z5 buggy+fixed, then `tracelens eval detect --runs 5`; real `compare`; first real `fix` run (needs ANTHROPIC_API_KEY) |
| 2026-11-14 | **Real Z2–Z4 (user chose to stay on the mkqnximage VM over the Quick Start image).** **QNX 8.0 findings:** `ThreadCtl(_NTO_TCTL_RUNMASK)` accepts one CPU or all CPUs, EINVAL for subsets (0x3, 0x6; also via GET_AND_SET_INHERIT) → Z3/Z4 use `TL_ALL_CPUS`; clock tick fixed at 1 ms (`ClockPeriod` set → Not supported) and absolute sleeps wake ~1.1–1.4 ms late → Z4 redesigned to 10 ms period, 1.5 ms work, 4 ms budget. **Tool bugs found on real data and fixed:** release grid now per (job name, thread) stream (four Z4 workers share 'frame'; one grid gave 1996/2000 false misses); wrapped quoted-string lines; deadlock title uses thread names when forked processes share a name; stale-binary trap (`make -B`). **Results (1 run each):** Z2 buggy CRITICAL inversion via message channel 200/200 + deadline, fix 0 findings; Z3 buggy CRITICAL deadlock 1001 ms (timeout-broken), fix 0 findings; Z4 buggy HIGH contention + CRITICAL deadline, fix only a MEDIUM kernel-space mutex. All 8 real pairs: buggy exit 1, fix exit 0, 0 unparsed lines. Fixtures `fixtures/real/` (2.1 MB gz), 12 real tests, CI loops all pairs, README results table. 90 tests. | Z5 needs an interrupt source in the VM | Z5 IRQ source; `tracelens eval detect --runs 5`; first real `fix` (needs ANTHROPIC_API_KEY) |
| 2026-11-14 | **Z5 on real QNX: all 5 bugs verified.** QNX 8.0 interrupt events (verified): `INTERRUPT :INT_DELIVER intr_id:0x4(4)` (no INT_ENTR) and `SYSTEM :IST_ATTACH pid tid intr_id … ist_prio` → model `irq_handlers`, detector reads both formats. IRQ source: console UART IRQ 4 driven by writing /dev/ser1 (~2,700 irq/s; ser2/IRQ 3 has no QEMU backend). `capture --background`, zoo.toml `background`, eval/fix pass it. Real Z5 buggy: HIGH overrun (masked ≤2.38 ms) + slow response (p99 2.05 ms), exit 1; fixed: 0 findings, p50 63 µs / p99 315 µs (noise floor) → bug-zoo `irq_max_latency_us` 1000. Lossy rule now rate-based (any violation voids a trace < 100k events; above, > 1 per 100k): real Z5 had 1 violation in 245,085 events. 16 real tests, 6.2 MB fixtures, CI loops all 5 pairs. `tracelens eval detect --runs 5` running on the VM. | — | eval results into README/Devpost; first real `fix` (needs key) |
| 2026-11-14 | **Held-out eval on real QNX: 10/10 everywhere.** `tracelens eval detect --runs 10 --irq 4`: Z1–Z5 buggy caught 10/10, reference fixes 0/10 flagged, all VERIFIED; healthy programs 0/30; 3 of 133 captures lossy (replaced). Calibration runs (3 × 5 runs, kept in captures/eval_calib) exposed: **workloads** Z1/Z2 releases < 1 tick apart (3/5, 4/5) → whole-tick spacing; Z3 mutual MsgSend raced (1/5, 0/5) → process-shared barrier; **tool** kernel-space mutex (procnto proc_pool_thread) failed Z4's fix → LOW; release-grid numbering moved by one >½-period-late job (199/200 false misses) → floor vs median phase; late wake-up while only lower-prio threads ran → platform latency; sparse p99 (7 waits) → HIGH needs ≥10% share or ≥3 long waits; rare marginal deadline miss (1/800, +2%) → MEDIUM (`deadline_marginal_rate`, 0 = hard RT); isolated IRQ overrun (1/9686) → MEDIUM; **harness** VERIFIED for a bug that never reproduced → needs ≥60% before-rate; lossy runs now replaced; clear error when traceprinter is missing. Fixtures Z1–Z3 refreshed from the new sources; results in docs/results/; README results + 'what real QNX taught the tool'; Devpost TBDs filled (except fix table); codelab §4–5 show real output. Healthy-program captures committed (`fixtures/real/healthy_*`, CI gate). 107 tests. | — | first real `tracelens fix` + `eval fix` (needs ANTHROPIC_API_KEY); codelab end-to-end pass on the VM |
| 2026-11-14 | **No AI, no CI: deterministic fix engine, 4/5 VERIFIED on QNX.** User decision: no API-key dependency, no CI pipelines, solve real problems. Deleted Claude/Gemini explain+fix, `llm.py`, MCP server, `service.py`, CircleCI + GitHub workflow; `scripts/ci.sh` → `scripts/check.sh` (local). New `remedy/` (C toolkit: masking, statements, declarations, alias taint; 5 rules) + `fix/engine.py` (multi-round) + `tracelens remedy` (no target). Real QNX (`eval fix --runs 5`): Z1 PI mutex VERIFIED (inversion 5/5→0/5, p99 5.74→1.29 ms, budget 2 ms); Z2 flag drop VERIFIED (misses 1000→0, p99 6.75→0.77 ms); Z4 lock shrink VERIFIED (p99 7.45→2.99 ms); Z5 IST defer VERIFIED (p99 masked 2.41→0.24 ms, response 2.08→0.57 ms); Z3 GUIDED. **Found on the way:** first Z5 remedy started the worker after InterruptAttachEvent (20 ms spikes) at prio IST-1 → start before attach, prio below the lowest interrupt thread in the trace (virtio 21 → 20, matches the hand-written reference); eval fix did not replace lossy before-captures; at Z1's 1 ms budget the mutex left a ~1 ms critical-section wait (round 2 fixes it) and VM jitter decided the verdict → budget 2 ms per the slack rule, Z1 detect re-run (10/10, 0/10); host load during captures inflates VM timings → measure with the host idle. `docs/results/fix.md` + per-workload bundles (patch, summary, verdict). README, codelab (mkqnximage VM, remedy step), Devpost, video script rewritten. 113 tests (Linux). | — | Commit; codelab end-to-end run as a new user; record video; real-world QNX software beyond the bug zoo |
| 2026-11-14 | **Codelab verified end to end + before/after fix reports.** Ran every codelab command in a fresh clone on the VM (target check, qcc build, capture, threads, analyze, export, remedy, fix, gate): all work; `fix` went VERIFIED in 2 rounds (round 1 PI mutex: inversion gone, p99 7.18→2.48 ms > 2 ms budget, NOT FIXED; round 2 critical-section shrink: p99 0.54 ms, 0 misses). (verify) markers removed; step 1 now the mkqnximage VM. New `report/fix_html.py`: per-fix `report.html` (workload threads before/after on one scale, mid-run windows, verdict KPIs, remedy rationale, coloured patch), written by every `tracelens fix`, re-rendered by `tracelens fix-report`; generated for all 5 bundles + the codelab 2-round bundle (docs/results/fixes/). Results page published as a private Artifact for the user. Found: py3.11 nested-quote f-string; report import now inside the engine's try. | GitHub push needs the user's OK; results page is private until shared | Push; record the video from the codelab flow; Devpost form |
| 2026-11-14 | **Hosted demo for Render (user's choice).** `tracelens serve` (stdlib http.server): results landing page + 'try it' panel, /trace/<name> analysis, /remedy/<w> fix plan + patch, /fix/<w> recorded before/after proof, /upload (traceprinter text or .gz, optional C source → patch, optional toml; 12 MB cap, one analysis at a time), /healthz; CSP + nosniff headers; path whitelist. Render sim showed 777 MB peak (free tier 512 MB) and 5–7 MB Z5 pages → (1) HTML timelines downsampled to one rect per pixel column per thread (Z5 report 5,044 KB → 78 KB, every TraceLens report benefits), (2) `serve --prebuild` renders committed traces at deploy time, one per subprocess (peak 392 MB, 45 s); server RSS 23 MB, pages < 10 ms. `render.yaml` Blueprint. `target up` now reuses a running VM (never a 2nd QEMU on one disk). demo/run_demo.sh verified offline (8 s) and live (2 min, VERIFIED). | Render deploy needs the repo pushed + user's Render account; PYTHON_VERSION value (verify) | Push; user deploys Blueprint; put the URL in Devpost |
| 2026-11-15 | **Consumer web app + guided demo (user: 'UI is shit… consumer based… judges should have a demo on a trace').** New `app.py` design system (IBM Plex, teal, light/dark, mobile-safe) and pages: home (problem → 3 steps → 5 problem types → before/after dumbbell chart from docs/results), /demo (7-step tour on the real Z1 trace: program, raw kernel events, findings with zoomed 'moment it happened' timelines, patch, 2-round proof with before/after timelines, reliability stats + chart + tables + method), /analyze (upload + how to record with tracelogger/traceprinter), /examples + /example/<w> plain-language reports with patch download, /guide (reading results). Developer warnings translated (lossy → 'recording incomplete, record again') or moved under 'Technical details'; causes listed before symptoms. Prebuild now renders example pages + demo; Render sim: build 18 s (peak 392 MB), 10 routes ~1 ms, server 23 MB. Folder renamed to 'QNX Global hackathon' (venv reinstalled). | — | User deploys on Render; record video from /demo |
| 2026-11-15 | **Phase 6 started: ML (user: 'take this to a new level').** Analysis in docs/ml/DESIGN.md; scaffold: tlgen generator (13 scenarios), `tracelens data plan|collect|features`, features (17), radar v0 + `analyze --radar`, tree JSON inference, sklearn trainer, `tracelens ml train-radar|train-classifier|eval`. First experiment on real traces: radar fitted on 5 healthy traces flags Z1-Z4 buggy on the right threads, 0/1,420 windows on held-out pidin loop, but a false alarm on the healthy Z5 fix (no healthy IRQ program in training) -> healthy_irq/irq_overrun scenarios. Fixed on the way: MAD scale saturates on sparse features; same-process exclusion hid inversions; thread start/exit windows. Also built today: live fix view (`tracelens fix --watch`, events.jsonl, hosted replay) and `target up` fixes (detached QEMU, ssh-verified lease, DHCP check). 135 tests. | libvirt DHCP down after reboot (user sudo command); WSL unresponsive at end of session | Build tlgen, one run per scenario, then overnight collection |
| 2026-11-15 | **QNX scheduling simulator + first models (user: 'we need sample trace data').** `src/tracelens/sim/` writes real-format QNX 8.0 traces for every tlgen scenario (sched, PI mutex, sem, condvar, MsgSend, shared IRQ, ticks); `tracelens simulate`, `tracelens data simulate`; 15 samples in fixtures/sim. Found and fixed: irq rule crash + pre-attach latency, condvar_inversion not unseen, cpu_starvation untriggerable, feature hygiene, zoo deadline config unfit for tlgen (new bugzoo/gen/tlgen.toml); added lost_wakeup, period_overrun. Radar (persistence rule) and classifier (victim labels) trained on 1,800 sim traces: held-out FA 4/124, 3 of 4 unseen families 100%; classifier region B >= 0.91. Never trained on real: radar right on 9/10 zoo builds, 0 false alarms on 8 healthy/fixed; classifier right cause on Z1/Z2/Z4. Bundled radar.json. 148 tests. | WSL still unresponsive: tlgen.c changes not compiled | Real pilot when WSL is back (wsl --shutdown); per-feature gap table |
| 2026-11-15 | **Simulator measured against the real captures, and the radar shipped in the product.** Gap table (median per feature, each real victim thread vs its simulated family) drove three fidelity fixes: a driver on a shared IRQ only works for its own device (simulated handler was preempted 4.75x/ms, real one never), `ipc_deadlock` serves its peer in a MsgReceive loop before deadlocking (as the real Z3 does), healthy handler work narrowed to the measured ~7 us. Two new features: longest unbroken CPU burst, time holding an interrupt masked. New healthy scenario `healthy_irq_deferred` (the pattern our own ist-defer-work remedy writes) after the radar flagged the real Z5 fix's worker; loads now drawn as fractions of the period after it flagged the real Z1 fix's logger; healthy training traces that miss deadlines are dropped. Retrieval (`ml/retrieve.py`): every radar finding names the labelled pattern it resembles and how loosely. Radar wired into `analyze --radar`, the web app and the live fix view ('Second opinion', never a fix target). 1 of 158 false alarms on held-out healthy traces, the radar flags all five real buggy builds on the victim thread and stays quiet on all five fixes and three healthy system traces. | WSL frozen all session (degraded Windows host network service; needs a Windows restart), so tlgen.c is still uncompiled | Windows restart, then the real pilot and the gap table against it |
| 2026-11-16 | **Pilot blocked on the VM's network, not on TraceLens.** After the Windows restart WSL is healthy and `tlgen` builds clean for QNX with all 16 scenarios (one qcc warning fixed). The QNX VM boots under KVM, but libvirt's `default` network reports started while nothing listens on UDP 67: an orphaned dnsmasq from the deleted bridge keeps libvirt's pid file, so the guest never gets an address and `target up` times out on ssh. destroy + pkill + bridge delete + start did not clear it. Fixed on the way: `target up`'s DHCP check called a healthy network broken, because a shell started by wsl.exe can sit outside systemd's PID namespace and see none of its daemons; it now falls back to the bridge's address. | VM has no IP; pilot and overnight collection still waiting | Try `systemctl restart libvirtd`, read libvirt's own log, or run QEMU with user-mode networking and an ssh port forward |
| 2026-11-16 | **Codebase audit and cleanup.** Ruff added as a dev tool and wired into `scripts/check.sh lint`, with config in pyproject; pytest now fails on DeprecationWarning. Fixed: 7 modules imported `Callable`/`Iterable` from `typing` (deprecated since 3.9), 15 `zip()` calls that truncate silently now pass `strict=True`, a closure over a loop variable in the inversion detector, 6 unused imports, 2 ambiguous names. Removed as dead: `report/showcase.py` (260 lines, superseded by app.py's pages), `_cite`/`_link`/`_CITE` in report/html.py, `BLOCKED_STATES`. **Claims corrected**: README, Devpost, the video script, the web footer and the PLAN headline still said 'no model'/'no AI' after Phase 6 shipped one; they now say no API keys, no cloud, no black box, and say plainly what the learned part does and does not do. No deprecated or removed stdlib APIs anywhere; packaging is PEP 621 with no setup.py; repo has no tracked build junk. 153 tests, lint clean. | None | Commit; then the VM network (libvirt DHCP) or user-mode networking |
| 2026-11-23 | **Third-party proof (rt-tests v2.11 on QNX 8.0).** `pi_stress`/`ptsematest`/`pmqtest` vendored unmodified under `third_party/rt-tests/` (GPL-2.0+, hashes in PROVENANCE) with a QNX compat layer; built with qcc, run and traced on the target (16 runs). Rules: **0 findings on all 16** (one lossy run correctly INCONCLUSIVE); radar MEDIUM on `ptsematest` 4/4 = benchmark shape, judged not a bug, not tuned. Parser bug found and fixed (multi-line quoted payload) with 2 regression tests; 166 tests pass. Write-up: `docs/results/third_party/README.md`. | Negative control run (pi_stress, PI off, 3 runs): silent, but the control does not sustain an inversion, so inconclusive. `check.sh gate` passes. Not run: re-run of ML evals; remedy/fix had no finding to act on | **Busy-medium control built and run** (`third_party/rt-tests/control/busy_medium.c`, ours, self-measures the high thread's wait): inversion rule CRITICAL on 9/9 runs without inheritance (mutex `PRIO_NONE` and `sem_t`), none on 6/6 with `PTHREAD_PRIO_INHERIT`; documented limit: the contention rule raises HIGH on the fixed variant when its critical section is long (waits of ~3 ms every round), not tuned. `remedy` points at the semaphore lock lines but gives no remedy for the `PRIO_NONE` mutex inversion (gap, not fixed). `PRIO_NONE` is honoured on QNX 8.0 (read back). Not done: ML evals re-run; `fix`; more third-party programs |
| 2026-11-16 | **The real QNX pilot ran: 16 of 16, and the models passed their first clean test.** VM network fixed itself after the libvirtd restart (DHCP listening again), VM up at 192.168.122.238. One real capture per scenario with the freshly built `tlgen`: 16/16 succeeded, none lossy, every planted problem showing, each known family firing its own rule and the four unseen ones firing none. The radar and classifier, trained only on simulated data and frozen before these captures existed, flagged 8 of 10 buggy traces on the victim thread with 0 false alarms on 6 healthy ones. Gap table: 210 of 274 feature/thread medians agree within 0.10; the rest are interrupt-thread preemption and CPU spread. **Parser bug found by the pilot**: some traceprinter builds print a user string event only as raw payload words, which silently lost every TL_META thread name (8 of 3,954 events here); the parser now decodes them, 3 tests pin it. | None | Close the two measured gaps, then the overnight collection |

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
- [x] **Real-trace check** (2026-11-14, QNX 8.0): THREAD `priority:` + `policy:`, `sync_p`, quoted STR, TRACE_CYCLES_PER_SEC, 64-bit timestamps + CONTROL TIME msb/lsb, PROCTHREAD_NAME, tracelogger `-w -n 0 -s -k`, pidin info ProcessorN. Still to see in a real trace: COMM SND/REC_MESSAGE (Z2/Z3), INT_ENTR (Z5), SCHED_SET args
- [ ] Fix-rate **ablation**: source only vs source + findings + trace. Harness ready: `tracelens eval fix` (both contexts share one set of before-captures per workload) writes `docs/results/fix.md`; run it on QNX
- [x] **N-run statistical verdict**: `tracelens compare --before … --after …` (≥5 clean runs a side, lossy runs
      skipped, findings must vanish in every after-run, no new kinds, one-sided Mann-Whitney U on per-job response)
- [x] Measure the reference fixes' noise floor under WSL2→KVM→QEMU and set thresholds above it: wake-ups
      1.1–1.4 ms late, IRQ response p99 ~0.3 ms, rare multi-ms host stalls; held-out 10-run eval: 0/50 reference runs flagged
- [x] Typed-claim citation checks: each citation = {event, thread, observed}; thread and event class/kind are checked against the trace (a claimed SEM that is really an IRQ is rejected and retried)
- [x] IPC pairing from COMM events: SND_MESSAGE rcvid/pid → REC_MESSAGE names the server thread; works for
      connections made before the capture; RECEIVE waits carry their channel, so a pool thread on another
      channel no longer hides a deadlock **(verify COMM field names)**
- [x] Z5 interrupt source: console UART IRQ 4, driven by writing /dev/ser1 during the run (verified)
- [x] Negative corpus of healthy QNX programs, committed as real fixtures (`fixtures/real/healthy_*`, CI gate); 0/30 runs flagged in the held-out eval
- [ ] Time the fix loop end to end before any duration claim

---

## 16. Phase 6: learning from traces (ML), started 2026-11-15

Design and evaluation protocol: [docs/ml/DESIGN.md](docs/ml/DESIGN.md). Rules stay the proof; ML adds a
radar for behaviour no rule knows, and a second opinion on the cause. Models are JSON files scored by
the stdlib: no API key, no network, deterministic.

- [x] Analysis: data (generate, not scrape), unit (thread x 20 ms window), features, models, evaluation protocol, risks
- [x] Generator `bugzoo/gen/tlgen.c`: 16 scenarios (6 healthy, 6 known bugs, 4 unseen) in one qcc binary, built and verified on QNX 2026-11-16
- [x] Data engine `tracelens data plan|collect|features`: seeded plan, splits fixed in advance, resumable collection, post-capture check
- [x] Features (17, normalised, no identities) incl. the generic inversion signal; smoke-tested on real traces
- [x] Radar v0 (robust z, per-side tail scale) + `analyze --radar`; tree-ensemble JSON inference; sklearn trainer (offline)
- [x] Evaluation code for the protocol (`tracelens ml eval`)
- [x] QNX scheduling simulator `src/tracelens/sim/`: real QNX 8.0 traceprinter format, all tlgen scenarios, `tracelens simulate`, `tracelens data simulate` (1,920 traces in ~6 min), samples in `fixtures/sim/`
- [x] Two genuinely unseen families (`lost_wakeup`, `period_overrun`) in tlgen.c and the simulator; `condvar_inversion` moved to known
- [x] Models trained on simulated data, evaluated (held-out sim + real zoo as development set): `scripts/sim_experiment.py` -> docs/ml/results_sim.md
- [x] Detector fixes found by the simulator: irq rule crash on never-run handlers; pre-attach interrupts counted as latency
- [x] Build `tlgen` with qcc and run each scenario once on the VM: 16/16 captured, none lossy, every planted problem triggers, every known family fires its own rule (2026-11-16)
- [x] Clean held-out test of the frozen models on those captures: radar 8/10 buggy flagged, 0 false alarms on 6 healthy (docs/ml/results_real.md, `scripts/real_vs_sim.py`)
- [ ] Overnight collection: ~1,950 runs (~5.4 h, host idle)
- [ ] Train radar + classifier; held-out evaluation; README/Devpost numbers from the frozen models only
- [x] Per-feature gap table against the committed real captures; simulator corrected (shared-IRQ driver, serving loop before the deadlock, measured handler work)
- [x] Two features the gap table demanded: longest unbroken CPU burst, time holding an interrupt masked
- [x] Healthy coverage: the deferred-worker fix pattern (`healthy_irq_deferred`), unpinned IPC, loads drawn as fractions of the period
- [x] Retrieval: labelled exemplars ride with the radar; every finding names the pattern it resembles and how loosely
- [x] Radar in the product: `analyze --radar`, the web app's reports and uploads, a "Second opinion" block in the live fix view
- [ ] Per-feature sim-vs-real gap table from the **real pilot**; recalibrate simulator knobs
- [ ] Close the sim-to-real misses: Z3 (cross-process deadlock), Z5 (real interrupt bursts)
- [ ] Retrieval of labelled exemplars to explain radar findings
- [ ] Radar note in the web report and the live fix view

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
| 2026-11-14 | Build our own QEMU VM with mkqnximage instead of the Quick Start image | Same SDP, instrumented kernel by default, SSH key login, no 4 GB download; the Quick Start CLI install crashed |
| 2026-11-14 | Fit the deadline release grid (Theil-Sen) instead of a rigid period grid | Real trace clocks drift 0.05% vs the workload clock; a rigid grid produced 124 false misses in 200 jobs |
| 2026-11-14 | Late wake-ups on an idle CPU are reported as platform latency (MEDIUM) | Measured on QEMU/KVM: the fixed program's only miss was the timer firing 1.26 ms late; CI must not fail on virtualization jitter |
| 2026-11-14 | Bug-zoo timing keeps ≥ 2 ms of slack over the 1 ms QNX tick | Measured 1.1–1.4 ms wake lateness; a planted bug must be gross enough that platform noise never decides the verdict |
| 2026-11-14 | Lossy = violation rate, not any violation | One dropped event in 245k only distorts one interval; voiding the verdict would make heavy-interrupt traces unusable. Small traces stay strict |
| 2026-11-14 | Bug-zoo releases are whole QNX ticks apart | Timers fire on 1 ms tick boundaries; sub-tick offsets made planted bugs reproduce 0–4 times in 5 |
| 2026-11-14 | Severity needs a pattern; rare small outliers are MEDIUM | Real VM noise (one 5.3 ms stall, one 564 µs handler, one 2.5 ms lock wait) must not fail a healthy build; `deadline_marginal_rate = 0` for hard RT |
| 2026-11-14 | Published numbers come from a held-out run | Detectors were calibrated on three 5-run evals; the 10-run table was captured after the last change |
| 2026-11-14 | No AI, no API keys, no CI pipelines (user) | Solve real problems on the user's machine and target; nothing to configure or pay for; deterministic, reproducible fixes |
| 2026-11-14 | Automatic remedy only when its preconditions hold in the code; else guidance | A wrong rewrite of real-time code is worse than none; tests prove each rule backs off |
| 2026-11-14 | Deferred interrupt work runs below the lowest interrupt thread in the trace | It must never delay any driver's interrupt; measured: IST-1 broke Z5, 20 (below virtio 21) verified |
| 2026-11-14 | Z1 budget 2 ms (was 1 ms) | The 1 ms budget left < 1 ms slack over measured VM jitter, violating the bug-zoo slack rule; detection and fix re-run at 2 ms |
| 2026-11-14 | Capture with the host idle | QEMU vCPUs share host cores; host load showed up as 10x job running time in the guest |
| 2026-11-14 | Hosted demo on Render runs TraceLens itself, not the QNX VM | A public QNX instance raises licence (non-commercial), cost (nested KVM) and uptime problems; detection and fix planning need no target |
| 2026-11-15 | ML data is generated on our QNX VM, not scraped | No public labelled QNX kernel traces exist; planted scenarios give labels for free; scraped code has no traces and mixed licences |
| 2026-11-15 | Models ship as JSON scored by the stdlib; training offline | Keeps the no-key, no-network, deterministic promise; scikit-learn is a dev-only extra |
| 2026-11-15 | Radar findings are MEDIUM and never auto-patched | A model's 'unusual' is not a proof; rules stay the proof |
| 2026-11-15 | Evaluation protocol fixed before collecting data | Unseen families held out entirely; published numbers only from frozen models |
| 2026-11-15 | Build a QNX scheduling simulator that writes the real traceprinter format | Real captures cost ~10 s each and need the VM; a simulator gives unlimited labelled data and exercises the whole pipeline unchanged; real traces stay the ground truth |
| 2026-11-15 | The real zoo traces are a development set from now on | They were used to find sim-to-real gaps; clean tests are the real tlgen pilot and new zoo programs |
| 2026-11-15 | Radar reports a thread only when its unusual windows persist (calibrated on healthy training traces) | Bugs repeat every period, noise does not; any-window flagging gave trace-level false alarms |
| 2026-11-15 | Bug labels only on the planted victim thread's windows | A preempted lock holder looks healthy; labelling it as the bug taught the classifier to blame a healthy logger |
| 2026-11-15 | Data engine uses bugzoo/gen/tlgen.toml (no deadline periods) | tlgen periods vary per run; the zoo's 10 ms frame period produced false deadline misses |
| 2026-11-15 | The simulator is corrected only by mechanisms, never by per-trace tuning | A gap table says *what* differs; the fix must be a real QNX behaviour we had not modelled (a shared line, a serving loop), or the simulator becomes a copy of five traces |
| 2026-11-15 | Healthy coverage must include the fixes TraceLens itself recommends | The radar flagged the deferred worker its own ist-defer-work remedy writes; a tool that flags its own fix is worse than no tool |
| 2026-11-15 | Exemplars for retrieval come from the training split only | Otherwise the held-out families leak into the model and the evaluation stops meaning anything |
| 2026-11-16 | 'No AI' became 'no API keys, no cloud, no black box' | Phase 6 ships two learned models; a claim that is false in the README is worse than no claim, and the true one is still strong: nothing leaves the machine and nothing a model says can fail a build or write a patch |
| 2026-11-16 | Lint and deprecation warnings are errors, not advice | A deprecation ignored today is a build that will not run on the next Python; `scripts/check.sh lint` keeps it from drifting again |
