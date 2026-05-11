#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CUSTOM="$ROOT/build/sqlite3_custom"

if [[ ! -x "$CUSTOM" && ! -x "$CUSTOM.exe" ]]; then
  echo "Custom SQLite binary not found. Run scripts/build_sqlite.sh first." >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "Error: python3 or python is required to run experiments." >&2
  exit 1
fi

mkdir -p "$ROOT/results"

echo "Running source-instrumented execution trace..."
(cd "$ROOT" && "$PYTHON" experiment_execution_trace.py)

echo "Running batch-size experiment..."
(cd "$ROOT" && "$PYTHON" experiment_batch_size.py)

echo "Running crash-recovery experiment..."
(cd "$ROOT" && "$PYTHON" experiment_crash_recovery.py)

echo "Running WAL vs rollback experiment..."
(cd "$ROOT" && "$PYTHON" experiment_wal_vs_rollback.py)

echo "All experiments completed. Outputs are in results/."
