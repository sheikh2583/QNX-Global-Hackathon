#!/usr/bin/env bash
# Install QNX SDP 8.0 and the QEMU Quick Start target image with the QNX Software Center
# command-line tool, no GUI needed. Run it yourself inside Linux/WSL:
#
#   bash scripts/qnx_install.sh            # installs to ~/qnx800 (override with QNX_DEST=...)
#
# It asks for your myQNX email and password (the password is not echoed) and, optionally, a
# license key; without one it fetches the keys registered to your myQNX account. Credentials
# go only to qnxsoftwarecenter_clt for this run: nothing is written to disk or shell history
# by this script. (While a CLT step runs, they are visible to local `ps`, as with any CLI flag.)
set -euo pipefail

CLT="${QNX_CLT:-$HOME/qnx/qnxsoftwarecenter/qnxsoftwarecenter_clt}"
DEST="${QNX_DEST:-$HOME/qnx800}"
[ -x "$CLT" ] || { echo "QNX Software Center CLI not found at $CLT (run the qnx-setup .run installer first)"; exit 2; }

read -rp  "myQNX login (your FULL email address, including @...): " QUSER
case "$QUSER" in
    *@*.*) ;;
    *) echo "That is not a full email address. myQNX signs in with the whole address (name@domain)."; exit 2 ;;
esac
read -rsp "myQNX password (hidden): " QPASS; echo
read -rp  "License key (press Enter to fetch it from your myQNX account): " QKEY
AUTH=(-myqnx.user "$QUSER" -myqnx.password "$QPASS")

step() { printf '\n== %s\n' "$*"; }

step "1/5 License"
LICDIR="$HOME/.qnx/license"
if [ -n "$QKEY" ]; then
    "$CLT" "${AUTH[@]}" -addLicenseKey "$QKEY" 2>&1 | tee /tmp/qnx_lic.log
else
    "$CLT" "${AUTH[@]}" -syncLicenseKeys 2>&1 | tee /tmp/qnx_lic.log
fi
AUTH_FAILED=$(grep -ci "authentication failed" /tmp/qnx_lic.log || true)
rm -f /tmp/qnx_lic.log
if [ "${AUTH_FAILED:-0}" != "0" ]; then
    echo "myQNX rejected the login: check the full email address and the password, then run this again."
    exit 1
fi
if [ -z "$(ls -A "$LICDIR" 2>/dev/null)" ]; then
    echo "No QNX license is on this myQNX account yet (License Manager is empty)."
    echo "Request the free license at https://www.qnx.com/products/everywhere/ and wait until it appears"
    echo "in myQNX -> License Manager, or rerun this and paste the key at the license prompt."
    exit 1
fi
"$CLT" -listLicenseKeys || true

step "2/5 Packages your license gives access to (SDP 8.0)"
"$CLT" "${AUTH[@]}" -mirrorBaseline qnx800 -listAccessible 2>/dev/null | grep -i -E "qnx800|quickstart" | head -20 || true

step "3-4/5 Install QNX SDP 8.0 and the QEMU Quick Start image to $DEST (several GB; takes a while)"
# One command: in QSC 2.0.4 a separate -installPackage into an existing installation fails with
# "Cannot invoke String.split because env is null" (seen 2026-11-14), so baseline and image go together.
# -cleanInstall replaces any earlier partial install; downloaded artifacts are reused from the cache.
QEMU_PKG="${QNX_QEMU_PKG:-com.qnx.qnx800.quickstart.qemu}"
"$CLT" "${AUTH[@]}" -cleanInstall -mirrorBaseline qnx800 -installBaseline com.qnx.qnx800 \
    -installPackage "$QEMU_PKG" -destination "$DEST"
unset QPASS AUTH

step "5/5 Unpack the QEMU image"
IMG="$DEST/images/qemu"
if [ -x "$IMG/unpack_qemu_image.sh" ]; then
    (cd "$IMG" && ./unpack_qemu_image.sh)
else
    echo "unpack_qemu_image.sh not found under $IMG; look for it with: find $DEST -name 'unpack_qemu_image.sh'"
fi

step "Done"
ls "$DEST" "$DEST/images" 2>/dev/null || true
echo "Next: source $DEST/qnxsdp-env.sh && tracelens target up && tracelens target check"
