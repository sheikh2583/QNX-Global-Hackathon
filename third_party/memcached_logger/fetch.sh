#!/bin/sh
# Fetch memcached 1.6.45 (BSD-3, but we do not vendor it) at the exact commit the issue names, and
# copy the four unedited source files the workload needs into work/.
set -e
cd "$(dirname "$0")"
COMMIT=2d51e364799bc9698bd4b11728ea978cea12da6e
[ -d src/.git ] || git clone --quiet https://github.com/memcached/memcached.git src
git -C src fetch --quiet --depth 1 origin "$COMMIT" 2>/dev/null || true
git -C src checkout --quiet "$COMMIT"
mkdir -p work
for f in logger.c bipbuffer.c globals.c util.c; do cp "src/$f" "work/$f"; done
cp harness.c work/harness.c
echo "ready: work/ ($(git -C src rev-parse --short HEAD))"
