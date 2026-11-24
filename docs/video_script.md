# Video script: TraceLens (target 2:45, hard limit 3:00)

> **Two videos, two scripts.** This file is the longer **screen-recording walkthrough** of the `/demo` page
> and a live QNX run. The short **promo video** (109 s, v7, with the learned second opinion, the gate, code we
> did not write and emulated aarch64) is built separately in the git-ignored `promo/` folder; its script is
> `promo/script.md` and its description is `promo/out/youtube_and_credits.md`. Numbers in both come from
> `docs/results/`. Pick one for the submission; the promo is the one drafted for YouTube.

Recording: OBS at 1920x1080, terminal font 18 pt, browser zoom 125%. **Every shot is a real run.** If a shot
cannot be reproduced live on the QNX target, it is not in the video. Voiceover is about 150 words per minute;
the lines below are about 370 words, so about 2:30, which leaves room for screen time.

Numbers in `[brackets]` are read off your own screen when you record; say what is on screen, not what is
written here. Numbers without brackets are committed results and are safe to say as written.

## Start the demo (run in this order, 5 minutes before recording)

In WSL, with the host otherwise idle (VM timing is the thing being measured):

```bash
source ~/qnx800/qnxsdp-env.sh
tracelens target up --user-net                  # boots QNX 8.0 in QEMU; ssh on 127.0.0.1:2222
export TRACELENS_TARGET=127.0.0.1:2222
tracelens target check                          # all green, or fix it before recording
make -C bugzoo                                  # builds the five programs with qcc
```

Run each command below once off camera first. For the website shots, in a second terminal:

```bash
tracelens serve --port 8000                     # http://127.0.0.1:8000/demo
```

## Shots

| Time | Shot | Voiceover |
|---|---|---|
| 0:00-0:14 | Terminal: `tracelens target up --user-net`, then `tracelens target check` all green; cut to the logo | "Real-time bugs on QNX are found by an engineer staring at a timeline. TraceLens finds them, writes the fix, and proves it on the real kernel. This is QNX 8.0 booting in QEMU. No API keys, no cloud, no black box." |
| 0:14-0:24 | A raw `traceprinter` dump scrolling | "This is a few seconds of an infusion pump, as the kernel saw it. The bug is in here somewhere." |
| 0:24-0:52 | `tracelens capture bugzoo/out/z1_infusion_pump -c bugzoo/tracelens.toml --analyze -- -d 2`; the CRITICAL finding; HTML report timeline | "One command records the trace on QNX and analyzes it. Priority inversion: the dose controller, priority 50, [waited 5 milliseconds] on a semaphore held by the logger, while telemetry held the CPU. [200 of 200] jobs missed the deadline. Every claim links to the kernel events that prove it." |
| 0:52-1:08 | Browser, `/demo` step 5 "How it knows": the chain of evidence and the QNX facilities table | "QNX mutexes inherit priority, so this cannot happen with a mutex. A semaphore has no owner, so the kernel has nobody to boost. These are four facts, each one a kernel event with a timestamp. Nothing is guessed." |
| 1:08-1:48 | `tracelens fix bugzoo/z1_infusion_pump -c bugzoo/tracelens.toml -- -d 2`: remedy, patch (semaphore to priority-inheriting mutex), qcc, five runs before and after, **VERIFIED**. Then `/demo` step 7 verdict table | "Now the fix. TraceLens rewrites the code only after checking the semaphore really is used as a lock, builds it with qcc, and runs it five times before and five after on the real kernel. The verdict is a one-sided Mann-Whitney test, not one lucky run: [worst case from 5.9 down to 1.0 milliseconds, budget 2, late jobs from 1000 to zero]. Verified." |
| 1:48-2:10 | `/demo` step 8 "What it learned": the radar finding, then the contribution table | "Rules only find what someone wrote a rule for. TraceLens also learns what healthy QNX scheduling looks like. On 883 held-out buggy recordings the rules alone find 400. With the learned radar, 726, and zero false alarms on 148 healthy ones. A learned finding is only a lead: it never fails a build and never gets an automatic patch." |
| 2:10-2:26 | Z3: `tracelens analyze` finds the Send/Reply deadlock; `tracelens remedy` shows the two `MsgSend()` lines | "Some fixes change a protocol. For a Send/Reply deadlock, TraceLens does not guess: it points at the exact lines and the QNX send-hierarchy pattern." |
| 2:26-2:42 | `tracelens baseline save` then `tracelens gate` blocking the buggy build; or `scripts/check.sh gate` passing | "And it can guard a release. Record a baseline once; the gate fails a build that is statistically slower, with the false-alarm odds stated. Every result here is a committed real QNX trace you can re-check with one command." |
| 2:42-2:55 | Home page results; the trust rules | "Fifty of fifty bugs caught, none flagged in eighty healthy runs. A recording where the kernel dropped events gets no verdict, and a fix only counts if the kernel says so." |
| 2:55-3:00 | Repo URL, codelab URL | "TraceLens. Open source, with a codelab. Links below." |

## Say these limits if asked (do not hide them)

- The learned radar does not see a starved low-priority job (cpu_starvation, 0 of those caught); the deadline rule catches it when a deadline is declared.
- On the five bug classes with rules, rules are the answer. The radar is a second opinion and is never auto-fixed.
- Four of five bugs are fixed automatically and verified. The Send/Reply deadlock (Z3) is guided by design.
- Third-party code: on three programs from the Linux `rt-tests` suite, ported to QNX, no rule fired in 16 runs (a clean result, not a bug find). The radar flagged one benchmark as unusual, which is a known false positive on an unseen shape.
- aarch64 is emulated (no KVM for ARM on this host): the tool is not x86-specific, but interrupt-handler detection did not transfer cleanly. Say "runs on emulated aarch64", never "validated on ARM".

## Before recording

- [ ] `tracelens target check` is green and the host is idle (nothing else running in WSL)
- [ ] Every command above run once off camera; numbers in `[brackets]` noted from your own run
- [ ] `tracelens serve` is up and `/demo` loads; browser zoom 125%, no dev tools open
- [ ] Terminal history cleared; no account details, paths or usernames visible
- [ ] Duration measured under 3:00 after editing
