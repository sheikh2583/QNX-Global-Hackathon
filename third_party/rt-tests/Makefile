# Build the vendored rt-tests programs for QNX 8.0 with the SDP toolchain.
# NOT upstream code: upstream's own Makefile is Linux-only and is not used.
#
#   source ~/qnx800/qnxsdp-env.sh
#   make                      # out/pi_stress, out/ptsematest, out/pmqtest
#   make ARCH=aarch64le       # other target
#
# Every source under upstream/ is compiled byte-for-byte as released
# (PROVENANCE has the hashes).  All QNX adaptation lives in qnx/ and is
# pulled in with -include and -I; see README.md.

ARCH     ?= x86_64
QCC      ?= qcc
VERSION  ?= 2.11
OUT      ?= out
UP        = upstream

CFLAGS   ?= -O2 -g
WARN      = -Wall -Wextra
INCLUDES  = -Iqnx/include -I$(UP)/src/include -Iqnx
DEFS      = -DVERSION=$(VERSION)
FORCE     = -include qnx/qnx_compat.h
QCCFLAGS  = -Vgcc_nto$(ARCH) $(CFLAGS) $(WARN) $(INCLUDES) $(DEFS) $(FORCE)

LIB_SRC   = $(UP)/src/lib/rt-utils.c $(UP)/src/lib/rt-error.c $(UP)/src/lib/rt-sched.c
COMPAT    = $(OUT)/qnx_compat.o
PROGS     = $(OUT)/pi_stress $(OUT)/ptsematest $(OUT)/pmqtest

# NEGATIVE CONTROL (not part of `all`): pi_stress with priority inheritance switched off.
# The only change is the mutex protocol, applied by sed to a copy in $(OUT)/ so upstream/ stays
# byte-for-byte.  Upstream's own header comment says this build 'will deadlock the program'.
CONTROL   = $(OUT)/pi_stress_nopi

.PHONY: all clean control
all: $(PROGS)

$(OUT):
	mkdir -p $@

# The compatibility layer is the one file that may call the real
# pthread_create and the real syscall(), so it defines QNXRT_COMPAT_IMPL.
$(COMPAT): qnx/qnx_compat.c qnx/qnx_compat.h | $(OUT)
	$(QCC) -Vgcc_nto$(ARCH) $(CFLAGS) $(WARN) $(INCLUDES) $(DEFS) \
	    -DQNXRT_COMPAT_IMPL=1 $(FORCE) -c -o $@ $<

$(OUT)/pi_stress: $(UP)/src/pi_tests/pi_stress.c $(LIB_SRC) $(COMPAT) | $(OUT)
	$(QCC) $(QCCFLAGS) -o $@ $^ -lm

$(OUT)/ptsematest: $(UP)/src/ptsematest/ptsematest.c $(LIB_SRC) $(COMPAT) | $(OUT)
	$(QCC) $(QCCFLAGS) -o $@ $^ -lm

$(OUT)/pmqtest: $(UP)/src/pmqtest/pmqtest.c $(LIB_SRC) $(COMPAT) | $(OUT)
	$(QCC) $(QCCFLAGS) -o $@ $^ -lm

$(OUT)/pi_stress_nopi.c: $(UP)/src/pi_tests/pi_stress.c | $(OUT)
	sed 's/PTHREAD_PRIO_INHERIT/PTHREAD_PRIO_NONE/' $< > $@
	@diff $< $@ | grep -c '^>' | grep -qx 1 || { echo "control must differ in exactly one line"; exit 1; }

$(CONTROL): $(OUT)/pi_stress_nopi.c $(LIB_SRC) $(COMPAT)
	$(QCC) $(QCCFLAGS) -o $@ $^ -lm

control: $(CONTROL)

clean:
	rm -rf $(OUT)
