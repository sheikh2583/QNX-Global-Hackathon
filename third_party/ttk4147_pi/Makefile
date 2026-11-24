# Build the NTNU TTK4147 exercise program for QNX 8.0 (NOT upstream's build: it uses clang on Linux).
#
#   source ~/qnx800/qnxsdp-env.sh
#   ./fetch.sh               # downloads the pinned upstream file and checks its sha256
#   make                     # out/ttk4147_inversion
#   make ARCH=aarch64le      # NOT supported: the shim's counter emulation is x86_64 only (verify)
#
# The same compile line `tracelens fix` uses, so this binary equals its "before" build.
ARCH ?= x86_64
SRC   = ttk4147_inversion/UnboundedPriorityInversion.c

out/ttk4147_inversion: $(SRC) qnx/include/pthread.h qnx/include/sched.h qnx/include/qnxrt_compat.h
	mkdir -p out
	qcc -Vgcc_nto$(ARCH) -O2 -g -Wall -Wextra -std=gnu11 -Ittk4147_inversion -Iqnx/include -o $@ $(SRC)

$(SRC):
	./fetch.sh

clean:
	rm -rf out
.PHONY: clean
