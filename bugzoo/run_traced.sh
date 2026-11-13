#!/bin/sh
# Run a bug-zoo workload under a kernel event trace ON THE QNX TARGET.
#
#   ./run_traced.sh <binary> [args...]
#   -> /tmp/tracelens/<binary>.kev and <binary>.txt (traceprinter output, if available)
#
# Requires the instrumented kernel (procnto-smp-instr). (verify on the QEMU image)
# tracelogger flags (verify against `use tracelogger` on QNX 8.0):
#   -w        wide mode: full kernel-call arguments (sync addresses, coids, ...)
#   -s <sec>  stop after <sec> seconds
#   -f <file> output file
set -eu

if [ $# -lt 1 ]; then
    echo "usage: $0 <binary> [args...]" >&2
    exit 2
fi

BIN=$1
NAME=$(basename "$BIN")
OUT=${TRACELENS_OUT:-/tmp/tracelens}
SECS=${TRACE_SECONDS:-4}
mkdir -p "$OUT"

tracelogger -w -s "$SECS" -f "$OUT/$NAME.kev" &
TL_PID=$!
sleep 1                      # let tracelogger start capturing

"$@"                         # workload runs ~2 s by default (-d)

wait "$TL_PID"
echo "trace: $OUT/$NAME.kev"

if command -v traceprinter >/dev/null 2>&1; then
    traceprinter -f "$OUT/$NAME.kev" > "$OUT/$NAME.txt"
    echo "text:  $OUT/$NAME.txt"
fi
