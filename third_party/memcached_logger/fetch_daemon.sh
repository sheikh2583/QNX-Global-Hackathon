#!/bin/sh
# Assemble work_daemon/: memcached 1.6.45's own .c files, unedited, from the pinned commit, plus our driver.
set -e
cd "$(dirname "$0")"
./fetch.sh >/dev/null
mkdir -p work_daemon
for f in assoc authfile base64 bipbuffer cache crawler daemon hash items itoa_ljust jenkins_hash logger \
         memcached murmur3_hash proto_bin proto_parser proto_text restart slab_automove slabs slabs_mover \
         stats_prefix thread util; do cp "src/$f.c" "work_daemon/$f.c"; done
cp src/vendor/mcmc/mcmc.c work_daemon/mcmc.c
cp daemon_repro.c work_daemon/daemon_repro.c
echo "ready: work_daemon/ ($(ls work_daemon | wc -l) files)"
