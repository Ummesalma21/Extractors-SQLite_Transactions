"""
Main source-instrumented experiment.

Runs the modified SQLite shell from build/sqlite3_custom and captures the
[SQLITE_TRACE] lines emitted by instrumentation in sqlite-master/src/.
"""

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
SQLITE_CUSTOM = ROOT / "build" / "sqlite3_custom"
RESULTS_DIR = ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "source_trace_output.txt"
DB_PATH = ROOT / "results" / "source_trace.db"


def require_custom_sqlite() -> Path:
    candidates = [SQLITE_CUSTOM]
    if sys.platform == "win32":
        candidates.append(SQLITE_CUSTOM.with_suffix(".exe"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    print("Custom SQLite binary not found. Run scripts/build_sqlite.sh first.", file=sys.stderr)
    sys.exit(1)


def run_sql(sqlite_bin: Path, sql: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(sqlite_bin), "-batch", str(DB_PATH)],
        input=sql,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def main() -> int:
    sqlite_bin = require_custom_sqlite()
    RESULTS_DIR.mkdir(exist_ok=True)

    for path in [DB_PATH, DB_PATH.with_name(DB_PATH.name + "-journal"),
                 DB_PATH.with_name(DB_PATH.name + "-wal"),
                 DB_PATH.with_name(DB_PATH.name + "-shm")]:
        if path.exists():
            path.unlink()

    sql = """
PRAGMA journal_mode=DELETE;
PRAGMA synchronous=FULL;
DROP TABLE IF EXISTS trace_test;
CREATE TABLE trace_test(id INTEGER PRIMARY KEY, data TEXT);
BEGIN;
INSERT INTO trace_test VALUES (1, 'source_trace_row');
COMMIT;
SELECT COUNT(*) FROM trace_test;
"""

    result = run_sql(sqlite_bin, sql)
    OUTPUT_PATH.write_text(result.stdout, encoding="utf-8")

    trace_lines = [line for line in result.stdout.splitlines() if "[SQLITE_TRACE]" in line]
    print("Source-instrumented execution trace")
    print(f"SQLite binary: {sqlite_bin}")
    print(f"Output file: {OUTPUT_PATH}")
    print(f"SQLite exit code: {result.returncode}")
    print(f"Trace lines captured: {len(trace_lines)}")
    for line in trace_lines[:20]:
        print(line)

    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        return result.returncode
    if not trace_lines:
        print("No [SQLITE_TRACE] lines were captured; verify the custom binary was built from modified source.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
