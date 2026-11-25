#!/usr/bin/env bash
# Run all R2 captures, resuming after host-load pauses. Usage (WSL, SDP env and venv active):
#   research/mutants/overnight.sh 127.0.0.1:2222 4
# run.py is resumable: it counts attempts already stored under docs/results/oracle_study/ and continues.
host="${1:?host:port}"; irq="${2:?irq}"
cd "$(dirname "$0")/../.."
while true; do
    python research/mutants/run.py capture --host "$host" --irq "$irq" --n 20
    rc=$?
    [ "$rc" -eq 3 ] || exit "$rc"   # 3 = host not idle: wait and resume; anything else ends the run
    sleep 60
done
