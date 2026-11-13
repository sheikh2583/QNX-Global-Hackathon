#!/usr/bin/env bash
# P0 host prep inside WSL2 Ubuntu 24.04 (run as root: wsl -d Ubuntu-24.04 -u root -- bash scripts/wsl_prep.sh)
# Installs what QNX SDP 8.0 + the QEMU quick start image + TraceLens need on the host.
# Sources: QNX "Using QNX SDP with WSL2 on Windows" blog; QSTI QEMU getting-started page.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y \
    build-essential make git curl ca-certificates unzip xz-utils \
    python3 python3-venv python3-pip \
    openssh-client rsync \
    default-jre libswt-gtk-4-java \
    qemu-system-x86 qemu-utils bridge-utils net-tools iproute2 \
    libvirt-clients libvirt-daemon-system

# QEMU in WSL2 needs /dev/kvm (nested virtualization) to be usable at real-time timescales.
if [ -c /dev/kvm ]; then
    echo "KVM: /dev/kvm present"
else
    echo "KVM: /dev/kvm MISSING - QEMU would fall back to TCG (too slow/noisy for timing traces)" >&2
fi

# QEMU bridge helper config used by mkqnximage networking (virbr0 from libvirt).
mkdir -p /etc/qemu
grep -qx 'allow virbr0' /etc/qemu/bridge.conf 2>/dev/null || echo 'allow virbr0' >> /etc/qemu/bridge.conf

qemu-system-x86_64 --version | head -1
echo "wsl_prep: done"
