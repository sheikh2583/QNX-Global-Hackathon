# TraceLens: where it stands

**2026-11-24.** Submit target **Dec 10**; hard deadline **Dec 16, 1:00 AM Dhaka**. 16 days to the target.
Source of truth for plan and history stays [PLAN.md](../PLAN.md); numbers come from the committed files in
[results/](results/) and [ml/](ml/), never typed by hand. This is the short version.

**What it is:** a host tool for QNX 8.0 that reads a kernel event trace, names the real-time bug, writes
the QNX-specific fix, and proves the fix on the target. No API keys, no cloud, no black box.

---

## Proven, on QNX 8.0

| | Result | Source |
|---|---|---|
| **Detection** (10 captures per build) | all 50 planted-bug runs caught; all 50 hand-written reference-fix runs clean; healthy system programs 0 findings in 30 scored runs (32 captured, 2 lossy runs discarded) | [results/detect.md](results/detect.md) |
| **Fixes** | **4 of 5** fixed automatically and **VERIFIED on the target** (Z1, Z2, Z4, Z5). Z3 (Send/Reply deadlock) changes the protocol, so it gets the exact lines and the send-hierarchy fix | [results/fix.md](results/fix.md) |
| **Learned models** | on **883 held-out buggy real captures** the rules alone catch 400; with the learned radar **726** (**+326** in bug classes no rule exists for); **0 false alarms on 148 healthy** real captures. Re-run on 2026-11-24 and reproduced exactly | [ml/results_train.md](ml/results_train.md), [results/ml.json](results/ml.json) |
| **Regression gate** | `tracelens baseline save` and `tracelens gate`: Z1, Z2 and Z4 fixed builds pass their own baseline; their buggy builds are blocked by the fixed baseline. Says INCONCLUSIVE instead of guessing | README, `scripts/check.sh gate` |
| **Code we did not write** | `rt-tests` v2.11 (`pi_stress`, `ptsematest`, `pmqtest`) on QNX 8.0: **0 rule findings in 16 runs** (a clean result, not a bug find). Our own sustained-inversion control `busy_medium`: flagged **9 of 9** without priority inheritance, **0 of 6** with it. Found and fixed a real parser bug on the way | [results/third_party/](results/third_party/README.md) |
| **Fix on code we did not write** | NTNU course exercise `UnboundedPriorityInversion.c` (unedited; header-level QNX port layer only): CRITICAL inversion in 10/10 captures, automatic fix applied in 1 round, **VERIFIED** (inversion 10/10 to 0/10, p99 1,103 to 702 ms, p = 5.4e-06). A teaching exercise, not production code; upstream has no licence, so the file is fetched by hash and not copied | [results/third_party_fix/](results/third_party_fix/README.md) |
| **A real bug in production code** (case study: both rules written after this exact bug, not a blind test) | memcached 1.6.45, unedited, on QNX 8.0, as the **real daemon** and as the logger thread alone ([memcached#1348](https://github.com/memcached/memcached/issues/1348), a lost wake-up that hangs graceful shutdown). The new `lost_wakeup` rule names it from the kernel trace (0 findings on the healthy control); the new `recheck-before-wait` rule writes the one-line fix; **VERIFIED, hung 10/10 before and 0/10 after** (daemon: 1 lossy run skipped; logger alone: run twice). The learned radar flagged the hang **and the healthy control**, so it was not useful here. Reduced build (no TLS, SASL, extstore or proxy), signalled from inside the process, x86_64 only, rule written after seeing the bug | [results/memcached_logger/](results/memcached_logger/README.md) |
| **A famous bug, cold** | NNG's `nng_close()` deadlock (#1543/#1813, three years to close) on QNX 8.0. The system **missed it at first** (no rule fired; the radar gave vague findings). After the new `stuck_job` rule: flagged in **10/10** buggy runs (NNG v1.7.3), **0/10** runs of upstream's fix; `tracelens compare` **VERIFIED**. **Not our fix**: TraceLens cannot write it; the radar flagged all 20 runs, so it was useless again. Driver and rule written by us after the first trace | [results/nng_close/](results/nng_close/README.md) |
| **Blind test (frozen system)** | Pre-registered, system frozen (hash recorded). jemalloc#585 and libzmq#2759 dropped before running (cannot occur on QNX / no fix to verify). Mosquitto#3175 built buggy and fixed on QNX: **0 hangs in 39 runs, so it did not reproduce** and nothing could be detected. **No blind detection result was obtained**; NNG stays the only cold test, and the system missed it first | [results/blind_test/](results/blind_test/README.md) |
| **aarch64** (emulated) | 65 captures over 13 scenarios on QNX 8.0 `aarch64le` under QEMU: the same rules fire on the same workloads; the x86-trained radar flags 38 of 45 planted bugs, 0 false alarms on 20 healthy | [results/aarch64.md](results/aarch64.md) |
| **Generator** (16 scenarios, one qcc binary) | 16/16 captures on the target, none lossy, every planted problem reproduced | [ml/results_real.md](ml/results_real.md) |
| **Simulator fidelity** | 210 of 274 feature medians agree with the real target within 0.10 | [ml/results_real.md](ml/results_real.md) |
| **Codebase** | 219 tests pass (5 skipped), ruff clean, deprecations are build failures, stdlib-only core, pre-push hook runs lint, tests and the gate | `scripts/check.sh`, `.githooks/pre-push` |

## Built

- **Analyzer**: parser (counter wraps, cross-CPU reordering, lossy detection), thread and priority model,
  7 detectors (priority inversion, Send/Reply deadlock, lock contention, interrupt overrun, **lost wake-up**) plus
  deadline misses and **stuck jobs** (a job that never finishes), HTML/JSON/SARIF/Perfetto output, exit codes.
- **Fix engine**: QNX-specific source transforms with safety preconditions, `qcc` build, before/after
  capture, Mann-Whitney U verdict, up to 3 rounds.
- **Regression gate**: per-deadline and per-job-stream baselines with provenance; one-sided Mann-Whitney U
  on per-capture p99, Holm-Bonferroni across metrics, effect floors; new finding kinds and newly-over-budget
  also fail.
- **Learning**: data engine, 19 features, radar (bundled `radar.json`), classifier, retrieval of labelled
  exemplars, an evaluation protocol fixed before the data existed. A learned finding is MEDIUM, never
  fails a build and never gets an automatic patch.
- **Simulator**: a model of the QNX 8.0 scheduler writing real `traceprinter` traces; 1,920 labelled
  recordings in about 6 minutes.
- **Web app and demo**: consumer pages, a guided demo for judges (10 steps, including the QEMU target and
  "What it learned"), upload-your-own-trace, a recorded live fix replay, Render blueprint.

## Hosted site and video

- **Live demo:** https://qnx-global-hackathon.onrender.com/ (free tier: the first request after idle takes
  about a minute).
- **Promo video v7** (109 s, `promo/`, not in git): hook, fix, proof on QNX, **learned second opinion**,
  regression gate, code we did not write, emulated aarch64. Description with every caveat:
  `promo/out/youtube_and_credits.md`.
- **Screen-recording demo script** ([video_script.md](video_script.md)): the longer walkthrough of `/demo`.

---

## Left to do

- [ ] **You:** listen check of the promo voice lines ("TraceLens", "aarch64"), confirm the Mixkit music
      licence, upload to YouTube (public), paste the link into Devpost.
- [ ] **You:** Devpost form: paste [devpost.md](devpost.md), codelab URL, video URL.
- [ ] **Z5 live replay** still to record (its first attempt reported "nothing to fix": the interrupt bug
      needs the serial load, which `tracelens fix` now takes from `bugzoo/zoo.toml`).
- [ ] **Close the measured simulator gaps** (simulated interrupt threads are preempted about 2x more
      often than real ones) and re-run `scripts/sim_experiment.py`.
- [ ] Codelab ([codelab/index.md](codelab/index.md)): add the `tracelens simulate` path so a judge without
      a QNX target can follow it.

## Known limits, keep stating them

- **aarch64 is emulated** (QEMU TCG, no KVM for ARM). The claim is "the tool does not depend on x86",
  not "validated on a Cortex-A part". The radar does not transfer on interrupt traces, and the median
  interrupt-handler rule that fixes the rules there is optional and off by default.
- **Third-party results are narrow.** `rt-tests` is a clean result (no rule fired; it has no bugs). The one
  genuine third-party fix is a small teaching exercise with exactly the shape of one fix rule, on one VM,
  x86_64 only; it is not a bug found in production code.
- **Starved low-priority job**: invisible to the radar by construction (it behaves like healthy deferred
  work); the deadline rule catches it when a deadline is declared.
- **Classifier misses Z3 and Z5** on real traces; the rules catch both outright.
- **The four rule-less bug families were written by us**, so withholding them is an honest experiment,
  not proof the radar finds an unknown bug in a stranger's code.
- **Bug-zoo traces are a development set** since 2026-11-15; clean tests are the pilots and anything new.
- **VM networking**: `tracelens target up --user-net` (QEMU's own NAT, ssh on 127.0.0.1:2222) avoids the
  libvirt DHCP problem and needs no `sudo`.
