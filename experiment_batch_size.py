"""
Batch-size helper experiment using the modified SQLite shell.

This is still a performance helper experiment, but it executes build/sqlite3_custom
so the same run can confirm pager/B-tree source instrumentation is active.
"""

from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
SQLITE_CUSTOM = ROOT / "build" / "sqlite3_custom"
RESULTS_DIR = ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "batch_size_output.txt"
TOTAL_ROWS = 2000
BATCH_SIZES = [1, 10, 100, 500, TOTAL_ROWS]


def require_custom_sqlite() -> Path:
    candidates = [SQLITE_CUSTOM]
    if sys.platform == "win32":
        candidates.append(SQLITE_CUSTOM.with_suffix(".exe"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    print("Custom SQLite binary not found. Run scripts/build_sqlite.sh first.", file=sys.stderr)
    sys.exit(1)


def build_sql(batch_size: int) -> str:
    lines = [
        "PRAGMA journal_mode=DELETE;",
        "PRAGMA synchronous=NORMAL;",
        "DROP TABLE IF EXISTS data;",
        "CREATE TABLE data(id INTEGER PRIMARY KEY, val REAL, txt TEXT);",
    ]
    for start in range(0, TOTAL_ROWS, batch_size):
        lines.append("BEGIN;")
        end = min(start + batch_size, TOTAL_ROWS)
        for rowid in range(start, end):
            lines.append(f"INSERT INTO data VALUES({rowid}, {rowid * 1.5}, 'data_{rowid}');")
        lines.append("COMMIT;")
    lines.append("SELECT COUNT(*) FROM data;")
    return "\n".join(lines) + "\n"


def run_batch(sqlite_bin: Path, batch_size: int) -> tuple[float, int, int, str]:
    db_path = RESULTS_DIR / f"batch_{batch_size}.db"
    for suffix in ["", "-journal", "-wal", "-shm"]:
        path = Path(str(db_path) + suffix)
        if path.exists():
            path.unlink()

    start = time.perf_counter()
    result = subprocess.run(
        [str(sqlite_bin), "-batch", str(db_path)],
        input=build_sql(batch_size),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    elapsed = time.perf_counter() - start
    trace_count = result.stdout.count("[SQLITE_TRACE]")
    if result.returncode != 0:
        raise RuntimeError(result.stdout)
    for suffix in ["", "-journal", "-wal", "-shm"]:
        path = Path(str(db_path) + suffix)
        if path.exists():
            path.unlink()
    
    # Extract first 20 trace lines if available
    trace_lines = [line for line in result.stdout.split('\n') if "[SQLITE_TRACE]" in line][:20]
    trace_sample = '\n'.join(trace_lines)
    
    commits = (TOTAL_ROWS + batch_size - 1) // batch_size
    return elapsed, commits, trace_count, trace_sample


def main() -> int:
    sqlite_bin = require_custom_sqlite()
    RESULTS_DIR.mkdir(exist_ok=True)

    lines = [
        "SQLite batch size experiment",
        f"SQLite binary: {sqlite_bin}",
        f"Total rows: {TOTAL_ROWS}",
        "Mode: rollback journal (DELETE), synchronous=NORMAL",
        "",
        f"{'Batch Size':>12} {'Time (s)':>10} {'Rows/sec':>12} {'Commits':>10} {'Trace lines':>12}",
        "-" * 62,
    ]

    trace_sample = None
    for batch_size in BATCH_SIZES:
        elapsed, commits, trace_count, sample = run_batch(sqlite_bin, batch_size)
        rows_per_sec = TOTAL_ROWS / elapsed
        lines.append(f"{batch_size:>12} {elapsed:>10.3f} {rows_per_sec:>12,.0f} {commits:>10} {trace_count:>12}")
        # Capture trace sample from a representative run (batch size 100)
        if batch_size == 100 and sample and not trace_sample:
            trace_sample = sample

    lines.extend([
        "",
        "Interpretation: larger batches reduce the number of commits. The trace",
        "line counts come from the modified pager.c and btree.c paths in the",
        "custom SQLite binary, but timing is machine-dependent.",
    ])
    
    # Add sample trace section
    if trace_sample:
        lines.extend([
            "",
            "Sample source trace lines (batch size 100):",
            "-" * 40,
            trace_sample,
        ])

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nOutput file: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
