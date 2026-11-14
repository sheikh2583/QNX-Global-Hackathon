# TraceLens fix: z2_brake_by_wire

- Status: **VERIFIED** after 1 round
- Runs per side: 5
- Findings in most 'before' runs: deadline_miss, priority_inversion

## Automatic: Let the server inherit its clients' priority: drop _NTO_CHF_FIXED_PRIORITY

_Rule `fixed-priority-channel`, for finding TL-001 (priority_inversion)._

By default a QNX server thread runs at the priority of the client whose message it receives, so a high-priority request is served at high priority. _NTO_CHF_FIXED_PRIORITY turns that off: the server stays at its own low priority and any medium-priority thread delays the high-priority client's reply.

Source locations:
- `main.c:79` `int chid = ChannelCreate(_NTO_CHF_FIXED_PRIORITY);`

## Symptom: Deadline misses in 'brake': a symptom

_Rule `symptom`, for finding TL-002 (deadline_miss)._

deadline miss is the visible effect; the trace also shows its cause (priority_inversion). It is expected to clear with that fix, and the re-trace checks that it does.

## Patch

```diff
--- a/main.c
+++ b/main.c
@@ -76,7 +76,7 @@
 {
     t0 = tl_parse_args(argc, argv, &run_s);
 
-    int chid = ChannelCreate(_NTO_CHF_FIXED_PRIORITY);
+    int chid = ChannelCreate(0);
     if (chid == -1)
         tl_die("ChannelCreate");
```

## Verdict on the target: VERIFIED

- deadline_miss: in 100% of runs before, 0% after
- priority_inversion: in 100% of runs before, 0% after
- deadline 'brake': p99 6.75 -> 0.77 ms (budget 2.00 ms), misses 1000 -> 0: significantly faster (p=0)
