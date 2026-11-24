#!/bin/bash
# Copy the two Mosquitto builds to the QNX target and start a broker per side. Run in WSL.
# Usage: target_setup.sh <buggy|fixed> <retained-count>
# The scenario is the one in eclipse-mosquitto/mosquitto#3175: many retained messages, then
# `mosquitto_sub --retained-only -W 1 -d`, so the SIGALRM from -W can land while a log line is being written.
set -e
SIDE=$1; N=${2:-5000}
HERE="$(cd "$(dirname "$0")" && pwd)"
SSH="ssh -p 2222 -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR root@127.0.0.1"
SCP="scp -P 2222 -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
D=/tmp/mq_$SIDE
$SSH "slay -s KILL -f mosquitto; sleep 1; rm -rf $D; mkdir -p $D"
$SCP "$HERE/deps/$SIDE/sbin/mosquitto" "$HERE/deps/$SIDE/bin/mosquitto_sub" "$HERE/deps/$SIDE/bin/mosquitto_pub" root@127.0.0.1:$D/
printf 'user root\nlistener 1883 127.0.0.1\nallow_anonymous true\n' > /tmp/mq.conf
$SCP /tmp/mq.conf root@127.0.0.1:$D/mq.conf
$SSH "cd $D && chmod +x mosquitto mosquitto_sub mosquitto_pub && (./mosquitto -c mq.conf >/dev/null 2>&1 </dev/null &) ; sleep 2; i=0; while [ \$i -lt $N ]; do ./mosquitto_pub -t retained/\$i -m \$i -r -q 0; i=\$((i+1)); done; echo published \$i"
