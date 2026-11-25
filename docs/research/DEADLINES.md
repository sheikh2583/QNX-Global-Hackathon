# Research deadlines and schedule

Owner: the research supervisor (the "Solution analysis and research contribution" session). Main Build executes.
Written 2026-11-25. Dates were checked against the official conf.researchr.org pages on 2026-11-25 unless marked
**(inferred)**, which means taken from the previous year's cycle; re-check those when the call is posted.

**Rule 0: the hackathon comes first.** Submit target Dec 10, hard deadline Dec 16 01:00 Dhaka. On any day the hackathon
needs the VM, the host or Main Build's attention, research yields. Research captures run only when the VM is not
needed for the demo or video, and with the host idle.

## Targets

| # | Venue / track | Deadline | Status | What we send |
|---|---|---|---|---|
| **T1** | **ISSTA 2027, research papers** (Singapore, 7-10 Sep 2027) | **abstract Fri 8 Jan 2027, full paper Mon 11 Jan 2027** (time zone not stated on page: assume AoE, **(verify)**) | **PRIMARY** | Full paper: trace-validated repair of scheduling bugs on a microkernel RTOS. RQ1 oracle mutation study, RQ3 precondition ablation, RQ6 gate study, third-party case studies, honest blind-test status. The major-revision round (resubmission Thu 20 May 2027) is where the blind benchmark and the hardware results go. |
| **T2** | **FSE 2027, tool demonstrations** (Shenzhen, 12-16 Jul 2027) | **Tue 26 Jan 2027** | SECONDARY | Tool demo paper and screencast (reuse the promo footage). Check FSE's policy on overlap with a paper under review **(verify)**. |
| T3 | FSE 2027 Student Research Competition | not posted yet; the FSE 2026 SRC closed 26 Jan 2026 **(inferred: late Jan 2027)** | WATCH | Undergraduate-entrant abstract (the user is a final-year student). |
| T4 | OSPERT 2027 (with ECRTS 2027) | **(inferred: ~April 2027)** | PLANNED | Experience paper, "What real QNX 8.0 taught a trace-analysis tool" (the README section of that name). Little overlap with T1. |
| T5 | ECRTS 2027 | **(inferred: ~late Feb 2027)**, from the 2026 deadline of 26 Feb | FALLBACK | Only if T1 is not submitted. |
| T6 | EMSOFT 2027 (ESWEEK) | **(inferred: ~late Mar 2027)** | FALLBACK | Real-time/embedded framing with hardware results; only if T1 is not submitted (ISSTA's initial notification, 20 Apr, comes after this deadline). |
| T7 | RTSS 2027 / ASE 2027 | **(inferred: ~May 2027)** | FALLBACK | If T1 is rejected on 20 Apr 2027. |
| T8 | MSR 2028, data and tool showcase | **(inferred: ~Nov 2027)** | PLANNED | The labelled QNX kernel-trace dataset (R7). |

**Already passed (do not plan for these):** ICSE 2027 demos (23 Oct 2026), FSE 2027 research (2 Oct 2026), RTAS 2027 (5 Nov 2026),
MSR 2027 data showcase (10 Nov 2026), ICSE 2027 SRC (13 Nov 2026), ICSE 2027 workshops incl. CASE2Space (13 Nov 2026) and
SERP4IoT (20 Nov 2026).

## Schedule to T1 (ISSTA, 11 Jan 2027)

| Window | Main Build (research share) | Supervisor | User |
|---|---|---|---|
| **Nov 26-30** (hackathon build window ends) | O1 fix `BenchBlind`; O2 commit research files; O3 R2 preparation (mutants, `expected.toml`, `research/oracles.py`, freeze E2); O4 NNG residual preregistration | ISSTA paper skeleton, related work (R10), background, method sections | Order a QNX 8.0-capable board now **(verify image)**; decide authorship and any faculty co-author; decide on the LLM arm |
| **Dec 1-9** (hackathon polish and submission) | Only VM-idle overnight work: R2 captures, NNG residual run; O5 freeze tag `research-freeze-1` by **Dec 5**; O6 10 bench candidates (metadata) by **Dec 9** | Keep writing; review each result as it lands | Hackathon first |
| **Dec 10** | Hackathon submission. No research. | | Submit Devpost |
| **Dec 11-20** | R2 analysis; R5.1 precondition suite and ablation; R3 blind runs on reproduced candidates; R8 VM part (A/A, slowdown knob) | Evaluation section from each result | Confirm semantic-equivalence judgements (R3/R5) |
| **Dec 21-31** | R6 radar baselines (offline, cheap); **all results frozen Dec 31**; `make_numbers.py` final | Full draft by Dec 31 | Read the draft |
| **Jan 1-7** | Artifact package (anonymised if ISSTA is double-blind **(verify)**) | Revise; internal harsh review | |
| **Jan 8** | | | **Register the abstract** (user's account) |
| **Jan 11** | | Final PDF | **Submit** |
| Jan 12-26 | Screencast | Tool-demo paper (T2) | Submit T2 on Jan 26 |
| Feb-May | R4 hardware and probe effect, R3 expansion | Revision material, OSPERT paper | Board set-up, licences |

## Minimum viable ISSTA paper (what must exist by Dec 31)

1. RQ1: oracle mutation study on the VM, at least 18 mutants, oracles O1-O5, the N-curve (R2). **The headline experiment. Non-negotiable.**
2. RQ3: guarded vs naive transforms on the zoo + precondition suite (R5.1), rounds ablation (R5.2).
3. RQ6: gate A/A, VM part (R8); the simulator part already exists.
4. Case studies on third-party code: TTK4147 (fix verified), memcached#1348 (rule written after the bug, labelled so),
   NNG (missed first, rule added, upstream fix possibly incomplete: pending the preregistered residual run).
5. RQ2: whatever the frozen blind run gives by Dec 20, reported as-is, even if it is a null; the full benchmark is promised for the revision.
6. Threats: VM timing, emulated aarch64, no hardware yet, rules written by the authors.

## Sources (checked 2026-11-25)

- ISSTA 2027 dates: https://conf.researchr.org/home/issta-2027
- FSE 2027 dates: https://conf.researchr.org/dates/fse-2027
- ICSE 2027 workshops: https://conf.researchr.org/track/icse-2027/icse-2027-workshops
- ICSE 2027 dates (demos, SRC): https://conf.researchr.org/dates/icse-2027
- MSR 2027 dates: https://conf.researchr.org/dates/msr-2027
- RTAS 2027 CFP: https://2027.rtas.org/cfp/
