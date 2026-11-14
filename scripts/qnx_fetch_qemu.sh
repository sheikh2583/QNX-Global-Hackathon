#!/usr/bin/env bash
# Fetch and install the QNX SDP 8.0 QEMU Quick Start image when the Software Center CLI cannot
# install it into an existing SDP installation (QSC 2.0.4 crashes with "String.split ... env is
# null"). Run it yourself inside Linux/WSL after scripts/qnx_install.sh:
#
#   bash scripts/qnx_fetch_qemu.sh
#
# The image ships as one .tar.gz split across packages com.qnx.qnx800.quickstart.qemu.0..N, plus
# com.qnx.qnx800.quickstart.qemu (README + unpack_qemu_image.sh). Each package is an xz-compressed
# tar in the CLI's download cache. This script downloads any missing or empty parts (download
# only, no install step), extracts their images/ payload into the SDP, and runs QNX's unpack script.
# Credentials are prompted for (password hidden) and passed only to qnxsoftwarecenter_clt.
set -uo pipefail

CLT="${QNX_CLT:-$HOME/qnx/qnxsoftwarecenter/qnxsoftwarecenter_clt}"
DEST="${QNX_DEST:-$HOME/qnx800}"
CACHE="$HOME/.qnx/swupdate/cache/binary"
META="$HOME/.qnx/swupdate/cache/metadata/.packages/metadata"
BASE=com.qnx.qnx800.quickstart.qemu
[ -x "$CLT" ] || { echo "QNX Software Center CLI not found at $CLT"; exit 2; }
[ -d "$DEST/target" ] || { echo "No SDP at $DEST: run scripts/qnx_install.sh first"; exit 2; }

step() { printf '\n== %s\n' "$*"; }

# Parts known from the package metadata (com.qnx.qnx800.quickstart.qemu.0, .1, ...).
mapfile -t PARTS < <(ls -d "$META/$BASE".[0-9]* 2>/dev/null | xargs -n1 basename | sort -t. -k6 -n)
[ ${#PARTS[@]} -gt 0 ] || PARTS=("$BASE.0" "$BASE.1" "$BASE.2" "$BASE.3")
echo "Image parts: ${PARTS[*]}"

part_file() { ls "$CACHE/$1"_*.qpkg 2>/dev/null | head -1; }
missing() {
    local m=()
    for p in "$BASE" "${PARTS[@]}"; do
        f=$(part_file "$p")
        if [ -z "$f" ] || [ ! -s "$f" ]; then m+=("$p"); fi
    done
    echo "${m[*]}"
}

step "1/4 Check the download cache"
MISSING=$(missing)
if [ -n "$MISSING" ]; then
    echo "Missing or empty: $MISSING"
    for p in $MISSING; do f=$(part_file "$p"); [ -n "$f" ] && [ ! -s "$f" ] && rm -f "$f"; done

    step "2/4 Download the missing parts (several GB from qnx.com; retries on timeouts)"
    read -rp  "myQNX login (full email address): " QUSER
    read -rsp "myQNX password (hidden): " QPASS; echo
    AUTH=(-myqnx.user "$QUSER" -myqnx.password "$QPASS")
    for attempt in 1 2 3; do
        MISSING=$(missing)
        [ -z "$MISSING" ] && break
        echo "Attempt $attempt: downloading $MISSING"
        "$CLT" "${AUTH[@]}" -mirrorBaseline qnx800 -downloadPackage "$(echo "$MISSING" | tr ' ' ',')" \
            -destination "$DEST" || true
    done
    unset QPASS AUTH
    MISSING=$(missing)
    if [ -n "$MISSING" ]; then
        echo "Still missing after 3 attempts: $MISSING"
        echo "qnx.com may be timing out; run this script again later (finished parts are kept)."
        exit 1
    fi
else
    step "2/4 All parts already downloaded"
fi

step "3/4 Extract the image into $DEST/images/qemu"
for p in "$BASE" "${PARTS[@]}"; do
    f=$(part_file "$p")
    echo "  $(basename "$f") ($(du -h "$f" | cut -f1))"
    xz -dc "$f" | tar -x -C "$DEST" --exclude='.packages/*' || { echo "extract failed: $f"; exit 1; }
done
ls -la "$DEST/images/qemu"

step "4/4 Unpack (QNX's unpack_qemu_image.sh)"
cd "$DEST/images/qemu" && ./unpack_qemu_image.sh
ls -la "$DEST/images/qemu"
echo
echo "Next: source $DEST/qnxsdp-env.sh && tracelens target up && tracelens target check"
