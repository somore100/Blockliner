#!/usr/bin/env bash
# Which Tk tests fail now but passed at an older commit?
#   tests/compare_baseline.sh <ref>      e.g. fd754f8
# Runs every tests/test_*.py (exit code = pass/fail) under Xvfb in the current
# tree and in a temporary checkout of <ref>, then lists the differences.
set -u
ref="${1:?usage: compare_baseline.sh <git ref>}"
here="$(cd "$(dirname "$0")/.." && pwd)"
base="$(mktemp -d)/base"
git -C "$here" worktree add --detach "$base" "$ref" >/dev/null || exit 1
trap 'git -C "$here" worktree remove --force "$base" >/dev/null 2>&1' EXIT

run_all() {   # $1 = tree; prints "name status"
  for f in "$1"/tests/test_*.py; do
    ( cd "$1" && timeout 120 xvfb-run -a python3 "$f" >/dev/null 2>&1 ) && s=pass || s=FAIL
    echo "$(basename "$f") $s"
  done
}
run_all "$here" > "$base.now"
run_all "$base" > "$base.old"
echo "Failing now but passing at $ref (regressions):"
join "$base.old" "$base.now" | awk '$2=="pass" && $3=="FAIL" {print "  " $1}'
echo "Failing at both (not caused by the changes since $ref):"
join "$base.old" "$base.now" | awk '$2=="FAIL" && $3=="FAIL" {print "  " $1}'
echo "New tests failing now:"
join -v2 "$base.old" "$base.now" | awk '$2=="FAIL" {print "  " $1}'
