# Residual hang after upstream's fix: pre-registration (NOT RUN)

Written 2026-11-25, before any capture for this question. Status: **preregistered, not yet run** (needs the QNX VM).

**Observation.** In the first NNG batch, with the client started before the server, the upstream-fixed commit (aac4dc36)
hung in 2 of 7 captures; v1.7.3 hung in 8 of 8 (see [README.md](README.md)). We did not chase it. One batch of 7 is not
evidence of a bug: the driver may be the cause.

**Hypotheses.**
- H1 (residual bug): the fixed commit hangs in `nng_close()` when the dialer has not yet connected, independent of the driver.
- H0 (artifact or noise): the "hang" is the driver's 6 s watchdog firing on a legitimately slow cycle (dial retry with no
  server up), or an ordering bug in `third_party/nng_close/nng_repro.c`, and a longer watchdog or a corrected driver removes it.

**Driver change (the only one).** The watchdog threshold is a parameter; the server-first arm keeps today's 6 s. The
client-first arm runs with the server started 0 s after the client (no `sleep(3)`), 6 s watchdog **and** a 60 s watchdog
variant, so a slow-but-finishing cycle is told apart from a stuck one. The detector's own view (`stuck_job`: threads in
condvar wait with no signal, joiner in JOIN) is recorded for every hang, so we see whether the thread states match the
original bug's shape or something else.

**Design.** Fixed commit only. 20 captures server-first and 20 captures client-first (6 s watchdog), plus 20 client-first
with the 60 s watchdog. Lossy captures are replaced and counted. Unit: the capture. Host idle, load logged.

**Success criterion (H1 supported).** Client-first hangs in the 60 s arm in at least 3 of 20 captures, server-first in 0 of 20,
with the stuck threads inside `nng_close()`/aio teardown, and the hang reproduces after an independent re-run of the driver
by someone who has read nng_repro.c. Anything else is reported as a null or an artifact: if the 60 s arm shows 0 hangs,
the 2 of 7 was the watchdog; if hangs appear in both orders, the 2 of 7 is not about ordering.

**Before claiming anything:** search upstream NNG issues and later commits for a known follow-up fix (not done yet); check the
driver for the artifact in H0; report a null honestly. Even if H1 holds, the claim is "a hang in the fixed commit under this
driver", reported upstream by the user if they choose, not a vulnerability claim.

**Frozen system:** every `.py` file under `src/tracelens/` hashes to `a4b43ec945d06db3` (sha256, sorted by path, working tree
at 7f601cf plus the uncommitted research edits, which add `--confidence` to `tracelens eval fix` only). No detector, rule or
threshold changes during this check.
