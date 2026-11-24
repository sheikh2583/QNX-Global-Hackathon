/* Hand-written stand-in for memcached's autoconf config.h (no autotools in this environment).
   Only what logger.c and its headers need; every feature macro is left undefined. */
#define PACKAGE "memcached"
#define VERSION "1.6.45"
#define HAVE_SYS_TYPES_H 1
#define _GNU_SOURCE 1
/* the real config.h pulls these in through autoconf checks */
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
