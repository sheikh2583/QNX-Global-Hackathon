# TraceLens fix: z1_infusion_pump

- Status: **VERIFIED** after 2 rounds
- Runs per side: 5
- Findings in most 'before' runs: deadline_miss, priority_inversion

## Automatic: Replace semaphore 'buf_lock' (used as a lock) with a priority-inheriting mutex

_Rule `semaphore-as-lock`, for finding TL-001 (priority_inversion)._

A POSIX semaphore has no owner, so the QNX kernel cannot raise the priority of the thread that holds it: a medium-priority thread preempts the holder and the high-priority waiter waits for both. A pthread mutex has an owner; with PTHREAD_PRIO_INHERIT (the QNX default) the holder runs at the waiter's priority until it unlocks.

Source locations:
- `main.c:36` `sem_wait(&buf_lock);`
- `main.c:41` `sem_post(&buf_lock);`
- `main.c:65` `sem_wait(&buf_lock);`
- `main.c:70` `sem_post(&buf_lock);`

## Symptom: Deadline misses in 'control': a symptom

_Rule `symptom`, for finding TL-002 (deadline_miss)._

deadline miss is the visible effect; the trace also shows its cause (priority_inversion). It is expected to clear with that fix, and the re-trace checks that it does.

## Automatic: Shrink the 'buf_lock' critical section: move tl_spin_us outside the lock

_Rule `shrink-critical-section`, for finding TL-002 (mutex_contention)._

Every MUTEX wait in a QNX trace is real contention (uncontended mutexes never enter the kernel). The lock only needs to cover statements that read or write the data it protects; computation on private buffers inside it serialises the threads for nothing.

Source locations:
- `main.c:53` `pthread_mutex_lock(&buf_lock);`
- `main.c:82` `pthread_mutex_lock(&buf_lock);`

## Symptom: Deadline misses in 'control': a symptom

_Rule `symptom`, for finding TL-001 (deadline_miss)._

deadline miss is the visible effect; the trace also shows its cause (mutex_contention). It is expected to clear with that fix, and the re-trace checks that it does.

## Patch

```diff
--- a/main.c
+++ b/main.c
@@ -10,8 +10,25 @@
  * control at 0. Timers fire on tick boundaries, so a spacing of whole ticks fixes the
  * order on every run regardless of the tick's phase.
  */
+#include <errno.h>
+#include <pthread.h>
 #include <semaphore.h>
 #include "tl.h"
+
+/* --- TraceLens remedy: priority-inheriting mutex (replaces a semaphore used as a lock) --- */
+static int tracelens_pi_mutex_init(pthread_mutex_t *m)
+{
+    pthread_mutexattr_t a;
+    int rc = pthread_mutexattr_init(&a);
+    if (rc == 0)
+        rc = pthread_mutexattr_setprotocol(&a, PTHREAD_PRIO_INHERIT);
+    if (rc == 0)
+        rc = pthread_mutex_init(m, &a);
+    pthread_mutexattr_destroy(&a);
+    if (rc != 0)
+        errno = rc;
+    return rc;
+}
 
 #define PERIOD_US 10000
 
@@ -20,7 +37,7 @@
     unsigned n;
 } sensor_buf;
 
-static sem_t buf_lock;
+static pthread_mutex_t buf_lock;
 static uint64_t t0;
 static unsigned run_s;
 
@@ -33,12 +50,12 @@
     for (unsigned k = 0; k < periods(); k++) {
         tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US);
         tl_job_start("control");
-        sem_wait(&buf_lock);
         double dose = 0;
+        pthread_mutex_lock(&buf_lock);
         for (unsigned i = 0; i < sensor_buf.n; i++)
             dose += sensor_buf.samples[i];
+        pthread_mutex_unlock(&buf_lock);
         tl_spin_us(100); /* dose computation */
-        sem_post(&buf_lock);
         (void)dose;
         tl_job_end("control");
     }
@@ -62,12 +79,12 @@
     tl_thread_init("logger", 10, 0x1);
     for (unsigned k = 0; k < periods(); k++) {
         tl_sleep_until(t0 + (uint64_t)k * PERIOD_US * TL_NS_PER_US - 2000 * TL_NS_PER_US);
-        sem_wait(&buf_lock);
+        pthread_mutex_lock(&buf_lock);
         sensor_buf.n = 64;
         for (unsigned i = 0; i < sensor_buf.n; i++)
             sensor_buf.samples[i] = (double)(k + i);
+        pthread_mutex_unlock(&buf_lock);
         tl_spin_us(2500); /* write to flash */
-        sem_post(&buf_lock);
     }
     return NULL;
 }
@@ -75,12 +92,12 @@
 int main(int argc, char **argv)
 {
     t0 = tl_parse_args(argc, argv, &run_s);
-    if (sem_init(&buf_lock, 0, 1) == -1)
+    if (tracelens_pi_mutex_init(&buf_lock) != 0)
         tl_die("sem_init");
 
     pthread_t th[3] = { tl_spawn(logger, NULL), tl_spawn(telemetry, NULL), tl_spawn(control, NULL) };
     for (int i = 0; i < 3; i++)
         pthread_join(th[i], NULL);
-    sem_destroy(&buf_lock);
+    pthread_mutex_destroy(&buf_lock);
     return 0;
 }
```

## Verdict on the target: VERIFIED

- deadline_miss: in 100% of runs before, 0% after
- priority_inversion: in 100% of runs before, 0% after
- deadline 'control': p99 7.18 -> 0.54 ms (budget 2.00 ms), misses 953 -> 0: significantly faster (p=7.1e-310)
