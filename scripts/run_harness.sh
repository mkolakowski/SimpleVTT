#!/usr/bin/env bash
# Run the click-through harness with LIVE timestamped progress + per-test
# timing, and capture machine-readable results for the admin test dashboard.
#
# Why this exists: `pytest -q` buffers output to the end, so a long serial run
# (the harness shares one campaign-1 stack, so it can't parallelise) shows
# nothing until it finishes — and on a box where the demo reseeds every 60 min
# a >60-min run straddles a reseed and fails spuriously. This wrapper streams a
# timestamped line per test (start + finish + duration) so you can WATCH it and
# spot a hang live, prints the slowest 30 at the end, and writes a JSON/JUnit
# pair the admin "Tests" page reads.
#
# Usage:
#   scripts/run_harness.sh                      # whole suite
#   scripts/run_harness.sh tests/harness/test_attack.py   # a subset
#   scripts/run_harness.sh -k "homebrew or aoe"           # a -k expr
#
# Output: test-results/harness-<ts>.{log,xml,json} + latest.{log,xml,json}.
set -uo pipefail
cd "$(dirname "$0")/.."

ts="$(date +%Y%m%d-%H%M%S)"
outdir="test-results"
mkdir -p "$outdir"
log="$outdir/harness-$ts.log"
xml="$outdir/harness-$ts.xml"
json="$outdir/harness-$ts.json"

# Default target is the whole harness suite; any args override it.
targets=("tests/harness/")
if [ "$#" -gt 0 ]; then
    targets=("$@")
fi

echo "▶ Harness run $ts"
echo "  log: $log"
echo "  xml: $xml"
echo

HARNESS_PROGRESS=1 PYTHONUNBUFFERED=1 python3 -m pytest "${targets[@]}" \
    -v -rA --durations=30 --junitxml="$xml" -p no:cacheprovider 2>&1 | tee "$log"
code=${PIPESTATUS[0]}

# Stable "latest" symlinks for the dashboard + quick local inspection.
ln -sf "harness-$ts.log" "$outdir/latest.log"
ln -sf "harness-$ts.xml" "$outdir/latest.xml"

# Post-hoc summary (slowest tests + failures) + a JSON the admin page reads.
if [ -f "$xml" ]; then
    python3 scripts/harness_report.py "$xml" --json "$json" || true
    ln -sf "harness-$ts.json" "$outdir/latest.json"
fi

echo
echo "▶ Done (pytest exit $code). Results: $log"
exit "$code"
