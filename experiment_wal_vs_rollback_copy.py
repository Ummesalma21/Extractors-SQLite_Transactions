"""
Experiment 1: WAL vs Rollback Journal Write Performance

Tests write throughput and concurrent read behavior under both journal modes.
"""

import sqlite3
import time
import threading
import os
import tempfile

NUM_ROWS = 50000
BATCH_SIZE = 500


def run_concurrent_read(db_path, results, stop_event):
    """Continuously read from DB while writes are happening"""
    read_count = 0
    blocked_count = 0
    conn = sqlite3.connect(db_path, timeout=0)
    while not stop_event.is_set():
        try:
            cur = conn.execute("SELECT COUNT(*) FROM data")
            cur.fetchone()
            read_count += 1
        except sqlite3.OperationalError:
            blocked_count += 1
        time.sleep(0.0001)
    conn.close()
    results['reads'] = read_count
    results['blocked'] = blocked_count


def benchmark_mode(journal_mode, label):
    print(f"\n{'='*50}")
    print(f"  Mode: {label}")
    print(f"{'='*50}")

    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    os.unlink(db_path)

    # Setup: create DB and set journal mode
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE data (id INTEGER PRIMARY KEY, val TEXT)")
    conn.commit()
    conn.execute(f"PRAGMA journal_mode={journal_mode}")
    conn.commit()
    conn.close()

    # Start concurrent reader
    stop_event = threading.Event()
    read_results = {}
    reader = threading.Thread(target=run_concurrent_read, args=(db_path, read_results, stop_event))
    reader.start()

    # Write benchmark
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute(f"PRAGMA journal_mode={journal_mode}")
    start = time.perf_counter()
    for batch_start in range(0, NUM_ROWS, BATCH_SIZE):
        conn.execute("BEGIN")
        for i in range(batch_start, min(batch_start + BATCH_SIZE, NUM_ROWS)):
            conn.execute("INSERT INTO data VALUES (?, ?)", (i, f"value_{i}"))
            time.sleep(0.0005)  # slow down writes
        conn.execute("COMMIT")
    elapsed = time.perf_counter() - start
    conn.close()

    stop_event.set()
    reader.join()

    print(f"  Write time:       {elapsed:.3f}s")
    print(f"  Throughput:       {NUM_ROWS / elapsed:,.0f} rows/sec")
    print(f"  Concurrent reads: {read_results.get('reads', 0):,}")
    print(f"  Blocked reads:    {read_results.get('blocked', 0):,}")

    # Cleanup
    os.unlink(db_path)
    wal_path = db_path + '-wal'
    shm_path = db_path + '-shm'
    for p in [wal_path, shm_path]:
        if os.path.exists(p):
            os.unlink(p)

    return elapsed, read_results


if __name__ == "__main__":
    print("SQLite Journal Mode Performance Experiment")
    print(f"Inserting {NUM_ROWS:,} rows in batches of {BATCH_SIZE}")

    rollback_time, rollback_reads = benchmark_mode("DELETE", "Rollback Journal (DELETE)")
    wal_time, wal_reads = benchmark_mode("WAL", "WAL (Write-Ahead Log)")

    print(f"\n{'='*50}")
    print("  SUMMARY")
    print(f"{'='*50}")
    print(f"  Rollback journal:  {rollback_time:.3f}s | reads={rollback_reads.get('reads',0)}, blocked={rollback_reads.get('blocked',0)}")
    print("    -> Uses src/pager.c -> pager_open_journal() & pagerLockDb(EXCLUSIVE_LOCK)")
    
    print(f"  WAL mode:          {wal_time:.3f}s | reads={wal_reads.get('reads',0)}, blocked={wal_reads.get('blocked',0)}")
    print("    -> Uses src/wal.c -> sqlite3WalBeginWriteTransaction() & walWriteToLog()")
    speedup = rollback_time / wal_time if wal_time > 0 else 0
    print(f"\n  WAL speedup for concurrent access: {speedup:.2f}×")
    print(f"\n  Key finding: WAL allows concurrent reads during writes.")
    print(f"  Rollback journal blocks readers while writer holds EXCLUSIVE lock.")
