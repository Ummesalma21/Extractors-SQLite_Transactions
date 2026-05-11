#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIFF_DIR="$ROOT/diffs"
DIFF_FILE="$DIFF_DIR/sqlite_trace_instrumentation.diff"

mkdir -p "$DIFF_DIR"
cd "$ROOT"

git diff -- \
  sqlite-master/src/pager.c \
  sqlite-master/src/btree.c \
  sqlite-master/src/wal.c > "$DIFF_FILE"

if [[ ! -s "$DIFF_FILE" ]]; then
  echo "Warning: no instrumentation diff was produced. Are the source files tracked and modified?" >&2
else
  echo "Saved instrumentation diff to diffs/sqlite_trace_instrumentation.diff"
fi
