"""
Crash-recovery experiment using the modified SQLite shell where practical.

The script starts a transaction with build/sqlite3_custom, kills the process
before COMMIT, then reopens the database with the same binary to trigger
rollback-journal recovery if a hot journal was left behind.
"""

from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
SQLITE_CUSTOM = ROOT / "build" / "sqlite3_custom"
RESULTS_DIR = ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "crash_recovery_output.txt"
DB_PATH = RESULTS_DIR / "crash_recovery.db"
ROWS_BEFORE_KILL = 1000


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
        [str(sqlite_bin), "-batch", "-noheader", str(DB_PATH)],
        input=sql,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def cleanup() -> None:
    for suffix in ["", "-journal", "-wal", "-shm"]:
        path = Path(str(DB_PATH) + suffix)
        if path.exists():
            path.unlink()


def main() -> int:
    sqlite_bin = require_custom_sqlite()
    RESULTS_DIR.mkdir(exist_ok=True)
    cleanup()

    lines = [
        "SQLite crash recovery experiment",
        f"SQLite binary: {sqlite_bin}",
        f"Database: {DB_PATH}",
    ]

    setup = run_sql(
        sqlite_bin,
        """
PRAGMA journal_mode=DELETE;
PRAGMA synchronous=FULL;
DROP TABLE IF EXISTS crash_test;
CREATE TABLE crash_test(id INTEGER PRIMARY KEY, data TEXT);
""",
    )
    lines.append(f"Setup exit code: {setup.returncode}")
    if setup.returncode != 0:
        lines.append(setup.stdout)
        OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
        return setup.returncode

    proc = subprocess.Popen(
        [str(sqlite_bin), "-batch", str(DB_PATH)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdin is not None
    proc.stdin.write("PRAGMA journal_mode=DELETE;\nPRAGMA synchronous=FULL;\nBEGIN;\n")
    for rowid in range(ROWS_BEFORE_KILL):
        proc.stdin.write(f"INSERT INTO crash_test VALUES({rowid}, 'row_{rowid}');\n")
    proc.stdin.flush()

    time.sleep(0.5)
    lines.append(f"Killing writer before COMMIT after sending {ROWS_BEFORE_KILL} inserts.")
    proc.kill()
    writer_output, _ = proc.communicate(timeout=5)
    lines.append(f"Writer exit code: {proc.returncode}")
    lines.append(f"Writer trace lines: {writer_output.count('[SQLITE_TRACE]')}")

    journal_path = Path(str(DB_PATH) + "-journal")
    lines.append(f"Rollback journal present before reopen: {journal_path.exists()}")

    verify = run_sql(sqlite_bin, "SELECT COUNT(*) FROM crash_test;\n")
    lines.append(f"Verifier exit code: {verify.returncode}")
    lines.append(f"Verifier trace lines: {verify.stdout.count('[SQLITE_TRACE]')}")
    lines.append("Verifier output:")
    lines.append(verify.stdout.strip())

    count_lines = [line.strip() for line in verify.stdout.splitlines() if line.strip().isdigit()]
    if verify.returncode != 0:
        status = verify.returncode
        lines.append("FAIL: verifier could not open/read the database.")
    elif count_lines and int(count_lines[-1]) == 0:
        status = 0
        lines.append("PASS: uncommitted rows did not persist after reopening the database.")
    else:
        status = 2
        lines.append("FAIL: uncommitted rows appear to have persisted, or row count was not parsed.")

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nOutput file: {OUTPUT_PATH}")
    cleanup()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
