# TraceLens fix: ttk4147_inversion

- Status: **VERIFIED** after 1 round
- Runs per side: 10
- Findings in most 'before' runs: priority_inversion

## Automatic: Replace semaphore 'sem' (used as a lock) with a priority-inheriting mutex

_Rule `semaphore-as-lock`, for finding TL-001 (priority_inversion)._

A POSIX semaphore has no owner, so the QNX kernel cannot raise the priority of the thread that holds it: a medium-priority thread preempts the holder and the high-priority waiter waits for both. A pthread mutex has an owner; with PTHREAD_PRIO_INHERIT (the QNX default) the holder runs at the waiter's priority until it unlocks.

Source locations:
- `UnboundedPriorityInversion.c:118` `sem_wait(&sem);`
- `UnboundedPriorityInversion.c:125` `sem_post(&sem);`
- `UnboundedPriorityInversion.c:161` `sem_wait(&sem);`
- `UnboundedPriorityInversion.c:170` `sem_post(&sem);`

## Patch

```diff
--- a/UnboundedPriorityInversion.c
+++ b/UnboundedPriorityInversion.c
@@ -2,6 +2,7 @@
 #define _GNU_SOURCE
 #define CPU_ID 1
 
+#include <errno.h>
 #include <stdio.h>
 #include <stdlib.h>
 #include <unistd.h>
@@ -11,7 +12,22 @@
 #include <semaphore.h>
 #include <inttypes.h>
 
-sem_t sem;
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
+
+pthread_mutex_t sem;
 pthread_barrier_t barrier;
 pthread_t threadL, threadM, threadH;
 
@@ -70,7 +86,7 @@
 	// Setting up barrier and semaphore
 	int threadNum = 4;
 	pthread_barrier_init(&barrier, NULL, threadNum);
-	sem_init(&sem, 0, 1);
+	tracelens_pi_mutex_init(&sem);
 
 	// TODO set up priority inheritance
 	/*
@@ -98,7 +114,7 @@
 	printf("-------------------End test-------------------\n");
 
 	// Delete semaphore
-	sem_destroy(&sem);
+	pthread_mutex_destroy(&sem);
 
 	printf("Finished\n");
 
@@ -115,14 +131,14 @@
 	print_pri(&threadH, "H1: high usleep\n");
 	usleep(200 * 1000);
 	print_pri(&threadH, "H3: high priority thread waits lock\n");
-	sem_wait(&sem);
+	pthread_mutex_lock(&sem);
 	print_pri(&threadH, "H4: high priority thread has lock\n");
 	print_pri(&threadH, "H5: high priority thread runs with lock\n");
 	busy_wait_ms(100);
 	print_pri(&threadH, "H6: high priority thread runs with lock\n");
 	busy_wait_ms(100);
 	print_pri(&threadH, "H7: high priority thread return lock\n");
-	sem_post(&sem);
+	pthread_mutex_unlock(&sem);
 
 	return NULL;
 }
@@ -158,7 +174,7 @@
 	pthread_barrier_wait(&barrier);
 
 	print_pri(&threadL, "L1: low priority thread waits lock\n");
-	sem_wait(&sem);
+	pthread_mutex_lock(&sem);
 	print_pri(&threadL, "L2: low priority thread has lock\n");
 	print_pri(&threadL, "L3: low priority thread runs with lock\n");
 	busy_wait_ms(100);
@@ -167,7 +183,7 @@
 	print_pri(&threadL, "L5: low priority thread runs with lock\n");
 	busy_wait_ms(100);
 	print_pri(&threadL, "L6: low priority thread return lock\n");
-	sem_post(&sem);
+	pthread_mutex_unlock(&sem);
 
 	return NULL;
 }
```

## Verdict on the target: VERIFIED

- priority_inversion: in 100% of runs before, 0% after
- deadline 'task_p3': p99 1102.99 -> 701.98 ms (budget 1200.00 ms), misses 0 -> 0: within budget
