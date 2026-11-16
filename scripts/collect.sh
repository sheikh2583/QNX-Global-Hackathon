#!/usr/bin/env bash
# Collect labelled QNX traces from the target, configurably. Run it from the repository root in
# WSL/Linux with the QNX SDP environment sourced (or let it source ~/qnx800/qnxsdp-env.sh itself).
#
#   scripts/collect.sh                                  # 120 runs of every scenario into data/real
#   scripts/collect.sh -n 30                            # 30 runs of every scenario
#   scripts/collect.sh -n 200 -s healthy_periodic -s healthy_ipc -s healthy_mixed -o data/healthy
#   scripts/collect.sh -n 10 -d 8 --seed 42             # 10 runs each, 8-second captures
#   scripts/collect.sh --features-only -o data/real     # just (re)build features from traces already there
#
# Options
#   -n N          runs per scenario (default 120)
#   -s NAME       only this scenario (repeat for several; default: all 16)
#   -o DIR        output directory (default data/real)
#   -d SECONDS    capture length per run (default 4)
#   --seed N      plan seed; change it for a different parameter sample (default 11)
#   --host H[:P]  target; default $TRACELENS_TARGET, else the VM is started and used
#   --features-only   skip capturing, only extract features from DIR
#   --no-vm       do not start a VM, require a reachable target
#
# It is resumable: run the same command again and it continues where it stopped (the manifest
# records what is already collected). Keep the machine idle while it runs - host load distorts guest
# timing and shows up as lossy traces.
set -u
cd "$(dirname "$0")/.." || exit 1

RUNS=120 OUT=data/real SECONDS_PER=4 SEED=11 HOST="${TRACELENS_TARGET:-}" FEATURES_ONLY=0 START_VM=1
SCENARIOS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -n) RUNS="$2"; shift 2 ;;
    -s) SCENARIOS+=("--scenario" "$2"); shift 2 ;;
    -o) OUT="$2"; shift 2 ;;
    -d) SECONDS_PER="$2"; shift 2 ;;
    --seed) SEED="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --features-only) FEATURES_ONLY=1; shift ;;
    --no-vm) START_VM=0; shift ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "unknown option: $1 (try --help)" >&2; exit 2 ;;
  esac
done

CFG=bugzoo/gen/tlgen.toml
BIN=bugzoo/out/tlgen
[ -f "$HOME/qnx800/qnxsdp-env.sh" ] && . "$HOME/qnx800/qnxsdp-env.sh" >/dev/null 2>&1

if [ "$FEATURES_ONLY" = 0 ]; then
  if [ ! -x "$BIN" ]; then
    echo "building the generator ($BIN)"
    make -C bugzoo out/tlgen || { echo "FAILED: qcc build (is the QNX SDP sourced?)" >&2; exit 1; }
  fi
  if [ -z "$HOST" ] && [ "$START_VM" = 1 ]; then
    echo "starting the QNX VM (QEMU's own network: no bridge, no DHCP server, no sudo)"
    OUTPUT=$(tracelens target up --user-net --timeout 300 2>&1) || { echo "$OUTPUT" >&2; exit 1; }
    HOST=$(echo "$OUTPUT" | sed -n 's/.*export TRACELENS_TARGET=//p' | tail -1)
  fi
  [ -n "$HOST" ] || { echo "no target: pass --host, set TRACELENS_TARGET, or drop --no-vm" >&2; exit 1; }
  export TRACELENS_TARGET="$HOST"
  echo "target $HOST, $RUNS runs per scenario, ${SECONDS_PER}s captures -> $OUT"

  tracelens data plan --per-scenario "$RUNS" --seed "$SEED" --out "$OUT/plan.jsonl" "${SCENARIOS[@]+"${SCENARIOS[@]}"}" || exit 1
  tracelens data collect --plan "$OUT/plan.jsonl" --out "$OUT" --binary "$BIN" -c "$CFG" \
      --seconds "$SECONDS_PER" || exit 1
fi

echo "extracting features"
tracelens data features --data "$OUT" --out "$OUT/features.jsonl" -c "$CFG" || exit 1

python - "$OUT" <<'PY'
import json, sys
from collections import Counter
from pathlib import Path
out = Path(sys.argv[1])
rows = [json.loads(l) for l in (out / "manifest.jsonl").open(encoding="utf-8")]
ok = [r for r in rows if r.get("status") == "ok"]
print(f"\n{len(ok)} of {len(rows)} captured, {sum(1 for r in ok if r.get('triggered'))} with the planted problem "
      f"showing, {sum(1 for r in ok if r.get('lossy'))} lossy")
miss = Counter(r["scenario"] for r in ok if not r.get("triggered"))
if miss:
    print("  not triggered:", dict(miss))
f = out / "features.jsonl"
if f.exists():
    print(f"  {sum(1 for _ in f.open(encoding='utf-8')):,} feature rows -> train with scripts/train_eval.py --real {out}")
PY
