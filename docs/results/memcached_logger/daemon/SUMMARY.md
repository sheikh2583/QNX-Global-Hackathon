# TraceLens fix: work_daemon

- Status: **VERIFIED** after 1 round
- Runs per side: 10
- Findings in most 'before' runs: lost_wakeup

## Automatic: Re-check 'do_run_logger_thread' under the lock before the wait: if ((watcher_count == 0) && do_run_logger_thread)

_Rule `recheck-before-wait`, for finding TL-001 (lost_wakeup)._

pthread_cond_signal() wakes only a thread that is already waiting. The stopper sets the flag and signals under the mutex, but the waiter tests only its own idle condition before it waits, so a stop that lands while the waiter is not yet waiting is lost and the waiter sleeps forever. Testing the flag under the same mutex, in the same condition that guards the wait, makes the two orderings equivalent: either the waiter sees the flag and skips the wait, or it is already waiting when the signal arrives.

Source locations:
- `assoc.c:247` `pthread_cond_wait(&maintenance_cond, &maintenance_lock);`
- `crawler.c:623` `pthread_cond_wait(&lru_crawler_cond, &lru_crawler_lock);`
- `crawler.c:785` `pthread_cond_wait(&lru_crawler_cond, &lru_crawler_lock);`
- `logger.c:931` `pthread_cond_wait(&logger_stack_cond, &logger_stack_lock);`
- `thread.c:139` `pthread_cond_wait(&init_cond, &init_lock);`

Notes:
- memcached.c: braces do not balance (preprocessor alternatives?); not scanned
- proto_parser.c: braces do not balance (preprocessor alternatives?); not scanned

## Patch

```diff
--- a/logger.c
+++ b/logger.c
@@ -925,7 +925,7 @@
 
         /* Call function to iterate each logger. */
         pthread_mutex_lock(&logger_stack_lock);
-        if (watcher_count == 0) {
+        if ((watcher_count == 0) && do_run_logger_thread) {
             // Not bothering to loop on the condition here since it's fine to
             // walk through with zero watchers.
             pthread_cond_wait(&logger_stack_cond, &logger_stack_lock);
```

## Verdict on the target: VERIFIED

- lost_wakeup: in 100% of runs before, 0% after
