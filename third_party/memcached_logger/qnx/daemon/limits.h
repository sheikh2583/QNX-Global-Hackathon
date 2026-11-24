/* SPDX-License-Identifier: MIT -- QNX's <limits.h> undefines IOV_MAX ("_XOPEN_IOV_MAX", 16); memcached
 * needs the macro. 16 is the POSIX minimum, so sendmsg() never gets more entries than QNX must accept. */
#ifndef QNXRT_LIMITS_H
#define QNXRT_LIMITS_H
#include_next <limits.h>
#ifndef IOV_MAX
#define IOV_MAX 16
#endif
#endif
