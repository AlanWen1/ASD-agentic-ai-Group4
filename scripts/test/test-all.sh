#!/usr/bin/env bash
# Runs every student module's test suite from the repository root — the
# same compile-check + pytest steps each student's own GitHub Actions
# workflow (.github/workflows/student-N.yml) runs individually, but in one
# pass for local use. Exits non-zero if any module fails.
#
# Note: this deliberately does NOT start any backend server first. Modules
# whose tests use Flask's test_client (expense-category-tracker, student-3)
# pass standalone. Modules whose tests make real HTTP calls to a running
# server (student-1-budget's test_budget_api.py, student-5's
# test_savings_goal_api.py) will fail here with connection errors unless
# that module's backend is already running on its usual port — see that
# module's own .github/workflows/student-N.yml for the exact startup steps
# it needs.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

MODULES=(
  "finance-application"
  "bill-tracker"
  "student-1-budget"
  "expense-category-tracker"
  "student-3"
  "student-5"
)

failures=0

for module in "${MODULES[@]}"; do
  if [ ! -d "$module" ]; then
    continue
  fi
  echo "=== ${module}: compile-check ==="
  python3 -m compileall -q "$module" || failures=$((failures + 1))

  # Run pytest against every "tests" directory found under this module
  # (some modules have one per service, e.g. backend/tests, database/tests).
  while IFS= read -r test_dir; do
    echo "=== ${test_dir} ==="
    (cd "$(dirname "$test_dir")" && python3 -m pytest "$(basename "$test_dir")" -q) || failures=$((failures + 1))
  done < <(find "$module" -type d -name tests)
done

if [ "$failures" -gt 0 ]; then
  echo "FAILED: ${failures} check(s) did not pass."
  exit 1
fi

echo "All checks passed."
