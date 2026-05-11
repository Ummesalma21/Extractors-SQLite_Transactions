"""
WAL vs rollback journal experiment using build/sqlite3_custom.

This experiment uses the custom SQLite binary and SQLITE_TRACE logs to compare
DELETE rollback-journal mode with WAL mode under a concurrent reader workload.
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


ROOT = Path(__file__).resolve().parent
SQLITE_CUSTOM = ROOT / "build" / "sqlite3_custom"
RESULTS_DIR = ROOT / "results"
OUTPUT_PATH = RESULTS_DIR / "wal_vs_rollback_output.txt"
NUM_ROWS = 5000
BATCH_SIZE = 200
BUSY_TIMEOUT_MS = 50
READER_LOOP_DELAY = 0.002


def require_custom_sqlite() -> Path:
    candidates = [SQLITE_CUSTOM]
    if sys.platform == "win32":
        candidates.append(SQLITE_CUSTOM.with_suffix(".exe"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    print("Custom SQLite binary not found. Run scripts/build_sqlite.sh first.", file=sys.stderr)
    sys.exit(1)


def unlink_db_files(db_path: Path) -> None:
    for suffix in ["", "-journal", "-wal", "-shm"]:
        path = db_path.with_name(db_path.name + suffix)
        if path.exists():
            path.unlink()


def run_sqlite(sqlite_bin: Path, db_path: Path, sql: str, timeout: float | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(sqlite_bin), "-batch", str(db_path)],
        input=sql,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )


def setup_database(sqlite_bin: Path, db_path: Path, journal_mode: str) -> None:
    unlink_db_files(db_path)
    setup_sql = "\n".join([
        f"PRAGMA journal_mode={journal_mode};",
        "PRAGMA synchronous=NORMAL;",
        "DROP TABLE IF EXISTS data;",
        "CREATE TABLE data(id INTEGER PRIMARY KEY, val TEXT);",
        "SELECT COUNT(*) FROM data;",
    ]) + "\n"
    result = run_sqlite(sqlite_bin, db_path, setup_sql, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stdout)


def reader_work(sqlite_bin: Path, db_path: Path, stop_event: threading.Event) -> tuple[int, int]:
    successful_reads = 0
    blocked_reads = 0
    read_sql = f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}; SELECT COUNT(*) FROM data;\n"

    while not stop_event.is_set():
        try:
            result = run_sqlite(sqlite_bin, db_path, read_sql, timeout=(BUSY_TIMEOUT_MS / 1000.0) + 1.0)
        except subprocess.TimeoutExpired:
            blocked_reads += 1
            continue

        output = result.stdout.strip()
        if result.returncode == 0 and output and "database is locked" not in output.lower():
            successful_reads += 1
        else:
            blocked_reads += 1

        time.sleep(READER_LOOP_DELAY)

    return successful_reads, blocked_reads


def build_writer_sql() -> str:
    lines = [
        "PRAGMA synchronous=FULL;",
    ]
    for start in range(0, NUM_ROWS, BATCH_SIZE):
        lines.append("BEGIN;")
        for rowid in range(start, min(start + BATCH_SIZE, NUM_ROWS)):
            payload = 'x' * 128
            lines.append(f"INSERT INTO data VALUES({rowid}, 'value_{rowid}_{payload}');")
        lines.append("COMMIT;")
    lines.append("SELECT COUNT(*) FROM data;")
    return "\n".join(lines) + "\n"


def count_trace_metrics(output: str) -> dict[str, int | str]:
    trace_lines = [line for line in output.splitlines() if "[SQLITE_TRACE]" in line]
    pager_commit_lines = [line for line in trace_lines if "pager.c:sqlite3Pager" in line]
    wal_lines = [line for line in trace_lines if "wal.c:" in line]
    return {
        "trace_lines": len(trace_lines),
        "pager_commit_phase_one": sum("pager.c:sqlite3PagerCommitPhaseOne begin" in line for line in trace_lines),
        "pager_commit_phase_two": sum("pager.c:sqlite3PagerCommitPhaseTwo begin" in line for line in trace_lines),
        "wal_begin": sum("wal.c:sqlite3WalBeginWriteTransaction begin" in line for line in trace_lines),
        "wal_frames": sum("wal.c:walFrames begin" in line for line in trace_lines),
        "pager_sample": "\n".join(pager_commit_lines[:5]),
        "wal_sample": "\n".join(wal_lines[:5]),
    }


def run_mode(sqlite_bin: Path, journal_mode: str) -> dict[str, float | int | str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test.db"
        setup_database(sqlite_bin, db_path, journal_mode)

        stop_event = threading.Event()
        reader_result: tuple[int, int] = (0, 0)

        def reader_target() -> None:
            nonlocal reader_result
            reader_result = reader_work(sqlite_bin, db_path, stop_event)

        reader_thread = threading.Thread(target=reader_target)
        reader_thread.start()
        time.sleep(0.1)

        writer_sql = build_writer_sql()
        start = time.perf_counter()
        result = run_sqlite(sqlite_bin, db_path, writer_sql, timeout=120)
        elapsed = time.perf_counter() - start

        stop_event.set()
        reader_thread.join(timeout=10.0)

        if result.returncode != 0:
            raise RuntimeError(result.stdout)

        metrics = count_trace_metrics(result.stdout)
        successful_reads, blocked_reads = reader_result
        expected_transactions = NUM_ROWS // BATCH_SIZE

        metrics.update({
            "mode": journal_mode,
            "elapsed": elapsed,
            "successful_reads": successful_reads,
            "blocked_reads": blocked_reads,
            "expected_transactions": expected_transactions,
            "trace_sample": metrics["pager_sample"] if journal_mode == "DELETE" else metrics["wal_sample"],
        })

        return metrics


def main() -> int:
    sqlite_bin = require_custom_sqlite()
    RESULTS_DIR.mkdir(exist_ok=True)

    rows = [run_mode(sqlite_bin, "DELETE"), run_mode(sqlite_bin, "WAL")]
    lines = [
        "SQLite WAL vs rollback journal experiment",
        f"SQLite binary: {sqlite_bin}",
        f"Rows: {NUM_ROWS}, batch size: {BATCH_SIZE}",
        f"Expected insert transactions: {NUM_ROWS // BATCH_SIZE}",
        f"Concurrent reader busy timeout: {BUSY_TIMEOUT_MS}ms",
        "",
        f"{'Mode':>8} {'Time (s)':>10} {'Success':>10} {'Blocked':>10} {'Trace':>8} {'Pager P1':>10} {'Pager P2':>10} {'WAL begin':>10} {'WAL frames':>10}",
        "-" * 98,
    ]
    for row in rows:
        lines.append(
            f"{row['mode']:>8} {row['elapsed']:>10.3f} {row['successful_reads']:>10} {row['blocked_reads']:>10} "
            f"{row['trace_lines']:>8} {row['pager_commit_phase_one']:>10} {row['pager_commit_phase_two']:>10} "
            f"{row['wal_begin']:>10} {row['wal_frames']:>10}"
        )
    lines.extend([
        "",
        "Interpretation:",
        "- Both DELETE and WAL still pass through pager commit phase-one and phase-two when committing.",
        "- DELETE rollback-journal mode should show no wal.c WAL begin/frame traces.",
        "- WAL mode should show wal.c:sqlite3WalBeginWriteTransaction and wal.c:walFrames traces.",
        "- WAL mode should also allow more concurrent readers to succeed during the writer workload.",
        "- Measurements are machine-dependent and should be regenerated locally.",
    ])

    lines.append("")
    lines.append("Read counts:")
    for row in rows:
        lines.append(f"- {row['mode']}: Successful reads={row['successful_reads']}, Blocked reads={row['blocked_reads']}")

    lines.append("")
    lines.append("Sample DELETE trace lines (workload only):")
    lines.append("-" * 60)
    delete_sample = next((r['trace_sample'] for r in rows if r['mode'] == 'DELETE'), '')
    lines.append(delete_sample or "(no pager.c traces captured)")

    lines.append("")
    lines.append("Sample WAL trace lines (workload only):")
    lines.append("-" * 60)
    wal_sample = next((r['trace_sample'] for r in rows if r['mode'] == 'WAL'), '')
    lines.append(wal_sample or "(no wal.c traces captured)")

    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nOutput file: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
