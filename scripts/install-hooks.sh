#!/usr/bin/env bash
# Point this clone at the versioned hooks in .githooks/ (free local CI: no service, no account).
set -eu
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
chmod +x .githooks/pre-push scripts/check.sh
echo "installed: git push now runs lint, tests and the gate first (skip once with --no-verify)"
