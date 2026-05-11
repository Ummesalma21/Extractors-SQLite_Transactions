# Experiment Reproducibility Guide

## What was modified in SQLite source

The SQLite source instrumentation is in these files:

- `sqlite-master/src/pager.c`
- `sqlite-master/src/btree.c`
- `sqlite-master/src/wal.c`

Functions modified:

- `pager.c:sqlite3PagerBegin()` logs transaction begin, pager state, lock level, journal mode, and whether the pager is using WAL.
- `pager.c:pagerLockDb()` logs requested lock transitions and the resulting lock level.
- `pager.c:sqlite3PagerCommitPhaseOne()` logs commit phase one begin/complete, pager state, lock level, journal mode, WAL flag, and database size fields.
- `pager.c:sqlite3PagerCommitPhaseTwo()` logs commit phase two begin/complete and final transaction cleanup state.
- `pager.c:hasHotJournal()` logs rollback-journal existence checks.
- `pager.c:sqlite3PagerSharedLock()` logs hot-journal recovery begin/complete when recovery is attempted.
- `btree.c:sqlite3BtreeInsert()` logs insert begin, root page, cursor page, key/data size, storage-path entry, pager-write entry, and completion.
- `wal.c:sqlite3WalBeginWriteTransaction()` logs WAL write-lock acquisition.
- `wal.c:walFrames()` and `wal.c:sqlite3WalFrames()` log WAL frame writes and WAL commit-index updates.

All added logs use the prefix `[SQLITE_TRACE]`.

## How to build

On Ubuntu, install the required tools:

```bash
sudo apt update
sudo apt install -y build-essential tcl python3
```

Then build:

```bash
bash scripts/build_sqlite.sh
```

The expected output binary is `build/sqlite3_custom`.

## How to run all experiments

After building `build/sqlite3_custom`, run:

```bash
bash scripts/run_all_experiments.sh
```

Outputs are written to:

- `results/source_trace_output.txt`
- `results/batch_size_output.txt`
- `results/crash_recovery_output.txt`
- `results/wal_vs_rollback_output.txt`

## Main source-instrumented experiment

`experiment_execution_trace.py` runs `build/sqlite3_custom`, executes a rollback-journal transaction, captures stdout/stderr, and saves the trace to `results/source_trace_output.txt`.

Expected logs include:

- `btree.c:sqlite3BtreeInsert`
- `pager.c:sqlite3PagerBegin`
- `pager.c:pagerLockDb`
- `pager.c:sqlite3PagerCommitPhaseOne`
- `pager.c:sqlite3PagerCommitPhaseTwo`

This is not black-box because the evidence comes from logs inserted into SQLite source files and emitted by the rebuilt SQLite binary.

## Batch size experiment

`experiment_batch_size.py` invokes `build/sqlite3_custom` for each batch size and counts `[SQLITE_TRACE]` lines. It is a helper performance experiment because timings are machine-dependent, but it still uses the modified SQLite binary rather than Python's built-in `sqlite3`.

## Crash recovery experiment

`experiment_crash_recovery.py` uses `build/sqlite3_custom` to create a rollback-journal database, starts a transaction, kills the SQLite process before `COMMIT`, and reopens the database with the same binary.

Expected behavior:

- uncommitted transaction rows should not persist after crash/reopen
- if a hot journal remains, pager recovery logs should show the relevant source path
- if the OS/SQLite cleaned up before the kill, the output should be interpreted conservatively rather than overclaimed

## WAL vs rollback journal experiment

`experiment_wal_vs_rollback.py` runs the same batched write workload with `PRAGMA journal_mode=DELETE` and `PRAGMA journal_mode=WAL`.

The comparison is:

- rollback journal: pager commit and lock logs should dominate
- WAL: `wal.c:sqlite3WalBeginWriteTransaction` and WAL frame logs should appear

Timing is included only as local, reproducible output.

## How the diffs prove source-code modification

Run:

```bash
bash scripts/save_instrumentation_diff.sh
```

The script saves:

`diffs/sqlite_trace_instrumentation.diff`

That diff shows the source-code changes in `sqlite-master/src/pager.c`, `sqlite-master/src/btree.c`, and `sqlite-master/src/wal.c`.
