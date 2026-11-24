# TraceLens — handoff context

Everything another person or assistant needs to continue this project without the conversation that
built it. Written 2026-11-16. Companion documents: [PLAN.md](../PLAN.md) (full history and decisions),
[STATUS.md](STATUS.md) (what is done and what is left), [ml/DESIGN.md](ml/DESIGN.md) (the learning phase).

---

## 1. What this is

**TraceLens** turns a QNX 8.0 kernel event trace into a named real-time bug, a QNX-specific source fix,
and a verdict measured on the target. Entry for the **QNX Global Hackathon 2026** (Developer Tooling,
aiming at the Grand Prize). Submit target **Dec 10**, hard deadline **Dec 16 2026, 1:00 AM Dhaka**.

The pipeline, end to end:

```
QNX target ──tracelogger──► .kev ──traceprinter──► text ──parse──► model ──rules──► findings
                                                                       └──learned radar──► "unusual"
findings ──remedy rules──► patched C ──qcc──► rebuilt program ──re-capture──► Mann-Whitney U ──► VERIFIED
```

## 2. Ground rules that must not be broken

These are decisions, not preferences. Breaking one makes the project worse in a way judges will notice.

1. **No API keys, no cloud, no network at runtime.** The core is the Python standard library. The two
   learned models are small JSON files scored by hand-written code. `scikit-learn` is a dev-only extra
   used to *train* the classifier offline, never to run it.
2. **Rules prove; models suggest.** A rule finding cites the exact trace events that prove it. A learned
   finding is MEDIUM, never fails the gate, never becomes a fix target, never gets an automatic patch.
3. **Claims must be true and checkable.** Every number in README/Devpost comes from a recorded run in
   `docs/results/` or `docs/ml/results_*.md`. If a claim stops being true, fix the claim the same day —
   the repo once said "no model" after shipping two, and that was a correctness bug like any other.
4. **The evaluation protocol was fixed before the data existed** (DESIGN.md §5). Families with no rule
   (`cpu_starvation`, `mutex_abba`, `lost_wakeup`, `period_overrun`) never train anything. Known families
   train on one parameter region and are tested on another. Splits are decided when the *plan* is made.
5. **The committed bug-zoo traces in `fixtures/real/` are a development set** (since 2026-11-15): they
   were used to find simulator gaps. Clean tests come from new captures.
6. **Mark anything unverified about QNX as `(verify)`** until it has run on the target.

## 3. Layout

| Path | What it is |
|---|---|
| `src/tracelens/ingest/`, `model/` | traceprinter parser (counter wraps, reordering, lossy detection) and the thread/priority/IPC model |
| `src/tracelens/detectors/` | the five rules + deadline misses; each encodes QNX semantics, see README |
| `src/tracelens/remedy/`, `fix/` | C source transforms with safety preconditions; the fix loop (capture → patch → qcc → re-capture → verdict) |
| `src/tracelens/ml/` | data engine, 19 features, radar, classifier, retrieval of labelled exemplars |
| `src/tracelens/sim/` | a model of the QNX scheduler that writes real `traceprinter` text — labelled data with no target |
| `src/tracelens/app.py`, `web.py`, `live.py`, `live.js` | the web app, the live fix view and its replay |
| `bugzoo/` | five planted-bug C workloads + reference fixes (`reference/`), and `gen/tlgen.c`, the 16-scenario generator |
| `fixtures/real/`, `fixtures/sim/` | committed sample traces (real captures; simulated samples) |
| `docs/results/`, `docs/ml/results_*.md` | every published number, as recorded runs |
| `scripts/` | `check.sh` (lint+tests+gate), `collect.sh`, `train_eval.py`, `sim_experiment.py`, `real_vs_sim.py` |

## 4. Setup

**Analysis only (any OS, no QNX):**

```bash
python3 -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                                          # 156 tests
tracelens analyze fixtures/real/z1_infusion_pump.txt.gz -c fixtures/real/tracelens.toml --radar
tracelens simulate lost_wakeup -o t.txt.gz         # make a trace without a target
```

**With the QNX target (WSL2 Ubuntu on this machine):**

```bash
wsl -d Ubuntu-24.04
cd "/mnt/x/Hackathons/QNX Global hackathon"
source ~/.venvs/tracelens/bin/activate && source ~/qnx800/qnxsdp-env.sh
make -C bugzoo                 # all workloads, or: make -C bugzoo out/tlgen
tracelens target up --user-net # prints: export TRACELENS_TARGET=127.0.0.1:2222
tracelens target check
```

`--user-net` runs the VM on QEMU's own NAT with ssh forwarded to 127.0.0.1:2222 — **no bridge, no DHCP
server, no sudo**. Use it. libvirt's DHCP orphaned itself three times in one evening on this machine and
every repair needed a password; `--bridge` forces the old path if you ever want it.

## 5. Collecting data and training — the two scripts you will actually run

```bash
# Collect from the target. Resumable: rerun the same command to continue.
scripts/collect.sh -n 120                       # 120 runs of each of the 16 scenarios (~4 h)
scripts/collect.sh -n 200 -s healthy_periodic -s healthy_ipc -o data/healthy   # one family, own folder
scripts/collect.sh --features-only -o data/real # rebuild features from traces already collected

# Simulate instead (no target, ~6 min for 1,920 traces)
tracelens data simulate --per-scenario 120 --out data/sim

# Train and evaluate any mix. Writes models/ and a markdown report.
python scripts/train_eval.py --real data/real                   # real only
python scripts/train_eval.py --sim data/sim --real data/real --test-on data/real   # both; tested on real only (the quoted numbers)
python scripts/train_eval.py --sim data/sim --test-on data/real # train simulated, test on real
python scripts/train_eval.py --real data/real --no-classifier   # radar only, no scikit-learn

cp models/radar.json src/tracelens/ml/radar.json   # ship a model with the tool
```

Both scripts take `--help`. Everything is deterministic: same inputs, same models, same numbers.

## 6. Where it stands (2026-11-16)

**Proven on real QNX 8.0** (QEMU x86_64, 4 CPUs, `procnto-smp-instr`):

- detection 10/10 per planted bug, reference fixes clean 10/10, 0 findings in 32 healthy runs
- 4 of 5 bugs fixed automatically and VERIFIED on the target; the 5th (Send/Reply deadlock) is guided
- the 16-scenario generator reproduces every planted problem on the target
- models trained only on simulated data, on a clean held-out real pilot: radar flagged 8 of 10 buggy
  traces on the victim thread, 0 false alarms on 6 healthy ones
- **1,920 real captures collected overnight** (1,846 triggered, 11 lossy, 0 errors) → 525k labelled
  windows; trained on simulated + real and tested on **real held-out traces**
  ([results_train.md](ml/results_train.md)): **0 false alarms in 148 healthy real traces**, every
  inversion family and `ipc_deadlock` at 100%, `irq_overrun` 85%, `lock_contention` 70%, and of the
  families with no rule at all `lost_wakeup` and `period_overrun` 100%, `mutex_abba` 84%. The
  classifier reaches 0.96-1.00 precision on real region-B windows. The shipped
  `src/tracelens/ml/radar.json` is this model.
- **The simulated data earns its keep**: trained on real data alone and tested on the same 148 real
  healthy traces, the radar gives 2 false alarms; adding the simulated traces to training takes it to
  0. Breadth of healthy behaviour is what the simulator contributes, and it is measurable.

**Known limits, stated deliberately:** a starved low-priority job is invisible to the radar (it behaves
exactly like healthy deferred work — the deadline rule catches it); the classifier misses Z3 and Z5 on
real traces (the rules catch both); simulated interrupt threads are preempted about twice as often as
real ones, and real threads spread over more CPUs than the simulated scheduler allows.

## 7. What to do next, in order

1. **Train on the overnight data.** `python scripts/train_eval.py --sim data/sim --real data/real --test-on data/real` (without `--test-on` the test set also includes simulated rows, so the numbers differ).
   This is the first time the models see real QNX data; the report tells you which claim is weakest.
2. **Re-record the Z5 live replay** (~15 min): `tracelens fix bugzoo/z5_motor_encoder --watch --no-browser
   --out fixes/z5_live` then copy `events.jsonl` to `docs/results/fixes/z5_motor_encoder_live/`. The
   serial load it needs now comes from `bugzoo/zoo.toml` automatically. Z1's replay is already recorded
   and plays at `/replay/z1_infusion_pump_live`.
3. **Tighten the false-alarm bound if that is the weak claim.** With ~158 healthy test traces and zero
   false alarms the 95% upper bound is ~1.9% (rule of three). `scripts/collect.sh -n 200 -s healthy_periodic
   -s healthy_pi_mutex -s healthy_ipc -s healthy_mixed -s healthy_irq -s healthy_irq_deferred -o data/healthy`
   (~4 h) takes it to ~0.15%. More runs of the *bug* families buy almost nothing.
4. **Widen `healthy_mixed`'s slack**: 26 of its 120 real runs missed the 2.5 ms job deadline because real
   wake-ups land 1.1–1.4 ms late. Raise `JOB_MARGIN_US` in `src/tracelens/ml/dataset.py` and re-collect
   that family only.
5. **Close the two measured simulator gaps** (interrupt-thread preemption rate, CPU spread), then re-run
   `python scripts/sim_experiment.py` so the recorded numbers match the code.
6. **Submission**: record the Render URL in README and `docs/devpost.md` (it is nowhere yet), check the
   hosted pages, finish `docs/devpost.md`, record the video from `docs/video_script.md`.

## 8. Things that cost hours to learn

- **A user string event is not always a string.** Some `traceprinter` builds print one only as raw payload
  words (`d0:0x4d5f4c54 …`), no `STR:` field — and it hit exactly the `TL_META` markers that name threads,
  silently breaking every name-dependent check. The parser decodes the words itself now
  (`_text_from_dwords`); three tests pin it.
- **QNX 8.0 fires timers on 1 ms tick boundaries.** Releases that are not whole ticks apart wake in a
  random order, so a planted bug reproduces only sometimes. Space them by whole ticks.
- **Host load distorts guest timing.** Keep the machine idle during collection; load shows up as lossy
  traces and false deadline misses.
- **A trace's windows are not independent samples.** ~275 windows come from one run of one program; the
  effective sample size is the trace count, not the window count. Report both.
- **Healthy coverage decides the false-alarm rate.** Every false alarm this project hit was a missing
  healthy *shape* (a busy low-priority logger; a deferred interrupt worker — the very pattern TraceLens
  recommends as a fix), never too little data.
- **WSL + libvirt is fragile**: if `wsl` commands hang, check `(Get-CimInstance Win32_Service -Filter
  "Name='hns'").Status` in PowerShell — `Degraded` means restart Windows. For the VM, just use `--user-net`.
- **Shell quoting**: write patch scripts to a file and run them; heredocs mangle backslashes in this
  environment. Files are written with `newline="\n"`; git converts on checkout.

## 9. Before you commit

```bash
scripts/check.sh lint     # ruff: dead code, bug patterns, deprecated APIs
scripts/check.sh tests    # 156 tests; DeprecationWarning is an error
scripts/check.sh gate     # every real and synthetic trace gets its expected verdict
```

Keep `PLAN.md` §14 (a row per session: done / blocked / next) and §15 (decisions with the reason) current —
that file is the project's memory, and this document is only its summary.
