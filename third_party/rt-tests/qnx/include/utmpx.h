/* <utmpx.h> for the QNX port of rt-tests.  NOT upstream code.
 * ptsematest/pmqtest include it (on glibc it is where sched_getcpu() comes
 * from).  QNX has no utmpx.h, and the port gets the current CPU through
 * qnx/include/sys/syscall.h instead, so this is deliberately empty.
 * SPDX-License-Identifier: MIT
 */
#ifndef TRACELENS_QNX_UTMPX_H
#define TRACELENS_QNX_UTMPX_H
#endif
