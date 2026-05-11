"""
WAL vs rollback journal experiment using build/sqlite3_custom.

Compares the trace paths and elapsed time for the same batched write workload
under rollback journal DELETE mode and WAL mode.
"""

from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent
SQLITE_CUSTOM = ROOT / "build" / "sqlite3_custom"
RESULTS_DIR = ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "wal_vs_rollback_output.txt"
NUM_ROWS = 2000
BATCH_SIZE = 200


def require_custom_sqlite() -> Path:
    candidates = [SQLITE_CUSTOM]
    if sys.platform == "win32":
        candidates.append(SQLITE_CUSTOM.with_suffix(".exe"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    print("Custom SQLite binary not found. Run scripts/build_sqlite.sh first.", file=sys.stderr)
    sys.exit(1)


def build_sql(journal_mode: str) -> str:
    lines = [
        f"PRAGMA journal_mode={journal_mode};",
        "PRAGMA synchronous=NORMAL;",
        "DROP TABLE IF EXISTS data;",
        "CREATE TABLE data(id INTEGER PRIMARY KEY, val TEXT);",
    ]
    for start in range(0, NUM_ROWS, BATCH_SIZE):
        lines.append("BEGIN;")
        for rowid in range(start, min(start + BATCH_SIZE, NUM_ROWS)):
            lines.append(f"INSERT INTO data VALUES({rowid}, 'value_{rowid}');")
        lines.append("COMMIT;")
    lines.append("SELECT COUNT(*) FROM data;")
    return "\n".join(lines) + "\n"


def run_mode(sqlite_bin: Path, journal_mode: str) -> dict[str, float | int | str]:
    db_path = RESULTS_DIR / f"journal_{journal_mode.lower()}.db"
    for suffix in ["", "-journal", "-wal", "-shm"]:
        path = Path(str(db_path) + suffix)
        if path.exists():
            path.unlink()

    start = time.perf_counter()
    result = subprocess.run(
        [str(sqlite_bin), "-batch", str(db_path)],
        input=build_sql(journal_mode),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    elapsed = time.perf_counter() - start
    if result.returncode != 0:
        raise RuntimeError(result.stdout)

    output = result.stdout
    metrics = {
        "mode": journal_mode,
        "elapsed": elapsed,
        "trace_lines": output.count("[SQLITE_TRACE]"),
        "pager_commit_phase_one": output.count("pager.c:sqlite3PagerCommitPhaseOne begin"),
        "pager_commit_phase_two": output.count("pager.c:sqlite3PagerCommitPhaseTwo begin"),
        "wal_begin": output.count("wal.c:sqlite3WalBeginWriteTransaction begin"),
        "wal_frames": output.count("wal.c:walFrames begin"),
    }

    for suffix in ["", "-journal", "-wal", "-shm"]:
        path = Path(str(db_path) + suffix)
        if path.exists():
            path.unlink()
    return metrics


def main() -> int:
    sqlite_bin = require_custom_sqlite()
    RESULTS_DIR.mkdir(exist_ok=True)

    rows = [run_mode(sqlite_bin, "DELETE"), run_mode(sqlite_bin, "WAL")]
    lines = [
        "SQLite WAL vs rollback journal experiment",
        f"SQLite binary: {sqlite_bin}",
        f"Rows: {NUM_ROWS}, batch size: {BATCH_SIZE}",
        "",
        f"{'Mode':>8} {'Time (s)':>10} {'Trace':>8} {'Pager P1':>10} {'Pager P2':>10} {'WAL begin':>10} {'WAL frames':>10}",
        "-" * 76,
    ]
    for row in rows:
        lines.append(
            f"{row['mode']:>8} {row['elapsed']:>10.3f} {row['trace_lines']:>8} "
            f"{row['pager_commit_phase_one']:>10} {row['pager_commit_phase_two']:>10} "
            f"{row['wal_begin']:>10} {row['wal_frames']:>10}"
        )
    lines.extend([
        "",
        "Interpretation: WAL mode should show wal.c write-transaction and frame",
        "logs. DELETE mode should primarily show rollback-journal pager commit",
        "logs. Timing is machine-dependent and should be regenerated locally.",
    ])

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nOutput file: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
