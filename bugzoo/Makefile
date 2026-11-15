# TraceLens bug zoo - build with the QNX SDP 8.0 toolchain.
#
#   source ~/qnx800/qnxsdp-env.sh   # (verify path after install)
#   make                            # out/<name> (buggy) and out/<name>_fixed (reference)
#   make ARCH=aarch64le             # other targets (default: x86_64 for the QEMU guest)
#   make hostcheck                  # type-check every source with host gcc + QNX API stubs
#
# <name>/main.c         = the planted bug (what the fix agent sees and patches)
# reference/<name>.c    = ground-truth fix (never shown to the fix agent)

ARCH    ?= x86_64
CC       = qcc
CFLAGS  ?= -O2 -g
WARN     = -Wall -Wextra -std=gnu11
OUT      = out

WORKLOADS = z1_infusion_pump z2_brake_by_wire z3_sensor_fusion z4_camera_pipeline z5_motor_encoder
SOURCES   = $(foreach w,$(WORKLOADS),$(w)/main.c reference/$(w).c) gen/tlgen.c
BINS      = $(foreach w,$(WORKLOADS),$(OUT)/$(w) $(OUT)/$(w)_fixed) $(OUT)/tlgen

.PHONY: all clean hostcheck
all: $(BINS)

$(OUT):
	mkdir -p $@

# The ML data engine's generator: one program, many scenarios (docs/ml/DESIGN.md).
$(OUT)/tlgen: gen/tlgen.c common/tl.h | $(OUT)
	$(CC) -Vgcc_nto$(ARCH) $(CFLAGS) $(WARN) -Icommon -o $@ $<

$(OUT)/%_fixed: reference/%.c common/tl.h | $(OUT)
	$(CC) -Vgcc_nto$(ARCH) $(CFLAGS) $(WARN) -Icommon -o $@ $<

$(OUT)/%: %/main.c common/tl.h | $(OUT)
	$(CC) -Vgcc_nto$(ARCH) $(CFLAGS) $(WARN) -Icommon -o $@ $<

# Host-only check against minimal QNX API declarations in hostcheck/.
# Catches typos and type errors; says nothing about behaviour on QNX.
HOSTCC ?= gcc
hostcheck:
	@for f in $(SOURCES); do \
		echo "hostcheck $$f"; \
		$(HOSTCC) -fsyntax-only $(WARN) -Werror -D_GNU_SOURCE $(HOSTCHECK_EXTRA) -Ihostcheck -Icommon $$f || exit 1; \
	done

clean:
	rm -rf $(OUT)
