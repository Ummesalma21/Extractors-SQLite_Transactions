#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQLITE_DIR="$ROOT/sqlite-master"
OUT_DIR="$ROOT/build"
OUT_BIN="$OUT_DIR/sqlite3_custom"

if [[ ! -d "$SQLITE_DIR/src" ]]; then
  echo "Error: sqlite-master/src not found. Run this script from the project checkout." >&2
  exit 1
fi

if ! command -v make >/dev/null 2>&1; then
  echo "Error: make not found. On Ubuntu run: sudo apt install -y build-essential tcl python3" >&2
  exit 1
fi

if ! command -v cc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1; then
  echo "Error: C compiler not found. On Ubuntu run: sudo apt install -y build-essential" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

echo "Building modified SQLite from $SQLITE_DIR"
(
  cd "$SQLITE_DIR"
  if [[ ! -f Makefile && -f ./configure ]]; then
    bash ./configure
  elif [[ ! -f Makefile ]]; then
    echo "Error: sqlite-master/Makefile is missing and sqlite-master/configure is not present." >&2
    echo "Ensure the SQLite source tree is present in the clone." >&2
    exit 1
  fi
  make sqlite3
)

if [[ -x "$SQLITE_DIR/sqlite3" ]]; then
  cp "$SQLITE_DIR/sqlite3" "$OUT_BIN"
elif [[ -x "$SQLITE_DIR/sqlite3.exe" ]]; then
  cp "$SQLITE_DIR/sqlite3.exe" "$OUT_BIN.exe"
  cp "$SQLITE_DIR/sqlite3.exe" "$OUT_BIN"
else
  echo "Error: build finished but sqlite3 binary was not found in sqlite-master." >&2
  exit 1
fi

chmod +x "$OUT_BIN" 2>/dev/null || true
echo "Success: custom SQLite binary available at build/sqlite3_custom"
