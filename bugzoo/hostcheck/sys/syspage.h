/* Host-only stub of <sys/syspage.h> for `make hostcheck`. Not for QNX builds. */
#ifndef TL_STUB_SYSPAGE_H
#define TL_STUB_SYSPAGE_H

#include <stdint.h>

struct qtime_entry {
    uint64_t cycles_per_sec;
};

extern struct qtime_entry *tl_stub_syspage_qtime;
#define SYSPAGE_ENTRY(entry) (tl_stub_syspage_##entry)

#endif
