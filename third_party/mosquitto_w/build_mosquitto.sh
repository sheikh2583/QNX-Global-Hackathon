#!/bin/bash
# Build Eclipse Mosquitto for QNX 8.0 x86_64 at two commits, the only difference being upstream's fix:
#   buggy  cd0987a6~1  (the parent of the fix)
#   fixed  cd0987a6    "Fix potential deadlock in mosquitto_sub if `-W` is used." (2025-02-27)
# Run in WSL after `source ~/qnx800/qnxsdp-env.sh`; needs cmake. Nothing in Mosquitto is edited.
# Output: deps/buggy/{mosquitto,mosquitto_sub,mosquitto_pub}, deps/fixed/...
set -e
cd "$(dirname "$0")"; HERE=$PWD
export PATH=$PATH:$QNX_HOST/usr/bin
# QNX has dlopen() in libc and no libdl; Mosquitto links -ldl, so give the linker an empty one
mkdir -p /tmp/qnxlibs && x86_64-pc-nto-qnx8.0.0-ar rcs /tmp/qnxlibs/libdl.a
cat > /tmp/qnx-toolchain.cmake <<'T'
set(CMAKE_SYSTEM_NAME QNX)
set(CMAKE_C_COMPILER qcc)
set(CMAKE_C_COMPILER_TARGET gcc_ntox86_64)
set(CMAKE_CXX_COMPILER q++)
set(CMAKE_CXX_COMPILER_TARGET gcc_ntox86_64)
set(CMAKE_C_FLAGS_INIT "-O2 -g -DSA_RESTART=0")
set(CMAKE_C_STANDARD_LIBRARIES "-lsocket")
set(CMAKE_EXE_LINKER_FLAGS_INIT "-L/tmp/qnxlibs")
T
FIX=cd0987a6
build() {  # name, ref
  rm -rf /tmp/mq-$1-src /tmp/mq-$1-build /tmp/mq-$1-install
  git clone -q --filter=blob:none https://github.com/eclipse-mosquitto/mosquitto.git /tmp/mq-$1-src
  git -C /tmp/mq-$1-src checkout -q "$2"
  cmake -S /tmp/mq-$1-src -B /tmp/mq-$1-build -DCMAKE_TOOLCHAIN_FILE=/tmp/qnx-toolchain.cmake \
    -DCMAKE_INSTALL_PREFIX=/tmp/mq-$1-install -DWITH_TLS=OFF -DWITH_CJSON=OFF -DDOCUMENTATION=OFF \
    -DWITH_PLUGINS=OFF -DWITH_TESTS=OFF -DWITH_STATIC_LIBRARIES=ON -DWITH_PIC=OFF >/tmp/mq-$1-cmake.log 2>&1
  cmake --build /tmp/mq-$1-build -j8 >/tmp/mq-$1-make.log 2>&1
  cmake --install /tmp/mq-$1-build >/tmp/mq-$1-inst.log 2>&1
  rm -rf "$HERE/deps/$1" && mkdir -p "$HERE/deps/$1"
  cp -r /tmp/mq-$1-install/. "$HERE/deps/$1/"
}
build buggy "$FIX~1"
build fixed "$FIX"
ls deps/buggy/bin deps/buggy/sbin deps/fixed/bin deps/fixed/sbin 2>/dev/null
