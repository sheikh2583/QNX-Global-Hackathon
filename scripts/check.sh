#!/usr/bin/env bash
# Run every TraceLens check on this machine (Linux/WSL; expects `pip install -e ".[dev]"`).
#
#   scripts/check.sh            everything
#   scripts/check.sh tests      unit tests + committed synthetic fixtures match the generator
#   scripts/check.sh hostcheck  bug-zoo workloads and reference fixes compile against QNX API stubs
#   scripts/check.sh gate       every real QNX 8.0 and synthetic trace gets the expected verdict
#
# Reports (HTML, JSON, SARIF) land in reports/. Exit status is non-zero if any step fails.
set -u
cd "$(dirname "$0")/.."
mkdir -p reports
failed=0
fail() { echo "FAIL: $*" >&2; failed=1; }

step_tests() {
  echo "== unit tests"
  python -m pytest -q --junitxml=reports/junit.xml || fail "unit tests"
  echo "== committed synthetic fixtures match the generator"
  tracelens synth --out fixtures/synthetic >/dev/null && git diff --exit-code -- fixtures/synthetic \
    || fail "fixtures/synthetic differs from 'tracelens synth' output"
}

step_hostcheck() {
  echo "== bug zoo compiles against QNX API stubs (host gcc, no QNX license)"
  make -C bugzoo hostcheck || fail "bug zoo host compile check"
}

step_gate() {
  echo "== clean synthetic baseline passes"
  tracelens analyze fixtures/synthetic/z0_clean.txt -c fixtures/synthetic/tracelens.toml -q \
    --html reports/z0_clean.html --json reports/z0_clean.json || fail "z0_clean should pass"

  echo "== real QNX 8.0 captures: every buggy build fails, every reference fix passes"
  for t in fixtures/real/z*_fixed.txt.gz; do
    fixed=$(basename "$t" .txt.gz); buggy=${fixed%_fixed}
    tracelens analyze "fixtures/real/$buggy.txt.gz" -c fixtures/real/tracelens.toml -q \
      --html "reports/real_$buggy.html" --sarif "reports/real_$buggy.sarif"
    rc=$?; [ $rc -eq 1 ] && echo "  ok   $buggy caught" || fail "real $buggy should fail the gate (exit $rc)"
    tracelens analyze "$t" -c fixtures/real/tracelens.toml -q --html "reports/real_$fixed.html"
    rc=$?; [ $rc -eq 0 ] && echo "  ok   $fixed clean" || fail "real $fixed should pass the gate (exit $rc)"
  done
  for t in fixtures/real/healthy_*.txt.gz; do
    tracelens analyze "$t" -c fixtures/real/tracelens.toml -q
    rc=$?; [ $rc -eq 0 ] && echo "  ok   $(basename "$t" .txt.gz) clean" || fail "healthy $(basename "$t") should pass (exit $rc)"
  done

  echo "== every planted synthetic bug is caught"
  for t in fixtures/synthetic/z[1-9]*.txt; do
    name=$(basename "$t" .txt)
    tracelens analyze "$t" -c fixtures/synthetic/tracelens.toml -q \
      --html "reports/$name.html" --json "reports/$name.json"
    rc=$?; [ $rc -eq 1 ] && echo "  ok   $name caught" || fail "expected $name to be flagged (exit 1), got $rc"
  done
}

case "${1:-all}" in
  tests) step_tests ;;
  hostcheck) step_hostcheck ;;
  gate) step_gate ;;
  all) step_tests; step_hostcheck; step_gate ;;
  *) echo "usage: $0 [all|tests|hostcheck|gate]" >&2; exit 2 ;;
esac
[ $failed -eq 0 ] && echo "all checks passed" || echo "FAILED" >&2
exit $failed
