#!/usr/bin/env bash
# Does TraceLens work on QNX 8.0 on aarch64? This runs the whole answer, start to finish.
#
#   scripts/aarch64_pilot.sh                 # build, boot, collect 1 run per scenario, compare
#   PER_SCENARIO=5 scripts/aarch64_pilot.sh  # more runs per scenario (slower, tighter medians)
#   scripts/aarch64_pilot.sh --no-build      # image already built
#
# It never touches the x86 VM: its own image directory (~/qnx-vm-aarch64) and its own forwarded ssh
# port (2223, where the x86 one uses 2222), so both can be up at the same time.
#
# Prerequisites, in order of how likely they are to be missing:
#
#  1. The SDP package "QNX SDP 8.0 QEMU Virtualization Drivers (Startup)"
#     (com.qnx.qnx800.target.qemuvirt). It provides startup-qemu-virt, the only piece of an aarch64le
#     QEMU image that is not in a default SDP 8.0 install, and downloading it needs a myQNX login,
#     so install it in QNX Software Center. Without it mkqnximage stops with
#     "Host file 'startup-qemu-virt' not available" (docs/results/aarch64.md).
#  2. qemu-system-aarch64 on PATH (Ubuntu: the qemu-system-arm package).
#  3. The SDP environment and the venv: source ~/qnx800/qnxsdp-env.sh and the tracelens venv.
#
# Timing note: aarch64 on an x86 host has no KVM, so QEMU emulates every instruction (TCG). Expect
# every step to take several times longer than the x86 equivalent, and expect timing-dependent
# behaviour to differ - that is the measurement, not a failure.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE_DIR="${IMAGE_DIR:-$HOME/qnx-vm-aarch64}"
SSH_PORT="${SSH_PORT:-2223}"
PER_SCENARIO="${PER_SCENARIO:-1}"
DATA="${DATA:-$ROOT/data/aarch64}"
BINS="${BINS:-$ROOT/bugzoo/out-aarch64le}"
REF="${REF:-$ROOT/data/real}"          # the x86 collection every published number comes from
CFG="${CFG:-$ROOT/bugzoo/gen/tlgen.toml}"
BUILD=1
[ "${1:-}" = "--no-build" ] && BUILD=0

step() { printf '\n=== %s\n' "$*"; }
need() { command -v "$1" >/dev/null || { echo "missing: $1 ($2)" >&2; exit 2; }; }

step "0. tools"
need qcc "source ~/qnx800/qnxsdp-env.sh"
need mkqnximage "source ~/qnx800/qnxsdp-env.sh"
need qemu-system-aarch64 "install the qemu-system-arm package, or put the binary on PATH"
need tracelens "activate the tracelens venv"

step "1. the bug zoo and the generator, built for aarch64le"
make -C "$ROOT/bugzoo" ARCH=aarch64le OUT=out-aarch64le
file "$BINS/tlgen" | grep -q aarch64 || { echo "$BINS/tlgen is not an aarch64 binary" >&2; exit 1; }

if [ "$BUILD" = 1 ]; then
  step "2. the aarch64le QNX image in $IMAGE_DIR (the x86 image in ~/qnx-vm is left alone)"
  mkdir -p "$IMAGE_DIR"
  ( cd "$IMAGE_DIR" && mkqnximage --type=qemu --arch=aarch64le --cpu=4 --ram=2G --noprompt \
      --hostname=tracelens-a64 --ssh-ident="$HOME/.ssh/id_ed25519.pub" --sshd-pregen=yes )
fi
[ -f "$IMAGE_DIR/output/ifs.bin" ] || { echo "no $IMAGE_DIR/output/ifs.bin: see prerequisite 1" >&2; exit 1; }

step "3. the QEMU command, logged once so the VM can run on QEMU's own network"
# mkqnximage's runimage prints "QEMU Command: ..." before it starts QEMU, and `tracelens target up
# --user-net` rewrites that command to swap the bridge for QEMU's own NAT. The run below may well
# fail at the bridge - that is fine, the command is already logged by then.
grep -q "QEMU Command" "$IMAGE_DIR/tracelens-qemu.log" 2>/dev/null || \
  ( cd "$IMAGE_DIR" && mkqnximage --run=-h --noprompt > tracelens-qemu.log 2>&1 || true )
grep -q "QEMU Command" "$IMAGE_DIR/tracelens-qemu.log" || {
  echo "mkqnximage never printed a QEMU command; see $IMAGE_DIR/tracelens-qemu.log" >&2; exit 1; }
( cd "$IMAGE_DIR" && mkqnximage --stop >/dev/null 2>&1 || true )   # in case the bridged run came up

step "4. boot it on 127.0.0.1:$SSH_PORT"
tracelens target up --user-net --image-dir "$IMAGE_DIR" --ssh-port "$SSH_PORT" --timeout 900
export TRACELENS_TARGET="127.0.0.1:$SSH_PORT"
tracelens target check

step "5. the 16 scenarios, captured on aarch64 (resumable: rerun to continue)"
mkdir -p "$DATA"
[ -f "$DATA/plan.jsonl" ] || tracelens data plan --per-scenario "$PER_SCENARIO" --out "$DATA/plan.jsonl"
tracelens data collect --plan "$DATA/plan.jsonl" --out "$DATA" --binary "$BINS/tlgen" -c "$CFG"
tracelens data features --data "$DATA" --out "$DATA/features.jsonl" -c "$CFG"

step "6. aarch64 against x86, feature by feature, and the shipped radar on aarch64"
[ -f "$REF/features.jsonl" ] || { echo "no x86 reference in $REF (collect it, or set REF=)" >&2; exit 1; }
python "$ROOT/scripts/arch_compare.py" --a "$DATA" --b "$REF" \
  --label-a aarch64le --label-b x86_64 --out "$ROOT/docs/results/aarch64_features.md"

step "7. the bug zoo on aarch64: does every rule still fire on the right thread?"
tracelens eval detect --zoo "$ROOT/bugzoo" --bin-dir "$BINS" -c "$ROOT/bugzoo/tracelens.toml" \
  --runs 5 --out "$ROOT/docs/results/aarch64" || true   # a failing table is a result, not an error

cat <<EOF

Done. Written:
  docs/results/aarch64_features.md   aarch64 against x86 per feature, and the radar's transfer
  docs/results/aarch64/detect.md     the detection table on aarch64

Read the gap table against the same-architecture control (docs/results/arch_control.md): a gap only
means something next to how much two x86 collections already differ.

If the deadline rule misses on aarch64 because emulated wake-ups land later than the budgets in
bugzoo/tracelens.toml allow, do NOT edit that file - it is calibrated for the KVM x86 guest every
published number comes from. Copy it to bugzoo/tracelens.aarch64.toml, raise only budget_us, say in
docs/results/aarch64.md which budget moved and what measurement justified it, and rerun step 7 with
-c bugzoo/tracelens.aarch64.toml.
EOF
