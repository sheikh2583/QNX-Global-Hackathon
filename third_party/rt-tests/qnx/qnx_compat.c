/* qnx_compat.c - QNX 8.0 compatibility layer for the rt-tests programs.
 *
 * NOT upstream code.  See qnx_compat.h and ../README.md.
 *
 * SPDX-License-Identifier: MIT   (this file only; upstream/ is GPL-2.0-or-later)
 */
#include "qnx_compat.h"

#include <errno.h>
#include <stdarg.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <sys/neutrino.h>
#include <sys/syspage.h>
#include <sys/syscall.h>

/* ------------------------------------------------------------------ *
 * The runmask this thread was last given through sched_setaffinity()
 * or through the pthread_create wrapper.
 *
 * QNX has no portable "read my runmask" call whose semantics we were
 * willing to guess at, so the port tracks what it set.  __bits == 0
 * means "never set": sched_getaffinity() then reports every online CPU,
 * which is what an unpinned QNX thread may run on.
 * ------------------------------------------------------------------ */
static __thread uint64_t qnxrt_current_mask;

int qnxrt_cpu_count(const cpu_set_t *set)
{
	int n = 0;
	uint64_t b = set->__bits;

	while (b) {
		n += (int)(b & 1u);
		b >>= 1;
	}
	return n;
}

static int qnxrt_num_cpus(void)
{
	long n = sysconf(_SC_NPROCESSORS_ONLN);

	if (n < 1)
		n = 1;
	if (n > QNXRT_CPU_SETSIZE)
		n = QNXRT_CPU_SETSIZE;
	return (int)n;
}

static uint64_t qnxrt_all_cpus(void)
{
	int n = qnxrt_num_cpus();

	return (n >= 64) ? ~(uint64_t)0 : (((uint64_t)1 << n) - 1);
}

/* Apply a mask to the calling thread.
 *
 * Primary path: _NTO_TCTL_RUNMASK_GET_AND_SET_INHERIT, whose argument is a
 * struct _thread_runmask followed by runmask[size] and inherit_mask[size].
 * Both are set to the same value, so a thread this one creates starts on the
 * same CPUs (the pthread_create wrapper re-pins it anyway).
 *
 * Fallback: the older _NTO_TCTL_RUNMASK, whose argument is the 32-bit mask
 * itself cast to void *.  Used only if the first call fails, and only when
 * the mask fits in 32 bits.
 */
static int qnxrt_runmask_apply(uint64_t bits)
{
	int size = RMSK_SIZE(qnxrt_num_cpus());
	struct {
		struct _thread_runmask hdr;
		unsigned words[2 * (QNXRT_CPU_SETSIZE / 32)];
	} rq;
	int i;

	if (size < 1)
		size = 1;
	if (size > QNXRT_CPU_SETSIZE / 32)
		size = QNXRT_CPU_SETSIZE / 32;

	memset(&rq, 0, sizeof(rq));
	rq.hdr.size = size;
	for (i = 0; i < size; i++) {
		unsigned w = (unsigned)((bits >> (32 * i)) & 0xffffffffu);

		rq.words[i] = w;		/* runmask */
		rq.words[size + i] = w;		/* inherit_mask */
	}

	if (ThreadCtl(_NTO_TCTL_RUNMASK_GET_AND_SET_INHERIT, &rq) != -1) {
		qnxrt_current_mask = bits;
		return 0;
	}

	if ((bits >> 32) == 0) {
		unsigned w = (unsigned)(bits & 0xffffffffu);

		if (ThreadCtl(_NTO_TCTL_RUNMASK, (void *)(uintptr_t)w) != -1) {
			qnxrt_current_mask = bits;
			return 0;
		}
	}
	return -1;
}

int sched_setaffinity(pid_t pid, size_t setsize, const cpu_set_t *set)
{
	if (pid != 0 || setsize < sizeof(cpu_set_t) || set == NULL) {
		errno = EINVAL;
		return -1;
	}
	if ((set->__bits & qnxrt_all_cpus()) == 0) {
		errno = EINVAL;
		return -1;
	}
	return qnxrt_runmask_apply(set->__bits & qnxrt_all_cpus());
}

int sched_getaffinity(pid_t pid, size_t setsize, cpu_set_t *set)
{
	if (pid != 0 || setsize < sizeof(cpu_set_t) || set == NULL) {
		errno = EINVAL;
		return -1;
	}
	set->__bits = qnxrt_current_mask ? qnxrt_current_mask : qnxrt_all_cpus();
	return 0;
}

/* ------------------------------------------------------------------ *
 * pthread_attr_setaffinity_np + the pthread_create wrapper.
 *
 * QNX cannot carry a runmask in a pthread_attr_t, so the mask is parked
 * in a small table keyed by the attr object's address and applied by the
 * new thread itself, before the upstream start routine runs.
 * ------------------------------------------------------------------ */
#define QNXRT_ATTR_SLOTS 16

static struct {
	const pthread_attr_t *attr;
	uint64_t bits;
} qnxrt_attr_mask[QNXRT_ATTR_SLOTS];

static pthread_mutex_t qnxrt_attr_lock = PTHREAD_MUTEX_INITIALIZER;

static int qnxrt_attr_find(const pthread_attr_t *attr)
{
	int i;

	for (i = 0; i < QNXRT_ATTR_SLOTS; i++)
		if (qnxrt_attr_mask[i].attr == attr)
			return i;
	return -1;
}

int pthread_attr_setaffinity_np(pthread_attr_t *attr, size_t setsize,
				const cpu_set_t *set)
{
	int i;

	if (attr == NULL || set == NULL || setsize < sizeof(cpu_set_t))
		return EINVAL;
	if ((set->__bits & qnxrt_all_cpus()) == 0)
		return EINVAL;

	pthread_mutex_lock(&qnxrt_attr_lock);
	i = qnxrt_attr_find(attr);
	if (i < 0)
		i = qnxrt_attr_find(NULL);
	if (i >= 0) {
		qnxrt_attr_mask[i].attr = attr;
		qnxrt_attr_mask[i].bits = set->__bits & qnxrt_all_cpus();
	}
	pthread_mutex_unlock(&qnxrt_attr_lock);

	return (i < 0) ? ENOMEM : 0;
}

int pthread_attr_getaffinity_np(const pthread_attr_t *attr, size_t setsize,
				cpu_set_t *set)
{
	int i;

	if (attr == NULL || set == NULL || setsize < sizeof(cpu_set_t))
		return EINVAL;

	pthread_mutex_lock(&qnxrt_attr_lock);
	i = qnxrt_attr_find(attr);
	set->__bits = (i >= 0) ? qnxrt_attr_mask[i].bits : qnxrt_all_cpus();
	pthread_mutex_unlock(&qnxrt_attr_lock);
	return 0;
}

struct qnxrt_trampoline {
	void *(*start)(void *);
	void *arg;
	uint64_t bits;
};

static void *qnxrt_thread_entry(void *raw)
{
	struct qnxrt_trampoline t = *(struct qnxrt_trampoline *)raw;

	free(raw);
	if (t.bits)
		(void)qnxrt_runmask_apply(t.bits);
	return t.start(t.arg);
}

int qnxrt_pthread_create(pthread_t *tid, const pthread_attr_t *attr,
			 void *(*start)(void *), void *arg)
{
	struct qnxrt_trampoline *t;
	uint64_t bits = 0;
	int i, rc;

	if (attr != NULL) {
		pthread_mutex_lock(&qnxrt_attr_lock);
		i = qnxrt_attr_find(attr);
		if (i >= 0)
			bits = qnxrt_attr_mask[i].bits;
		pthread_mutex_unlock(&qnxrt_attr_lock);
	}
	if (bits == 0)
		return pthread_create(tid, attr, start, arg);

	t = malloc(sizeof(*t));
	if (t == NULL)
		return ENOMEM;
	t->start = start;
	t->arg = arg;
	t->bits = bits;

	rc = pthread_create(tid, attr, qnxrt_thread_entry, t);
	if (rc != 0)
		free(t);
	return rc;
}

/* ------------------------------------------------------------------ *
 * syscall(): only the two numbers rt-tests actually needs.  Everything
 * else (sched_setattr/sched_getattr, which rt-sched.c reaches through
 * syscall()) fails with ENOSYS, because QNX has no SCHED_DEADLINE.
 * ------------------------------------------------------------------ */
long qnxrt_syscall(long number, ...)
{
	va_list ap;
	long rc;

	switch (number) {
	case QNXRT_SYS_gettid:
		return (long)pthread_self();

	case QNXRT_SYS_getcpu: {
		int *cpu;
		uint64_t m = qnxrt_current_mask;
		int i;

		va_start(ap, number);
		cpu = va_arg(ap, int *);
		va_end(ap);

		/* Only answerable when this thread is pinned to one CPU. */
		if (cpu == NULL || m == 0 || (m & (m - 1)) != 0) {
			errno = ENOSYS;
			return -1;
		}
		for (i = 0; i < QNXRT_CPU_SETSIZE; i++)
			if (m >> i == 1) {
				*cpu = i;
				return 0;
			}
		errno = ENOSYS;
		return -1;
	}

	default:
		errno = ENOSYS;
		rc = -1;
		break;
	}
	return rc;
}
