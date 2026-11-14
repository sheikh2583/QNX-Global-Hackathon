#!/usr/bin/env bash
# TraceLens one-command demo.
#
#   demo/run_demo.sh            offline: committed bug-zoo traces, no QNX needed
#   demo/run_demo.sh --live     live: boot the QNX QEMU target, build with qcc, capture, analyze, fix
#
# Output goes to demo/out/. Run from the repo root inside Linux/WSL with TraceLens installed
# (pip install -e .). Live mode also needs `source ~/qnx800/qnxsdp-env.sh`. No API keys.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT="$ROOT/demo/out"
FIX="$ROOT/fixtures/synthetic"
mkdir -p "$OUT"
cd "$ROOT"

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

offline() {
    say "1. The clean baseline (reference fixes): no findings"
    tracelens analyze "$FIX/z0_clean.txt" -c "$FIX/tracelens.toml" --html "$OUT/z0.html"
    echo "   exit $? (0 = clean)"

    for z in z1_prio_inversion z2_fixed_prio_channel z3_ipc_deadlock z4_mutex_contention z5_irq_overrun; do
        say "2. $z"
        tracelens analyze "$FIX/$z.txt" -c "$FIX/tracelens.toml" \
            --html "$OUT/$z.html" --json "$OUT/$z.json" --sarif "$OUT/$z.sarif"
        echo "   exit $? (1 = the CI gate fails, as it should)"
    done

    say "3. Timeline for ui.perfetto.dev"
    tracelens export "$FIX/z1_prio_inversion.txt" -c "$FIX/tracelens.toml" -o "$OUT/z1.perfetto.json"

    say "4. Was the fix real? Five runs before, five after"
    tracelens compare -c "$FIX/tracelens.toml" \
        --before "$FIX/z1_prio_inversion.txt" "$FIX/z1_prio_inversion.txt" "$FIX/z1_prio_inversion.txt" \
                 "$FIX/z1_prio_inversion.txt" "$FIX/z1_prio_inversion.txt" \
        --after "$FIX/z0_clean.txt" "$FIX/z0_clean.txt" "$FIX/z0_clean.txt" "$FIX/z0_clean.txt" "$FIX/z0_clean.txt"
    echo "   (identical synthetic copies; real captures vary run to run)"

    say "5. The fix, from a real QNX 8.0 trace: no target, no model"
    tracelens remedy fixtures/real/z1_infusion_pump.txt.gz --source bugzoo/z1_infusion_pump \
        -c fixtures/real/tracelens.toml --patch "$OUT/z1.patch"

    say "Reports in $OUT"
    ls -1 "$OUT"
}

live() {
    command -v mkqnximage >/dev/null || { echo "source ~/qnx800/qnxsdp-env.sh first"; exit 2; }
    say "1. Boot the QNX 8.0 target"
    IP=$(tracelens target up | sed -n 's/.*TRACELENS_TARGET=//p')
    [ -n "$IP" ] || { echo "target did not come up"; exit 2; }
    export TRACELENS_TARGET="$IP"

    say "2. Preflight: ssh, instrumented kernel, tracelogger"
    tracelens target check || { echo "fix the failed checks above first"; exit 2; }

    say "3. Build the bug zoo with qcc"
    make -C bugzoo || exit 2

    say "4. Capture and analyze the infusion pump on QNX"
    tracelens capture bugzoo/out/z1_infusion_pump -c bugzoo/tracelens.toml --out "$OUT/captures" --analyze -- -d 2

    say "5. Fix it: remedy from the trace, qcc builds, QNX re-runs 5x, compare decides"
    tracelens fix bugzoo/z1_infusion_pump -c bugzoo/tracelens.toml --out "$OUT/fix-z1" -- -d 2
    echo "   evidence: $OUT/fix-z1/SUMMARY.md"
}

case "${1:-}" in
    --live) live ;;
    ""|--offline) offline ;;
    *) echo "usage: $0 [--live]"; exit 2 ;;
esac
