# SQLite Transactions Source-Instrumentation Project

This project studies SQLite transactions through source-code instrumentation, not only through black-box Python experiments. The modified SQLite source emits `[SQLITE_TRACE]` logs from the B-tree, pager, rollback-journal, and WAL paths.

## Project Goal

The goal is to show how a SQL write transaction moves through SQLite:

`SQL statement -> sqlite3_step/sqlite3_exec -> B-tree insert -> pager begin -> lock acquisition -> rollback journal or WAL write -> commit phase one -> commit phase two`

## Build

Ubuntu setup:

```bash
sudo apt update
sudo apt install -y build-essential tcl python3
```

Build the modified SQLite binary:

```bash
bash scripts/build_sqlite.sh
```

This builds the modified SQLite shell and places it at:

`build/sqlite3_custom`

## Run Experiments

Run all experiments:

```bash
bash scripts/run_all_experiments.sh
```

Generated outputs:

- `results/source_trace_output.txt`
- `results/batch_size_output.txt`
- `results/crash_recovery_output.txt`
- `results/wal_vs_rollback_output.txt`

To save the source instrumentation diff:

```bash
bash scripts/save_instrumentation_diff.sh
```

Output:

`diffs/sqlite_trace_instrumentation.diff`

## File Structure

- `sqlite-master/src/pager.c`: pager state, locking, commit, rollback-journal recovery instrumentation
- `sqlite-master/src/btree.c`: `sqlite3BtreeInsert()` instrumentation
- `sqlite-master/src/wal.c`: WAL write transaction and frame instrumentation
- `experiment_execution_trace.py`: main source-instrumented experiment
- `experiment_batch_size.py`: batch-size helper experiment using the custom binary
- `experiment_crash_recovery.py`: crash-recovery experiment using the custom binary where practical
- `experiment_wal_vs_rollback.py`: WAL vs rollback comparison using the custom binary
- `scripts/`: build, run, and diff scripts
- `results/`: generated experiment outputs
- `diffs/`: generated instrumentation diff
- `EXPERIMENTS.md`: reproducibility guide
- `report.md`: project report

## Source-Instrumented vs Helper Evidence

The main evidence is source-instrumented: `experiment_execution_trace.py` runs `build/sqlite3_custom` and captures `[SQLITE_TRACE]` output from SQLite source files.

The batch-size and WAL-vs-rollback scripts also invoke `build/sqlite3_custom`, but their timings are helper performance observations and should be regenerated locally. The crash-recovery script kills the custom SQLite process before commit and verifies that uncommitted rows do not persist.

No script generates mock or simulated trace files. If the custom binary is missing, the experiments fail with a clear build instruction.

See [EXPERIMENTS.md](EXPERIMENTS.md) for exact reproduction steps and [report.md](report.md) for the write-up.
