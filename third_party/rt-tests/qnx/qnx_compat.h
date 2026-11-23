/* qnx_compat.h - QNX 8.0 compatibility layer for the rt-tests programs.
 *
 * NOT upstream code. Written for TraceLens so that the rt-tests sources under
 * ../upstream/ compile and run on QNX Neutrino 8.0 **without being edited**.
 * The build force-includes this header (qcc -include .../qnx_compat.h), so
 * every upstream translation unit sees it before its own includes.
 *
 * What it supplies, and why (see ../README.md for the full list):
 *   - cpu_set_t and the CPU_* macros, which QNX does not have
 *   - sched_setaffinity / sched_getaffinity / pthread_attr_setaffinity_np,
 *     mapped onto QNX's ThreadCtl(_NTO_TCTL_RUNMASK) runmask
 *   - the Linux-only scheduling policy constants rt-tests names in switches
 *   - syscall(), enough of it for gettid() and for the sched_setattr() stubs
 *
 * SPDX-License-Identifier: MIT   (this file only; upstream/ is GPL-2.0-or-later)
 */
#ifndef TRACELENS_QNX_RT_COMPAT_H
#define TRACELENS_QNX_RT_COMPAT_H

#if !defined(__QNX__) && !defined(__QNXNTO__)
#error "qnx_compat.h is only for the QNX port"
#endif

#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
#include <sched.h>
#include <pthread.h>

/* ------------------------------------------------------------------ *
 * strdupa(): a glibc extension pi_stress uses to parse --sched.
 * Same definition glibc gives it, on QNX's alloca.
 * ------------------------------------------------------------------ */
#include <alloca.h>
#include <string.h>

#ifndef strdupa
#define strdupa(s)							\
	(__extension__ ({						\
		const char *__sd_s = (s);				\
		size_t __sd_n = strlen(__sd_s) + 1;			\
		char *__sd_d = (char *)alloca(__sd_n);			\
		(char *)memcpy(__sd_d, __sd_s, __sd_n);			\
	}))
#endif

/* ------------------------------------------------------------------ *
 * Linux scheduling policies that rt-tests mentions in switch/else-if
 * chains (policy_to_string, string_to_policy, pi_stress --sched).
 *
 * QNX already uses 0..9: SCHED_NOCHANGE 0, FIFO 1, RR 2, OTHER 3,
 * SPORADIC 4, ADJTOHEAD 5, ADJTOTAIL 6, SETPRIO 7, ...  A `switch` with
 * two labels of the same value will not compile, and SCHED_DEADLINE in
 * upstream's rt-sched.h would otherwise land on QNX's SCHED_ADJTOTAIL,
 * so these get values no QNX policy uses.  Consequence: `--sched
 * policy=batch|idle|deadline` is accepted on the command line and then
 * rejected by the kernel.  The tests we run use SCHED_FIFO only.
 * ------------------------------------------------------------------ */
#ifndef SCHED_BATCH
#define SCHED_BATCH    0x7f01
#endif
#ifndef SCHED_IDLE
#define SCHED_IDLE     0x7f02
#endif
#ifndef SCHED_DEADLINE
#define SCHED_DEADLINE 0x7f03
#endif

/* ------------------------------------------------------------------ *
 * cpu_set_t.  QNX uses a runmask: an array of unsigned words with the
 * RMSK_SET/RMSK_CLR macros from <sys/neutrino.h>.  One 64-bit word is
 * enough for every QNX x86_64 configuration we target (max 64 CPUs).
 * ------------------------------------------------------------------ */
#define QNXRT_CPU_SETSIZE 64
#define CPU_SETSIZE       QNXRT_CPU_SETSIZE

typedef struct qnxrt_cpu_set {
	uint64_t __bits;
} cpu_set_t;

#define CPU_ZERO(s)       ((void)((s)->__bits = (uint64_t)0))
#define CPU_SET(c, s)     ((void)((s)->__bits |=  ((uint64_t)1 << ((unsigned)(c) & 63u))))
#define CPU_CLR(c, s)     ((void)((s)->__bits &= ~((uint64_t)1 << ((unsigned)(c) & 63u))))
#define CPU_ISSET(c, s)   (((s)->__bits >> ((unsigned)(c) & 63u)) & (uint64_t)1)
#define CPU_EQUAL(a, b)   ((a)->__bits == (b)->__bits)
#define CPU_COUNT(s)      qnxrt_cpu_count(s)
#define CPU_AND(d, a, b)  ((void)((d)->__bits = (a)->__bits & (b)->__bits))
#define CPU_OR(d, a, b)   ((void)((d)->__bits = (a)->__bits | (b)->__bits))

int qnxrt_cpu_count(const cpu_set_t *set);

/* Affinity, on QNX's runmask.  pid must be 0 ("this thread"): rt-tests
 * only ever passes 0.  Both return 0 on success, -1 with errno set. */
int sched_setaffinity(pid_t pid, size_t setsize, const cpu_set_t *set);
int sched_getaffinity(pid_t pid, size_t setsize, cpu_set_t *set);

/* pthread_attr_setaffinity_np records the mask against this attr object;
 * the pthread_create wrapper below applies it in the new thread before
 * calling the thread's start routine. */
int pthread_attr_setaffinity_np(pthread_attr_t *attr, size_t setsize,
				const cpu_set_t *set);
int pthread_attr_getaffinity_np(const pthread_attr_t *attr, size_t setsize,
				cpu_set_t *set);

int qnxrt_pthread_create(pthread_t *tid, const pthread_attr_t *attr,
			 void *(*start)(void *), void *arg);

/* QNX has no per-thread create-time runmask, so pthread_create has to be
 * the wrapper.  QNXRT_COMPAT_IMPL keeps qnx_compat.c itself able to call
 * the real one. */
#ifndef QNXRT_COMPAT_IMPL
#define pthread_create qnxrt_pthread_create
#endif

#endif /* TRACELENS_QNX_RT_COMPAT_H */
