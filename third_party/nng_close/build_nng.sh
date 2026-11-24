#!/bin/bash
# Build NNG for QNX 8.0 x86_64 twice, then link our driver against each:
#   v1.7.3     (tag, the version the report names, has the bug)   -> out/nng_repro
#   aac4dc36   (merge of upstream's fix, PR #1824, 2024-04-24)    -> out/nng_repro_fixed
# Run in WSL after `source ~/qnx800/qnxsdp-env.sh`; needs cmake. Nothing in NNG is edited.
set -e
cd "$(dirname "$0")"; HERE=$PWD
export PATH=$PATH:$QNX_HOST/usr/bin
cat > /tmp/qnx-toolchain.cmake <<'T'
set(CMAKE_SYSTEM_NAME QNX)
set(CMAKE_C_COMPILER qcc)
set(CMAKE_C_COMPILER_TARGET gcc_ntox86_64)
set(CMAKE_CXX_COMPILER q++)
set(CMAKE_CXX_COMPILER_TARGET gcc_ntox86_64)
set(CMAKE_C_FLAGS_INIT "-O2 -g -DSA_RESTART=0")
T
build() {  # name, git-fetch-ref, install dir
  rm -rf /tmp/$1-src /tmp/$1-build /tmp/$1-install
  git init -q /tmp/$1-src && git -C /tmp/$1-src remote add origin https://github.com/nanomsg/nng.git
  git -C /tmp/$1-src fetch -q --depth 1 origin "$2" && git -C /tmp/$1-src checkout -q FETCH_HEAD
  cmake -S /tmp/$1-src -B /tmp/$1-build -DCMAKE_TOOLCHAIN_FILE=/tmp/qnx-toolchain.cmake -DCMAKE_INSTALL_PREFIX=/tmp/$1-install \
    -DBUILD_SHARED_LIBS=OFF -DNNG_TESTS=OFF -DNNG_TOOLS=OFF -DNNG_ENABLE_TLS=OFF -DNNG_ENABLE_NNGCAT=OFF -DNNG_ENABLE_STATS=OFF >/dev/null
  cmake --build /tmp/$1-build -j8 >/dev/null && cmake --install /tmp/$1-build >/dev/null
  rm -rf "$HERE/deps/$3" && mkdir -p "$HERE/deps" && cp -r /tmp/$1-install "$HERE/deps/$3"
}
build nng v1.7.3 nng-install
build nngf aac4dc360faca9ccece487ba16371d20d90e6406 nngfix-install
mkdir -p out
qcc -Vgcc_ntox86_64 -O2 -g -Wall -Wextra -std=gnu11 -Ideps/nng-install/include -o out/nng_repro nng_repro.c -Ldeps/nng-install/lib -lnng -lsocket
qcc -Vgcc_ntox86_64 -O2 -g -Wall -Wextra -std=gnu11 -Ideps/nngfix-install/include -o out/nng_repro_fixed nng_repro.c -Ldeps/nngfix-install/lib -lnng -lsocket
echo built out/nng_repro out/nng_repro_fixed
