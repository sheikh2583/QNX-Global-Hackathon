# Blind test: result

Pre-registered in [PREREGISTRATION.md](PREREGISTRATION.md) before any run, with the system frozen
(`src/tracelens/` hash `24fec05b8f9f7746`, re-checked after the test: unchanged).

**Result: no blind detection result was obtained.** The one candidate that survived selection did not reproduce on
QNX, and a second one could not be set up. This is a null result, reported as one.

| Candidate | What happened |
|---|---|
| jemalloc#585 `deadlock in je_prof_boot2` | Dropped before running: needs musl libc and libgcc's unwinder re-entering `malloc`; it cannot occur on QNX's libc |
| libzmq#2759 inproc PAIR deadlock | Dropped before running: no code fix exists (maintainers closed it as misuse of PAIR sockets), so a fix cannot be verified |
| Eclipse Mosquitto#3175 `mosquitto_sub -W` deadlock | Built the buggy parent (`cd0987a6~1`) and upstream's fix (`cd0987a6`) for QNX 8.0 ([third_party/mosquitto_w/](../../../third_party/mosquitto_w/)), with their real broker and client binaries. Ran the report's scenario, `mosquitto_sub --retained-only -W 1 -d` against a broker with retained messages: **0 hangs in 39 runs on the buggy build** (12 with 3,000 retained messages, 12 more with the output going to a slow pipe, 15 with 20,000 retained messages as in the report). The bug did not reproduce, so there was nothing for TraceLens to detect or for the fix to be verified against. The report itself calls it "somewhat difficult to reproduce" |
| Eclipse Mosquitto#1090 (callback set inside a callback) | Looked at as a deterministic backup: the commit the issue references is not in the repository's history, so no buggy and fixed pair could be built. Not tested |

## What this does and does not say

- It does **not** say TraceLens would miss the Mosquitto bug: it never saw it. Only the bug's reproduction failed.
- It means the honest evidence on unseen bugs is still just NNG: reproduced, **missed by the system as it stood**, and
  only detected after a new rule was written. Everything else in this repository on real code (memcached, the NTNU
  exercise) is a case study where the rules were written after the bug.
- Why the Mosquitto hang may not reproduce here: it needs the SIGALRM to land while the main thread holds the logging
  mutex; on QNX that did not happen in 39 runs. Signal delivery timing differs by platform; we did not investigate.
- Setup details for anyone repeating it: Mosquitto needs `-lsocket`, an empty stand-in for `libdl` (QNX has `dlopen` in
  libc), and `user root` in the broker config. None of that touches Mosquitto's source.
