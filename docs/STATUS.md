# TraceLens — where it stands

**2026-11-16.** Submit target **Dec 10**; hard deadline **Dec 16, 1:00 AM Dhaka**. ~24 days to the target.
Source of truth for plan and history stays [PLAN.md](../PLAN.md); this is the short version.

**What it is:** a host tool for QNX 8.0 that reads a kernel event trace, names the real-time bug, writes
the QNX-specific fix, and proves the fix on the target. No API keys, no cloud, no black box.

---

## Proven, on real QNX 8.0

| | Result |
|---|---|
| **Detection** (10 captures per build) | every planted bug caught **10/10**; every hand-written reference fix clean **10/10**; healthy system programs **0 findings in 32 runs** |
| **Fixes** | **4 of 5** fixed automatically and **VERIFIED on the target** (Z1, Z2, Z4, Z5). Z3 (Send/Reply deadlock) gets the exact lines and the send-hierarchy fix — it changes the protocol, so it is guided by design |
| **Generator** (16 scenarios, one qcc binary) | **16/16** captures on the target, none lossy, every planted problem reproduced, each known family firing its own rule |
| **Learned models, clean held-out test** | trained only on simulated data, frozen before the captures existed: radar flagged **8/10** buggy traces on the thread that suffers, **0 false alarms** on 6 healthy ones |
| **Learned models, simulated held-out** | **1 false alarm in 158** healthy traces; 3 of the 4 bug families with no rule caught **100%** |
| **Simulator fidelity** | **210 of 274** feature medians agree with the real target within 0.10 |
| **Codebase** | 156 tests, lint clean, deprecations are build failures, stdlib-only core |

Recorded runs: [results_real.md](ml/results_real.md), [results_sim.md](ml/results_sim.md), [results/](results/).

## Built

- **Analyzer** — parser (counter wraps, cross-CPU reordering, lossy detection), thread/priority model,
  5 detectors + deadline misses, HTML/JSON/SARIF/Perfetto output, exit codes.
- **Fix engine** — QNX-specific source transforms with safety preconditions, `qcc` build, before/after
  capture, Mann-Whitney U verdict, up to 3 rounds.
- **Web app** — consumer pages, guided demo for judges, upload-your-own-trace, Render blueprint.
- **Simulator** — a model of the QNX 8.0 scheduler writing real `traceprinter` traces: 1,920 labelled
  recordings in ~6 minutes, no target needed.
- **Learning** — data engine, 19 features, radar (bundled `radar.json`), classifier, retrieval of
  labelled exemplars, evaluation protocol fixed before the data existed.

---

## Left to do

### 1. The dataset that upgrades every ML number — *biggest win left*
- [~] **Overnight collection running** since 2026-11-16 18:33: 1,920 planned runs (~5.3 h), resumable,
      detached so it survives this session. Progress: `tail -f data/overnight.log`.
- [ ] Retrain on simulated + real-train, test on **real held-out**; publish only those numbers.

### 2. Live debugging in the demo
- [x] **Z1 recorded** (2026-11-16): a real `tracelens fix` run on the target, 32 events, VERIFIED in one
      round. `/replay/z1_infusion_pump_live` plays it back, and `/examples` offers "Watch the fix happen".
- [x] The radar's "Second opinion" block ran against a real fix for the first time, and reads:
      *control behaves unlike healthy QNX, closest known pattern priority_inversion — score 19.23 vs 3.39*.
- [ ] **Z5 still to record**: the first attempt reported "nothing to fix" because its interrupt bug needs
      the serial load running. `tracelens fix` now takes that command from `bugzoo/zoo.toml` by itself, so
      the re-run is one command once the target is free. *(me, ~15 min)*

### 3. Close the measured simulator gaps
- [ ] Simulated interrupt threads are preempted ~2x more often than real ones (`preempts_per_ms` 4.2–4.9
      vs 0–2.1) and serve interrupts ~2x as often; real threads spread over more CPUs than the simulated
      scheduler allows. Then re-run `scripts/sim_experiment.py` so the recorded numbers match. *(me)*

### 4. Submission
- [ ] **Render URL is recorded nowhere** (README, Devpost) and the live site has not been checked since
      the last three deploys. *(you deploy / confirm the URL, me to wire it in and check the pages)*
- [ ] Devpost text: draft is current in [devpost.md](devpost.md) — needs the final numbers and links. *(me)*
- [ ] **Demo video** against [video_script.md](video_script.md). *(you)*
- [ ] Codelab ([codelab/index.md](codelab/index.md)) is verified end to end on QNX; add the `tracelens simulate`
      path so a judge with no QNX target can still follow it. *(me, ~20 min)*

### 5. Known limits — keep stating them, don't hide them
- **Starved low-priority job**: invisible to the radar by construction (it behaves exactly like healthy
  deferred work). The deadline rule catches it when a deadline is declared.
- **Classifier misses Z3 and Z5** on real traces; the rules catch both outright.
- **The bug-zoo traces are a development set** since 2026-11-15 — they were used to find simulator gaps.
  Clean tests are the pilot and anything new.
- **VM networking**: libvirt's DHCP orphaned itself three times in one evening, each repair needing a
  password. `tracelens target up` now falls back to QEMU's own NAT (`--user-net`, ssh forwarded to
  127.0.0.1:2222) — no bridge, no DHCP server, no `sudo`. That is how the overnight run was started.

---

## If only three things get done

1. **Overnight collection** — turns "works on simulated data" into "works on real QNX, measured".
2. **Recorded live replays** — the demo currently tells judges about the fix loop instead of showing it.
3. **Hosted URL + video** — the two things a judge actually opens first.
