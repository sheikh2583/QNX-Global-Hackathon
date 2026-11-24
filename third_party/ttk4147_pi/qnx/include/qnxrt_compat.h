/* SPDX-License-Identifier: MIT
 *
 * QNX 8.0 compatibility layer for the NTNU TTK4147 exercise program UnboundedPriorityInversion.c.
 * Written for the TraceLens port; NOT part of the upstream project. It is reached only through the
 * two shim headers next to it (sched.h, pthread.h), so the upstream file compiles unmodified.
 *
 *   1. cpu_set_t, CPU_ZERO/CPU_SET and pthread_setaffinity_np()  (Linux; QNX uses a thread runmask)
 *   2. the aarch64 instruction pair  "isb; mrs Xn, cntvct_el0"  that upstream's busy_wait_ms() runs
 *      inline (a Raspberry Pi virtual counter, 54 MHz). The file is compiled for x86_64 here, so the
 *      two mnemonics are defined as assembler macros: isb does nothing and mrs reads the x86 time
 *      stamp counter scaled to 54 MHz, so busy_wait_ms(n) still lasts about n milliseconds.
 *   3. TraceLens job markers around every thread start routine (see pthread.h).
 */
#ifndef QNXRT_COMPAT_H
#define QNXRT_COMPAT_H

#include <stdint.h>
#include <string.h>
#include <sys/neutrino.h>
#include <sys/syspage.h>

/* ---- 1. CPU sets --------------------------------------------------------------------------- */
#ifndef CPU_SETSIZE
typedef struct { uint64_t qnxrt_bits; } cpu_set_t;
#define CPU_SETSIZE 64
#define CPU_ZERO(s)       ((s)->qnxrt_bits = 0)
#define CPU_SET(c, s)     ((s)->qnxrt_bits |= (1ULL << (c)))
#define CPU_CLR(c, s)     ((s)->qnxrt_bits &= ~(1ULL << (c)))
#define CPU_ISSET(c, s)   (((s)->qnxrt_bits >> (c)) & 1ULL)
#endif

/* QNX 8.0 accepts a single CPU or all CPUs as a runmask (measured on this target, see the TraceLens
 * bug zoo header). Upstream asks for exactly one CPU. */
static inline int qnxrt_setaffinity_self(size_t sz, const cpu_set_t *set)
{
    (void)sz;
    return ThreadCtl(_NTO_TCTL_RUNMASK, (void *)(uintptr_t)set->qnxrt_bits) == -1 ? -1 : 0;
}

/* ---- 2. aarch64 virtual counter on x86_64 --------------------------------------------------- */
#if defined(__x86_64__)
/* counter = tsc * qnxrt_cnt_k / 2^32, K chosen at start-up so the counter ticks at 54 MHz. */
static uint64_t qnxrt_cnt_k __attribute__((used));
static void qnxrt_cnt_init(void) __attribute__((constructor));
static void qnxrt_cnt_init(void)
{
    const uint64_t cps = SYSPAGE_ENTRY(qtime)->cycles_per_sec;  /* ClockCycles() is the TSC on x86 */
    qnxrt_cnt_k = (uint64_t)(((unsigned __int128)54000000ULL << 32) / cps);
}
__asm__(
    ".macro isb\n"
    ".endm\n"
    ".macro mrs dst, sysreg\n"
    "  lea -136(%rsp), %rsp\n"          /* skip the red zone */
    "  mov %rax, 0(%rsp)\n"
    "  mov %rdx, 8(%rsp)\n"
    "  mov %rcx, 24(%rsp)\n"
    "  rdtsc\n"
    "  shl $32, %rdx\n"
    "  or %rdx, %rax\n"
    "  mov qnxrt_cnt_k(%rip), %rcx\n"
    "  mul %rcx\n"                      /* rdx:rax = tsc * k */
    "  shrd $32, %rdx, %rax\n"          /* >> 32 */
    "  mov %rax, 16(%rsp)\n"
    "  mov 0(%rsp), %rax\n"
    "  mov 8(%rsp), %rdx\n"
    "  mov 24(%rsp), %rcx\n"
    "  mov 16(%rsp), \\dst\n"
    "  lea 136(%rsp), %rsp\n"
    ".endm\n");
#endif

#endif /* QNXRT_COMPAT_H */
