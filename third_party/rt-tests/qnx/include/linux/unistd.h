/* <linux/unistd.h> for the QNX port of rt-tests.  NOT upstream code.
 * ptsematest/pmqtest include it for __NR_gettid; QNX has no linux/ headers,
 * and qnx/include/sys/syscall.h already supplies the numbers.
 * SPDX-License-Identifier: MIT
 */
#ifndef TRACELENS_QNX_LINUX_UNISTD_H
#define TRACELENS_QNX_LINUX_UNISTD_H
#include <sys/syscall.h>
#include <unistd.h>
#endif
