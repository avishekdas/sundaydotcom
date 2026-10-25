# Migrations
- The pipeline runs `tasklane-<stage>-migrate` between the data stacks and the code stacks. It applies pending
  `backend/migrations/NNNN_*.sql` files in order (advisory lock, `lock_timeout` 5 s, one transaction per file).
- **Expand → migrate → contract** (PE-4): destructive DDL (drop/rename/type change/SET NOT NULL) only in a file marked
  `-- phase: contract`, shipped in a release after the code stopped using the object (enforced by
  `tests/unit/platform/test_migration_policy.py`).
- **Indexes on existing tables**: `CREATE INDEX CONCURRENTLY IF NOT EXISTS …` in a file starting with
  `-- run-mode: no-transaction`. If it fails, the index is left INVALID: `DROP INDEX CONCURRENTLY <name>;` then re-run
  the pipeline. Statements over the Data API 45 s limit (large tables) run from a CodeBuild job with psycopg instead
  (to be added when a table is big enough to need it; M2 rehearsal).
- A failed migration leaves its transaction rolled back; fix forward with a new file (applied files are immutable).
