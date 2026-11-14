#!/usr/bin/env bash
# Build (once) and boot the QNX 8.0 QEMU VM that TraceLens captures from. Verified 2026-11-14 on
# WSL2 Ubuntu 24.04 + QNX SDP 8.0. Run inside Linux/WSL as your normal user.
#
#   bash scripts/qnx_vm.sh            # build if needed, then boot headless and print the IP
#
# One-time host prerequisites (need sudo, so they are yours to run):
#   sudo chmod u+s /usr/lib/qemu/qemu-bridge-helper       # QEMU may attach to libvirt's virbr0
#   sudo virsh net-start default                           # libvirt NAT + DHCP (after a WSL restart;
#                                                          #  if "already in use": sudo ip link delete virbr0)
set -euo pipefail
VM="${QNX_VM_DIR:-$HOME/qnx-vm}"
source "${QNX_SDP:-$HOME/qnx800}/qnxsdp-env.sh" >/dev/null
[ -f "$HOME/.ssh/id_ed25519.pub" ] || { echo "No ~/.ssh/id_ed25519.pub: create one with ssh-keygen -t ed25519"; exit 2; }
mkdir -p "$VM" && cd "$VM"
if [ ! -f output/disk-qemu ]; then
    # Default image: procnto-smp-instr (instrumented kernel), tracelogger, pidin, sshd.
    mkqnximage --type=qemu --cpu=4 --ram=2G --hostname=tracelens \
        --ssh-ident="$HOME/.ssh/id_ed25519.pub" --sshd-pregen=yes --noprompt
fi
tracelens target up --image-dir "$VM"
