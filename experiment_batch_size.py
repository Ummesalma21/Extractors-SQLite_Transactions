"""
Experiment 2: Transaction Batch Size vs. Write Throughput

Demonstrates the cost of fsync per commit — the core bottleneck in SQLite write performance.
Maps to: src/pager.c -> sqlite3OsSync() called in sqlite3PagerCommitPhaseOne()
"""

import sqlite3
import time
import os
import tempfile

TOTAL_ROWS = 50_000
BATCH_SIZES = [1, 10, 100, 1000, 5000, TOTAL_ROWS]


def run_experiment(batch_size):
    # Create a temp DB file in the same folder as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, f"_bench_{batch_size}.db")

    # Remove if exists from a previous run
    if os.path.exists(db_path):
        os.unlink(db_path)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=NORMAL")   # NORMAL: sync at safe checkpoints (not every commit)
    conn.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, val REAL, txt TEXT)")

    start = time.perf_counter()
    i = 0
    while i < TOTAL_ROWS:
        conn.execute("BEGIN")
        batch_end = min(i + batch_size, TOTAL_ROWS)
        for j in range(i, batch_end):
            conn.execute("INSERT INTO data VALUES (?, ?, ?)", (j, j * 1.5, f"data_{j}"))
        conn.execute("COMMIT")
        i = batch_end
    elapsed = time.perf_counter() - start

    conn.close()
    if os.path.exists(db_path):
        os.unlink(db_path)

    num_commits = (TOTAL_ROWS + batch_size - 1) // batch_size
    rows_per_sec = TOTAL_ROWS / elapsed
    return elapsed, rows_per_sec, num_commits


if __name__ == "__main__":
    print("SQLite Transaction Batch Size Experiment")
    print(f"Total rows: {TOTAL_ROWS:,} | journal_mode=DELETE | synchronous=NORMAL")
    print()
    print(f"{'Batch Size':>12} {'Time (s)':>10} {'Rows/sec':>12} {'# Commits':>12}")
    print("-" * 50)

    results = []
    for batch_size in BATCH_SIZES:
        elapsed, rps, commits = run_experiment(batch_size)
        results.append((batch_size, elapsed, rps, commits))
        label = str(batch_size) if batch_size < TOTAL_ROWS else f"{TOTAL_ROWS} (1 txn)"
        print(f"{label:>12} {elapsed:>10.3f} {rps:>12,.0f} {commits:>12,}")

        # Adding source code trace mapping for demonstration
        if batch_size == 1:
            print(f"      -> Internally calls `sqlite3PagerCommitPhaseOne` and `sqlite3OsSync` {commits:,} times.")
            print(f"      -> File: sqlite-master/src/pager.c (Line 6465)")
        elif batch_size == TOTAL_ROWS:
            print(f"      -> Internally calls `sqlite3PagerCommitPhaseOne` and `sqlite3OsSync` ONLY {commits:,} time.")
            print(f"      -> B-Tree modification (sqlite-master/src/btree.c -> sqlite3BtreeInsert) happens {TOTAL_ROWS:,} times in memory.")

    print()
    baseline = results[0][1]   # batch_size = 1
    best     = results[-1][1]  # largest batch
    print(f"Batch=1 (autocommit) : {baseline:.3f}s")
    print(f"Batch={TOTAL_ROWS} (one txn) : {best:.3f}s")
    print(f"Speedup              : {baseline/best:.0f}x")
    print()
    print("Why? Larger transactions reduce commit-related sync overhead dramatically")
    print("Code: src/pager.c -> sqlite3PagerCommitPhaseOne() -> sqlite3OsSync()")
