#!/bin/bash
# Tonight, unattended: restart the VM, record two live fix replays (~30 min), then collect the
# overnight dataset (~1,920 real captures, ~5.5 h). Every step logs; one failure never stops the rest.
cd "/mnt/x/Hackathons/QNX Global hackathon" || exit 1
source "$HOME/.venvs/tracelens/bin/activate" || exit 1
source "$HOME/qnx800/qnxsdp-env.sh" >/dev/null 2>&1

say() { echo; echo "===== $(date '+%H:%M:%S') $*"; }

say "starting the VM on QEMU's own network (no bridge, no DHCP server, no sudo)"
tracelens target down 2>&1 | tail -2
sleep 3
OUT=$(tracelens target up --user-net --timeout 300 2>&1)
echo "$OUT" | tail -6
TARGET=$(echo "$OUT" | sed -n 's/.*export TRACELENS_TARGET=//p' | tail -1)
case "$TARGET" in
  127.0.0.1:*|192.168.122.*) echo "target $TARGET" ;;
  *) echo "FATAL: VM did not come up ($TARGET)"; exit 1 ;;
esac
export TRACELENS_TARGET="$TARGET"
tracelens target check 2>&1 | tail -4

# ---------------------------------------------------------------- live fix replays for the demo
for w in z1_infusion_pump z5_motor_encoder; do
  say "recording a live fix of $w"
  rm -rf "fixes/${w}_live"
  tracelens fix "bugzoo/$w" -c bugzoo/tracelens.toml --runs 5 --watch --no-browser \
    --watch-port 8787 --out "fixes/${w}_live" 2>&1 | tail -12
  if [ -s "fixes/${w}_live/events.jsonl" ]; then
    mkdir -p "docs/results/fixes/${w}_live"
    cp "fixes/${w}_live/events.jsonl" "docs/results/fixes/${w}_live/events.jsonl"
    echo "  saved $(wc -l < "docs/results/fixes/${w}_live/events.jsonl") events for the hosted replay"
  else
    echo "  WARN: no events recorded for $w"
  fi
done

# ---------------------------------------------------------------- the overnight dataset
say "planning the collection"
tracelens data plan --per-scenario 120 --seed 11 --out data/real/plan.jsonl 2>&1 | tail -3
say "collecting (resumable: rerun the same command to continue)"
tracelens data collect --plan data/real/plan.jsonl --out data/real --binary bugzoo/out/tlgen \
  -c bugzoo/gen/tlgen.toml --seconds 4 2>&1 | tail -40
say "features"
tracelens data features --data data/real --out data/real/features.jsonl -c bugzoo/gen/tlgen.toml 2>&1 | tail -2
say "done"
python - <<'PY'
import json
from collections import Counter
rows = [json.loads(l) for l in open("data/real/manifest.jsonl")]
ok = [r for r in rows if r.get("status") == "ok"]
print(f"{len(ok)} of {len(rows)} captured, {sum(1 for r in ok if r.get('triggered'))} triggered, "
      f"{sum(1 for r in ok if r.get('lossy'))} lossy")
by = Counter((r["scenario"], bool(r.get("triggered"))) for r in ok)
for s in sorted({r["scenario"] for r in ok}):
    n = by[(s, True)] + by[(s, False)]
    print(f"  {s:22s} {by[(s, True)]}/{n}")
PY
