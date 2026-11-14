# TraceLens fix: z4_camera_pipeline

- Status: **VERIFIED** after 1 round
- Runs per side: 5
- Findings in most 'before' runs: deadline_miss, mutex_contention

## Automatic: Shrink the 'store_lock' critical section: move memset, tl_spin_us outside the lock

_Rule `shrink-critical-section`, for finding TL-002 (mutex_contention)._

Every MUTEX wait in a QNX trace is real contention (uncontended mutexes never enter the kernel). The lock only needs to cover statements that read or write the data it protects; computation on private buffers inside it serialises the threads for nothing.

Source locations:
- `main.c:34` `pthread_mutex_lock(&store_lock);`

## Symptom: Deadline misses in 'frame': a symptom

_Rule `symptom`, for finding TL-001 (deadline_miss)._

deadline miss is the visible effect; the trace also shows its cause (mutex_contention). It is expected to clear with that fix, and the re-trace checks that it does.

## Patch

```diff
--- a/main.c
+++ b/main.c
@@ -31,10 +31,10 @@
     for (unsigned k = 0; k < periods; k++) {
         tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US + id * 100 * TL_NS_PER_US);
         tl_job_start("frame");
-        pthread_mutex_lock(&store_lock);
         /* Demosaic + colour-correct the tile, then publish it. */
         memset(tile, (int)(k + id), TILE_BYTES);
         tl_spin_us(1500);
+        pthread_mutex_lock(&store_lock);
         memcpy(frame_store[id], tile, TILE_BYTES);
         pthread_mutex_unlock(&store_lock);
         tl_job_end("frame");
```

## Verdict on the target: VERIFIED

- deadline_miss: in 100% of runs before, 0% after
- mutex_contention: in 100% of runs before, 0% after
- deadline 'frame': p99 7.45 -> 2.99 ms (budget 4.00 ms), misses 2031 -> 0: significantly faster (p=0)
