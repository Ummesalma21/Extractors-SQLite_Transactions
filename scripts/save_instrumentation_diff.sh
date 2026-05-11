#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIFF_DIR="$ROOT/diffs"
DIFF_FILE="$DIFF_DIR/sqlite_trace_instrumentation.diff"

mkdir -p "$DIFF_DIR"
cd "$ROOT"

# Generate a focused diff showing source-code instrumentation changes
# in the four key SQLite source files
# The diff spans from the initial instrumentation commit (172a0b0)
# to the latest changes (including VDBE cleanup in d59e16e)

echo "Generating instrumentation diff for source files..."

git show 172a0b0 -p -- \
  sqlite-master/src/btree.c \
  sqlite-master/src/pager.c \
  sqlite-master/src/wal.c > "$DIFF_FILE"

# Append VDBE changes if they were made separately
if git diff 172a0b0..d59e16e -- sqlite-master/src/vdbe.c | grep -q "SQLITE_TRACE"; then
  echo "" >> "$DIFF_FILE"
  echo "" >> "$DIFF_FILE"
  echo "=======================================
VDBE Trace Prefix Fix (Commit d59e16e)
=======================================" >> "$DIFF_FILE"
  echo "" >> "$DIFF_FILE"
  git diff 172a0b0..d59e16e -- sqlite-master/src/vdbe.c >> "$DIFF_FILE"
fi

if [[ ! -s "$DIFF_FILE" ]]; then
  echo "Warning: no instrumentation diff was produced. Are the source files tracked and modified?" >&2
else
  echo "✓ Saved instrumentation diff to diffs/sqlite_trace_instrumentation.diff"
  echo "  Size: $(du -h "$DIFF_FILE" | cut -f1)"
  echo "  Lines: $(wc -l < "$DIFF_FILE")"
  echo "  Contains: $(grep -c '\[SQLITE_TRACE\]' "$DIFF_FILE" || true) [SQLITE_TRACE] lines"
fi
