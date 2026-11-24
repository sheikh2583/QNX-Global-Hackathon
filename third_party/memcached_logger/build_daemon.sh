#!/bin/bash
# Build libevent 2.1.12-stable and memcached 1.6.45's own sources for QNX 8.0 x86_64, then link them with
# our driver. Run in WSL after `source ~/qnx800/qnxsdp-env.sh`. Needs autoconf, automake, libtool.
# Output: out/mc_daemon (the driver plus the real daemon). Nothing here edits upstream source.
set -e
cd "$(dirname "$0")"
HERE=$PWD
export PATH=$PATH:$QNX_HOST/usr/bin

# 1. libevent, built outside the repository folder: libtool's install step breaks on spaces in a path
LE=/tmp/le-src
if [ ! -d "$HERE/deps/le-install" ]; then
  rm -rf $LE /tmp/le-build
  git clone --quiet --depth 1 --branch release-2.1.12-stable https://github.com/libevent/libevent.git $LE
  (cd $LE && ./autogen.sh >/dev/null 2>&1)
  mkdir /tmp/le-build && cd /tmp/le-build
  # SA_RESTART does not exist on QNX; libevent uses it only to restart interrupted system calls
  CC="qcc -Vgcc_ntox86_64" CFLAGS="-O2 -DSA_RESTART=0" $LE/configure --host=x86_64-pc-nto-qnx8.0.0 \
    --prefix=/tmp/le-install --disable-openssl --disable-samples --disable-shared --disable-libevent-regress >/dev/null
  make -j8 >/dev/null && make install prefix=/tmp/le-install >/dev/null
  mkdir -p "$HERE/deps" && cp -r /tmp/le-install "$HERE/deps/le-install"
  cd "$HERE"
fi

# 2. memcached's own files, unedited, and the driver
./fetch_daemon.sh

# 3. compile and link (qnx/daemon/config.h is the autoconf output of a cross `configure` run, kept for reference)
qcc -Vgcc_ntox86_64 -O2 -g -std=gnu11 -w -DHAVE_CONFIG_H -DNDEBUG -DSA_RESTART=0 -Dmain=memcached_main \
  -Iqnx/daemon -Isrc -Isrc/vendor/mcmc -Ideps/le-install/include \
  -o out/mc_daemon work_daemon/*.c -Ldeps/le-install/lib -levent -lsocket
echo "built out/mc_daemon"
