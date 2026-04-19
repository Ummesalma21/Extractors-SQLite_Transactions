"""
Experiment 3: Crash Recovery via Rollback Journal

Simulates a process crash mid-transaction and verifies SQLite's crash recovery.
Maps to: src/pager.c -> pager_playback() — "hot journal" detection and rollback.
Windows-compatible version (uses taskkill instead of SIGKILL).
"""

import sqlite3
import os
import sys
import time
import subprocess

# Use a local path in the same folder as this script (works on Windows & Unix)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_test.db")
ROWS_BEFORE_CRASH = 1000


def writer_process():
    """Runs in a subprocess — will be killed mid-transaction."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=FULL")

    conn.execute("DROP TABLE IF EXISTS crash_test")
    conn.execute("CREATE TABLE crash_test (id INTEGER PRIMARY KEY, data TEXT)")
    conn.commit()

    print(f"[WRITER] Starting transaction, inserting {ROWS_BEFORE_CRASH} rows...", flush=True)
    conn.execute("BEGIN")
    for i in range(ROWS_BEFORE_CRASH):
        conn.execute("INSERT INTO crash_test VALUES (?, ?)", (i, f"row_{i}" * 10))

    print("[WRITER] Mid-transaction — about to be killed!", flush=True)
    time.sleep(10)

    conn.execute("COMMIT")   # Never reached
    print("[WRITER] COMMIT — this should NOT print!")
    conn.close()


def verify_recovery():
    """Open the database after crash and verify rollback occurred."""
    print("\n[VERIFIER] Opening database after crash...")

    journal_path = DB_PATH + "-journal"
    if os.path.exists(journal_path):
        print(f"[VERIFIER] Hot journal detected: {journal_path}")
        print("[VERIFIER] SQLite will replay it automatically on open.")
    else:
        print("[VERIFIER] Journal already cleaned up by SQLite on open.")
        
    print("\n[VERIFIER] -> Code mapping: src/pager.c -> hasHotJournal() detects the journal file.")
    print("[VERIFIER] -> Code mapping: src/pager.c -> pager_playback() rolls back uncommitted changes.")

    conn = sqlite3.connect(DB_PATH, timeout=5)
    try:
        count = conn.execute("SELECT COUNT(*) FROM crash_test").fetchone()[0]
        print(f"[VERIFIER] Row count after crash + recovery: {count}")
        if count == 0:
            print("[VERIFIER] PASS: All rows rolled back. ACID Atomicity preserved!")
        else:
            print(f"[VERIFIER] UNEXPECTED: {count} rows present without COMMIT.")
    except sqlite3.OperationalError as e:
        print(f"[VERIFIER] Table missing ({e})")
        print("[VERIFIER] PASS: Entire transaction was rolled back.")
    conn.close()


def kill_process(pid):
    """Kill a process — works on both Windows and Unix."""
    if sys.platform == "win32":
        subprocess.call(
            ["taskkill", "/F", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    else:
        import signal
        os.kill(pid, signal.SIGKILL)


if __name__ == "__main__":
    if "--writer" in sys.argv:
        writer_process()
        sys.exit(0)

    # Clean up any leftover files from a previous run
    for path in [DB_PATH, DB_PATH + "-journal", DB_PATH + "-wal", DB_PATH + "-shm"]:
        if os.path.exists(path):
            os.unlink(path)

    print("=" * 55)
    print("  SQLite Crash Recovery Experiment")
    print("=" * 55)
    print(f"\n[MAIN] DB path : {DB_PATH}")
    print("[MAIN] Launching writer subprocess...")

    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--writer"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Read writer output until it signals it's mid-transaction
    for line in iter(proc.stdout.readline, ""):
        print(line, end="")
        if "about to be killed" in line:
            break

    # Give the OS a moment to flush the journal to disk
    time.sleep(0.5)

    print(f"\n[MAIN] Forcefully terminating writer (pid={proc.pid})...")
    kill_process(proc.pid)
    proc.wait()
    print(f"[MAIN] Writer terminated. Exit code: {proc.returncode}")

    verify_recovery()

    print("\n--- Why this works ---")
    print("SQLite's rollback journal is written BEFORE any page is modified.")
    print("When the process is killed, the journal stays on disk.")
    print("On next open, sqlite3PagerOpen() calls hasHotJournal(),")
    print("detects the orphaned journal, and calls pager_playback()")
    print("to restore every page to its pre-transaction state.")
    print("Code: src/pager.c -> hasHotJournal() -> pager_playback()")

    # Cleanup
    for path in [DB_PATH, DB_PATH + "-journal", DB_PATH + "-wal", DB_PATH + "-shm"]:
        if os.path.exists(path):
            os.unlink(path)
