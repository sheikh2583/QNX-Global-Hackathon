# hostcheck: QNX API stubs

Minimal declarations of the QNX Neutrino APIs the bug zoo uses, so `make hostcheck`
can type-check every workload with a plain host `gcc` (CI runs it on Ubuntu, no QNX
license needed). Signatures follow the QNX 8.0 library reference **(verify)**; values
of constants are placeholders. These files are never used to build for QNX: `qcc`
uses the real SDP headers.
