# Brief for Codex: mine real concurrency bug-fix commits (step 1 of the fix-ranker plan)

You are working in the TraceLens repository (`X:\Hackathons\QNX Global hackathon`, Windows with WSL2 Ubuntu; shell is
Git Bash/PowerShell, Python 3.11 is at `.venv\Scripts\python.exe`). **Read `CLAUDE.md` and `PLAN.md` section 14 first.**

## Why this task exists (so you can make good judgment calls)

TraceLens reads QNX kernel traces, names real-time bugs, writes a fix and proves the fix on the target. Its fix step
today has only 6 hand-written rewrite templates (see `src/tracelens/remedy/rules.py`). The plan is to ship a **small
offline model (about 0.5B-1.5B parameters) that ranks which fix shape applies and which symbols fill it in**, with the
patch itself always coming from a deterministic template and a verifier on the target checking it. To know *which fix
shapes are worth building templates for*, we need data on how real projects fixed real concurrency bugs. **That is your
job: collect the data and tell us which fix shapes recur.** You are not training anything and not writing templates.

## What to collect

Real bug-fix commits from open-source C/C++ projects where the message says the commit fixed a concurrency or
real-time bug: deadlock, lock-order inversion, lost/missed wake-up, missed signal, spurious wake-up, race, priority
inversion, livelock, hang caused by waiting on a lock/condition variable/semaphore/join, "condition variable",
"pthread_cond", "mutex" together with "fix".

**Source repos (start here; add more of the same kind if you finish early).** Prefer projects used in embedded,
real-time or messaging work: `nanomsg/nng`, `zeromq/libzmq`, `memcached/memcached`, `redis/redis`, `curl/curl`,
`libuv/libuv`, `libevent/libevent`, `haproxy/haproxy`, `eclipse-mosquitto/mosquitto`, `civetweb/civetweb`,
`eclipse/paho.mqtt.c`, `eclipse-iceoryx/iceoryx`, `eclipse-cyclonedds/cyclonedds`, `eProsima/Fast-DDS`,
`zephyrproject-rtos/zephyr`, `FreeRTOS/FreeRTOS-Kernel`, `apache/nuttx`, `RIOT-OS/RIOT`, `jemalloc/jemalloc`,
`nginx/nginx`, `openssl/openssl`, `sqlite/sqlite` (if mirrored), `grpc/grpc` (C core), `ros2/rclcpp`, `opencv/opencv`
(threading only), `OpenAMP/open-amp`, `qnx-ports` repositories if any exist, `nanomsg/nanomsg`, `redis/hiredis`,
`libssh2/libssh2`. Skip the Linux kernel (too large; syzbot is a separate step).

**Method.** For each repo make a *blobless partial clone* (`git clone --filter=blob:none --no-checkout`), then
`git log --grep` over the keywords above (case-insensitive, `--all-match` where you combine "fix"). Fetch diffs with
`git show` (this pulls the needed blobs lazily). Do **not** hammer the GitHub REST API for commits; use it only for
issue text and licence lookups, through the `gh` CLI which is already logged in. Respect rate limits (sleep and resume).
Make everything **resumable** (a state file; re-running the script continues).

**Keep a commit only if all hold:** it touches C or C++ source (`.c .cc .cpp .cxx .h .hpp`); at most 4 files changed and
at most 250 changed lines in total (small, focused fixes); not a merge commit; not only tests/docs/CI; the message
really describes a fix (not "add support", not "refactor", not a revert unless the revert itself is the fix).

## What to store per commit (JSON Lines, one object per line)

`repo`, `sha`, `parent_sha`, `date` (ISO), `author_is_bot` (bool), `message` (full), `files` (list of paths), `diff`
(unified diff of C/C++ files only, 3 lines of context), `added_lines`, `deleted_lines`, `keywords_matched` (list),
`issue_refs` (numbers found in the message like `#1813`, `fixes #123`), `issue_text` (title + first 3000 chars of the body
for the first referenced issue, if the `gh` lookup works; otherwise null), `license_spdx` (repo licence from `gh`, or
null), `has_reproducer_hint` (bool: the issue text or message contains a code block or a stack trace).

## Where to put it (important: disk and git)

- **Everything on `X:`**. `C:` is nearly full. Cap total disk use at **5 GB**; delete clones when you are done with a repo
  (keep only the JSONL).
- Output: `data/bugfix/commits.jsonl`, plus `data/bugfix/state.json` (resume state). Add `data/bugfix/` to `.gitignore`
  (the raw diffs are other people's code under many licences and must not be committed or redistributed).
- Code: `scripts/mine_bugfix.py` (the miner) and `scripts/bugfix_shapes.py` (the shape analysis below). Python stdlib plus
  `subprocess` calls to `git` and `gh`; no new third-party dependencies.

## Shape analysis (the part that matters)

Write `scripts/bugfix_shapes.py` that reads `commits.jsonl` and labels each commit with **one or more fix shapes**
by simple, transparent heuristics on the diff (regex and line counting, no ML). Start from this taxonomy and extend it
when you see a recurring pattern the list misses (name new shapes clearly):

- `add-predicate-loop`: `if (cond) cond_wait` becomes `while (cond) cond_wait`, or a wait gains a re-check
- `check-flag-before-wait`: an extra `&& flag` or a flag test added to the guard of a wait, under the same lock
- `lock-order`: two lock acquisitions swapped, or a documented global order introduced
- `move-work-out-of-lock`: statements moved after the unlock (shrink the critical section)
- `add-lock` / `remove-lock`: a lock added around shared state / removed to avoid self-deadlock
- `use-trylock-or-timeout`: lock or wait replaced by a trylock/timedwait with error handling
- `sem-to-mutex`: a semaphore used as a lock becomes a mutex
- `priority-inheritance`: a mutex attribute `PTHREAD_PRIO_INHERIT` / protocol added
- `signal-under-lock` / `signal-outside-lock`: where `cond_signal`/`broadcast` sits relative to the mutex changes
- `signal-to-broadcast`: `cond_signal` becomes `cond_broadcast`
- `atomic-or-volatile`: a plain flag becomes atomic/volatile
- `add-cancel-or-shutdown-path`: a cancel/wake/shutdown call added so a waiting thread can leave
- `async-signal-safety`: a non-async-signal-safe call removed from a signal handler
- `other`

Report, for every shape: commit count, number of distinct repos, median size of the diff, and **20 randomly chosen
examples (repo, sha, one-line message)** so a human can check that the heuristic is not fooling itself. Also report the
share of commits that are `other`; if it is above 40%, say so loudly and look at 30 of them to find the missing shapes.

## What to hand back

1. `data/bugfix/commits.jsonl` (target: at least 3,000 kept commits; if the filters yield fewer, say how many and why).
2. `docs/ml/bugfix_mining.md`: how many commits per repo and per year, the shape table above, the licence mix
   (how many commits per SPDX id, how many with no licence), the share with `has_reproducer_hint`, and the **ranked list
   of the 5 fix shapes most worth turning into verified templates**, with your reasoning (frequency, repo spread, how
   mechanical the rewrite looks, whether a kernel trace could even show the bug).
3. A list of anything you could not do or are unsure about. Mark guesses as **(verify)**.

## Rules you must follow

- **No credentials.** Never ask for, read, store or write tokens, keys or passwords. Use the existing `gh` login only. If
  `gh` is not logged in, skip the issue/licence lookups, keep going and say so.
- **Do not commit, push, or create branches or PRs.** Leave the work uncommitted in the working tree.
- **Do not modify `src/tracelens/` or `tests/`.** You may add the two scripts, the `.gitignore` line and the doc.
- Do not install system packages (no `sudo`). `pip` into the repo's `.venv` only if truly needed, and say what.
- Do not redistribute or paste large blocks of other people's code into the doc; short diff excerpts in the examples
  list are fine. Quote at most a few lines per example.
- Work only with public data. Do not scrape anything behind a login.
- If a step would take more than about 30 minutes of wall time or more than 5 GB, stop, report what you have, and say what
  you would do next, instead of pushing on.
- Report numbers you measured, not numbers you expect. If something failed, say it failed.
