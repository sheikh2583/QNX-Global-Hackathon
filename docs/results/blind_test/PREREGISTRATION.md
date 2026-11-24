# Blind test: pre-registered before any run

Written 2026-11-25, **before** building or running any of these programs.

**Frozen system:** every file under `src/tracelens/` hashes to `24fec05b8f9f7746` (sha256 of all `.py` files, sorted by path;
base commit `15ee106` plus the uncommitted work in this tree). **No detector, remedy rule, threshold or model is changed
during this test.** If a result is a miss, it is recorded as a miss. Anything that is not the frozen system (drivers,
build scripts, config budgets) is listed in the results and was fixed before the comparison runs.

**Why this exists:** the memcached result was a case study (rules written after the bug) and NNG, the first cold test,
was missed until a new rule was written. This test asks what the frozen system does on bugs it has not seen.

## Candidates, chosen from issue comment counts, with the reason each was kept or dropped

| Bug | Decision |
|---|---|
| jemalloc#585 `deadlock in je_prof_boot2` | **Dropped**: it needs musl libc and libgcc's unwinder re-entering `malloc`; it cannot occur on QNX's libc |
| libzmq#2759 inproc PAIR deadlock | **Dropped**: no code fix exists; maintainers closed it as misuse of PAIR sockets, so a fix cannot be verified |
| Eclipse Mosquitto#3175 `mosquitto_sub -W` deadlock | **Kept**: famous broker, QNX is a supported platform, fixed upstream by `cd0987a6` (2025-02-27), reproducible with their own binaries |

## What counts as what

For each kept bug, on QNX 8.0 x86_64 with 10 runs per side (buggy tag vs the fix commit):
1. **Reproduced?** (the program hangs, from outside TraceLens: a watchdog or the exit code)
2. **Detected?** Did the frozen rules (not the radar) raise a finding on the hung runs, and what kind?
3. **Radar?** Did the frozen radar flag hung runs more than fixed runs?
4. **Verified?** Does `tracelens compare` on the two sides call upstream's fix VERIFIED?
5. **Fixed by TraceLens?** Only if a TraceLens remedy rule wrote a patch; otherwise no.
