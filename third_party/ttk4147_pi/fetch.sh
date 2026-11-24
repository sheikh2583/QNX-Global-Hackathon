#!/bin/sh
# Fetch the NTNU TTK4147 exercise program at the pinned commit and check its hash.
# The upstream repository carries no licence file, so this project does NOT redistribute the file:
# it is downloaded on demand, verified, and kept out of version control (see .gitignore).
set -eu
COMMIT=8b4ba232abd89988ff9ec38ec17e4f0749696d85
SHA256=49a59a88ac51eb3608a8caa7e2a28e3cf7b5d8f64b5a2ce5eeaefa03352e8abd
URL="https://raw.githubusercontent.com/TTK4147/ttk4147-2026-exercise-4-concurrency/$COMMIT/UnboundedPriorityInversion.c"
here=$(cd "$(dirname "$0")" && pwd)
dst="$here/ttk4147_inversion/UnboundedPriorityInversion.c"
mkdir -p "$here/ttk4147_inversion"
curl -sSfL "$URL" -o "$dst.tmp"
got=$(sha256sum "$dst.tmp" | cut -d' ' -f1)
if [ "$got" != "$SHA256" ]; then
    rm -f "$dst.tmp"
    echo "fetch.sh: sha256 mismatch (got $got, expected $SHA256)" >&2
    exit 1
fi
mv "$dst.tmp" "$dst"
echo "ok: $dst ($SHA256)"
