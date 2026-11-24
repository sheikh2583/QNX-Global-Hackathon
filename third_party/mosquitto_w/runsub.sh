#!/bin/sh
# On the QNX target: one run of the report's scenario, with a watchdog from outside the program.
# usage: runsub.sh <dir>     exits 0 if the pipeline ends by itself within 8 s, 3 if it hangs (then kills it)
cd "$1" || exit 1
# stdout goes to a pipe with a slow reader, like the terminal in the report: a writer blocks while it holds the log mutex
(./mosquitto_sub -h 127.0.0.1 --retained-only -W 1 -F %t -t 'retained/+' -d 2>&1 | while read l; do :; done) &
P=$!
i=0
while [ $i -lt 16 ]; do
    sleep 0.5
    kill -0 $P 2>/dev/null || { echo "exited"; exit 0; }
    i=$((i+1))
done
echo "HANG: mosquitto_sub still running 8 s after start (eclipse-mosquitto/mosquitto#3175)"
slay -s KILL -f mosquitto_sub
kill -9 $P
exit 3
