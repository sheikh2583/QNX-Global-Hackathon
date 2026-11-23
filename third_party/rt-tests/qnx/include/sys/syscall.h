/* <sys/syscall.h> for the QNX port of rt-tests.  NOT upstream code.
 *
 * QNX has no Linux syscall table.  rt-tests reaches for exactly three
 * numbers; qnx/qnx_compat.c implements the first two and fails the rest
 * with ENOSYS.  The numbers themselves are arbitrary and local.
 *
 * SPDX-License-Identifier: MIT
 */
#ifndef TRACELENS_QNX_SYS_SYSCALL_H
#define TRACELENS_QNX_SYS_SYSCALL_H

#define QNXRT_SYS_gettid 0x7e01
#define QNXRT_SYS_getcpu 0x7e02

#define SYS_gettid  QNXRT_SYS_gettid
#define __NR_gettid QNXRT_SYS_gettid
#define __NR_getcpu QNXRT_SYS_getcpu

long qnxrt_syscall(long number, ...);

#ifndef QNXRT_COMPAT_IMPL
#define syscall qnxrt_syscall
#endif

#endif /* TRACELENS_QNX_SYS_SYSCALL_H */
