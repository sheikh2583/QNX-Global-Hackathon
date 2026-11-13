/* Host-only stub of <sys/trace.h> for `make hostcheck`. Not for QNX builds. */
#ifndef TL_STUB_TRACE_H
#define TL_STUB_TRACE_H

#define _NTO_TRACE_USERFIRST 0
#define _NTO_TRACE_INSERTUSRSTREVENT 0x30

int TraceEvent(int mode, ...);

#endif
